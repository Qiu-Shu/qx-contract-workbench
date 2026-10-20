"""Jev additive schema must preserve every supported historical structure."""
from contextlib import closing
import hashlib
import importlib
import json
import sqlite3

import pytest

from cn_contract import storage_schema, schema_migrations
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.storage_bootstrap import initialize_storage

PREVIOUS = ('pre-intake', 'intake-v1', 'assistant-v1', 'assistant-attachments-v1', 'assistant-model-v1')
HISTORICAL = {False: '847514cddd3bd724f2814c3e0d5f9285dd06da8e72bca26fc922c51e6d25dc13',
              True: '452febfd65c660d10e3bbc16169fdf79fa54fafd090821502be85cc4d0ff1b38'}


def old_db(path, version, native):
    db = sqlite3.connect(path)
    rows = storage_schema.schema_rows(version, native=native)
    for kind in ('table', 'index', 'trigger'):
        for row in rows:
            if row[0] == kind and row[3] is not None:
                db.execute(row[3])
    db.commit()
    return db


def test_judge_is_additive_and_does_not_replace_main_ledger():
    previous = set(storage_schema.schema_rows('assistant-model-v1'))
    current = set(storage_schema.schema_rows('assistant-judge-v1'))
    assert previous < current
    assert {row[2] for row in current - previous} == {
        'assistant_judge_attempts', 'assistant_judge_receipts', 'assistant_judge_decisions'}


@pytest.mark.parametrize('native', [False, True])
def test_old_model_structure_is_frozen_even_if_current_schema_changes(monkeypatch, native):
    from cn_contract.assistant import model_schema
    before = storage_schema.schema_rows('assistant-model-v1', native=native)
    assert hashlib.sha256(json.dumps(before, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest() == HISTORICAL[native]
    try:
        monkeypatch.setattr(model_schema, 'expected_objects', lambda: [('table', 'bad', 'bad', 'bad')])
        importlib.reload(storage_schema)
        assert storage_schema.schema_rows('assistant-model-v1', native=native) == before
    finally:
        monkeypatch.undo()
        importlib.reload(storage_schema)


@pytest.mark.parametrize('version', PREVIOUS)
@pytest.mark.parametrize('native', [False, True])
def test_every_supported_old_version_upgrades_without_replacing_old_objects(tmp_path, version, native):
    with closing(old_db(tmp_path/'old.db', version, native)) as db:
        before = schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        after = schema_migrations.database_rows(db)
        assert set(before) < set(after)
        assert storage_schema.identify_schema(after, native=native) == storage_schema.CURRENT_VERSION
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert schema_migrations.upgrade_database(db) == storage_schema.CURRENT_VERSION
        assert schema_migrations.database_rows(db) == after


@pytest.mark.parametrize('native', [False, True])
def test_judge_migration_failure_is_atomic(tmp_path, monkeypatch, native):
    with closing(old_db(tmp_path/'old.db', 'assistant-model-v1', native)) as db:
        before = schema_migrations.database_rows(db)
        actual = schema_migrations.statements_for
        monkeypatch.setattr(schema_migrations, 'statements_for', lambda target:
            (*actual(target), 'INVALID SQL') if target == 'assistant-judge-v1' else actual(target))
        with pytest.raises(sqlite3.Error):
            schema_migrations.upgrade_database(db)
        assert schema_migrations.database_rows(db) == before
        assert not db.in_transaction


def test_partial_judge_schema_is_not_silently_repaired(tmp_path):
    from cn_contract.assistant import judge_schema
    database = Database('sqlite:///'+str(tmp_path/'partial.db'), tmp_path/'protected', load_settings())
    try:
        initialize_storage(database)
        with database.engine.begin() as db:
            trigger = db.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='assistant_judge_receipts' ORDER BY name LIMIT 1").scalar_one()
            db.exec_driver_sql('DROP TRIGGER '+trigger)
        with pytest.raises(ValueError, match='DATABASE_SCHEMA_MISMATCH'):
            judge_schema.initialize_storage(database)
    finally:
        database.engine.dispose()
