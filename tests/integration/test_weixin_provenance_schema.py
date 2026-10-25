"""Independent additive provenance DDL, historical fingerprints and native recovery."""
from contextlib import closing
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db


TARGET='weixin-target-provenance-v1'
CURRENT=storage_schema.CURRENT_VERSION
TABLE='weixin_descriptor_generations'
FIXTURES=Path(__file__).parents[1]/'fixtures'
FROZEN=json.loads((FIXTURES/'weixin_provenance_schema_predecessors.json').read_text('utf-8'))
PREVIOUS=tuple(item['version'] for item in FROZEN if not item['native'])
COLUMNS=('descriptor_id','generation_id','generation_sha256','task_binding_id',
    'scope_sha256','payload_sha256','provenance_sha256')
VALUES=('10000000-0000-4000-8000-000000000001','20000000-0000-4000-8000-000000000001',
    'a'*64,'30000000-0000-4000-8000-000000000001','b'*64,'c'*64,'d'*64)


def schema():
    name='cn_contract.weixin_inbox.provenance_schema'
    assert importlib.util.find_spec(name) is not None, 'D2g5b needs immutable additive provenance DDL'
    return importlib.import_module(name)


def digest(rows):
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def update_trigger(connection):
    return connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=? "
        "AND upper(sql) LIKE '%BEFORE UPDATE%'",(TABLE,)).fetchone()[0]


@pytest.mark.parametrize('item',FROZEN,ids=lambda item:item['version']+('-native' if item['native'] else ''))
def test_all_seventeen_predecessors_keep_independently_frozen_structure(item):
    rows=storage_schema.schema_rows(item['version'],native=item['native'])
    assert digest(rows)==item['raw']
    assert digest(storage_schema.normalized_schema(item['version'],native=item['native']))==item['normalized']
    assert storage_schema.identify_schema(rows,native=item['native'])==item['version']


def test_fixture_preserves_original_thirty_two_and_adds_only_generation_predecessor():
    original=json.loads((FIXTURES/'weixin_generation_schema_predecessors.json').read_text('utf-8'))
    assert len(original)==32 and len(FROZEN)==34 and FROZEN[:32]==original
    assert [(row['version'],row['native']) for row in FROZEN[32:]]==[
        ('weixin-generations-v1',False),('weixin-generations-v1',True)]


def test_provenance_is_one_additive_family_without_rewriting_generation_schema():
    assert storage_schema.VERSIONS[:len(PREVIOUS)+1]==PREVIOUS+(TARGET,)
    before=set(storage_schema.schema_rows('weixin-generations-v1'))
    after=set(storage_schema.schema_rows(TARGET))
    assert before<after and {row[2] for row in after-before}=={TABLE}


@pytest.mark.parametrize('version',PREVIOUS)
@pytest.mark.parametrize('native',[False,True])
def test_every_predecessor_upgrades_and_repeats_without_losing_prior_user_rows(tmp_path,version,native):
    with closing(old_db(tmp_path/'old.db',version,native)) as connection:
        connection.execute("INSERT INTO users VALUES ('synthetic-schema-user','old-schema-user','unused','[]',0)")
        connection.commit()
        assert schema_migrations.upgrade_database(connection)==CURRENT
        assert schema_migrations.database_rows(connection)==storage_schema.schema_rows(CURRENT,native=native)
        assert connection.execute('SELECT username FROM users').fetchall()==[('old-schema-user',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert connection.execute('PRAGMA foreign_keys').fetchone()==(1,)
        assert schema_migrations.upgrade_database(connection)==CURRENT


@pytest.mark.parametrize('native',[False,True])
def test_provenance_ddl_failure_rolls_back_added_objects_and_preserves_old_data(tmp_path,monkeypatch,native):
    schema()
    with closing(old_db(tmp_path/'old.db','weixin-generations-v1',native)) as connection:
        connection.execute("INSERT INTO users VALUES ('synthetic-schema-user','old-schema-user','unused','[]',0)")
        connection.commit();before=schema_migrations.database_rows(connection)
        original=schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations,'statements_for',lambda version:
            (*original(version),'INVALID PROVENANCE SQL') if version==TARGET else original(version))
        with pytest.raises(sqlite3.Error):schema_migrations.upgrade_database(connection)
        assert schema_migrations.database_rows(connection)==before
        assert connection.execute('SELECT username FROM users').fetchall()==[('old-schema-user',)]
        assert not connection.in_transaction


def test_unknown_schema_is_not_repaired_or_upgraded(tmp_path):
    with closing(old_db(tmp_path/'old.db','weixin-generations-v1',False)) as connection:
        connection.execute('CREATE TABLE untrusted_provenance_state(id TEXT)');connection.commit()
        before=schema_migrations.database_rows(connection)
        with pytest.raises(ValueError,match='DATABASE_SCHEMA_MISMATCH'):
            schema_migrations.upgrade_database(connection)
        assert schema_migrations.database_rows(connection)==before


def test_fresh_repeated_initialization_matches_upgraded_exact_structure(tmp_path):
    schema();database=Database('sqlite:///'+str(tmp_path/'fresh.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database);initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            actual=schema_migrations.database_rows(connection)
        assert actual==storage_schema.schema_rows(CURRENT)
        with closing(old_db(tmp_path/'old.db','weixin-generations-v1',False)) as connection:
            assert schema_migrations.upgrade_database(connection)==CURRENT
            assert schema_migrations.database_rows(connection)==actual
    finally:database.engine.dispose()


@pytest.mark.parametrize('damage',['trigger','column','index'])
def test_partial_provenance_schema_cannot_be_silently_repaired(tmp_path,damage):
    module=schema();database=Database('sqlite:///'+str(tmp_path/'partial.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as connection:
            if damage=='trigger':
                name=connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND tbl_name=? AND upper(sql) LIKE '%BEFORE UPDATE%'",(TABLE,)).scalar_one()
                connection.exec_driver_sql('DROP TRIGGER '+name)
            else:
                connection.exec_driver_sql('ALTER TABLE '+TABLE+' ADD COLUMN untrusted TEXT' if damage=='column'
                    else 'CREATE INDEX unexpected_provenance_index ON '+TABLE+'(generation_id)')
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            before=schema_migrations.database_rows(connection)
        with pytest.raises(ValueError,match='DATABASE_SCHEMA_MISMATCH'):module.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            assert schema_migrations.database_rows(connection)==before
    finally:database.engine.dispose()


def table():
    module=schema();connection=sqlite3.connect(':memory:')
    connection.execute('PRAGMA foreign_keys=ON')
    for parent,identifier in [('weixin_inbox_descriptors',VALUES[0]),('weixin_peer_generations',VALUES[1]),
            ('task_channel_bindings',VALUES[3])]:
        connection.execute('CREATE TABLE '+parent+'(id TEXT PRIMARY KEY NOT NULL)')
        connection.execute('INSERT INTO '+parent+' VALUES(?)',(identifier,))
    for statement in module.STATEMENTS:connection.execute(statement)
    connection.execute('INSERT INTO '+TABLE+' VALUES('+','.join('?' for _ in VALUES)+')',VALUES)
    return connection


def test_seven_fields_exact_primary_key_and_three_real_foreign_keys():
    with closing(table()) as connection:
        columns=connection.execute('PRAGMA table_info('+TABLE+')').fetchall()
        assert tuple(row[1] for row in columns)==COLUMNS
        assert [row[1] for row in columns if row[5]]==['descriptor_id']
        assert {(row[3],row[2],row[4]) for row in connection.execute('PRAGMA foreign_key_list('+TABLE+')')}=={
            ('descriptor_id','weixin_inbox_descriptors','id'),('generation_id','weixin_peer_generations','id'),
            ('task_binding_id','task_channel_bindings','id')}
        assert connection.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('operation',['UPDATE','DELETE'])
def test_provenance_cannot_be_changed_or_deleted(operation):
    with closing(table()) as connection,pytest.raises(sqlite3.IntegrityError,match='IMMUTABLE_RECORD'):
        connection.execute('UPDATE '+TABLE+" SET scope_sha256='changed'" if operation=='UPDATE' else 'DELETE FROM '+TABLE)


@pytest.mark.parametrize('field',COLUMNS)
def test_every_provenance_field_is_required_even_with_update_trigger_disabled(field):
    with closing(table()) as connection:
        connection.execute('DROP TRIGGER '+update_trigger(connection))
        with pytest.raises(sqlite3.IntegrityError):connection.execute('UPDATE '+TABLE+' SET '+field+'=NULL')


def test_each_descriptor_can_have_only_one_provenance_row():
    with closing(table()) as connection,pytest.raises(sqlite3.IntegrityError):
        connection.execute('INSERT INTO '+TABLE+' VALUES('+','.join('?' for _ in VALUES)+')',VALUES)


@pytest.mark.parametrize('field',['descriptor_id','generation_id','task_binding_id'])
def test_missing_parent_is_rejected_by_sqlite_foreign_key_enforcement(field):
    with closing(table()) as connection:
        values=list(VALUES);values[0]='40000000-0000-4000-8000-000000000001'
        if field!='descriptor_id':connection.execute('INSERT INTO weixin_inbox_descriptors VALUES(?)',(values[0],))
        values[COLUMNS.index(field)]='50000000-0000-4000-8000-000000000001'
        with pytest.raises(sqlite3.IntegrityError,match='FOREIGN KEY'):
            connection.execute('INSERT INTO '+TABLE+' VALUES('+','.join('?' for _ in values)+')',values)


@pytest.mark.parametrize('allowed',[False,True])
def test_empty_current_schema_passes_all_registered_backup_family_checks(tmp_path,allowed):
    schema()
    from cn_contract.ops.backup import _file_references
    database=Database('sqlite:///'+str(tmp_path/'empty.db'),tmp_path/'protected',load_settings())
    try:
        initialize_storage(database)
        with database.session() as db:assert _file_references(db,allow_assistant=allowed)==[]
    finally:database.engine.dispose()


def native_predecessor(tmp_path,monkeypatch):
    from cn_contract.web import local_server
    root=tmp_path/'独立虚构来源升级'
    local_server.initialize_workspace(root,'synthetic-schema-lawyer','fiction123',data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        connection.execute('DROP INDEX weixin_dispatch_binding_cursor')
        connection.execute('DROP TABLE IF EXISTS '+TABLE);connection.commit()
        marker=json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256']=local_server._schema_hash(connection)
        assert schema_migrations.database_rows(connection)==storage_schema.schema_rows('weixin-generations-v1',native=True)
    (root/'workspace.json').write_text(json.dumps(marker),encoding='utf-8')
    from cn_contract.web import workspace_upgrade
    monkeypatch.setattr(workspace_upgrade,'VERSIONS',storage_schema.VERSIONS[:18])
    monkeypatch.setattr(local_server,'CURRENT_VERSION',TARGET)
    return root,marker


def test_native_upgrade_saves_verified_predecessor_and_preserves_workspace_identity(tmp_path,monkeypatch):
    schema()
    from cn_contract.web import local_server,workspace_upgrade
    root,marker=native_predecessor(tmp_path,monkeypatch)
    with local_server._worker_lock(root):workspace_upgrade.upgrade(root)
    receipt=json.loads((root/('upgrade-'+TARGET+'.json')).read_text('utf-8'))
    assert receipt['before_schema']==marker['schema_sha256'] and receipt['workspace_id']==marker['workspace_id']
    saved=root/receipt['backup'];assert hashlib.sha256(saved.read_bytes()).hexdigest()==receipt['backup_sha256']
    with closing(sqlite3.connect(saved)) as connection:
        assert schema_migrations.database_rows(connection)==storage_schema.schema_rows('weixin-generations-v1',native=True)
        assert connection.execute('SELECT id FROM local_workspace_identity').fetchall()==[(marker['workspace_id'],)]
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        assert schema_migrations.database_rows(connection)==storage_schema.schema_rows(TARGET,native=True)
        assert local_server._schema_hash(connection)==receipt['after_schema']
    assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256']==receipt['after_schema']


@pytest.mark.parametrize('damage',[None,'backup','receipt','trigger'])
def test_native_committed_ddl_marker_gap_accepts_only_verified_provenance_delta(tmp_path,monkeypatch,damage):
    schema()
    from cn_contract.web import local_server,workspace_upgrade
    root,marker=native_predecessor(tmp_path,monkeypatch);write_marker=workspace_upgrade._write_marker
    def interrupted(*args):raise OSError('independent synthetic marker write interruption')
    monkeypatch.setattr(workspace_upgrade,'_write_marker',interrupted)
    with local_server._worker_lock(root),pytest.raises(OSError):workspace_upgrade.upgrade(root)
    monkeypatch.setattr(workspace_upgrade,'_write_marker',write_marker)
    assert json.loads((root/'workspace.json').read_text('utf-8'))==marker
    receipt_path=root/('upgrade-'+TARGET+'.json');receipt=json.loads(receipt_path.read_text('utf-8'))
    backups=list((root/'upgrade-backups').iterdir())
    if damage=='backup':(root/receipt['backup']).write_bytes(b'independent synthetic corrupt backup')
    elif damage=='receipt':receipt_path.write_text(json.dumps(receipt|{'after_schema':'0'*64}),encoding='utf-8')
    elif damage=='trigger':
        with closing(sqlite3.connect(root/'workbench.db')) as connection:
            connection.execute('DROP TRIGGER '+update_trigger(connection))
    if damage:
        with pytest.raises(ValueError,match='WORKSPACE_DATABASE_MISMATCH'):
            local_server._open_workspace(root,data_parent=root.parent)
        assert json.loads((root/'workspace.json').read_text('utf-8'))==marker
    else:
        local_server._open_workspace(root,data_parent=root.parent)
        with local_server._worker_lock(root):workspace_upgrade.upgrade(root)
        assert list((root/'upgrade-backups').iterdir())==backups
        assert json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256']==receipt['after_schema']


def test_native_failed_ddl_preserves_predecessor_schema_and_marker(tmp_path,monkeypatch):
    schema()
    from cn_contract.web import local_server,workspace_upgrade
    root,marker=native_predecessor(tmp_path,monkeypatch);original=workspace_upgrade.statements_for
    monkeypatch.setattr(workspace_upgrade,'statements_for',lambda version:
        (*original(version),'INVALID PROVENANCE SQL') if version==TARGET else original(version))
    with local_server._worker_lock(root),pytest.raises(sqlite3.Error):workspace_upgrade.upgrade(root)
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        assert schema_migrations.database_rows(connection)==storage_schema.schema_rows('weixin-generations-v1',native=True)
    assert json.loads((root/'workspace.json').read_text('utf-8'))==marker
