"""Profile model storage evolves without rewriting historical schema or evidence."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db
from tests.integration.test_assistant_profile_schema import insert
from tests.integration.test_assistant_rounds_schema import _attempt_row, _seed_attempt_chain


TARGET = 'assistant-profile-model-v1'
PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1',
            'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1',
            'assistant-context-v1', 'assistant-rounds-v1', 'assistant-rounds-v2',
            'assistant-profiles-v1')
FROZEN = json.loads((Path(__file__).parents[1]/'fixtures/profile_model_schema_predecessors.json').read_text('utf-8'))['signatures']


def digest(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def snapshot(db):
    return {row[1]: db.execute('SELECT * FROM '+row[1]).fetchall()
            for row in schema_migrations.database_rows(db) if row[0] == 'table'}


def seed_profile(db):
    _seed_attempt_chain(db)
    insert(db, 'assistant_run_events', dict(run_id='run1', seq=1, event_type='response.ready',
        audience='internal', payload_json='{}', created_at='2026-01-01T00:00:03+00:00'))
    insert(db, 'assistant_profile_revisions', dict(conversation_id='c1', revision=1,
        profile_json='{}', profile_sha256='0'*64, created_at='2026-01-01T00:00:04+00:00'))
    insert(db, 'assistant_profile_receipts', dict(conversation_id='c1', sequence=1,
        request_id='pr1', request_json='{}', request_sha256='1'*64, profile_revision=1,
        profile_changed=1, intake_id=None, intake_revision=None, intake_sha256=None,
        projection_changed=0, consultation_origin='user', event_type='profile.saved',
        audience='internal', actor_id='u1', session_id='s1', created_at='2026-01-01T00:00:04+00:00'))
    db.commit()


def handler(**changes):
    return dict(run_id='run1', event_seq=1, handler_id='profile.save', handler_version='1',
        attempt_id='a1', output_id='o1', conversation_id='c1', profile_receipt_sequence=1,
        outcome='applied', reason_code=None, basis_sha256='a'*64,
        created_at='2026-01-01T00:00:04+00:00') | changes


@pytest.mark.parametrize('item', FROZEN, ids=lambda item: item['version']+('-native' if item['native'] else ''))
def test_all_eleven_predecessors_keep_both_schema_algorithms(item):
    version, native = item['version'], item['native']
    rows = storage_schema.schema_rows(version, native=native)
    assert digest(rows) == item['raw']
    assert digest(storage_schema.normalized_schema(version, native=native)) == item['normalized']
    assert storage_schema.identify_schema(rows, native=native) == version


def test_upgrade_opens_profile_format_but_not_unknown_formats(tmp_path):
    with closing(old_db(tmp_path/'before.db', 'assistant-profiles-v1', False)) as db:
        seed_profile(db)
        schema_migrations.upgrade_database(db)
        insert(db, 'assistant_model_attempts', _attempt_row('a2', 2) | {'input_format':'profile-text-v1'})
        db.commit()
        assert db.execute("SELECT input_format FROM assistant_model_attempts WHERE id='a2'").fetchone() == ('profile-text-v1',)
        with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
            insert(db, 'assistant_model_attempts', _attempt_row('a3', 3) | {'input_format':'profile-text-v2'})
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
            db.execute("UPDATE assistant_model_attempts SET input_format='plain-text-v1' WHERE id='a2'")


def test_version_changes_only_attempts_check_and_adds_handler_family():
    assert storage_schema.VERSIONS == PREVIOUS + (TARGET,)
    assert storage_schema.CURRENT_VERSION == TARGET
    old = set(storage_schema.schema_rows('assistant-profiles-v1'))
    new = set(storage_schema.schema_rows(TARGET))
    assert {row[1] for row in old-new} == {'assistant_model_attempts'}
    assert {row[2] for row in new-old} == {'assistant_model_attempts', 'assistant_profile_handlers'}


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_every_predecessor_upgrades_without_losing_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'before.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        assert schema_migrations.upgrade_database(db) == TARGET
        assert schema_migrations.database_rows(db) == storage_schema.schema_rows(TARGET, native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('SELECT * FROM assistant_profile_handlers').fetchall() == []
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert schema_migrations.upgrade_database(db) == TARGET


@pytest.mark.parametrize('native', [False, True])
def test_rebuild_preserves_model_and_profile_children(tmp_path, native):
    with closing(old_db(tmp_path/'before.db', 'assistant-profiles-v1', native)) as db:
        seed_profile(db)
        before = snapshot(db)
        schema_migrations.upgrade_database(db)
        after = snapshot(db)
        assert {table: after[table] for table in before} == before
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('completed', range(14))
def test_each_partial_step_rolls_back_all_rows_and_restores_fk(tmp_path, monkeypatch, completed):
    with closing(old_db(tmp_path/'before.db', 'assistant-profiles-v1', False)) as db:
        seed_profile(db)
        before, data = schema_migrations.database_rows(db), snapshot(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version)[:completed], 'INVALID SQL') if version == TARGET else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert snapshot(db) == data
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert not db.in_transaction


@pytest.mark.parametrize('failure', ['copy', 'handler', 'complete', 'foreign-key'])
def test_initializer_failure_preserves_predecessor_and_restores_fk(tmp_path, monkeypatch, failure):
    from cn_contract.assistant import profile_model_schema
    path = tmp_path/'before.db'
    with closing(old_db(path, 'assistant-profiles-v1', False)) as db:
        seed_profile(db)
        before, data = schema_migrations.database_rows(db), snapshot(db)
    database = Database('sqlite:///'+str(path), tmp_path/'protected', load_settings(), initialize_schema=False)
    expected = profile_model_schema.expected_objects()
    statements = profile_model_schema.STATEMENTS
    # Keep schema reference fixed while injecting failure into the executing DDL.
    monkeypatch.setattr(profile_model_schema, 'expected_objects', lambda: expected)
    if failure == 'foreign-key':
        broken = statements + ("INSERT INTO assistant_model_receipts VALUES ('missing','{}','2026-01-01T00:00:00+00:00')",)
        error, match = ValueError, 'DATABASE_INTEGRITY'
    else:
        completed = {'copy':5, 'handler':11, 'complete':13}[failure]
        broken = statements[:completed] + ('INVALID SQL',)
        error, match = sqlite3.Error, 'syntax'
    monkeypatch.setattr(profile_model_schema, 'STATEMENTS', broken)
    try:
        with pytest.raises(error, match=match):
            profile_model_schema.initialize_storage(database)
        raw = database.engine.raw_connection()
        try:
            assert schema_migrations.database_rows(raw) == before
            assert snapshot(raw) == data
            assert raw.execute('PRAGMA foreign_keys').fetchone() == (1,)
            assert raw.execute('PRAGMA foreign_key_check').fetchall() == []
            assert not raw.driver_connection.in_transaction
        finally:
            raw.close()
    finally:
        database.engine.dispose()


def test_staging_upgrade_rolls_back_dangling_foreign_key(tmp_path, monkeypatch):
    with closing(old_db(tmp_path/'before.db', 'assistant-profiles-v1', False)) as db:
        seed_profile(db)
        before, data = schema_migrations.database_rows(db), snapshot(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version), "INSERT INTO assistant_model_receipts VALUES ('missing','{}','2026-01-01T00:00:00+00:00')")
            if version == TARGET else original(version))
        with pytest.raises(ValueError, match='DATABASE_INTEGRITY'):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert snapshot(db) == data
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert not db.in_transaction


@pytest.mark.parametrize('native', [False, True])
def test_fresh_upgrade_and_repeat_initialization_have_identical_structure(tmp_path, native):
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        if native:
            with database.engine.begin() as db:
                db.exec_driver_sql('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)')
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            before = schema_migrations.database_rows(db)
        initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            assert schema_migrations.database_rows(db) == before
        with closing(old_db(tmp_path/'before.db', 'assistant-profiles-v1', native)) as db:
            schema_migrations.upgrade_database(db)
            assert schema_migrations.database_rows(db) == before
        assert before == storage_schema.schema_rows(TARGET, native=native)
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage', ['handler_table', 'handler_trigger', 'handler_column', 'handler_index', 'attempt_trigger'])
def test_partial_new_family_is_never_repaired(tmp_path, damage):
    from cn_contract.assistant import profile_model_schema
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql({
                'handler_table':'DROP TABLE assistant_profile_handlers',
                'handler_trigger':'DROP TRIGGER immutable_assistant_profile_handlers_update',
                'handler_column':'ALTER TABLE assistant_profile_handlers ADD COLUMN unexpected TEXT',
                'handler_index':'CREATE INDEX unexpected_handler ON assistant_profile_handlers(created_at)',
                'attempt_trigger':'DROP TRIGGER immutable_assistant_model_claim',
            }[damage])
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            before = schema_migrations.database_rows(db)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            profile_model_schema.initialize_storage(database)
        with closing(sqlite3.connect(database.engine.url.database)) as db:
            assert schema_migrations.database_rows(db) == before
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            storage_schema.identify_schema(before)
    finally:
        database.engine.dispose()


@pytest.fixture
def handler_rows(tmp_path):
    with closing(old_db(tmp_path/'handlers.db', TARGET, False)) as db:
        seed_profile(db)
        db.execute('PRAGMA foreign_keys=ON')
        yield db


@pytest.mark.parametrize('outcome,reason,sequence', [
    ('applied', None, 1), ('unchanged', None, 1),
    ('blocked', 'version_conflict', None), ('blocked', 'save_failed', None)])
def test_fixed_handler_outcomes_keep_explicit_receipt_link(handler_rows, outcome, reason, sequence):
    db = handler_rows
    row = handler(outcome=outcome, reason_code=reason, profile_receipt_sequence=sequence)
    insert(db, 'assistant_profile_handlers', row)
    db.commit()
    assert db.execute('SELECT outcome,reason_code,profile_receipt_sequence FROM assistant_profile_handlers').fetchone() == (outcome, reason, sequence)
    for field, value in row.items():
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
            db.execute('UPDATE assistant_profile_handlers SET '+field+'=?', (value,))
        db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        db.execute('DELETE FROM assistant_profile_handlers')


@pytest.mark.parametrize('changes', [
    {'event_seq':0}, {'event_seq':1.5}, {'event_seq':None},
    {'handler_id':'library.search'}, {'handler_version':'2'},
    {'profile_receipt_sequence':0}, {'profile_receipt_sequence':1.5},
    {'profile_receipt_sequence':None}, {'outcome':'unknown'}, {'outcome':None},
    {'outcome':'blocked', 'profile_receipt_sequence':None},
    {'outcome':'blocked', 'reason_code':'save_failed'},
    {'reason_code':'version_conflict'},
    {'outcome':'blocked', 'reason_code':'unknown', 'profile_receipt_sequence':None},
    {'basis_sha256':'a'*63}, {'basis_sha256':'a'*65}, {'basis_sha256':'A'*64},
    {'basis_sha256':'g'*64}, {'basis_sha256':b'a'*64}, {'basis_sha256':None},
    {'basis_sha256':'a'*64+'\0x'},
    {'created_at':None}], ids=[
    'zero-event','fraction-event','null-event','handler','handler-version','zero-sequence',
    'fraction-sequence','missing-receipt','unknown-outcome','null-outcome','missing-reason',
    'blocked-with-receipt','success-with-reason','unknown-reason','short-sha','long-sha',
    'uppercase-sha','nonhex-sha','blob-sha','null-sha','nul-suffix-sha','null-time'])
def test_handler_rejects_incomplete_or_forged_outcome(handler_rows, changes):
    with pytest.raises(sqlite3.IntegrityError, match='CHECK|NOT NULL'):
        insert(handler_rows, 'assistant_profile_handlers', handler(**changes))


@pytest.mark.parametrize('changes', [
    {'run_id':'missing'}, {'event_seq':99}, {'attempt_id':'missing'},
    {'output_id':'missing'}, {'conversation_id':'missing'}, {'profile_receipt_sequence':99}],
    ids=['run','event','attempt','output','conversation','profile-receipt'])
def test_handler_requires_existing_references(handler_rows, changes):
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        insert(handler_rows, 'assistant_profile_handlers', handler(**changes))


def clone(db, table, **changes):
    columns = [row[1] for row in db.execute('PRAGMA table_info('+table+')')]
    row = dict(zip(columns, db.execute('SELECT * FROM '+table+' LIMIT 1').fetchone()))
    insert(db, table, row | changes)


@pytest.mark.parametrize('duplicate', ['event', 'attempt', 'output', 'profile-receipt'])
def test_handler_has_one_owner_for_each_execution_and_profile_receipt(handler_rows, duplicate):
    db = handler_rows
    clone(db, 'assistant_messages', id='m2', source_revision=2)
    clone(db, 'assistant_runs', id='run2', message_id='m2', request_id='req2')
    clone(db, 'assistant_model_attempts', id='a2', run_id='run2')
    clone(db, 'assistant_model_outputs', id='o2', attempt_id='a2', run_id='run2')
    clone(db, 'assistant_run_events', run_id='run2')
    clone(db, 'assistant_profile_receipts', sequence=2, request_id='pr2')
    insert(db, 'assistant_profile_handlers', handler())
    db.commit()
    row = handler(run_id='run2', attempt_id='a2', output_id='o2', profile_receipt_sequence=2)
    row.update({'event':{'run_id':'run1'}, 'attempt':{'attempt_id':'a1'},
                'output':{'output_id':'o1'}, 'profile-receipt':{'profile_receipt_sequence':1}}[duplicate])
    with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
        insert(db, 'assistant_profile_handlers', row)
