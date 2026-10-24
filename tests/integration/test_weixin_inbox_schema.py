"""Synthetic inbox foundation preserves historical schemas and immutable receipts."""
from contextlib import closing
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db


TARGET = 'weixin-inbox-v1'
FROZEN = json.loads((Path(__file__).parents[1]/'fixtures/task_drafts_schema_predecessors.json').read_text('utf-8'))['signatures'] + [
    {'version':'task-drafts-v1', 'native':False,
     'raw':'07f12df959a164f976260c3e70f80d25477a1d21f5c38b579709925ac0c92e4c',
     'normalized':'e85cf5977c1fa67afe6351aa45f1d62b08967a877e2da560d1eb666b68a11c54'},
    {'version':'task-drafts-v1', 'native':True,
     'raw':'99e5f2d13527a9116f5dce523b02ea3a31d92c2fc81e1e36112205cc8e653afd',
     'normalized':'15a6334d6033b7a0eba1dda3f58fe78b6a3f5d9fef2e8b83a70702cd2de50ff3'},
]
PREVIOUS = tuple(item['version'] for item in FROZEN if not item['native'])
TABLES = {'weixin_accounts','weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors'}


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('item', FROZEN, ids=lambda item:item['version']+('-native' if item['native'] else ''))
def test_all_thirteen_predecessors_keep_frozen_fingerprints(item):
    rows = storage_schema.schema_rows(item['version'], native=item['native'])
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized']
    assert storage_schema.identify_schema(rows, native=item['native']) == item['version']


def test_inbox_is_an_additive_successor_without_changing_task_schema():
    assert storage_schema.VERSIONS == PREVIOUS + (TARGET,)
    assert storage_schema.CURRENT_VERSION == TARGET
    before = set(storage_schema.schema_rows('task-drafts-v1'))
    after = set(storage_schema.schema_rows(TARGET))
    assert before < after
    assert {row[2] for row in after-before} == TABLES


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False,True])
def test_every_predecessor_upgrades_preserving_old_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db',version,native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        assert schema_migrations.upgrade_database(db) == TARGET
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(TARGET,native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(db) == TARGET


def test_failed_inbox_migration_rolls_back_all_ddl_and_rows(tmp_path,monkeypatch):
    with closing(old_db(tmp_path/'old.db','task-drafts-v1',False)) as db:
        before = schema_migrations.database_rows(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations,'statements_for',lambda version:
            (*original(version),'INVALID SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


def test_fresh_reinitialized_and_upgraded_inbox_structures_are_equal(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'new.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            actual = schema_migrations.database_rows(db)
        assert actual == storage_schema.schema_rows(TARGET)
        with closing(old_db(tmp_path/'old.db','task-drafts-v1',False)) as db:
            schema_migrations.upgrade_database(db)
            assert schema_migrations.database_rows(db) == actual
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage',[
    'DROP TABLE weixin_inbox_descriptors',
    'DROP TRIGGER immutable_weixin_poll_receipts_update',
    'ALTER TABLE weixin_accounts ADD COLUMN untrusted TEXT',
    'CREATE INDEX unexpected_weixin_index ON weixin_accounts(created_at)',
])
def test_partial_inbox_schema_is_rejected_without_silent_repair(tmp_path,damage):
    schema = importlib.import_module('cn_contract.weixin_inbox.schema')
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
def family():
    schema = importlib.import_module('cn_contract.weixin_inbox.schema')
    with closing(sqlite3.connect(':memory:')) as db:
        for statement in schema.STATEMENTS:
            db.execute(statement)
        db.execute("INSERT INTO weixin_accounts (id,workspace_id,owner_id,bot_account_id,mode,initial_cursor,checkpoint_revision,upstream_cursor,created_at) VALUES ('account','workspace','owner','bot','synthetic','initial',0,'initial','at')")
        db.execute("INSERT INTO weixin_peer_bindings (id,account_id,sender_peer_id,task_binding_id,scope_json,scope_sha256,created_at) VALUES ('mapping','account','peer','binding','{}','hash','at')")
        db.execute("INSERT INTO weixin_poll_receipts VALUES ('poll','account','request','request-hash','response-hash',0,1,'initial','next',1,'receipt-hash','at')")
        db.execute("INSERT INTO weixin_inbox_descriptors VALUES ('descriptor','poll',1,'peer','1','event','hash','accepted_pending_dispatch',NULL,'mapping',NULL,'{}')")
        yield db


@pytest.mark.parametrize('table',['weixin_poll_receipts','weixin_inbox_descriptors'])
@pytest.mark.parametrize('operation',['UPDATE','DELETE'])
def test_receipts_and_descriptors_cannot_be_changed_or_deleted(family,table,operation):
    sql = 'UPDATE '+table+" SET id='changed'" if operation == 'UPDATE' else 'DELETE FROM '+table
    with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_RECORD'):
        family.execute(sql)


@pytest.mark.parametrize('sql',[
    "DELETE FROM weixin_accounts",
    "DELETE FROM weixin_peer_bindings",
    "UPDATE weixin_accounts SET initial_cursor='other'",
    "UPDATE weixin_accounts SET owner_id='other'",
    "UPDATE weixin_peer_bindings SET task_binding_id='other'",
    "UPDATE weixin_peer_bindings SET scope_json='other'",
    "UPDATE weixin_accounts SET upstream_cursor='next'",
    "UPDATE weixin_accounts SET checkpoint_revision=2,upstream_cursor='next'",
    "UPDATE weixin_accounts SET checkpoint_revision=-1",
])
def test_identity_and_checkpoint_mutations_fail_closed(family,sql):
    with pytest.raises(sqlite3.IntegrityError):
        family.execute(sql)


def test_checkpoint_can_only_advance_one_revision(family):
    family.execute("UPDATE weixin_accounts SET checkpoint_revision=1,upstream_cursor='next'")
    family.execute("UPDATE weixin_accounts SET checkpoint_revision=2,upstream_cursor='next',revoked_at='at',revoked_by='owner',revoke_reason='synthetic revoke'")
    assert family.execute('SELECT checkpoint_revision,upstream_cursor FROM weixin_accounts').fetchone() == (2,'next')
    assert family.execute('SELECT revoked_at,revoked_by,revoke_reason FROM weixin_accounts').fetchone() == ('at','owner','synthetic revoke')
    with pytest.raises(sqlite3.IntegrityError):
        family.execute("UPDATE weixin_accounts SET checkpoint_revision=1,upstream_cursor='earlier'")


@pytest.mark.parametrize('table',['weixin_accounts','weixin_peer_bindings'])
def test_revocation_is_complete_once_only_and_irreversible(family,table):
    with pytest.raises(sqlite3.IntegrityError):
        family.execute('UPDATE '+table+" SET revoked_at='at'")
    family.execute('UPDATE '+table+" SET revoked_at='at',revoked_by='owner',revoke_reason='synthetic revoke'")
    for value in ["revoked_at=NULL,revoked_by=NULL,revoke_reason=NULL","revoke_reason='changed'"]:
        with pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_RECORD'):
            family.execute('UPDATE '+table+' SET '+value)


@pytest.mark.parametrize('assignments',[
    "ordinal=0", "ordinal=101", "status='ready'",
    "sender_peer_id=NULL", "upstream_message_id=NULL", "source_event_id=NULL",
    "status='blocked',reason=NULL,payload_json=NULL",
    "status='blocked',reason='message_invalid'",
    "status='duplicate',payload_json=NULL,prior_descriptor_id=NULL",
    "status='duplicate',payload_json=NULL,prior_descriptor_id='descriptor',reason=NULL",
])
def test_descriptor_shape_constraints_reject_incomplete_records(family,assignments):
    family.execute('DROP TRIGGER immutable_weixin_inbox_descriptors_update')
    with pytest.raises(sqlite3.IntegrityError):
        family.execute('UPDATE weixin_inbox_descriptors SET '+assignments)


@pytest.fixture
def native_task_workspace(tmp_path):
    from cn_contract.web import local_server
    root = tmp_path/'workspace'
    local_server.initialize_workspace(root,'synthetic-lawyer','fiction123',data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        for table in ('weixin_inbox_descriptors','weixin_poll_receipts','weixin_peer_bindings','weixin_accounts'):
            db.execute('DROP TABLE '+table)
        db.commit()
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('task-drafts-v1',native=True)
    (root/'workspace.json').write_text(json.dumps(marker),encoding='utf-8')
    return root,marker


def test_native_upgrade_records_verified_backup_and_preserves_workspace_identity(native_task_workspace):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_task_workspace
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    receipt = json.loads((root/('upgrade-'+TARGET+'.json')).read_text('utf-8'))
    assert receipt['before_schema'] == marker['schema_sha256']
    assert receipt['workspace_id'] == marker['workspace_id']
    before = root/receipt['backup']
    assert hashlib.sha256(before.read_bytes()).hexdigest() == receipt['backup_sha256']
    with closing(sqlite3.connect(before)) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('task-drafts-v1',native=True)
        assert db.execute('SELECT id FROM local_workspace_identity').fetchall() == [(marker['workspace_id'],)]
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(TARGET,native=True)
        assert local_server._schema_hash(db) == receipt['after_schema']
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == receipt['after_schema']


@pytest.mark.parametrize('damage',[None,'backup','receipt','trigger'])
def test_native_committed_ddl_marker_gap_accepts_only_intact_receipt(native_task_workspace,monkeypatch,damage):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_task_workspace
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
            db.execute('DROP TRIGGER immutable_weixin_poll_receipts_update')
    if damage:
        with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):
            local_server._open_workspace(root,data_parent=root.parent)
        assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
    else:
        local_server._open_workspace(root,data_parent=root.parent)
        with local_server._worker_lock(root):
            workspace_upgrade.upgrade(root)
        assert list((root/'upgrade-backups').iterdir()) == folders
        assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == receipt['after_schema']


def test_native_failed_inbox_ddl_preserves_prior_schema_and_marker(native_task_workspace,monkeypatch):
    from cn_contract.web import local_server,workspace_upgrade
    root,marker = native_task_workspace
    original = workspace_upgrade.statements_for
    monkeypatch.setattr(workspace_upgrade,'statements_for',lambda version:
        (*original(version),'INVALID SQL') if version == TARGET else original(version))
    with local_server._worker_lock(root),pytest.raises(sqlite3.Error):
        workspace_upgrade.upgrade(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('task-drafts-v1',native=True)
    assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
