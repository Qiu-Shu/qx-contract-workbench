"""Synthetic dispatch storage preserves every predecessor and immutable receipt."""
from contextlib import closing
import hashlib
import importlib
import json
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db
from tests.integration.test_weixin_inbox_schema import FROZEN as INBOX_PREDECESSORS


TARGET = 'weixin-dispatch-v1'
FROZEN = INBOX_PREDECESSORS + [
    {'version':'weixin-inbox-v1', 'native':False,
     'raw':'534e5b03133a91bb9f891bdef594c4123331b69e3f504c64a29048b437906d6a',
     'normalized':'47f89467c40691af4bcd1b183a6858fcb8ac596b447e4a97109281020de587c7'},
    {'version':'weixin-inbox-v1', 'native':True,
     'raw':'70108dde543cf6cc868e21efd556850974be3b91049857ed40945c5ff8f8f775',
     'normalized':'aa9c8be0cf260314c4923a7f122a8687cf990add5b5ff26fb6777242d68384dd'},
]
PREVIOUS = tuple(item['version'] for item in FROZEN if not item['native'])


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('item', FROZEN, ids=lambda item:item['version']+('-native' if item['native'] else ''))
def test_all_fourteen_predecessors_keep_frozen_fingerprints(item):
    rows = storage_schema.schema_rows(item['version'], native=item['native'])
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized']
    assert storage_schema.identify_schema(rows, native=item['native']) == item['version']


def test_dispatch_is_an_additive_successor_without_changing_inbox_schema():
    assert storage_schema.VERSIONS[:len(PREVIOUS)+1] == PREVIOUS + (TARGET,)
    before = set(storage_schema.schema_rows('weixin-inbox-v1'))
    after = set(storage_schema.schema_rows(TARGET))
    assert before < after
    assert {row[2] for row in after-before} == {'weixin_dispatch_receipts'}


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False,True])
def test_every_predecessor_upgrades_preserving_old_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db',version,native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION,native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION


@pytest.mark.parametrize('native', [False,True])
def test_failed_dispatch_migration_rolls_back_all_ddl_and_rows(tmp_path,monkeypatch,native):
    with closing(old_db(tmp_path/'old.db','weixin-inbox-v1',native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations,'statements_for',lambda version:
            (*original(version),'INVALID SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert not db.in_transaction


def test_unknown_schema_cannot_upgrade_or_silently_repair(tmp_path):
    with closing(old_db(tmp_path/'old.db','weixin-inbox-v1',False)) as db:
        db.execute('CREATE TABLE unexpected_dispatch_state (id TEXT)')
        db.commit()
        before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError,match='DATABASE_SCHEMA_MISMATCH'):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before


def test_fresh_reinitialized_and_upgraded_dispatch_structures_are_equal(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'new.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            actual = schema_migrations.database_rows(db)
        assert actual == storage_schema.schema_rows(storage_schema.CURRENT_VERSION)
        with closing(old_db(tmp_path/'old.db','weixin-inbox-v1',False)) as db:
            schema_migrations.upgrade_database(db)
            assert schema_migrations.database_rows(db) == actual
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage',[
    'DROP TRIGGER immutable_weixin_dispatch_receipts_update',
    'ALTER TABLE weixin_dispatch_receipts ADD COLUMN untrusted TEXT',
    'CREATE INDEX unexpected_dispatch_index ON weixin_dispatch_receipts(created_at)',
])
def test_partial_dispatch_schema_is_rejected_without_silent_repair(tmp_path,damage):
    schema = importlib.import_module('cn_contract.weixin_inbox.dispatch_schema')
    database = Database('sqlite:///'+str(tmp_path/'new.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql(damage)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError,match='DATABASE_SCHEMA_MISMATCH'):
            schema.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            assert schema_migrations.database_rows(db) == before
    finally:
        database.engine.dispose()


@pytest.fixture
def receipt_table():
    schema = importlib.import_module('cn_contract.weixin_inbox.dispatch_schema')
    with closing(sqlite3.connect(':memory:')) as db:
        for statement in schema.STATEMENTS:
            db.execute(statement)
        db.execute("INSERT INTO weixin_dispatch_receipts VALUES ('receipt','descriptor','account','mapping','actor','binding','task-event','wx1:source','hash',0,1,'at','hash')")
        yield db


@pytest.mark.parametrize('operation',['UPDATE','DELETE'])
def test_dispatch_receipts_cannot_be_changed_or_deleted(receipt_table,operation):
    sql = "UPDATE weixin_dispatch_receipts SET id='changed'" if operation == 'UPDATE' else 'DELETE FROM weixin_dispatch_receipts'
    with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_RECORD'):
        receipt_table.execute(sql)


@pytest.mark.parametrize('column,value',[
    ('expected_task_cursor',-1),('expected_task_cursor',0.5),('expected_task_cursor','invalid'),
    ('next_task_cursor',0),('next_task_cursor',2),('next_task_cursor',1.5),
    ('next_task_cursor',None),('descriptor_id',None),('task_event_id',None),
])
def test_receipt_shape_constraints_reject_invalid_cursor_and_missing_links(receipt_table,column,value):
    receipt_table.execute('DROP TRIGGER immutable_weixin_dispatch_receipts_update')
    with pytest.raises(sqlite3.IntegrityError):
        receipt_table.execute('UPDATE weixin_dispatch_receipts SET '+column+'=?',(value,))


@pytest.mark.parametrize('duplicate',['descriptor_id','task_event_id'])
def test_descriptor_and_task_event_each_have_one_dispatch_receipt(receipt_table,duplicate):
    columns = [row[1] for row in receipt_table.execute('PRAGMA table_info(weixin_dispatch_receipts)')]
    values = list(receipt_table.execute('SELECT * FROM weixin_dispatch_receipts').fetchone())
    values[0],values[1],values[6] = 'other','other-descriptor','other-event'
    values[columns.index(duplicate)] = 'descriptor' if duplicate == 'descriptor_id' else 'task-event'
    with pytest.raises(sqlite3.IntegrityError):
        receipt_table.execute('INSERT INTO weixin_dispatch_receipts VALUES ('+','.join('?' for _ in values)+')',values)


def test_dispatch_foreign_keys_match_persisted_provenance(receipt_table):
    actual = {(row[3],row[2],row[4]) for row in receipt_table.execute('PRAGMA foreign_key_list(weixin_dispatch_receipts)')}
    assert actual == {('descriptor_id','weixin_inbox_descriptors','id'),('account_id','weixin_accounts','id'),
        ('mapping_id','weixin_peer_bindings','id'),('actor_id','users','id'),
        ('task_binding_id','task_channel_bindings','id'),('task_event_id','task_inbox_events','id')}


@pytest.fixture
def native_inbox_workspace(tmp_path):
    from cn_contract.web import local_server
    root = tmp_path/'workspace'
    local_server.initialize_workspace(root,'synthetic-lawyer','fiction123',data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('DROP TABLE weixin_peer_scope_grants')
        db.execute('DROP TABLE weixin_dispatch_receipts')
        db.commit()
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-inbox-v1',native=True)
    (root/'workspace.json').write_text(json.dumps(marker),encoding='utf-8')
    return root,marker


def test_native_upgrade_records_verified_backup_and_preserves_workspace_identity(native_inbox_workspace):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_inbox_workspace
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    receipt = json.loads((root/('upgrade-'+TARGET+'.json')).read_text('utf-8'))
    assert receipt['before_schema'] == marker['schema_sha256']
    assert receipt['workspace_id'] == marker['workspace_id']
    before = root/receipt['backup']
    assert hashlib.sha256(before.read_bytes()).hexdigest() == receipt['backup_sha256']
    with closing(sqlite3.connect(before)) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-inbox-v1',native=True)
        assert db.execute('SELECT id FROM local_workspace_identity').fetchall() == [(marker['workspace_id'],)]
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION,native=True)
        assert local_server._schema_hash(db) == digest(storage_schema.schema_rows(storage_schema.CURRENT_VERSION,native=True))
    assert receipt['after_schema'] == digest(storage_schema.schema_rows(TARGET,native=True))
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == digest(storage_schema.schema_rows(storage_schema.CURRENT_VERSION,native=True))


@pytest.mark.parametrize('damage',[None,'backup','receipt','trigger'])
def test_native_committed_ddl_marker_gap_accepts_only_intact_receipt(native_inbox_workspace,monkeypatch,damage):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_inbox_workspace
    original = workspace_upgrade._write_marker
    def fail(*args):
        raise OSError('synthetic marker write failure')
    monkeypatch.setattr(workspace_upgrade,'_write_marker',fail)
    with local_server._worker_lock(root), pytest.raises(OSError):
        workspace_upgrade.upgrade(root)
    monkeypatch.setattr(workspace_upgrade,'_write_marker',original)
    assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
    receipt_path = root/('upgrade-'+TARGET+'.json')
    receipt = json.loads(receipt_path.read_text('utf-8'))
    folders = list((root/'upgrade-backups').iterdir())
    if damage == 'backup':
        (root/receipt['backup']).write_bytes(b'synthetic corruption')
    elif damage == 'receipt':
        receipt_path.write_text(json.dumps(receipt|{'after_schema':'0'*64}),encoding='utf-8')
    elif damage == 'trigger':
        with closing(sqlite3.connect(root/'workbench.db')) as db:
            db.execute('DROP TRIGGER immutable_weixin_dispatch_receipts_update')
    if damage:
        with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):
            local_server._open_workspace(root,data_parent=root.parent)
        assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
    else:
        local_server._open_workspace(root,data_parent=root.parent)
        with local_server._worker_lock(root):
            workspace_upgrade.upgrade(root)
        assert {p for p in (root/'upgrade-backups').iterdir() if p.name.startswith('weixin-dispatch-')} == set(folders)
        assert receipt['after_schema'] == digest(storage_schema.schema_rows(TARGET,native=True))
        assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == digest(storage_schema.schema_rows(storage_schema.CURRENT_VERSION,native=True))


def test_native_failed_dispatch_ddl_preserves_prior_schema_and_marker(native_inbox_workspace,monkeypatch):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_inbox_workspace
    original = workspace_upgrade.statements_for
    monkeypatch.setattr(workspace_upgrade,'statements_for',lambda version:
        (*original(version),'INVALID SQL') if version == TARGET else original(version))
    with local_server._worker_lock(root),pytest.raises(sqlite3.Error):
        workspace_upgrade.upgrade(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-inbox-v1',native=True)
    assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
