"""Read-only reviewer probes: entirely synthetic isolated SQLite databases."""
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cn_contract import schema_migrations, storage_schema
from cn_contract.assistant import profile_model_schema
from cn_contract.ops.backup import _file_references
from tests.integration.test_assistant_rounds_schema import _seed_attempt_chain

ROOT = Path(__file__).resolve().parents[3]
BASE = 'e133d5c39475388c6f8763d488cbbf3808e6855e'
BASE_SCHEMA = subprocess.check_output(['git', 'show', BASE+':src/cn_contract/storage_schema.py'], cwd=ROOT).decode('utf-8')
BASE_NS = {'__name__':'cn_contract.review_frozen_schema', '__package__':'cn_contract'}
exec(compile(BASE_SCHEMA, 'baseline/storage_schema.py', 'exec'), BASE_NS)
VERSIONS = BASE_NS['VERSIONS']


def rows(db):
    return db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def snapshot(db):
    return {name: db.execute('SELECT * FROM "'+name+'"').fetchall()
            for kind, name, _, _ in rows(db) if kind == 'table'}


def old_database(path, *, populated=False):
    db = sqlite3.connect(path)
    for kind in ('table', 'index', 'trigger'):
        for item in BASE_NS['schema_rows']('assistant-profiles-v1'):
            if item[0] == kind and item[3] is not None:
                db.execute(item[3])
    if populated:
        _seed_attempt_chain(db)
    db.commit()
    db.execute('PRAGMA foreign_keys=ON')
    return db


def fake_database(db):
    # Retain the real SQLite handle after initializer returns for inspection.
    raw = SimpleNamespace(execute=db.execute, close=lambda: None)
    return SimpleNamespace(engine=SimpleNamespace(raw_connection=lambda: raw))


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def test_baseline_schema_builder_dependencies_unchanged_except_initialization():
    # Baseline loader deliberately reuses current imports; prove their structure
    # builders/constants have unchanged AST, rather than trusting the new fixture.
    for file in ('library_schema.py','model_schema.py','context_schema.py',
                 'rounds_schema.py','rounds_v2_schema.py','profile_schema.py'):
        relative = 'src/cn_contract/assistant/'+file
        before = subprocess.check_output(['git','show',BASE+':'+relative], cwd=ROOT).decode('utf-8')
        after = (ROOT/relative).read_text('utf-8')
        def structural_ast(source):
            parsed = ast.parse(source)
            parsed.body = [node for node in parsed.body if not (
                isinstance(node, ast.FunctionDef) and node.name == 'initialize_storage')]
            return ast.dump(parsed, include_attributes=False)
        assert structural_ast(before) == structural_ast(after), file


@pytest.mark.parametrize('version', VERSIONS)
@pytest.mark.parametrize('native', [False,True])
def test_predecessor_signature_matches_independently_loaded_git_baseline(version, native):
    fixture = json.loads((ROOT/'tests/fixtures/profile_model_schema_predecessors.json').read_text('utf-8'))
    frozen = next(x for x in fixture['signatures'] if (x['version'],x['native']) == (version,native))
    assert fixture['baseline'] == BASE
    for func, key in [('schema_rows','raw'),('normalized_schema','normalized')]:
        previous = BASE_NS[func](version, native=native)
        assert getattr(storage_schema,func)(version,native=native) == previous
        assert sha(previous) == frozen[key]


@pytest.mark.parametrize('blocked_object', [
    'assistant_model_attempts_profile', 'assistant_profile_handlers',
    'immutable_assistant_profile_handlers_delete'])
def test_real_sqlite_authorizer_failure_rolls_back_data_and_fk(tmp_path, blocked_object):
    with closing(old_database(tmp_path/'authorizer.db', populated=True)) as db:
        before, data = rows(db), snapshot(db)
        db.set_authorizer(lambda action, first, second, db_name, trigger:
            sqlite3.SQLITE_DENY if action in (sqlite3.SQLITE_CREATE_TABLE,sqlite3.SQLITE_CREATE_TRIGGER)
            and first == blocked_object else sqlite3.SQLITE_OK)
        with pytest.raises(sqlite3.DatabaseError, match='not authorized'):
            profile_model_schema.initialize_storage(fake_database(db))
        db.set_authorizer(None)
        assert rows(db) == before
        assert snapshot(db) == data
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert not db.in_transaction
        # Failure recovery remains usable, preserving children and retry safety.
        profile_model_schema.initialize_storage(fake_database(db))
        assert {k:v for k,v in snapshot(db).items() if k in data} == data
        assert rows(db) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION)


def test_begin_immediate_busy_restores_fk_without_altering_rows(tmp_path):
    path = tmp_path/'busy.db'
    with closing(old_database(path, populated=True)) as db, closing(sqlite3.connect(path)) as locker:
        before, data = rows(db), snapshot(db)
        db.execute('PRAGMA busy_timeout=0')
        locker.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.OperationalError, match='database is locked'):
            profile_model_schema.initialize_storage(fake_database(db))
        locker.rollback()
        assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
        assert not db.in_transaction
        assert rows(db) == before and snapshot(db) == data


def test_all_rows_and_original_column_bytes_survive_success_then_repeat(tmp_path):
    with closing(old_database(tmp_path/'preserve.db', populated=True)) as db:
        before = snapshot(db)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        for _ in range(2):
            profile_model_schema.initialize_storage(fake_database(db))
            assert {k:v for k,v in snapshot(db).items() if k in before} == before
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []
            assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
            assert rows(db) == storage_schema.schema_rows(storage_schema.CURRENT_VERSION)


@pytest.mark.parametrize('damage,expected', [
    ('orphan_handler','ASSISTANT_PROFILE_MODEL_NOT_ENABLED'),
    ('legacy_profile','ASSISTANT_PROFILE_INTEGRITY')])
def test_archive_full_entry_rejects_orphan_new_handler_and_old_profile(tmp_path,damage,expected):
    path = tmp_path/'integrity.db'
    with closing(old_database(path)) as db:
        schema_migrations.upgrade_database(db)
        db.execute('PRAGMA foreign_keys=OFF')
        if damage == 'orphan_handler':
            db.execute('''INSERT INTO assistant_profile_handlers
                (run_id,event_seq,handler_id,handler_version,attempt_id,output_id,
                 conversation_id,outcome,reason_code,basis_sha256,created_at)
                VALUES ('absent',1,'profile.save','1','absent','absent','absent',
                'blocked','save_failed',?, '2026-10-23T00:00:00+00:00')''', ('a'*64,))
        else:
            db.execute('INSERT INTO assistant_profile_revisions VALUES (?,?,?,?,?)',
                ('missing',1,'{}','a'*64,'2026-10-23T00:00:00+00:00'))
        db.commit()
    engine = create_engine('sqlite:///'+str(path))
    try:
        with Session(engine) as session:
            with pytest.raises(ValueError, match='^'+expected+'$'):
                _file_references(session)
    finally:
        engine.dispose()
