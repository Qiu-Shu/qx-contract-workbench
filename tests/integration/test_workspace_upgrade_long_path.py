"""Real old workspaces recover a committed upgrade with an unwritten marker."""
from contextlib import closing
import hashlib
import json
import shutil
import sqlite3

from fastapi.testclient import TestClient
import pytest

from cn_contract.ops.file_paths import filesystem_path, sqlite_readonly_uri
from cn_contract.persistence import read_original
from cn_contract.security import authenticate
from cn_contract.storage_schema import CURRENT_VERSION, VERSIONS, identify_schema, schema_rows
from cn_contract.web import local_server, workspace_upgrade
from tests.helpers.legacy_assistant_backup import legacy_world, USERNAME, PASSWORD
from tests.integration.test_local_workbench import login


def file_bytes(root):
    native = filesystem_path(root)
    return {path.relative_to(native).as_posix(): path.read_bytes()
            for path in native.rglob('*') if path.is_file()}


def business_rows(root):
    with closing(sqlite3.connect(sqlite_readonly_uri(root/'workbench.db'), uri=True)) as db:
        return {table: sorted(db.execute('SELECT * FROM '+table).fetchall())
                for table in ('matters', 'document_versions', 'intake_cases', 'intake_revisions',
                              'local_workspace_identity')}


@pytest.fixture
def old_long_workspace(tmp_path):
    source, database, _, matter, document, _, raw = legacy_world(tmp_path/'source', native=True)
    database.engine.dispose()
    before = file_bytes(source)
    root = tmp_path/'independent-upgrade'
    while len(str(root)) <= 300:
        root /= 'long-workspace-segment'
    filesystem_path(root.parent).mkdir(parents=True, exist_ok=True)
    shutil.copytree(filesystem_path(source), filesystem_path(root))
    assert file_bytes(root) == before
    assert len(str(root/'workbench.db')) > 300
    try:
        yield {'root': root, 'parent': tmp_path, 'matter': matter, 'document': document, 'raw': raw,
               'marker': before['workspace.json'], 'business': business_rows(root)}
    finally:
        assert file_bytes(source) == before


def interrupt_committed_step(context, monkeypatch):
    root = context['root']
    target_hash = workspace_upgrade._hash(schema_rows('assistant-v1', native=True))
    observed = []

    def fail_marker(directory, marker):
        assert marker['schema_sha256'] == target_hash
        with closing(sqlite3.connect(sqlite_readonly_uri(directory/'workbench.db'), uri=True)) as db:
            assert identify_schema(workspace_upgrade._rows(db), native=True) == 'assistant-v1'
        receipt = filesystem_path(directory/'upgrade-assistant-v1.json')
        assert receipt.is_file()
        observed.append('sql-and-receipt-committed')
        raise OSError('synthetic interrupted marker')

    with monkeypatch.context() as patch:
        patch.setattr(workspace_upgrade, '_write_marker', fail_marker)
        with pytest.raises(OSError, match='synthetic interrupted marker'):
            local_server.build_local_app(root, data_parent=context['parent'])
    assert observed == ['sql-and-receipt-committed']
    assert filesystem_path(root/'workspace.json').read_bytes() == context['marker']
    assert business_rows(root) == context['business']
    receipt = json.loads(filesystem_path(root/'upgrade-assistant-v1.json').read_text('utf8'))
    assert receipt['before_schema'] == json.loads(context['marker'])['schema_sha256']
    backup = filesystem_path(root/receipt['backup'])
    assert len(str(root/receipt['backup'])) > 300
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == receipt['backup_sha256']
    with closing(sqlite3.connect(sqlite_readonly_uri(backup), uri=True)) as db:
        assert identify_schema(workspace_upgrade._rows(db), native=True) == 'intake-v1'
    return {name: raw for name, raw in file_bytes(root).items()
            if name.startswith('upgrade-backups/') or name.startswith('upgrade-') and name.endswith('.json')}


def test_long_pending_marker_recovers_without_repeating_committed_step(old_long_workspace, monkeypatch, record_property):
    context = old_long_workspace;root = context['root']
    historical = interrupt_committed_step(context, monkeypatch)
    real_statements = workspace_upgrade.statements_for
    executed = []

    def track_remaining_steps(target):
        assert target != 'assistant-v1', 'committed migration must not run again'
        executed.append(target)
        return real_statements(target)

    monkeypatch.setattr(workspace_upgrade, 'statements_for', track_remaining_steps)
    app = local_server.build_local_app(root, data_parent=context['parent'])
    assert str(app.state.database.engine.url.database) == str(root/'workbench.db')
    with TestClient(app) as client:
        login(client, USERNAME, PASSWORD)
        assert client.get('/api/matters').json()[0]['id'] == str(context['matter'].id)
        with app.state.database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
            assert read_original(context['matter'].id, context['document'].id, actor, db) == context['raw']
    assert executed == list(VERSIONS[VERSIONS.index('assistant-v1')+1:])
    assert business_rows(root) == context['business']
    after = file_bytes(root)
    assert all(after[name] == raw for name, raw in historical.items())
    assert len([name for name in after if name.endswith('/before.db')]) == len(VERSIONS)-1-VERSIONS.index('intake-v1')
    marker = json.loads(after['workspace.json'])
    assert marker['workspace_id'] == json.loads(context['marker'])['workspace_id']
    assert marker['schema_sha256'] == workspace_upgrade._hash(schema_rows(CURRENT_VERSION, native=True))
    assert after['protected/'+context['document'].storage_ref] == context['raw']
    executed.clear()
    with TestClient(local_server.build_local_app(root, data_parent=context['parent'])) as client:
        login(client, USERNAME, PASSWORD)
    assert executed == []
    assert all(file_bytes(root)[name] == raw for name, raw in historical.items())
    record_property('database_path_chars', len(str(root/'workbench.db')))
    record_property('receipt_path_chars', len(str(root/'upgrade-assistant-v1.json')))


@pytest.mark.parametrize('damage', ['receipt', 'backup'])
def test_long_pending_marker_rejects_damaged_recovery_without_writes(old_long_workspace, monkeypatch, damage):
    context = old_long_workspace;root = context['root']
    interrupt_committed_step(context, monkeypatch)
    receipt_path = filesystem_path(root/'upgrade-assistant-v1.json')
    receipt = json.loads(receipt_path.read_text('utf8'))
    if damage == 'receipt':
        receipt['before_schema'] = '0'*64
        receipt_path.write_text(json.dumps(receipt), encoding='utf8')
    else:
        filesystem_path(root/receipt['backup']).write_bytes(b'independent damaged backup')
    before = file_bytes(root)
    with pytest.raises(ValueError, match='^WORKSPACE_DATABASE_MISMATCH$'):
        local_server.build_local_app(root, data_parent=context['parent'])
    assert file_bytes(root) == before
    assert business_rows(root) == context['business']
