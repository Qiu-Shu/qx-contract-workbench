"""Real synthetic contract DOCX originals survive long-path native recovery."""
from hashlib import sha256
import os
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from cn_contract.ops import backup, workspace_backup
from cn_contract.ops.file_paths import filesystem_path
from cn_contract.persistence import read_original, read_version
from cn_contract.security import authenticate
from cn_contract.web import local_server
from tests.integration.test_local_materials import independent_docx, new_local_case, upload_and_parse
from tests.integration.test_local_workbench import login, PASSWORD
from tests.integration.test_workspace_backup import PASSPHRASE


def long_directory(base, label, length):
    return base/(label+'资料'*max(1, (length-len(str(base))-len(label))//2))


def contract_source(tmp_path):
    root = long_directory(tmp_path, '中文合同', 195)
    local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=tmp_path)
    raw = independent_docx()
    with TestClient(local_server.build_local_app(root, data_parent=tmp_path)) as client:
        headers = login(client)
        matter = new_local_case(client, headers)
        document = upload_and_parse(client, headers, matter, raw)
        parsed = client.get(f'/api/matters/{matter}/documents/{document["version_id"]}/anchors')
        assert parsed.status_code == 200
        assert any('独立虚构材料，仅供工程测试。' in anchor['quote'] for anchor in parsed.json()['anchors'])
        with client.app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            version = read_version(UUID(matter), UUID(document['version_id']), actor, db)
            assert read_original(UUID(matter), version.id, actor, db) == raw
        assert not str(client.app.state.database.storage_root).startswith('\\\\?\\')
        assert not str(client.app.state.database.engine.url.database).startswith('\\\\?\\')
        cookies = dict(client.cookies)
    reference = f'{matter}/{version.id}/original.bin'
    assert version.storage_ref == reference and version.sha256 == sha256(raw).hexdigest()
    original = root/'protected'/reference
    assert len(str(original.parent)) > 260
    assert filesystem_path(original).read_bytes() == raw
    return root, matter, version, raw, cookies


def recovered_original(root, parent, matter, version, raw, cookies):
    assert not str(root).startswith('\\\\?\\')
    original = root/'protected'/version.storage_ref
    assert len(str(original.parent)) > 260
    assert backup.checked_file(original, root/'protected') == raw
    with TestClient(local_server.build_local_app(root, data_parent=parent)) as client:
        client.cookies.update(cookies)
        assert client.get('/api/matters').status_code == 401
        client.cookies.clear()
        headers = login(client)
        response = client.get(f'/api/recovery/matters/{matter}/originals/{version.id}')
        assert response.status_code == 200 and response.content == raw
        assert sha256(response.content).hexdigest() == version.sha256
        with client.app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            historical = read_version(UUID(matter), version.id, actor, db)
            assert historical.storage_ref == version.storage_ref and historical.sha256 == version.sha256
        denied = client.post('/api/matters', headers=headers, json={})
        assert denied.status_code == 409 and denied.json()['code'] == 'BLOCKED_LIVE'
        assert client.post(f'/api/matters/{matter}/documents', headers=headers).status_code == 409


def test_contract_long_path_original_roundtrip_and_rebackup(tmp_path, record_property):
    root, matter, version, raw, cookies = contract_source(tmp_path)
    archive = tmp_path/'合同长路径.qxbak'
    created = workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    assert created['verified'] and created['archive_sha256'] == sha256(archive.read_bytes()).hexdigest()
    restore_parent = long_directory(tmp_path, '中文恢复', 160)
    first = workspace_backup.restore_workspace_backup(archive, restore_parent, PASSPHRASE)
    restored = Path(first['restored_root'])
    assert first['quarantined'] and first['workspace_id'] == created['workspace_id']
    recovered_original(restored, tmp_path, matter, version, raw, cookies)
    again = tmp_path/'合同再次备份.qxbak'
    workspace_backup.create_workspace_backup(restored, again, PASSPHRASE, data_parent=tmp_path)
    final = workspace_backup.restore_workspace_backup(again,
        long_directory(tmp_path, '二次恢复', 160), PASSPHRASE)
    assert final['quarantined'] and final['workspace_id'] == created['workspace_id']
    recovered_original(Path(final['restored_root']), tmp_path, matter, version, raw, cookies)
    assert backup.checked_file(root/'protected'/version.storage_ref, root/'protected') == raw
    record_property('source_database_path_chars', len(str(root/'workbench.db')))
    record_property('source_original_parent_chars', len(str((root/'protected'/version.storage_ref).parent)))
    record_property('restored_original_parent_chars', len(str((restored/'protected'/version.storage_ref).parent)))
    record_property('source_sha256', version.sha256)
    record_property('storage_ref', version.storage_ref)


def test_contract_long_path_hardlink_is_not_archived(tmp_path):
    root, _, version, raw, _ = contract_source(tmp_path)
    original = root/'protected'/version.storage_ref
    linked = original.parent/'禁止硬链接.bin'
    os.link(filesystem_path(original), filesystem_path(linked))
    archive = tmp_path/'不得生成.qxbak'
    try:
        with pytest.raises(ValueError):
            backup.checked_file(original, root/'protected')
        with pytest.raises(ValueError):
            workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
        assert not archive.exists()
    finally:
        filesystem_path(linked).chmod(0o600)
        filesystem_path(linked).unlink()
        filesystem_path(original).chmod(0o400)
    assert backup.checked_file(original, root/'protected') == raw


def test_contract_long_path_boundaries_reject_external_source_and_internal_archive(tmp_path):
    root, _, version, raw, _ = contract_source(tmp_path)
    original = root/'protected'/version.storage_ref
    outside = long_directory(tmp_path, '外部独立资料', 200)/('合成目录'+'资料'*40)/'outside.bin'
    filesystem_path(outside.parent).mkdir(parents=True)
    filesystem_path(outside).write_bytes(b'independent synthetic bytes outside protected root')
    assert len(str(outside.parent)) > 260
    for path in (outside, filesystem_path(outside)):
        with pytest.raises(ValueError):
            backup.checked_file(path, root/'protected')
    for target in (original.parent/'self.qxbak', filesystem_path(original.parent/'alias.qxbak')):
        with pytest.raises(ValueError, match='BACKUP_DESTINATION_INVALID'):
            workspace_backup.create_workspace_backup(root, target, PASSPHRASE, data_parent=tmp_path)
        assert not filesystem_path(target).exists()
    assert backup.checked_file(original, root/'protected') == raw
