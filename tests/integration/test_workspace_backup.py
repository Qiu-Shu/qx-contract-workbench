"""Offline backups use independent synthetic local materials, never real cases."""
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from uuid import UUID

from fastapi.testclient import TestClient
import pytest

from cn_contract.web import local_server
from tests.integration.test_local_workbench import login, PASSWORD
from tests.integration.test_local_materials import independent_docx, new_local_case, upload_and_parse
from tests.integration.test_intake import create as create_intake

PASSPHRASE = 'synthetic-backup-only-2026'


def feature():
    assert importlib.util.find_spec('cn_contract.ops.workspace_backup'), 'full local backup missing'
    return importlib.import_module('cn_contract.ops.workspace_backup')


@pytest.fixture
def source(tmp_path):
    parent = tmp_path/'中文 账户'
    root = parent/'workspaces'/'main'
    local_server.initialize_workspace(root, 'local-lawyer', PASSWORD, data_parent=parent)
    raw = independent_docx()
    with TestClient(local_server.build_local_app(root, data_parent=parent)) as client:
        headers = login(client)
        matter = new_local_case(client, headers)
        document = upload_and_parse(client, headers, matter, raw)
        intake = create_intake(client, headers)
        cookies = dict(client.cookies)
    return parent, root, matter, document, intake, cookies, raw


def test_full_local_roundtrip_separate_root_and_old_sessions_revoked(source, tmp_path):
    backup = feature()
    parent, root, matter, document, intake, cookies, raw = source
    before = {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}
    archive = tmp_path/'案件 备份.qxbak'
    report = backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=parent)
    assert report['archive_sha256'] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report['file_count'] >= 3
    assert '独立虚构'.encode() not in archive.read_bytes()
    restored = backup.restore_workspace_backup(archive, parent/'restores', PASSPHRASE)
    target = Path(restored['restored_root'])
    assert target != root and target.is_relative_to(parent/'restores')
    assert restored['quarantined'] is True
    with TestClient(local_server.build_local_app(target, data_parent=parent)) as client:
        client.cookies.update(cookies)
        assert client.get('/api/matters').status_code == 401
        client.cookies.clear()
        login(client)
        assert client.get('/api/matters').json()[0]['id'] == matter
        assert client.get('/api/intakes/'+intake['id']).json()['consultation'] == intake['consultation']
        from cn_contract.security import authenticate
        from cn_contract.persistence import read_original
        with client.app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            assert read_original(UUID(matter), UUID(document['version_id']), actor, db) == raw
    assert {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


def test_restored_workspace_http_is_read_only_and_has_clear_entry(source, tmp_path):
    module=feature();parent,root,matter,document,intake,*_=source
    archive=tmp_path/'readonly.qxbak'
    module.create_workspace_backup(root,archive,PASSPHRASE,data_parent=parent)
    result=module.restore_workspace_backup(archive,parent/'restores',PASSPHRASE)
    with TestClient(local_server.build_local_app(result['restored_root'],data_parent=parent)) as client:
        headers=login(client)
        page=client.get('/workspace')
        assert '恢复副本 · 仅供核对' in page.text
        assert client.post('/api/intakes',headers=headers,json={}).status_code==409
        assert client.post('/api/matters',headers=headers,json={}).status_code==409
        assert client.get('/api/matters/'+matter+'/reviews').status_code==409
        assert client.get('/recovery/matters/'+matter).status_code==200
        response=client.get(f'/api/recovery/matters/{matter}/originals/{document["version_id"]}')
        assert response.content==source[-1]
        assert client.get('/recovery/intakes/'+intake['id']).status_code==200


@pytest.mark.parametrize('corruption', ['password', 'header', 'ciphertext', 'tag', 'truncated'])
def test_bad_archive_never_publishes_restore(source, tmp_path, corruption):
    module = feature(); parent, root, *_ = source
    archive = tmp_path/'bad.qxbak'
    module.create_workspace_backup(root, archive, PASSPHRASE, data_parent=parent)
    data = bytearray(archive.read_bytes())
    if corruption == 'header': data[3] ^= 1
    if corruption == 'ciphertext': data[len(data)//2] ^= 1
    if corruption == 'tag': data[-1] ^= 1
    if corruption == 'truncated': data = data[:-20]
    archive.write_bytes(data)
    destination = tmp_path/'restored'
    with pytest.raises(ValueError):
        module.restore_workspace_backup(archive, destination,
            PASSPHRASE+'wrong' if corruption == 'password' else PASSPHRASE)
    assert not destination.exists() or not list(destination.iterdir())


def test_busy_workspace_and_existing_destination_are_preserved(source, tmp_path):
    module = feature(); parent, root, *_ = source
    archive = tmp_path/'existing.qxbak'; archive.write_bytes(b'keep')
    with pytest.raises(ValueError): module.create_workspace_backup(root, archive, PASSPHRASE, data_parent=parent)
    assert archive.read_bytes() == b'keep'
    with local_server._worker_lock(root):
        with pytest.raises(ValueError, match='WORKSPACE_IN_USE'):
            module.create_workspace_backup(root, tmp_path/'busy.qxbak', PASSPHRASE, data_parent=parent)
    assert not (tmp_path/'busy.qxbak').exists()


def test_missing_original_and_unknown_schema_rejected(source, tmp_path):
    module = feature(); parent, root, _, document, *_ = source
    original = next((root/'protected').rglob('original.bin'))
    raw = original.read_bytes(); original.chmod(0o600); original.unlink()
    with pytest.raises(ValueError): module.create_workspace_backup(root, tmp_path/'missing.qxbak', PASSPHRASE, data_parent=parent)
    original.write_bytes(raw)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('CREATE TABLE attacker (id TEXT)'); db.commit()
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
    (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    with pytest.raises(ValueError, match='SCHEMA'):
        module.create_workspace_backup(root, tmp_path/'schema.qxbak', PASSPHRASE, data_parent=parent)


def test_weak_passphrase_and_archive_inside_source_rejected(source, tmp_path):
    module = feature(); parent, root, *_ = source
    for secret in ('short', 'x'*129):
        with pytest.raises(ValueError): module.create_workspace_backup(root, tmp_path/'secret.qxbak', secret, data_parent=parent)
    with pytest.raises(ValueError): module.create_workspace_backup(root, root/'self.qxbak', PASSPHRASE, data_parent=parent)


def test_extra_protected_files_preserved_and_hardlinks_rejected(source, tmp_path):
    import os
    module = feature(); parent, root, *_ = source
    attachment = root/'protected'/'人工证据.txt'; attachment.write_bytes(b'synthetic provenance')
    archive = tmp_path/'extra.qxbak'
    module.create_workspace_backup(root, archive, PASSPHRASE, data_parent=parent)
    report = module.restore_workspace_backup(archive, tmp_path/'copies', PASSPHRASE)
    assert (Path(report['restored_root'])/'protected'/'人工证据.txt').read_bytes() == attachment.read_bytes()
    os.link(attachment, root/'protected'/'linked.txt')
    with pytest.raises(ValueError): module.create_workspace_backup(root, tmp_path/'linked.qxbak', PASSPHRASE, data_parent=parent)


def test_committed_wal_is_included(source,tmp_path):
    module=feature();parent,root,*_=source
    archive=tmp_path/'wal.qxbak'
    with closing(sqlite3.connect(root/'workbench.db')) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()==('wal',)
        writer.execute("UPDATE users SET username='wal-lawyer' WHERE username='local-lawyer'");writer.commit()
        assert (root/'workbench.db-wal').stat().st_size>0
        module.create_workspace_backup(root,archive,PASSPHRASE,data_parent=parent)
    result=module.restore_workspace_backup(archive,parent/'wal-restores',PASSPHRASE)
    with TestClient(local_server.build_local_app(result['restored_root'],data_parent=parent)) as client:
        login(client,username='wal-lawyer')
        assert client.get('/api/matters').status_code==200


def test_failed_encryption_cleans_only_own_staging(source,tmp_path,monkeypatch):
    module=feature();parent,root,*_=source
    before=(root/'workbench.db').read_bytes()
    unrelated=tmp_path/'keep.txt';unrelated.write_text('unrelated',encoding='utf-8')
    def fail(*args):raise OSError('synthetic disk failure')
    monkeypatch.setattr(module,'_encrypt',fail)
    with pytest.raises(OSError):module.create_workspace_backup(root,tmp_path/'failed.qxbak',PASSPHRASE,data_parent=parent)
    assert (root/'workbench.db').read_bytes()==before
    assert unrelated.read_text('utf-8')=='unrelated'
    assert not list(tmp_path.glob('.qx-backup-*')) and not (tmp_path/'failed.qxbak').exists()


def test_count_limit_rejects_without_publishing(source,tmp_path,monkeypatch):
    module=feature();parent,root,*_=source
    monkeypatch.setattr(module,'MAX_FILES',2)
    with pytest.raises(ValueError,match='FILE_COUNT_LIMIT'):
        module.create_workspace_backup(root,tmp_path/'limit.qxbak',PASSPHRASE,data_parent=parent)
    assert not (tmp_path/'limit.qxbak').exists()


def test_plaintext_staging_stays_inside_workspace(source,tmp_path,monkeypatch):
    module=feature();parent,root,*_=source
    actual=module._encrypt
    def inspect(plain,target,secret):
        assert plain.is_relative_to(root), 'plaintext reached backup destination'
        return actual(plain,target,secret)
    monkeypatch.setattr(module,'_encrypt',inspect)
    destination=tmp_path/'portable';destination.mkdir()
    module.create_workspace_backup(root,destination/'encrypted.qxbak',PASSPHRASE,data_parent=parent)
    assert [p.name for p in destination.iterdir()]==['encrypted.qxbak']
