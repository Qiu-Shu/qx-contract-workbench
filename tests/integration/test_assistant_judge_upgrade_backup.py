"""Independent pre-Jev archives upgrade only inside isolated restored copies."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract.assistant_model_schema_baseline import ASSISTANT_MODEL_V1_ROWS
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, read_original
from cn_contract.security import authenticate, login
from cn_contract.storage_schema import identify_schema, CURRENT_VERSION
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import write_old_cnbak, USERNAME, PASSWORD, PASSPHRASE
from tests.helpers.synthetic_operations import keys
from tests.integration.test_assistant_model_upgrade_backup import old_workspace


def model_workspace(tmp_path, native):
    world = old_workspace(tmp_path, native)
    root, database, *_ = world
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        for kind in ('table', 'index', 'trigger'):
            for row in ASSISTANT_MODEL_V1_ROWS:
                if row[0] == kind and row[3] is not None:
                    db.execute(row[3])
        db.commit()
        assert identify_schema(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(), native=native) == 'assistant-model-v1'
        if native:
            marker = json.loads((root/'workspace.json').read_text('utf-8'))
            marker['schema_sha256'] = local_server._schema_hash(db)
            (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    return world


@pytest.mark.parametrize('native', [True, False])
@pytest.mark.parametrize('fail_migration', [False, True])
def test_pre_judge_archives_retain_sources_and_publish_only_complete_upgrade(tmp_path, monkeypatch, native, fail_migration):
    from cn_contract.assistant import attachments, judge_schema
    root, database, matter, document, raw, attachment = model_workspace(tmp_path, native)
    archive = tmp_path/('pre-judge.qxbak' if native else 'pre-judge.cnbak')
    try:
        if native:
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        else:
            write_old_cnbak(database, archive)
        source_before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        archive_before = archive.read_bytes()
        if fail_migration:
            monkeypatch.setattr(judge_schema, 'STATEMENTS', (*judge_schema.STATEMENTS, 'INVALID SQL'))
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
                assert identify_schema(rows, native=native) == CURRENT_VERSION == 'assistant-library-v1'
                for table in judge_schema.TABLES:
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
        assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()} == source_before
    finally:
        database.engine.dispose()
