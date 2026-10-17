"""Native attachment archives preserve sources, and reject broken provenance."""
from contextlib import closing
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import attachments, service
from cn_contract.config import canonical_json, load_settings
from cn_contract.ops import backup, workspace_backup
from cn_contract.persistence import Database
from cn_contract.security import authenticate, login, ServiceError
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import legacy_world, PASSWORD, USERNAME, PASSPHRASE
from tests.integration.test_assistant_attachments import sample


def test_unknown_schema_is_not_treated_as_attachment_free(tmp_path):
    _, database, *_ = legacy_world(tmp_path, native=True)
    try:
        with database.session() as db:
            db.execute(text('CREATE TABLE unexpected_attachment_state (id TEXT)'))
        with database.session() as db, pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            backup._file_references(db)
    finally:
        database.engine.dispose()


@pytest.fixture
def source(tmp_path, request):
    root = tmp_path/'中文资料库'/'main'
    if getattr(request, 'param', None) == 'long':
        root = tmp_path/('长路径'+'资料'*max(1, (190-len(str(tmp_path)))//2))/'main'
    local_server.initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    raw = sample()
    database._assistant_synthetic_hashes = frozenset({hashlib.sha256(raw).hexdigest()})
    with database.session() as db:
        token, _ = login(USERNAME, PASSWORD, db)
        actor = authenticate(token, db)
        value = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    cid = value.scope.conversation_id
    request = d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=value.scope,
        original_name='独立虚构咨询.docx',
        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True))
    receipt = attachments.ingest_attachment(actor, cid, request, BytesIO(raw), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    parsed = attachments.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    yield root, database, actor, cid, receipt, parsed, raw, request
    database.engine.dispose()


def corrupt(database, table, sql, arguments=()):
    """Alter only synthetic fixture data, restoring the exact immutable DDL."""
    with closing(sqlite3.connect(database.engine.url.database)) as db:
        triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchall()
        for name, _ in triggers:
            db.execute('DROP TRIGGER "'+name+'"')
        db.execute(sql, arguments)
        for _, statement in triggers:
            db.execute(statement)
        db.commit()


def test_native_roundtrip_preserves_source_history_and_service_fence(source, tmp_path):
    root, database, actor, cid, receipt, parsed, raw, request = source
    anchor = parsed.parse.result.anchors[0]
    current = attachments.read_materials(actor, cid, database=database)
    again = attachments.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    attachments.select_materials(actor, cid, d.AssistantMaterialSelectionInput(request_id=uuid4(),
        expected_scope=current.scope, items=()), database=database)
    # The native maintenance lock is runtime state, established before comparison.
    with local_server._worker_lock(root):
        pass
    before = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive = tmp_path/'对话附件.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    target = Path(result['restored_root'])
    restored = Database('sqlite:///'+str(target/'workbench.db'), target/'protected',
                        database.settings, initialize_schema=False)
    backup._mark_storage_flags(restored)
    try:
        with restored.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            current_actor = authenticate(token, db)
        assert attachments.read_original(current_actor, cid, receipt.attachment.id, database=restored) == raw
        assert attachments.read_parse(current_actor, cid, receipt.attachment.id, again.parse.revision,
            database=restored) == again.parse
        assert attachments.read_excerpt(current_actor, cid, receipt.attachment.id, 1,
            anchor.id, anchor.quote_sha256, database=restored).anchor == anchor
        current = attachments.read_materials(current_actor, cid, database=restored)
        assert current.items == () and current.scope.materials_revision == 4
        for operation in (
            lambda: attachments.ingest_attachment(current_actor, cid, request, BytesIO(raw), database=restored),
            lambda: attachments.parse_attachment(current_actor, cid, receipt.attachment.id,
                d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=restored),
            lambda: attachments.select_materials(current_actor, cid, d.AssistantMaterialSelectionInput(
                request_id=uuid4(), expected_scope=current.scope, items=()), database=restored),
        ):
            with pytest.raises(ServiceError) as error:
                operation()
            assert error.value.code == 'BLOCKED_LIVE'
        with restored.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM matters')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM intake_cases')) == 0
    finally:
        restored.engine.dispose()
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('source', ['long'], indirect=True)
def test_long_parent_paths_create_restore_and_rebackup(source, tmp_path):
    from cn_contract.ops.file_paths import filesystem_path
    root, database, actor, cid, receipt, _, raw, _ = source
    original = root/'protected'/'assistant'/str(cid)/str(receipt.attachment.id)/'original.bin'
    assert len(str(original.parent)) > 260
    assert backup.checked_root(original.parent).name == str(receipt.attachment.id)
    assert attachments.read_original(actor, cid, receipt.attachment.id, database=database) == raw
    archive = tmp_path/'long.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    target_parent = tmp_path/('恢复目录'+'资料'*30)
    first = workspace_backup.restore_workspace_backup(archive, target_parent, PASSPHRASE)
    restored_root = Path(first['restored_root'])
    restored_original = restored_root/'protected'/'assistant'/str(cid)/str(receipt.attachment.id)/'original.bin'
    assert len(str(restored_original.parent)) > 260
    assert backup.checked_file(restored_original, restored_root/'protected') == raw
    again = tmp_path/'restored-again.qxbak'
    workspace_backup.create_workspace_backup(restored_root, again, PASSPHRASE, data_parent=tmp_path)
    final = workspace_backup.restore_workspace_backup(again, tmp_path/'final', PASSPHRASE)
    assert backup.checked_file(Path(final['restored_root'])/'protected'/'assistant'/str(cid)/
        str(receipt.attachment.id)/'original.bin', Path(final['restored_root'])/'protected') == raw
    # Extended file access must retain the existing hard-link rejection.
    linked = root/'protected'/'forbidden-link.bin'
    os.link(filesystem_path(original), filesystem_path(linked))
    try:
        with pytest.raises(ValueError):
            workspace_backup.create_workspace_backup(root, tmp_path/'forbidden.qxbak', PASSPHRASE, data_parent=tmp_path)
    finally:
        filesystem_path(linked).chmod(0o600)
        filesystem_path(linked).unlink()
        filesystem_path(original).chmod(0o400)


@pytest.mark.parametrize('fault', ['missing', 'hash', 'size', 'hardlink', 'workspace', 'owner',
    'path', 'parse_digest', 'parse_version', 'quote_hash', 'snapshot_attachment',
    'snapshot_parse', 'snapshot_duplicate', 'snapshot_request', 'latest_revision'])
def test_native_backup_rejects_broken_attachment_provenance(source, tmp_path, fault):
    root, database, _, cid, receipt, parsed, *_ = source
    original = root/'protected'/'assistant'/str(cid)/str(receipt.attachment.id)/'original.bin'
    if fault in ('missing', 'hash', 'size', 'hardlink'):
        original.chmod(0o600)
        if fault == 'missing': original.unlink()
        elif fault == 'hash':
            raw = bytearray(original.read_bytes()); raw[-1] ^= 1; original.write_bytes(raw)
        elif fault == 'size': original.write_bytes(original.read_bytes()+b'x')
        else: os.link(original, root/'protected'/'synthetic-linked.bin')
    elif fault in ('workspace', 'owner', 'path'):
        column = {'workspace':'workspace_id', 'owner':'owner_id', 'path':'storage_ref'}[fault]
        replacement = str(uuid4()) if fault != 'path' else 'assistant/'+str(cid)+'/../original.bin'
        if fault == 'owner':
            from cn_contract.security import provision_user
            with database.session() as db:
                replacement = str(provision_user('independent-backup-other', PASSWORD,
                    {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True))
        corrupt(database, 'assistant_attachments', f'UPDATE assistant_attachments SET {column}=?', (replacement,))
    elif fault.startswith('parse_') or fault == 'quote_hash':
        value = parsed.parse.result.model_dump(mode='json')
        if fault == 'parse_version': value['version_id'] = str(uuid4())
        if fault == 'quote_hash': value['anchors'][0]['quote_sha256'] = '0'*64
        raw = canonical_json(value)
        digest = '0'*64 if fault == 'parse_digest' else hashlib.sha256(raw.encode()).hexdigest()
        corrupt(database, 'assistant_attachment_parses', 'UPDATE assistant_attachment_parses SET result_json=?,result_sha256=?', (raw,digest))
    elif fault == 'latest_revision':
        corrupt(database, 'assistant_conversations', 'UPDATE assistant_conversations SET materials_revision=1')
    elif fault == 'snapshot_request':
        corrupt(database, 'assistant_material_snapshots', 'UPDATE assistant_material_snapshots SET request_sha256=? WHERE revision=1', ('0'*64,))
    else:
        items = [{'attachment_id':str(receipt.attachment.id), 'parse_revision':1}]
        if fault == 'snapshot_attachment': items[0]['attachment_id'] = str(uuid4())
        if fault == 'snapshot_parse': items[0]['parse_revision'] = 999
        if fault == 'snapshot_duplicate': items.append(items[0])
        corrupt(database, 'assistant_material_snapshots', 'UPDATE assistant_material_snapshots SET items_json=? WHERE revision=2', (json.dumps(items),))
    archive = tmp_path/'must-not-publish.qxbak'
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    assert not archive.exists()


def test_cnbak_rejects_attachment_refs_instead_of_omitting_them(source):
    _, database, *_ = source
    with database.session() as db, pytest.raises(ValueError, match='ASSISTANT_ATTACHMENTS_REQUIRE_QXBAK'):
        backup._collect_files(db)


def test_snapshot_cannot_retroactively_reference_later_parse(source, tmp_path):
    root, database, actor, cid, receipt, *_ = source
    current = attachments.read_materials(actor, cid, database=database)
    attachments.select_materials(actor, cid, d.AssistantMaterialSelectionInput(request_id=uuid4(),
        expected_scope=current.scope, items=current.items), database=database)
    current = attachments.read_materials(actor, cid, database=database)
    attachments.parse_attachment(actor, cid, receipt.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(), expected_scope=current.scope), database=database)
    items = [{'attachment_id':str(receipt.attachment.id), 'parse_revision':2}]
    corrupt(database, 'assistant_material_snapshots',
        'UPDATE assistant_material_snapshots SET items_json=? WHERE revision=3', (json.dumps(items),))
    with pytest.raises(ValueError):
        workspace_backup.create_workspace_backup(root, tmp_path/'future.qxbak', PASSPHRASE, data_parent=tmp_path)


def test_parse_json_byte_cap_is_explicit(monkeypatch):
    from cn_contract.assistant import attachment_integrity
    monkeypatch.setattr(attachment_integrity, 'MAX_PARSE_JSON_BYTES', 8)
    with pytest.raises(ValueError, match='ASSISTANT_PARSE_RESULT_LIMIT'):
        attachment_integrity.parse_result_json('{"合成":"资料"}')


@pytest.mark.parametrize('raw', [b'{}', '{"version_id":null,"version_id":null}',
    '{"version_id":NaN}', '['*1100+']'*1100], ids=['blob','duplicate','nonfinite','nested'])
def test_parse_json_rejects_ambiguous_or_invalid_storage(raw):
    from cn_contract.assistant.attachment_integrity import parse_result_json
    with pytest.raises(ValueError):
        parse_result_json(raw)
