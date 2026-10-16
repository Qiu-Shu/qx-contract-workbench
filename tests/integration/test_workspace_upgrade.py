"""Synthetic legacy workspaces; precise additive migration and interrupted finalization."""
from contextlib import closing
import hashlib
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from cn_contract.web import local_server
from tests.integration.test_api import create_case
from tests.integration.test_local_workbench import login, PASSWORD


@pytest.fixture
def legacy(tmp_path,monkeypatch):
    monkeypatch.setattr(local_server,'PROJECT_ROOT',tmp_path)
    root=tmp_path/'.local'/'workbench'
    local_server.initialize_workspace(root,'local-lawyer',PASSWORD)
    with TestClient(local_server.build_local_app(root)) as client:
        matter=create_case(client,login(client),title='升级前合成案件')
    # Remove only the new extension, recreating an actual pre-intake schema.
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        for table in ('intake_revisions','intake_cases'):
            db.execute('DROP TABLE IF EXISTS '+table)
        db.commit()
        marker=json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256']=local_server._schema_hash(db)
    (root/'workspace.json').write_text(json.dumps(marker),encoding='utf-8')
    return root,matter,marker


def test_upgrade_keeps_identity_login_case_and_independent_backup(legacy):
    root,matter,marker=legacy
    with TestClient(local_server.build_local_app(root)) as client:
        login(client)
        assert client.get('/api/matters').json()[0]['id']==matter
        assert client.get('/api/intakes').status_code==200
    receipt=json.loads((root/'upgrade-intake-v1.json').read_text('utf-8'))
    backup=root/receipt['backup']
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==receipt['backup_sha256']
    with closing(sqlite3.connect(backup)) as db:
        assert local_server._schema_hash(db)==marker['schema_sha256']
        assert db.execute('SELECT id FROM matters').fetchall()==[(matter,)]
    with TestClient(local_server.build_local_app(root)) as client:
        login(client); assert client.get('/api/matters').json()[0]['id']==matter
    assert json.loads((root/'workspace.json').read_text('utf-8'))['workspace_id']==marker['workspace_id']


def test_marker_write_failure_recovers_without_rerunning_migration(legacy,monkeypatch):
    root,matter,marker=legacy
    from cn_contract.web import workspace_upgrade
    original=workspace_upgrade._write_marker
    def fail(*args):raise OSError('synthetic disk failure')
    monkeypatch.setattr(workspace_upgrade,'_write_marker',fail)
    with pytest.raises(OSError):local_server.build_local_app(root)
    assert json.loads((root/'workspace.json').read_text('utf-8'))==marker
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='intake_cases'").fetchone()
    monkeypatch.setattr(workspace_upgrade,'_write_marker',original)
    with TestClient(local_server.build_local_app(root)) as client:
        login(client);assert client.get('/api/matters').json()[0]['id']==matter


def test_unknown_schema_change_not_accepted(legacy):
    root,_,_=legacy
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('CREATE TABLE unknown_change (id TEXT)');db.commit()
    with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):
        local_server.build_local_app(root)
    assert not (root/'upgrade-intake-v1.json').exists()


def test_migration_transaction_failure_leaves_legacy_schema(legacy,monkeypatch):
    root,_,marker=legacy
    from cn_contract.web import workspace_upgrade
    monkeypatch.setattr(workspace_upgrade,'STATEMENTS',(*workspace_upgrade.STATEMENTS,'INVALID SQL'))
    with pytest.raises(sqlite3.Error):local_server.build_local_app(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert local_server._schema_hash(db)==marker['schema_sha256']
    assert json.loads((root/'workspace.json').read_text('utf-8'))==marker


def test_recovery_refuses_changed_extension_or_backup(legacy,monkeypatch):
    root,_,_=legacy
    from cn_contract.web import workspace_upgrade
    original=workspace_upgrade._write_marker
    monkeypatch.setattr(workspace_upgrade,'_write_marker',lambda *args:(_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):local_server.build_local_app(root)
    monkeypatch.setattr(workspace_upgrade,'_write_marker',original)
    receipt=json.loads((root/'upgrade-intake-v1.json').read_text('utf-8'))
    backup=root/receipt['backup'];old=backup.read_bytes();backup.write_bytes(b'not a backup')
    with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):local_server.build_local_app(root)
    backup.write_bytes(old)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('DROP TRIGGER immutable_intake_revisions_update');db.commit()
    with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):local_server.build_local_app(root)
