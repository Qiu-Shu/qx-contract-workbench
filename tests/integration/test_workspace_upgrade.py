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
    # Remove versioned extensions, recreating the fixed pre-intake schema.
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        for table in ('assistant_model_input_citations', 'assistant_library_citations', 'assistant_handler_receipts',
                      'assistant_judge_decisions', 'assistant_judge_receipts', 'assistant_judge_attempts',
                      'assistant_model_outputs', 'assistant_model_receipts', 'assistant_model_attempts',
                      'assistant_material_snapshots', 'assistant_attachment_parses', 'assistant_attachments',
                      'assistant_run_events', 'assistant_runs', 'assistant_messages',
                      'assistant_conversations', 'intake_revisions','intake_cases'):
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


@pytest.mark.parametrize('damage', ['unknown', 'missing_trigger'])
def test_self_consistent_marker_cannot_authorize_unknown_schema(legacy, damage):
    root, _, _ = legacy
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        sql = ('CREATE TABLE unknown_change (id TEXT)' if damage == 'unknown'
               else 'DROP TRIGGER immutable_document_versions_update')
        db.execute(sql); db.commit()
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
        before = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    with pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        local_server.build_local_app(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall() == before
    assert not (root/'upgrade-intake-v1.json').exists()


def test_existing_workspace_does_not_run_create_all(legacy, monkeypatch):
    root, _, _ = legacy
    with TestClient(local_server.build_local_app(root)) as client: login(client)
    monkeypatch.setattr(local_server, 'initialize_storage', lambda *_:
                        (_ for _ in ()).throw(AssertionError('existing database must not initialize schema')))
    with TestClient(local_server.build_local_app(root)) as client: login(client)


@pytest.mark.parametrize('target', ['assistant-v1', 'assistant-attachments-v1', 'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1', 'assistant-context-v1'])
def test_assistant_marker_failure_recovers_without_repeating_completed_steps(legacy, monkeypatch, target):
    from cn_contract.web import workspace_upgrade
    from cn_contract.storage_schema import CURRENT_VERSION, VERSIONS, schema_rows
    root, matter, _ = legacy
    original = workspace_upgrade._write_marker
    target_hash = workspace_upgrade._hash(schema_rows(target, native=True))
    def fail_assistant(root, marker):
        if marker['schema_sha256'] == target_hash: raise OSError('synthetic assistant marker failure')
        original(root, marker)
    monkeypatch.setattr(workspace_upgrade, '_write_marker', fail_assistant)
    with pytest.raises(OSError): local_server.build_local_app(root)
    receipt_paths = [root/('upgrade-'+name+'.json') for name in VERSIONS[1:VERSIONS.index(target)+1]]
    receipts = [path.read_bytes() for path in receipt_paths]
    backups = sorted(str(path) for path in (root/'upgrade-backups').rglob('before.db'))
    assert len(backups) == VERSIONS.index(target)
    monkeypatch.setattr(workspace_upgrade, '_write_marker', original)
    with TestClient(local_server.build_local_app(root)) as client:
        login(client)
        assert client.get('/api/matters').json()[0]['id'] == matter
    assert [path.read_bytes() for path in receipt_paths] == receipts
    after_backups = sorted(str(path) for path in (root/'upgrade-backups').rglob('before.db'))
    assert set(backups).issubset(after_backups)
    assert len(after_backups) == len(VERSIONS)-1
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == workspace_upgrade._hash(schema_rows(CURRENT_VERSION, native=True))


@pytest.mark.parametrize('target, previous', [('assistant-v1', 'intake-v1'),
                                             ('assistant-attachments-v1', 'assistant-v1'),
                                             ('assistant-model-v1', 'assistant-attachments-v1'),
                                             ('assistant-judge-v1', 'assistant-model-v1'),
                                             ('assistant-library-v1', 'assistant-judge-v1'),
                                             ('assistant-context-v1', 'assistant-library-v1')])
def test_assistant_ddl_failure_preserves_completed_steps(legacy, monkeypatch, target, previous):
    from cn_contract.web import workspace_upgrade
    from cn_contract.storage_schema import identify_schema
    root, matter, _ = legacy
    original = workspace_upgrade.statements_for
    monkeypatch.setattr(workspace_upgrade, 'statements_for', lambda name:
                        (*original(name), 'INVALID SQL') if name == target else original(name))
    with pytest.raises(sqlite3.Error): local_server.build_local_app(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert identify_schema(workspace_upgrade._rows(db), native=True) == previous
        assert db.execute('SELECT id FROM matters').fetchall() == [(matter,)]
        assert local_server._schema_hash(db) == json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256']
    previous_receipt = (root/('upgrade-'+previous+'.json')).read_bytes()
    monkeypatch.setattr(workspace_upgrade, 'statements_for', original)
    with TestClient(local_server.build_local_app(root)) as client: login(client)
    assert (root/('upgrade-'+previous+'.json')).read_bytes() == previous_receipt


@pytest.mark.parametrize('target', ['assistant-v1', 'assistant-attachments-v1', 'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1', 'assistant-context-v1'])
@pytest.mark.parametrize('damage', ['backup', 'receipt', 'trigger'])
def test_assistant_pending_recovery_rejects_tampering(legacy, monkeypatch, damage, target):
    from cn_contract.web import workspace_upgrade
    from cn_contract.storage_schema import schema_rows
    root, _, _ = legacy
    original = workspace_upgrade._write_marker
    target_hash = workspace_upgrade._hash(schema_rows(target, native=True))
    def fail_assistant(root, marker):
        if marker['schema_sha256'] == target_hash: raise OSError('synthetic assistant marker failure')
        original(root, marker)
    monkeypatch.setattr(workspace_upgrade, '_write_marker', fail_assistant)
    with pytest.raises(OSError): local_server.build_local_app(root)
    monkeypatch.setattr(workspace_upgrade, '_write_marker', original)
    path = root/('upgrade-'+target+'.json')
    receipt = json.loads(path.read_text('utf-8'))
    if damage == 'backup': (root/receipt['backup']).write_bytes(b'changed backup')
    elif damage == 'receipt':
        receipt['before_schema'] = '0'*64
        path.write_text(json.dumps(receipt), encoding='utf-8')
    else:
        with closing(sqlite3.connect(root/'workbench.db')) as db:
            trigger = {'assistant-v1':'immutable_assistant_messages_update',
                       'assistant-attachments-v1':'immutable_assistant_attachments_update',
                       'assistant-model-v1':'immutable_assistant_model_receipts_update',
                       'assistant-judge-v1':'immutable_assistant_judge_receipts_update',
                       'assistant-library-v1':'immutable_assistant_handler_receipts_update',
                       'assistant-context-v1':'immutable_assistant_model_input_citations_update'}[target]
            db.execute('DROP TRIGGER '+trigger); db.commit()
    with pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        local_server.build_local_app(root)
