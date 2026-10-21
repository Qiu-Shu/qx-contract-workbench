"""assistant-rounds-v1/v2: attempts rebuilds with immutable bounded round occupancy.

B2c1 ships the round-ledger structure; B2c2 widens input_format for the
library-context-v2 tool-plan wire via a second fixed rebuild (rounds-v2) and
defines the multi-round semantics opened by it.
"""
from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db

PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1',
            'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1',
            'assistant-context-v1', 'assistant-rounds-v1')
# Frozen exact rows of older versions; the rounds slices must not move them.
HISTORICAL = {
    ('assistant-context-v1', False): '05948e37eb270d809a5875637891ae2bbe157c3e13f723833b0a99622152b404',
    ('assistant-context-v1', True): '501259f33c2563ca7583661e467a1d5022631c982534ece5ca8c561f95b73182',
    ('assistant-rounds-v1', False): '80dc678f24b8de142ee4909d2b8981a18ee29afbd8e866322f0e8132d28268a9',
    ('assistant-rounds-v1', True): 'a7a84afcdd7958d1995af241e447de7d04cae518044b2f50a2e5159c77f34c18',
}

_SHA_C = 'c' * 64
_SHA_D = 'd' * 64
_SHA_E = 'e' * 64
_SHA_F = 'f' * 64
_SHA_0 = '0' * 64
_SHA_1 = '1' * 64
_TOKEN_A = 'a' * 64
_TOKEN_B = 'b' * 64

_ATTEMPT_COLUMNS = ('id', 'run_id', 'conversation_id', 'policy_id', 'config_sha256',
                    'policy_sha256', 'request_sha256', 'input_json', 'config_json',
                    'policy_json', 'reserved_usd', 'created_at', 'state', 'updated_at',
                    'input_format')


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _seed_attempt_chain(db):
    """Minimal synthetic model family with one received attempt and children."""
    execute = db.execute if isinstance(db, sqlite3.Connection) else db.exec_driver_sql
    execute("INSERT INTO users VALUES ('u1','rounds-user','not-a-real-password','[]',0)")
    execute("INSERT INTO sessions VALUES ('s1','u1','" + _TOKEN_A + "','" + _TOKEN_B +
               "','2030-01-01T00:00:00+00:00',0)")
    execute("INSERT INTO assistant_conversations "
               "(id,workspace_id,owner_id,request_id,request_sha256,scope_kind,scope_ref,"
               "binding_revision,input_revision,materials_revision,composer_revision,"
               "projection_intake_id,display_title,draft_input,created_at,archived_at) "
               "VALUES ('c1','w1','u1','r1','" + _SHA_C + "','conversation',NULL,1,1,0,0,"
               "NULL,'t','d','2026-01-01T00:00:00+00:00',NULL)")
    execute("INSERT INTO assistant_messages VALUES "
               "('m1','c1','user','synthetic question','2026-01-01T00:00:01+00:00',1)")
    execute("INSERT INTO assistant_runs "
               "(id,conversation_id,message_id,actor_id,session_id,request_id,request_sha256,"
               "scope_snapshot,state,requested_skill,selected_provider,selected_model,budget_json,"
               "cancel_requested,created_at) "
               "VALUES ('run1','c1','m1','u1','s1','req1','" + _SHA_D + "','{}','completed',NULL,"
               "'deepseek','deepseek-flash','{}',0,'2026-01-01T00:00:01+00:00')")
    execute("INSERT INTO assistant_model_attempts "
               "(id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,"
               "input_json,config_json,policy_json,reserved_usd,created_at,state,updated_at,input_format) "
               "VALUES ('a1','run1','c1','p1','" + _SHA_E + "','" + _SHA_F + "','" + _SHA_0 + "',"
               "'{}','{}','{}','0.01','2026-01-01T00:00:02+00:00','received',"
               "'2026-01-01T00:00:03+00:00','plain-text-v1')")
    execute("INSERT INTO assistant_model_receipts VALUES "
               "('a1','{}','2026-01-01T00:00:03+00:00')")
    execute("INSERT INTO assistant_model_outputs VALUES "
               "('o1','a1','c1','run1','{}','{}','2026-01-01T00:00:03+00:00')")
    db.commit()


def _attempt_row(identifier, round_no):
    return {'id': identifier, 'run_id': 'run1', 'conversation_id': 'c1', 'policy_id': 'p1',
            'config_sha256': _SHA_E, 'policy_sha256': _SHA_F, 'request_sha256': _SHA_1,
            'input_json': '{}', 'config_json': '{}', 'policy_json': '{}', 'reserved_usd': '0.01',
            'created_at': '2026-01-01T00:00:02+00:00', 'state': 'received',
            'updated_at': '2026-01-01T00:00:03+00:00', 'input_format': 'plain-text-v1',
            'round_no': round_no}


def test_rounds_is_current_and_keeps_every_older_version():
    assert storage_schema.CURRENT_VERSION == 'assistant-rounds-v2'
    assert storage_schema.VERSIONS == PREVIOUS + ('assistant-rounds-v2',)
    for version in PREVIOUS:
        for native in (False, True):
            rows = storage_schema.schema_rows(version, native=native)
            assert storage_schema.identify_schema(rows, native=native) == version


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('version', ['assistant-context-v1', 'assistant-rounds-v1'])
def test_older_context_structures_are_frozen(version, native):
    rows = storage_schema.schema_rows(version, native=native)
    assert digest(rows) == HISTORICAL[(version, native)]


def test_rounds_v1_rebuilds_only_the_attempts_table_and_input_trigger():
    previous = set(storage_schema.schema_rows('assistant-context-v1'))
    current = set(storage_schema.schema_rows('assistant-rounds-v1'))
    changed = {row[2] for row in current - previous} | {row[2] for row in previous - current}
    assert changed == {'assistant_model_attempts'}
    assert {row[1] for row in previous - current} == {
        'assistant_model_attempts', 'immutable_assistant_model_input'}
    assert {row[1] for row in current - previous} == {
        'assistant_model_attempts', 'immutable_assistant_model_input'}
    attempts = next(row for row in current if row[0] == 'table' and row[1] == 'assistant_model_attempts')
    assert 'round_no' in attempts[3] and 'UNIQUE(run_id, round_no)' in attempts[3]
    assert 'UNIQUE' not in attempts[3].replace('UNIQUE(run_id, round_no)', '')
    trigger = next(row for row in current if row[1] == 'immutable_assistant_model_input')
    assert 'round_no' in trigger[3]
    # The rebuilt claim and delete triggers keep the frozen V1 bytes.
    for name in ('immutable_assistant_model_claim', 'immutable_assistant_model_attempts_delete'):
        assert next(row for row in current if row[1] == name) == next(
            row for row in previous if row[1] == name)


def test_rounds_v2_widens_only_the_input_format_check():
    previous = set(storage_schema.schema_rows('assistant-rounds-v1'))
    current = set(storage_schema.schema_rows('assistant-rounds-v2'))
    # Exactly one object changes: the attempts table CHECK text.
    assert {row[1] for row in current - previous} == {'assistant_model_attempts'}
    assert {row[1] for row in previous - current} == {'assistant_model_attempts'}
    attempts = next(row for row in current if row[0] == 'table' and row[1] == 'assistant_model_attempts')
    assert "'library-context-v2'" in attempts[3]
    before = next(row for row in previous if row[0] == 'table' and row[1] == 'assistant_model_attempts')
    assert "'library-context-v2'" not in before[3]
    assert attempts[3].replace(", 'library-context-v2'", '') == before[3]


@pytest.mark.parametrize('native', [False, True])
def test_context_with_model_rows_rebuilds_preserving_every_row(tmp_path, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-context-v1', native)) as db:
        _seed_attempt_chain(db)
        before_attempts = db.execute('SELECT * FROM assistant_model_attempts').fetchall()
        before_receipts = db.execute('SELECT * FROM assistant_model_receipts').fetchall()
        before_outputs = db.execute('SELECT * FROM assistant_model_outputs').fetchall()
        assert schema_migrations.upgrade_database(db) == 'assistant-rounds-v2'
        after_attempts = db.execute('SELECT * FROM assistant_model_attempts').fetchall()
        # Every attempt row survives in column order with round_no appended as 1.
        assert after_attempts == [tuple(row) + (1,) for row in before_attempts]
        assert db.execute('SELECT * FROM assistant_model_receipts').fetchall() == before_receipts
        assert db.execute('SELECT * FROM assistant_model_outputs').fetchall() == before_outputs
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert schema_migrations.database_rows(db) == [tuple(row) for row in
            storage_schema.schema_rows('assistant-rounds-v2', native=native)]
        assert schema_migrations.upgrade_database(db) == 'assistant-rounds-v2'


@pytest.mark.parametrize('native', [False, True])
def test_rounds_v1_rows_rebuild_preserving_multi_round_occupancy(tmp_path, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-rounds-v1', native)) as db:
        _seed_attempt_chain(db)
        # A structurally occupied second round survives the v1 -> v2 rebuild.
        keys = tuple(_attempt_row('a2', 2))
        db.execute('INSERT INTO assistant_model_attempts (' + ','.join(keys) + ') VALUES ('
                   + ','.join(':' + key for key in keys) + ')', _attempt_row('a2', 2))
        db.commit()
        before = db.execute('SELECT * FROM assistant_model_attempts ORDER BY round_no').fetchall()
        assert schema_migrations.upgrade_database(db) == 'assistant-rounds-v2'
        assert db.execute('SELECT * FROM assistant_model_attempts ORDER BY round_no').fetchall() == before
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert schema_migrations.database_rows(db) == [tuple(row) for row in
            storage_schema.schema_rows('assistant-rounds-v2', native=native)]
        # The widened CHECK admits the v2 wire and still rejects unknown formats.
        row = dict(_attempt_row('a3', 3), input_format='library-context-v2')
        db.execute('INSERT INTO assistant_model_attempts (' + ','.join(tuple(row)) + ') VALUES ('
                   + ','.join(':' + key for key in row) + ')', row)
        db.commit()
        bad = dict(_attempt_row('a4', 4), input_format='library-context-v3')
        with pytest.raises(Exception, match='CHECK'):
            db.execute('INSERT INTO assistant_model_attempts (' + ','.join(tuple(bad)) + ') VALUES ('
                       + ','.join(':' + key for key in bad) + ')', bad)
        db.rollback()


@pytest.mark.parametrize('target', ['assistant-rounds-v1', 'assistant-rounds-v2'])
@pytest.mark.parametrize('failure', ['drop_trigger', 'create', 'insert', 'drop_table',
                                     'rename', 'trigger_input', 'trigger_claim', 'trigger_delete'])
def test_rounds_step_partial_failure_leaves_no_half_rebuild(tmp_path, monkeypatch, failure, target):
    with closing(old_db(tmp_path/'old.db', 'assistant-context-v1', False)) as db:
        _seed_attempt_chain(db)
        before = schema_migrations.database_rows(db)
        before_data = db.execute('SELECT * FROM assistant_model_attempts').fetchall()
        index = {'drop_trigger': 0, 'create': 3, 'insert': 4, 'drop_table': 5,
                 'rename': 6, 'trigger_input': 7, 'trigger_claim': 8, 'trigger_delete': 9}[failure]
        actual = schema_migrations.statements_for
        def faulty(version):
            statements = actual(version)
            if version != target:
                return statements
            return statements[:index] + ('INVALID SQL',) + statements[index + 1:]
        monkeypatch.setattr(schema_migrations, 'statements_for', faulty)
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert db.execute('SELECT * FROM assistant_model_attempts').fetchall() == before_data
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert not db.in_transaction
        # Enforcement is restored even after the failed FK OFF window.
        assert db.execute('PRAGMA foreign_keys').fetchall() == [(1,)]


@pytest.mark.parametrize('damage', ['trigger_claim', 'trigger_delete', 'old_trigger',
                                    'extra_index'])
def test_partial_or_modified_rounds_schema_is_not_repaired(tmp_path, damage):
    from cn_contract.assistant import context_schema, model_schema, rounds_schema, rounds_v2_schema
    database = Database('sqlite:///'+str(tmp_path/'partial.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            if damage == 'extra_index':
                db.exec_driver_sql('CREATE INDEX unexpected_rounds_index ON assistant_model_attempts(round_no)')
            elif damage == 'trigger_claim':
                db.exec_driver_sql('DROP TRIGGER immutable_assistant_model_claim')
            elif damage == 'trigger_delete':
                db.exec_driver_sql('DROP TRIGGER immutable_assistant_model_attempts_delete')
            elif damage == 'old_trigger':
                db.exec_driver_sql('DROP TRIGGER immutable_assistant_model_input')
                db.exec_driver_sql('''CREATE TRIGGER immutable_assistant_model_input BEFORE UPDATE OF
                    id,run_id,conversation_id,policy_id,config_sha256,policy_sha256,request_sha256,
                    input_json,config_json,policy_json,reserved_usd,created_at,input_format
                    ON assistant_model_attempts BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END''')
            before = list(db.exec_driver_sql(
                'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            rounds_v2_schema.initialize_storage(database)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            rounds_schema.initialize_storage(database)
        if damage in ('trigger_claim', 'trigger_delete', 'old_trigger'):
            with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
                model_schema.initialize_storage(database)
            with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
                context_schema.initialize_storage(database)
        with database.engine.connect() as db:
            assert list(db.exec_driver_sql(
                'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')) == before
    finally:
        database.engine.dispose()


def test_round_constraints_and_immutability(tmp_path):
    database = Database('sqlite:///'+str(tmp_path/'constraints.db'), tmp_path/'files', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            _seed_attempt_chain(db)
        keys = tuple(_attempt_row('x', 1))
        insert = ('INSERT INTO assistant_model_attempts (' + ','.join(keys) + ') VALUES ('
                  + ','.join(':' + key for key in keys) + ')')
        # A second round of the same run is structurally occupiable.
        with database.engine.begin() as db:
            db.exec_driver_sql(insert, _attempt_row('a2', 2))
        with database.engine.connect() as db:
            assert db.exec_driver_sql(
                "SELECT round_no FROM assistant_model_attempts WHERE id='a2'").fetchall() == [(2,)]
        # CHECK rejects rounds outside 1..4 (distinct ids avoid PK shadowing).
        for bad in (0, 5):
            with pytest.raises(Exception, match='CHECK'):
                with database.engine.begin() as db:
                    db.exec_driver_sql(insert, _attempt_row('bad' + str(bad), bad))
        # Duplicate (run_id, round_no) is rejected.
        with pytest.raises(Exception, match='UNIQUE'):
            with database.engine.begin() as db:
                db.exec_driver_sql(insert, _attempt_row('a3', 2))
        # round_no and the input evidence are immutable; rows cannot be deleted.
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            with database.engine.begin() as db:
                db.exec_driver_sql("UPDATE assistant_model_attempts SET round_no=1 WHERE id='a2'")
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            with database.engine.begin() as db:
                db.exec_driver_sql(
                    "UPDATE assistant_model_attempts SET input_format='plain-text-v1' WHERE id='a2'")
        with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
            with database.engine.begin() as db:
                db.exec_driver_sql("DELETE FROM assistant_model_attempts WHERE id='a2'")
        # The lifecycle state column stays mutable.
        with database.engine.begin() as db:
            db.exec_driver_sql("UPDATE assistant_model_attempts SET state='sent_unknown' WHERE id='a2'")
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('native', [False, True])
def test_fresh_bootstrap_matches_stepwise_upgrade(tmp_path, native):
    fresh = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'fresh-files', load_settings())
    try:
        initialize_storage(fresh)
        with closing(sqlite3.connect(fresh.engine.url.database)) as raw:
            built = raw.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
    finally:
        fresh.engine.dispose()
    with closing(old_db(tmp_path/'old.db', 'assistant-context-v1', False)) as db:
        _seed_attempt_chain(db)
        schema_migrations.upgrade_database(db)
        migrated = schema_migrations.database_rows(db)
    assert [tuple(row) for row in built] == [tuple(row) for row in migrated]
    assert [tuple(row) for row in migrated] == storage_schema.schema_rows('assistant-rounds-v2')
