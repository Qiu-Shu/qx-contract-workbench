"""Synthetic peer generations append a seventeenth immutable schema family."""
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


TARGET = 'weixin-generations-v1'
CURRENT = storage_schema.CURRENT_VERSION
FROZEN = json.loads((Path(__file__).parents[1]/'fixtures/weixin_generation_schema_predecessors.json').read_text('utf-8'))
PREVIOUS = tuple(item['version'] for item in FROZEN if not item['native'])


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


@pytest.mark.parametrize('item', FROZEN, ids=lambda item:item['version']+('-native' if item['native'] else ''))
def test_all_sixteen_predecessors_keep_frozen_fingerprints(item):
    rows = storage_schema.schema_rows(item['version'], native=item['native'])
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized']
    assert storage_schema.identify_schema(rows, native=item['native']) == item['version']


def test_generations_append_one_family_to_the_unchanged_grant_schema():
    assert storage_schema.VERSIONS[:17] == PREVIOUS + (TARGET,)
    assert storage_schema.identify_schema(storage_schema.schema_rows(TARGET)) == TARGET
    before = set(storage_schema.schema_rows('weixin-reauthorization-v1'))
    after = set(storage_schema.schema_rows(TARGET))
    assert before < after
    assert {row[2] for row in after-before} == {'weixin_peer_generations'}


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_every_predecessor_upgrades_preserving_old_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        assert schema_migrations.upgrade_database(db) == CURRENT
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(CURRENT, native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(db) == CURRENT


@pytest.mark.parametrize('native', [False, True])
def test_failed_generation_migration_rolls_back_all_ddl_and_rows(tmp_path, monkeypatch, native):
    with closing(old_db(tmp_path/'old.db', 'weixin-reauthorization-v1', native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version), 'INVALID SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert not db.in_transaction


def test_unknown_schema_cannot_upgrade_or_silently_repair(tmp_path):
    with closing(old_db(tmp_path/'old.db', 'weixin-reauthorization-v1', False)) as db:
        db.execute('CREATE TABLE unexpected_generation_state (id TEXT)')
        db.commit()
        before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before


def test_fresh_reinitialized_and_upgraded_generation_structures_are_equal(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'new.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            actual = schema_migrations.database_rows(db)
        assert actual == storage_schema.schema_rows(CURRENT)
        with closing(old_db(tmp_path/'old.db', 'weixin-reauthorization-v1', False)) as db:
            schema_migrations.upgrade_database(db)
            assert schema_migrations.database_rows(db) == actual
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage', [
    'DROP TRIGGER immutable_weixin_peer_generations_update',
    'ALTER TABLE weixin_peer_generations ADD COLUMN untrusted TEXT',
    'CREATE INDEX unexpected_generation_index ON weixin_peer_generations(created_at)',
])
def test_partial_generation_schema_is_rejected_without_silent_repair(tmp_path, damage):
    schema = importlib.import_module('cn_contract.weixin_inbox.generation_schema')
    database = Database('sqlite:///'+str(tmp_path/'new.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql(damage)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            schema.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            assert schema_migrations.database_rows(db) == before
    finally:
        database.engine.dispose()


@pytest.fixture
def generation_table():
    schema = importlib.import_module('cn_contract.weixin_inbox.generation_schema')
    with closing(sqlite3.connect(':memory:')) as db:
        for statement in schema.STATEMENTS:
            db.execute(statement)
        db.execute("INSERT INTO weixin_peer_generations VALUES ('generation','mapping',1,'request','actor','binding','{}','scope',NULL,'previous',0,'at','synthetic reason','hash')")
        yield db


@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE'])
def test_generations_cannot_be_changed_or_deleted(generation_table, operation):
    sql = "UPDATE weixin_peer_generations SET reason='changed'" if operation == 'UPDATE' else 'DELETE FROM weixin_peer_generations'
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        generation_table.execute(sql)


@pytest.mark.parametrize('column,value', [
    ('generation', 0), ('generation', -1), ('generation', 0.5), ('generation', 'invalid'),
    ('checkpoint_revision', -1), ('checkpoint_revision', 0.5), ('checkpoint_revision', 'invalid'),
    *[(column, None) for column in (
        'id', 'root_mapping_id', 'generation', 'request_id', 'actor_id', 'task_binding_id',
        'scope_json', 'scope_sha256', 'previous_scope_sha256', 'checkpoint_revision',
        'created_at', 'reason', 'generation_sha256')],
])
def test_generation_shape_rejects_invalid_revisions_and_missing_required_fields(generation_table, column, value):
    generation_table.execute('DROP TRIGGER immutable_weixin_peer_generations_update')
    with pytest.raises(sqlite3.IntegrityError):
        generation_table.execute('UPDATE weixin_peer_generations SET '+column+'=?', (value,))


@pytest.mark.parametrize('duplicate', ['generation', 'request_id', 'task_binding_id'])
def test_each_root_request_and_binding_has_one_generation(generation_table, duplicate):
    columns = [row[1] for row in generation_table.execute('PRAGMA table_info(weixin_peer_generations)')]
    values = list(generation_table.execute('SELECT * FROM weixin_peer_generations').fetchone())
    values[0], values[2], values[3], values[5] = 'other', 2, 'other-request', 'other-binding'
    values[columns.index(duplicate)] = {'generation':1, 'request_id':'request', 'task_binding_id':'binding'}[duplicate]
    values[8] = None if values[2] == 1 else 'prior-generation'
    if duplicate == 'task_binding_id':
        values[1] = 'other-mapping'
    with pytest.raises(sqlite3.IntegrityError):
        generation_table.execute('INSERT INTO weixin_peer_generations VALUES ('+','.join('?' for _ in values)+')', values)
    if duplicate != 'task_binding_id':
        values[1] = 'other-mapping'
        generation_table.execute('INSERT INTO weixin_peer_generations VALUES ('+','.join('?' for _ in values)+')', values)


def test_generation_foreign_keys_and_exact_fourteen_fields(generation_table):
    assert [row[1] for row in generation_table.execute('PRAGMA table_info(weixin_peer_generations)')] == [
        'id', 'root_mapping_id', 'generation', 'request_id', 'actor_id', 'task_binding_id',
        'scope_json', 'scope_sha256', 'previous_generation_sha256', 'previous_scope_sha256',
        'checkpoint_revision', 'created_at', 'reason', 'generation_sha256']
    actual = {(row[3], row[2], row[4]) for row in generation_table.execute('PRAGMA foreign_key_list(weixin_peer_generations)')}
    assert actual == {('root_mapping_id', 'weixin_peer_bindings', 'id'),
                      ('actor_id', 'users', 'id'), ('task_binding_id', 'task_channel_bindings', 'id')}


@pytest.mark.parametrize('generation,previous_hash', [(1, 'previous'), (2, None)])
def test_only_the_first_generation_has_no_previous_generation_hash(generation_table, generation, previous_hash):
    generation_table.execute('DROP TRIGGER immutable_weixin_peer_generations_update')
    with pytest.raises(sqlite3.IntegrityError):
        generation_table.execute('UPDATE weixin_peer_generations SET generation=?, previous_generation_sha256=?',
                                 (generation, previous_hash))


@pytest.mark.parametrize('allow_assistant', [False, True])
def test_backup_validates_empty_existing_families_in_the_generation_schema(tmp_path, allow_assistant):
    from cn_contract.ops.backup import _file_references
    database = Database('sqlite:///'+str(tmp_path/'empty.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.session() as db:
            assert _file_references(db, allow_assistant=allow_assistant) == []
    finally:
        database.engine.dispose()


@pytest.fixture
def native_grant_workspace(tmp_path, monkeypatch):
    from cn_contract.web import local_server
    root = tmp_path/'workspace'
    local_server.initialize_workspace(root, 'synthetic-lawyer', 'fiction123', data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('DROP TABLE IF EXISTS weixin_descriptor_generations')
        db.execute('DROP TABLE IF EXISTS weixin_peer_generations')
        db.commit()
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(db)
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-reauthorization-v1', native=True)
    (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    # Keep this historical crash-gap family at16->17; provenance tests cover17->18.
    from cn_contract.web import workspace_upgrade
    monkeypatch.setattr(workspace_upgrade, 'VERSIONS', storage_schema.VERSIONS[:17])
    monkeypatch.setattr(local_server, 'CURRENT_VERSION', TARGET)
    return root, marker


def test_native_upgrade_records_verified_backup_and_preserves_workspace_identity(native_grant_workspace):
    from cn_contract.web import local_server, workspace_upgrade
    root, marker = native_grant_workspace
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    receipt = json.loads((root/('upgrade-'+TARGET+'.json')).read_text('utf-8'))
    assert receipt['before_schema'] == marker['schema_sha256']
    assert receipt['workspace_id'] == marker['workspace_id']
    before = root/receipt['backup']
    assert hashlib.sha256(before.read_bytes()).hexdigest() == receipt['backup_sha256']
    with closing(sqlite3.connect(before)) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-reauthorization-v1', native=True)
        assert db.execute('SELECT id FROM local_workspace_identity').fetchall() == [(marker['workspace_id'],)]
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(TARGET, native=True)
        assert local_server._schema_hash(db) == receipt['after_schema']
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == receipt['after_schema']


@pytest.mark.parametrize('damage', [None, 'backup', 'receipt', 'trigger'])
def test_native_committed_ddl_marker_gap_accepts_only_intact_receipt(native_grant_workspace, monkeypatch, damage):
    from cn_contract.web import local_server, workspace_upgrade
    root, marker = native_grant_workspace
    original = workspace_upgrade._write_marker
    def fail(*args):
        raise OSError('synthetic marker write failure')
    monkeypatch.setattr(workspace_upgrade, '_write_marker', fail)
    with local_server._worker_lock(root), pytest.raises(OSError):
        workspace_upgrade.upgrade(root)
    monkeypatch.setattr(workspace_upgrade, '_write_marker', original)
    assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
    receipt_path = root/('upgrade-'+TARGET+'.json')
    receipt = json.loads(receipt_path.read_text('utf-8'))
    folders = list((root/'upgrade-backups').iterdir())
    if damage == 'backup':
        (root/receipt['backup']).write_bytes(b'synthetic corruption')
    elif damage == 'receipt':
        receipt_path.write_text(json.dumps(receipt|{'after_schema':'0'*64}), encoding='utf-8')
    elif damage == 'trigger':
        with closing(sqlite3.connect(root/'workbench.db')) as db:
            db.execute('DROP TRIGGER immutable_weixin_peer_generations_update')
    if damage:
        with pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
            local_server._open_workspace(root, data_parent=root.parent)
        assert json.loads((root/'workspace.json').read_text('utf-8')) == marker
    else:
        local_server._open_workspace(root, data_parent=root.parent)
        with local_server._worker_lock(root):
            workspace_upgrade.upgrade(root)
        assert list((root/'upgrade-backups').iterdir()) == folders
        assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256'] == receipt['after_schema']


def test_native_failed_generation_ddl_preserves_prior_schema_and_marker(native_grant_workspace, monkeypatch):
    from cn_contract.web import local_server, workspace_upgrade
    root, marker = native_grant_workspace
    original = workspace_upgrade.statements_for
    monkeypatch.setattr(workspace_upgrade, 'statements_for', lambda version:
        (*original(version), 'INVALID SQL') if version == TARGET else original(version))
    with local_server._worker_lock(root), pytest.raises(sqlite3.Error):
        workspace_upgrade.upgrade(root)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows('weixin-reauthorization-v1', native=True)
    assert json.loads((root/'workspace.json').read_text('utf-8')) == marker


def test_native_workspace_advances_two_versions_with_distinct_verified_receipts(tmp_path):
    from cn_contract.web import local_server,workspace_upgrade
    root=tmp_path/'two-step-workspace'
    local_server.initialize_workspace(root,'synthetic-lawyer','fiction123',data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        db.execute('DROP TABLE weixin_descriptor_generations')
        db.execute('DROP TABLE weixin_peer_generations');db.commit()
        marker=json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256']=local_server._schema_hash(db)
        assert schema_migrations.database_rows(db)==storage_schema.schema_rows('weixin-reauthorization-v1',native=True)
    (root/'workspace.json').write_text(json.dumps(marker),encoding='utf-8')
    with local_server._worker_lock(root):workspace_upgrade.upgrade(root)
    before=marker['schema_sha256']
    for version in (TARGET,CURRENT):
        receipt=json.loads((root/('upgrade-'+version+'.json')).read_text('utf-8'))
        assert receipt['workspace_id']==marker['workspace_id'] and receipt['before_schema']==before
        saved=root/receipt['backup']
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==receipt['backup_sha256']
        with closing(sqlite3.connect(saved)) as db:
            assert local_server._schema_hash(db)==before
        before=receipt['after_schema']
    with closing(sqlite3.connect(root/'workbench.db')) as db:
        assert schema_migrations.database_rows(db)==storage_schema.schema_rows(CURRENT,native=True)
        assert local_server._schema_hash(db)==before
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256']==before
