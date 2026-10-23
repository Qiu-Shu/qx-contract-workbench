"""Profile history extends every known database without changing old evidence."""
from contextlib import closing
import hashlib
import json
import sqlite3

import pytest

from cn_contract import schema_migrations, storage_schema
from cn_contract.assistant import profile_schema
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage
from tests.integration.test_assistant_judge_schema import old_db
from tests.integration.test_assistant_rounds_schema import _seed_attempt_chain


PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1',
            'assistant-model-v1', 'assistant-judge-v1', 'assistant-library-v1',
            'assistant-context-v1', 'assistant-rounds-v1', 'assistant-rounds-v2')
HISTORICAL = {False: '4fefc5cdee01545b2d0bf50e4fe26765a07877d058b3f5379677767a7110e3a9',
              True: 'faa7dd186c64d993df4a836977ca9cb1b622ed951856645abdeb1163b0c750bc'}


def test_profile_keeps_frozen_rounds_history():
    assert storage_schema.VERSIONS[:len(PREVIOUS)+1] == PREVIOUS + ('assistant-profiles-v1',)
    for native in (False, True):
        rows = storage_schema.schema_rows('assistant-rounds-v2', native=native)
        assert hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest() == HISTORICAL[native]
        assert storage_schema.identify_schema(rows, native=native) == 'assistant-rounds-v2'


def test_profile_migration_is_additive_and_keeps_old_rows(tmp_path):
    with closing(old_db(tmp_path/'old.db', 'assistant-rounds-v2', False)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        for statement in profile_schema.STATEMENTS:
            db.execute(statement)
        db.commit()
        after = schema_migrations.database_rows(db)
        assert set(before) < set(after)
        assert {row[2] for row in set(after)-set(before)} == {
            'assistant_profile_revisions', 'assistant_profile_receipts'}
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert storage_schema.identify_schema(after) == 'assistant-profiles-v1'


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_all_historical_versions_upgrade_without_losing_rows(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        after = schema_migrations.database_rows(db)
        assert {row[1] for row in set(before)-set(after)} <= {
            'assistant_model_attempts', 'immutable_assistant_model_input'}
        assert after == storage_schema.schema_rows(storage_schema.CURRENT_VERSION, native=native)
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(db) == after


@pytest.mark.parametrize('native', [False, True])
def test_profile_step_preserves_old_model_history_and_foreign_keys(tmp_path, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-rounds-v2', native)) as db:
        _seed_attempt_chain(db)
        tables = [r[1] for r in schema_migrations.database_rows(db) if r[0] == 'table']
        before = {table:db.execute('SELECT * FROM '+table).fetchall() for table in tables}
        schema_migrations.upgrade_database(db)
        assert {table:db.execute('SELECT * FROM '+table).fetchall() for table in tables} == before
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)


@pytest.mark.parametrize('start', ['pre-intake', 'assistant-rounds-v2'])
@pytest.mark.parametrize('completed', range(1, 7))
def test_each_partial_profile_step_rolls_back_entire_missing_chain(tmp_path, monkeypatch, start, completed):
    with closing(old_db(tmp_path/'old.db', start, False)) as db:
        db.execute("INSERT INTO users VALUES ('synthetic-user','old-user','unused','[]',0)")
        db.commit()
        before = schema_migrations.database_rows(db)
        original = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda version:
            (*original(version)[:completed], 'INVALID SQL') if version == 'assistant-profiles-v1' else original(version))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert db.execute('SELECT username FROM users').fetchall() == [('old-user',)]
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert not db.in_transaction


@pytest.mark.parametrize('native', [False, True])
def test_fresh_bootstrap_matches_migration_and_reinitialize_is_noop(tmp_path, native):
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
        with closing(old_db(tmp_path/'old.db', 'assistant-rounds-v2', native)) as db:
            schema_migrations.upgrade_database(db)
            assert before == schema_migrations.database_rows(db)
        assert before == storage_schema.schema_rows(storage_schema.CURRENT_VERSION, native=native)
    finally:
        database.engine.dispose()


@pytest.mark.parametrize('damage', ['trigger', 'table', 'extra_index', 'modified_table'])
def test_partial_or_unknown_profile_family_is_rejected_without_repair(tmp_path, damage):
    database = Database('sqlite:///'+str(tmp_path/'fresh.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            db.exec_driver_sql({
                'trigger': 'DROP TRIGGER immutable_assistant_profile_receipts_update',
                'table': 'DROP TABLE assistant_profile_receipts',
                'extra_index': 'CREATE INDEX unexpected_profile_index ON assistant_profile_receipts(created_at)',
                'modified_table': 'ALTER TABLE assistant_profile_receipts ADD COLUMN untrusted TEXT',
            }[damage])
            before = [tuple(row) for row in db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            profile_schema.initialize_storage(database)
        with database.engine.connect() as db:
            assert [tuple(row) for row in db.exec_driver_sql('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')] == before
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            storage_schema.identify_schema(before)
    finally:
        database.engine.dispose()


def insert(db, table, row):
    db.execute('INSERT INTO '+table+' ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')', tuple(row.values()))


@pytest.fixture
def profile_rows(tmp_path):
    with closing(old_db(tmp_path/'old.db', 'assistant-rounds-v2', False)) as db:
        _seed_attempt_chain(db)
        schema_migrations.upgrade_database(db)
        db.execute("INSERT INTO intake_cases VALUES ('i1','u1','ir1','hash',1,NULL,NULL)")
        db.execute("INSERT INTO intake_revisions VALUES ('i1',1,'2026-01-01T00:00:01+00:00','{}','','')")
        revision = dict(conversation_id='c1', revision=1, profile_json='{}', profile_sha256='0'*64,
                        created_at='2026-01-01T00:00:02+00:00')
        receipt = dict(conversation_id='c1', sequence=1, request_id='pr1', request_json='{}',
                       request_sha256='1'*64, profile_revision=1, profile_changed=1,
                       intake_id='i1', intake_revision=1, intake_sha256='2'*64, projection_changed=1,
                       consultation_origin='profile_summary', event_type='profile.saved', audience='internal',
                       actor_id='u1', session_id='s1', created_at='2026-01-01T00:00:02+00:00')
        insert(db, 'assistant_profile_revisions', revision)
        insert(db, 'assistant_profile_receipts', receipt)
        db.commit()
        yield db, revision, receipt


@pytest.mark.parametrize('table,index', [('assistant_profile_revisions', 1), ('assistant_profile_receipts', 2)])
def test_every_profile_history_field_and_deletion_are_immutable(profile_rows, table, index):
    db = profile_rows[0]
    before = db.execute('SELECT * FROM '+table).fetchall()
    for field, value in profile_rows[index].items():
        with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
            db.execute('UPDATE '+table+' SET '+field+'=?', (value,))
        db.rollback()
    with pytest.raises(sqlite3.IntegrityError, match='IMMUTABLE_RECORD'):
        db.execute('DELETE FROM '+table)
    db.rollback()
    assert db.execute('SELECT * FROM '+table).fetchall() == before


@pytest.mark.parametrize('change', [dict(sequence=0), dict(sequence=1.5), dict(profile_revision=0),
    dict(profile_changed=2), dict(projection_changed=2), dict(intake_revision=0), dict(intake_revision=1.5),
    dict(intake_id=None), dict(intake_revision=None), dict(intake_sha256=None),
    dict(profile_revision=None), dict(intake_id=None,intake_revision=None,intake_sha256=None),
    dict(consultation_origin='verified'), dict(audience='client'), dict(event_type='profile.unchanged'),
    dict(profile_changed=0,projection_changed=0), dict(request_json='x'*2097153)],
    ids=['zero-sequence','fraction-sequence','zero-profile','invalid-profile-flag','invalid-projection-flag',
         'zero-intake','fraction-intake','missing-intake','missing-intake-revision','missing-intake-hash',
         'changed-without-profile','projection-without-intake','unknown-origin','client-event',
         'changed-as-unchanged','unchanged-as-changed','oversize-request'])
def test_receipts_reject_invalid_bounds_links_and_event_flags(profile_rows, change):
    db, _, receipt = profile_rows
    with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
        insert(db, 'assistant_profile_receipts', {**receipt, 'sequence':2, 'request_id':'pr2', **change})
    db.rollback()


@pytest.mark.parametrize('change', [dict(revision=0),dict(revision=1.5),dict(profile_json='x'*2097153)],
                         ids=['zero-revision','fraction-revision','oversize-profile'])
def test_revisions_reject_invalid_bounds(profile_rows, change):
    db, revision, _ = profile_rows
    with pytest.raises(sqlite3.IntegrityError, match='CHECK'):
        insert(db, 'assistant_profile_revisions', {**revision, 'revision':2, **change})
    db.rollback()


@pytest.mark.parametrize('change', [dict(conversation_id='missing'),dict(profile_revision=999),
    dict(intake_id='missing'),dict(intake_revision=999),dict(actor_id='missing'),dict(session_id='missing')],
    ids=['conversation','profile','intake','intake-revision','actor','session'])
def test_receipts_require_existing_foreign_records(profile_rows, change):
    db, _, receipt = profile_rows
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        insert(db, 'assistant_profile_receipts', {**receipt,'sequence':2,'request_id':'pr2',**change})
    db.rollback()


def test_receipt_uniqueness_and_initial_no_change_without_projection(profile_rows):
    db, _, receipt = profile_rows
    for change in (dict(sequence=2), dict(request_id='pr2')):
        with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
            insert(db, 'assistant_profile_receipts', {**receipt, **change})
        db.rollback()
    insert(db, 'assistant_profile_receipts', {**receipt,'sequence':2,'request_id':'pr2',
        'profile_revision':None,'profile_changed':0,'intake_id':None,'intake_revision':None,
        'intake_sha256':None,'projection_changed':0,'event_type':'profile.unchanged','consultation_origin':'user'})
    db.commit()
    assert db.execute('SELECT sequence,event_type FROM assistant_profile_receipts ORDER BY sequence').fetchall() == [
        (1, 'profile.saved'), (2, 'profile.unchanged')]
