"""Frozen pre-model archives retain source bytes during isolated model upgrades."""
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import attachments, service
from cn_contract.assistant_schema_baseline import ASSISTANT_V1_ROWS
from cn_contract.assistant_attachment_schema_baseline import ASSISTANT_ATTACHMENTS_V1_ROWS
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database, read_original
from cn_contract.security import authenticate, login
from cn_contract.storage_schema import identify_schema, CURRENT_VERSION
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import legacy_world, write_old_cnbak, USERNAME, PASSWORD, PASSPHRASE
from tests.helpers.synthetic_operations import keys


def old_workspace(tmp_path, native):
    root, database, actor, matter, document, _, raw = legacy_world(tmp_path, native=native)
    path = Path(database.engine.url.database)
    with closing(sqlite3.connect(path)) as connection:
        for baseline in (ASSISTANT_V1_ROWS, ASSISTANT_ATTACHMENTS_V1_ROWS):
            for kind in ('table','index','trigger'):
                for row in baseline:
                    if row[0] == kind and row[3] is not None:
                        connection.execute(row[3])
        connection.commit()
        assert identify_schema(connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                               native=native) == 'assistant-attachments-v1'
        if native:
            marker = json.loads((root/'workspace.json').read_text('utf-8'))
            marker['schema_sha256'] = local_server._schema_hash(connection)
            (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    source = None
    if native:
        with database.session() as db:
            conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        cid = conversation.scope.conversation_id
        receipt = attachments.ingest_attachment(actor, cid, d.AssistantAttachmentInput(
            request_id=uuid4(), expected_scope=conversation.scope,
            original_name='旧版独立合成材料.docx', mime=document.mime,
            policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=database)
        current = attachments.read_materials(actor, cid, database=database)
        parsed = attachments.parse_attachment(actor, cid, receipt.attachment.id,
            d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
        source = (cid, receipt.attachment.id, parsed.parse)
        with local_server._worker_lock(root):
            pass
    return root, database, matter, document, raw, source


@pytest.mark.parametrize('native', [True, False])
@pytest.mark.parametrize('fail_migration', [False, True])
def test_pre_model_archives_preserve_data_or_fail_without_publication(tmp_path, monkeypatch, native, fail_migration):
    root, database, matter, document, raw, source = old_workspace(tmp_path, native)
    archive = tmp_path/('old.qxbak' if native else 'old.cnbak')
    try:
        if native:
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        else:
            write_old_cnbak(database, archive)
        before = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
        archive_before = archive.read_bytes()
        if fail_migration:
            from cn_contract.assistant import model_schema
            monkeypatch.setattr(model_schema, 'STATEMENTS', (*model_schema.STATEMENTS,'INVALID SQL'))
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
            with closing(sqlite3.connect(path)) as connection:
                assert identify_schema(connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall(),
                    native=native) == CURRENT_VERSION
                for table in ('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs'):
                    assert connection.execute('SELECT COUNT(*) FROM '+table).fetchone() == (0,)
            restored = Database('sqlite:///'+str(path), target/'protected', database.settings, initialize_schema=False)
            backup._mark_storage_flags(restored)
            try:
                with restored.session() as db:
                    token, _ = login(USERNAME,PASSWORD,db)
                    current_actor = authenticate(token,db)
                    assert read_original(matter.id,document.id,current_actor,db) == raw
                if source:
                    cid, identifier, parsed = source
                    assert attachments.read_original(current_actor,cid,identifier,database=restored) == raw
                    assert attachments.read_parse(current_actor,cid,identifier,parsed.revision,database=restored) == parsed
            finally:
                restored.engine.dispose()
        assert archive.read_bytes() == archive_before
        assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    finally:
        database.engine.dispose()
