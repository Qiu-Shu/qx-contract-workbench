"""Frozen predecessors and exact additive followup snapshot storage."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from test_assistant_routes import native, sign_in
from test_evidence_worksheet import begin, statement, request

FROZEN = json.loads((Path(__file__).parents[1]/'fixtures/followup_schema_predecessors.json').read_text())
TARGET = 'assistant-followups-v1'
TABLE = 'assistant_followup_revisions'
COLUMNS = ('conversation_id', 'revision', 'request_id', 'request_json', 'request_sha256',
           'snapshot_json', 'snapshot_sha256', 'actor_id', 'session_id', 'created_at')
VALUES = ('synthetic-conversation', 1, 'synthetic-request', '{}', 'request-hash', '{}',
          'snapshot-hash', 'synthetic-actor', 'synthetic-session', '2026-10-26T00:00:00Z')


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def extension():
    from cn_contract.assistant import followup_schema
    return followup_schema


def current_table():
    connection = sqlite3.connect(':memory:')
    connection.execute('PRAGMA foreign_keys=ON')
    for table in ('assistant_conversations', 'users', 'sessions'):
        connection.execute('CREATE TABLE '+table+' (id TEXT PRIMARY KEY)')
    for table, value in (('assistant_conversations', VALUES[0]), ('users', VALUES[7]), ('sessions', VALUES[8])):
        connection.execute('INSERT INTO '+table+' VALUES (?)', (value,))
    for sql in extension().STATEMENTS:
        connection.execute(sql)
    connection.execute('INSERT INTO '+TABLE+' VALUES ('+','.join('?' for _ in VALUES)+')', VALUES)
    return connection


@pytest.mark.parametrize('item', FROZEN)
def test_all_40_predecessor_structures_are_unchanged(item):
    assert digest(storage_schema.schema_rows(item['version'], native=item['native'])) == item['schema_sha256']
    assert digest(storage_schema.normalized_schema(item['version'], native=item['native'])) == item['normalized_sha256']


def test_followups_append_only_the_snapshot_family_to_v20():
    assert len(FROZEN) == 40
    assert storage_schema.VERSIONS[-2:] == ('assistant-evidence-v1', TARGET)
    before = set(storage_schema.schema_rows('assistant-evidence-v1'))
    after = set(storage_schema.schema_rows(TARGET))
    assert before < after
    assert {row[2] for row in after-before} == {TABLE}


@pytest.mark.parametrize('native_mode', [False, True])
def test_exact_v20_additive_upgrade(native_mode):
    with closing(sqlite3.connect(':memory:')) as connection:
        before = storage_schema.schema_rows('assistant-evidence-v1', native=native_mode)
        for kind in ('table', 'index', 'trigger'):
            for row in before:
                if row[0] == kind and row[3] is not None:
                    connection.execute(row[3])
        connection.commit()
        assert schema_migrations.database_rows(connection) == before
        assert schema_migrations.upgrade_database(connection) == TARGET
        assert storage_schema.identify_schema(schema_migrations.database_rows(connection), native=native_mode) == TARGET
        assert connection.execute('SELECT count(*) FROM '+TABLE).fetchone() == (0,)
        assert connection.execute('PRAGMA foreign_key_check').fetchall() == []
        schema_migrations.upgrade_database(connection)
        assert schema_migrations.database_rows(connection) == storage_schema.schema_rows(TARGET, native=native_mode)


def test_bootstrap_matches_current_catalog_and_is_idempotent(tmp_path):
    from cn_contract.config import load_settings
    from cn_contract.persistence import Database
    from cn_contract.storage_bootstrap import initialize_storage
    database = Database('sqlite:///'+str(tmp_path/'bootstrap.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        initialize_storage(database)
        with database.engine.connect() as db:
            rows = [tuple(r) for r in db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        assert storage_schema.identify_schema(rows) == TARGET
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage', ['unknown', 'missing_trigger', 'partial_table'])
def test_unknown_and_partial_followup_structures_reject_upgrade(damage):
    with closing(sqlite3.connect(':memory:')) as connection:
        for kind in ('table', 'index', 'trigger'):
            for row in storage_schema.schema_rows(TARGET):
                if row[0] == kind and row[3] is not None:
                    connection.execute(row[3])
        connection.execute({'unknown': 'CREATE TABLE future_followup (id TEXT)',
                            'missing_trigger': 'DROP TRIGGER immutable_'+TABLE+'_update',
                            'partial_table': 'ALTER TABLE '+TABLE+' ADD COLUMN future TEXT'}[damage])
        connection.commit()
        before = schema_migrations.database_rows(connection)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            storage_schema.identify_schema(before)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            schema_migrations.upgrade_database(connection)
        assert schema_migrations.database_rows(connection) == before


@pytest.mark.parametrize('operation', ['UPDATE', 'DELETE'])
def test_followup_snapshots_are_immutable(operation):
    with closing(current_table()) as connection, pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        connection.execute('UPDATE '+TABLE+' SET revision=2' if operation == 'UPDATE' else 'DELETE FROM '+TABLE)


@pytest.mark.parametrize('field', COLUMNS)
def test_all_followup_fields_are_required(field):
    with closing(current_table()) as connection:
        connection.execute('DROP TRIGGER immutable_'+TABLE+'_update')
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('UPDATE '+TABLE+' SET '+field+'=NULL')


@pytest.mark.parametrize('field', ['request_json', 'snapshot_json'])
def test_followup_json_size_is_bounded(field):
    with closing(current_table()) as connection:
        values = list(VALUES); values[1] = 2; values[2] = 'next-request'
        values[COLUMNS.index(field)] = 'x'*2097152
        connection.execute('INSERT INTO '+TABLE+' VALUES ('+','.join('?' for _ in values)+')', values)
        values[1] = 3; values[2] = 'oversize-request'; values[COLUMNS.index(field)] += 'x'
        with pytest.raises(sqlite3.IntegrityError, match='CHECK constraint failed'):
            connection.execute('INSERT INTO '+TABLE+' VALUES ('+','.join('?' for _ in values)+')', values)


@pytest.mark.parametrize('field,value', [('revision', 0), ('revision', -1), ('revision', 1.5),
                                         ('revision', 1), ('request_id', VALUES[2]),
                                         ('conversation_id', 'missing'), ('actor_id', 'missing'), ('session_id', 'missing')])
def test_revision_idempotency_and_foreign_keys(field, value):
    with closing(current_table()) as connection:
        values = list(VALUES); values[1] = 2; values[2] = 'next-request'
        values[COLUMNS.index(field)] = value
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute('INSERT INTO '+TABLE+' VALUES ('+','.join('?' for _ in values)+')', values)


def test_native_v20_upgrade_preserves_saved_evidence_and_identity(native):
    from fastapi.testclient import TestClient
    from cn_contract.web import local_server
    app, root = native; database = app.state.database
    with TestClient(app) as client:
        headers = sign_in(client); base, url = begin(client, headers)
        fact = statement(client, headers, base, url)
        response = client.post(url+'/commits', headers=headers, json=request(client.get(url).json(), [fact]))
        assert response.status_code == 200, response.text
        receipt = response.json()
    database.engine.dispose()
    with closing(sqlite3.connect(root/'workbench.db')) as connection:
        saved = connection.execute('SELECT * FROM assistant_evidence_revisions').fetchall()
        connection.execute('DROP TABLE '+TABLE)
        connection.commit()
        rows = schema_migrations.database_rows(connection)
        assert storage_schema.identify_schema(rows, native=True) == 'assistant-evidence-v1'
    marker = json.loads((root/'workspace.json').read_text())
    marker['schema_sha256'] = digest(rows)
    (root/'workspace.json').write_text(json.dumps(marker))
    recovered = local_server.build_local_app(root, data_parent=root.parent.parent)
    try:
        assert list((root/'upgrade-backups').glob('assistant-followups-*/before.db'))
        assert json.loads((root/'workspace.json').read_text())['workspace_id'] == marker['workspace_id']
        with closing(sqlite3.connect(root/'workbench.db')) as connection:
            assert connection.execute('SELECT * FROM assistant_evidence_revisions').fetchall() == saved
            assert storage_schema.identify_schema(schema_migrations.database_rows(connection), native=True) == TARGET
        with TestClient(recovered) as client:
            sign_in(client)
            assert client.get(url).json()['rows'] == [fact]
            assert client.get(url+'/receipts/'+receipt['request_id']).json() == receipt
    finally:
        recovered.state.database.engine.dispose()
