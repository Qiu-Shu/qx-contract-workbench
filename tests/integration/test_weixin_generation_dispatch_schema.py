"""Independent v19 cursor-slot constraint, frozen predecessors and native upgrade."""
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
from cn_contract.ops.backup import _file_references
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from cn_contract.weixin_inbox import dispatch_schema
from tests.integration.test_assistant_judge_schema import old_db


TARGET = 'weixin-generation-dispatch-v1'
PREVIOUS = 'weixin-target-provenance-v1'
INDEX = 'weixin_dispatch_binding_cursor'
SQL = 'CREATE UNIQUE INDEX weixin_dispatch_binding_cursor ON weixin_dispatch_receipts(task_binding_id,expected_task_cursor)'
FIXTURES = Path(__file__).parents[1]/'fixtures'
FROZEN = json.loads((FIXTURES/'weixin_generation_dispatch_schema_predecessors.json').read_text('utf-8'))


def extension():
    name = 'cn_contract.weixin_inbox.generation_dispatch_schema'
    assert importlib.util.find_spec(name) is not None, 'v19 needs the exact cursor-slot constraint'
    return importlib.import_module(name)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def test_fixture_keeps_all_thirty_four_old_entries_and_freezes_both_v18_variants():
    previous = json.loads((FIXTURES/'weixin_provenance_schema_predecessors.json').read_text('utf-8'))
    assert len(previous) == 34 and len(FROZEN) == 36 and FROZEN[:34] == previous
    assert [(item['version'], item['native']) for item in FROZEN[-2:]] == [(PREVIOUS, False), (PREVIOUS, True)]


@pytest.mark.parametrize('item', FROZEN, ids=lambda item:item['version']+('-native' if item['native'] else ''))
def test_all_eighteen_predecessors_keep_raw_and_normalized_fingerprints(item):
    rows = storage_schema.schema_rows(item['version'], native=item['native'])
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized']
    assert storage_schema.identify_schema(rows, native=item['native']) == item['version']


def test_v19_adds_only_the_useful_unique_binding_cursor_index():
    assert TARGET in storage_schema.VERSIONS
    index=storage_schema.VERSIONS.index(TARGET)
    assert storage_schema.VERSIONS[index-1:index+1] == (PREVIOUS, TARGET)
    before = set(storage_schema.schema_rows(PREVIOUS))
    after = set(storage_schema.schema_rows(TARGET))
    assert after-before == {('index', INDEX, 'weixin_dispatch_receipts', SQL)}
    assert before <= after
    assert extension().expected_objects() == [('index', INDEX, 'weixin_dispatch_receipts', SQL)]
    assert dispatch_schema.expected_objects() == [row for row in storage_schema.schema_rows('weixin-dispatch-v1')
        if row[2] == 'weixin_dispatch_receipts']


@pytest.mark.parametrize('version', ['pre-intake', PREVIOUS])
@pytest.mark.parametrize('native', [False, True])
def test_full_chain_and_immediate_predecessor_upgrade_preserve_user_rows(tmp_path, version, native):
    extension()
    with closing(old_db(tmp_path/'before.db', version, native)) as connection:
        connection.execute("INSERT INTO users VALUES ('synthetic-schema-user','original-user','unused','[]',0)")
        connection.commit()
        assert schema_migrations.upgrade_database(connection) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(connection) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION, native=native)
        assert connection.execute('SELECT username FROM users').fetchall() == [('original-user',)]
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert connection.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(connection) == storage_schema.CURRENT_VERSION


@pytest.mark.parametrize('native', [False, True])
def test_failed_index_step_rolls_back_schema_and_existing_rows(tmp_path, monkeypatch, native):
    extension()
    with closing(old_db(tmp_path/'before.db', PREVIOUS, native)) as connection:
        connection.execute("INSERT INTO users VALUES ('synthetic-schema-user','original-user','unused','[]',0)")
        connection.commit()
        before = schema_migrations.database_rows(connection)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version), 'INVALID GENERATION DISPATCH SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(connection)
        assert schema_migrations.database_rows(connection) == before
        assert connection.execute('SELECT username FROM users').fetchall() == [('original-user',)]
        assert not connection.in_transaction


def test_fresh_repeated_bootstrap_matches_upgrade_and_complete_native_family_validation(tmp_path):
    extension()
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with database.session() as records:
            assert _file_references(records) == []
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            actual = schema_migrations.database_rows(connection)
        assert actual == storage_schema.schema_rows(storage_schema.CURRENT_VERSION)
        with closing(old_db(tmp_path/'before.db', PREVIOUS, False)) as connection:
            assert schema_migrations.upgrade_database(connection) == storage_schema.CURRENT_VERSION
            assert schema_migrations.database_rows(connection) == actual
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('replacement', [
    'CREATE INDEX weixin_dispatch_binding_cursor ON weixin_dispatch_receipts(task_binding_id,expected_task_cursor)',
    'CREATE UNIQUE INDEX weixin_dispatch_binding_cursor ON weixin_dispatch_receipts(task_binding_id,next_task_cursor)',
    'CREATE INDEX untrusted_dispatch_index ON weixin_dispatch_receipts(created_at)',
])
def test_known_index_superset_does_not_accept_wrong_or_extra_objects(tmp_path, replacement):
    module = extension()
    database = Database('sqlite:///'+str(tmp_path/'altered.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as connection:
            if 'untrusted' not in replacement:
                connection.exec_driver_sql('DROP INDEX '+INDEX)
            connection.exec_driver_sql(replacement)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            before = schema_migrations.database_rows(connection)
        for initialize in (dispatch_schema.initialize_storage, module.initialize_storage):
            with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
                initialize(database)
        with closing(sqlite3.connect(database.engine.url.database)) as connection:
            assert schema_migrations.database_rows(connection) == before
    finally:
        database.engine.dispose()


def receipt(number, binding='synthetic-binding', cursor=0):
    return (f'receipt-{number}', f'descriptor-{number}', 'synthetic-account', 'synthetic-mapping',
            'synthetic-actor', binding, f'event-{number}', 'wx1:'+'a'*64, 'b'*64,
            cursor, cursor+1, '2026-10-25T00:00:00Z', 'c'*64)


def insert_receipt(connection, values):
    connection.execute('INSERT INTO weixin_dispatch_receipts VALUES ('+','.join('?' for _ in values)+')', values)


def test_distinct_sources_cannot_claim_one_target_slot_but_separate_targets_can():
    module = extension()
    with closing(sqlite3.connect(':memory:')) as connection:
        for statement in (*dispatch_schema.STATEMENTS, *module.STATEMENTS):
            connection.execute(statement)
        insert_receipt(connection, receipt(1))
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE constraint failed'):
            insert_receipt(connection, receipt(2))
        insert_receipt(connection, receipt(3, binding='another-synthetic-binding'))
        insert_receipt(connection, receipt(4, cursor=1))
        assert connection.execute('SELECT task_binding_id,expected_task_cursor FROM weixin_dispatch_receipts ORDER BY id').fetchall() == [
            ('synthetic-binding', 0), ('another-synthetic-binding', 0), ('synthetic-binding', 1)]


def test_index_creation_refuses_existing_overlapping_receipts_without_deleting_them():
    module = extension()
    with closing(sqlite3.connect(':memory:')) as connection:
        for statement in dispatch_schema.STATEMENTS:
            connection.execute(statement)
        insert_receipt(connection, receipt(1))
        insert_receipt(connection, receipt(2))
        connection.commit()
        before = connection.execute('SELECT * FROM weixin_dispatch_receipts ORDER BY id').fetchall()
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE constraint failed'):
            for statement in module.STATEMENTS:
                connection.execute(statement)
        assert connection.execute('SELECT * FROM weixin_dispatch_receipts ORDER BY id').fetchall() == before
        assert not connection.execute('SELECT 1 FROM sqlite_master WHERE name=?', (INDEX,)).fetchall()


def test_native_missing_version_index_is_rejected_before_any_repair(tmp_path):
    extension()
    from cn_contract.web import local_server
    root = tmp_path/'native'
    local_server.initialize_workspace(root, 'synthetic-lawyer', 'fiction123', data_parent=tmp_path)
    marker = (root/'workspace.json').read_bytes()
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        connection.execute('DROP TABLE assistant_followup_revisions')
        connection.execute('DROP TABLE assistant_evidence_revisions')
        connection.execute('DROP INDEX '+INDEX)
        connection.commit()
        from tests.helpers.legacy_material_model import downgrade_material_model
        downgrade_material_model(connection)
        assert schema_migrations.database_rows(connection) == storage_schema.schema_rows(PREVIOUS, native=True)
    before = (root/'workbench.db').read_bytes()
    with pytest.raises(ValueError, match='WORKSPACE_DATABASE_MISMATCH'):
        local_server._open_workspace(root, data_parent=tmp_path)
    assert (root/'workspace.json').read_bytes() == marker
    assert (root/'workbench.db').read_bytes() == before


def test_native_v18_upgrade_saves_old_structure_and_closes_marker_gap(tmp_path, monkeypatch):
    extension()
    from cn_contract.web import local_server, workspace_upgrade
    root = tmp_path/'native'
    local_server.initialize_workspace(root, 'synthetic-lawyer', 'fiction123', data_parent=tmp_path)
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        connection.execute('DROP TABLE assistant_followup_revisions')
        connection.execute('DROP TABLE assistant_evidence_revisions')
        connection.execute('DROP INDEX '+INDEX)
        connection.commit()
        from tests.helpers.legacy_material_model import downgrade_material_model
        downgrade_material_model(connection)
        marker = json.loads((root/'workspace.json').read_text('utf-8'))
        marker['schema_sha256'] = local_server._schema_hash(connection)
    (root/'workspace.json').write_text(json.dumps(marker), encoding='utf-8')
    original = workspace_upgrade._write_marker
    monkeypatch.setattr(workspace_upgrade, '_write_marker', lambda *args:
        (_ for _ in ()).throw(OSError('independent synthetic marker interruption')))
    with local_server._worker_lock(root), pytest.raises(OSError, match='marker interruption'):
        workspace_upgrade.upgrade(root)
    receipt_path = root/('upgrade-'+TARGET+'.json')
    saved_receipt = receipt_path.read_bytes()
    record = json.loads(saved_receipt)
    with closing(sqlite3.connect(root/record['backup'])) as connection:
        assert schema_migrations.database_rows(connection) == storage_schema.schema_rows(PREVIOUS, native=True)
    assert hashlib.sha256((root/record['backup']).read_bytes()).hexdigest() == record['backup_sha256']
    monkeypatch.setattr(workspace_upgrade, '_write_marker', original)
    with local_server._worker_lock(root):
        workspace_upgrade.upgrade(root)
    assert receipt_path.read_bytes() == saved_receipt
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        assert schema_migrations.database_rows(connection) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION, native=True)
        assert local_server._schema_hash(connection) == json.loads((root/'workspace.json').read_text('utf-8'))['schema_sha256']
