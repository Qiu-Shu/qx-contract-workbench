"""Frozen pre-library archives migrate in staging; failure never publishes a partial copy."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract.assistant_judge_schema_baseline import ASSISTANT_JUDGE_V1_ROWS
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, read_original
from cn_contract.security import authenticate, login
from cn_contract.storage_schema import identify_schema
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import write_old_cnbak, USERNAME, PASSWORD, PASSPHRASE
from tests.helpers.synthetic_operations import keys
from tests.integration.test_assistant_judge_upgrade_backup import model_workspace


def judge_workspace(tmp_path, native):
    world = model_workspace(tmp_path, native)
    root, database, *_ = world
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        for kind in ('table', 'index', 'trigger'):
            for row in ASSISTANT_JUDGE_V1_ROWS:
                if row[0] == kind and row[3] is not None:
                    db.execute(row[3])
        db.commit()
        assert identify_schema(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                               native=native) == 'assistant-judge-v1'
        if native:
            marker = json.loads((root/'workspace.json').read_text('utf-8'))
            marker['schema_sha256'] = local_server._schema_hash(db)
            (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    return world


def test_old_schema_cannot_hide_new_tool_events(tmp_path):
    root, database, *_ = judge_workspace(tmp_path, True)
    try:
        with database.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            view = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            run = service.save_message(actor, view.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content='旧容器中的不合格式虚构事件'), db)
            db.execute(text('''INSERT INTO assistant_run_events
                (run_id,seq,event_type,audience,payload_json,created_at)
                VALUES (:run,2,'tool.before','internal','{}',:at)'''),
                {'run':str(run.id), 'at':run.created_at.isoformat()})
        target = tmp_path/'hidden-new.qxbak'
        with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
            workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
        assert not target.exists()
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('native', [True, False])
@pytest.mark.parametrize('fail_migration', [False, True])
def test_pre_library_archive_upgrade_is_complete_or_unpublished(tmp_path, monkeypatch, native, fail_migration):
    from cn_contract.assistant import attachments, library_schema
    root, database, matter, document, raw, attachment = judge_workspace(tmp_path, native)
    archive = tmp_path/('pre-library.qxbak' if native else 'pre-library.cnbak')
    try:
        if native:
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        else:
            write_old_cnbak(database, archive)
        original = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
        archive_before = archive.read_bytes()
        if fail_migration:
            monkeypatch.setattr(library_schema, 'STATEMENTS', (*library_schema.STATEMENTS, 'INVALID SQL'))
        destination = tmp_path/'restored'
        def restore():
            return (workspace_backup.restore_workspace_backup(archive, destination, PASSPHRASE) if native else
                    backup.restore_backup(archive, key_resolver=keys(), restore_parent=destination, settings=database.settings))
        if fail_migration:
            with pytest.raises(sqlite3.Error):
                restore()
            assert not destination.exists() or not list(destination.iterdir())
        else:
            result = restore()
            target = Path(result['restored_root'] if native else result.restored_root)
            path = target/('workbench.db' if native else 'database.db')
            with closing(sqlite3.connect(path)) as db:
                rows = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
                assert identify_schema(rows, native=native) == 'assistant-context-v1'
                for table in library_schema.TABLES:
                    assert db.execute('SELECT COUNT(*) FROM '+table).fetchone() == (0,)
            restored = Database('sqlite:///'+str(path), target/'protected', database.settings, initialize_schema=False)
            backup._mark_storage_flags(restored)
            try:
                with restored.session() as db:
                    token, _ = login(USERNAME, PASSWORD, db)
                    actor = authenticate(token, db)
                    assert read_original(matter.id, document.id, actor, db) == raw
                if attachment:
                    cid, identifier, parsed = attachment
                    assert attachments.read_original(actor, cid, identifier, database=restored) == raw
                    assert attachments.read_parse(actor, cid, identifier, parsed.revision, database=restored) == parsed
            finally:
                restored.engine.dispose()
        assert archive.read_bytes() == archive_before
        assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} == original
    finally:
        database.engine.dispose()
