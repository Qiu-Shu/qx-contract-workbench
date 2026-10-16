"""Fixed synthetic schema fixtures, never a relabelled current initializer."""
from contextlib import closing
import importlib
import sqlite3

import pytest

from cn_contract.schema_baseline import INTAKE_V1_ROWS


def rows(connection):
    return connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()


def old_database(path, version='intake-v1'):
    connection = sqlite3.connect(path)
    baseline = [row for row in INTAKE_V1_ROWS
                if version != 'pre-intake' or row[2] not in ('intake_cases', 'intake_revisions')]
    for kind in ('table', 'index', 'trigger'):
        for row in baseline:
            if row[0] == kind and row[3] is not None:
                connection.execute(row[3])
    connection.execute("INSERT INTO users VALUES ('synthetic-user', 'old-user', 'not-a-real-password', '[]', 0)")
    connection.commit()
    assert rows(connection) == baseline
    return connection


@pytest.mark.parametrize('version', ['pre-intake', 'intake-v1'])
def test_fixed_old_versions_and_normalized_backup_algorithm(tmp_path, version):
    catalog = importlib.import_module('cn_contract.storage_schema')
    with closing(old_database(tmp_path/'old.db', version)) as connection:
        actual = rows(connection)
        assert catalog.schema_rows(version) == actual
        assert catalog.identify_schema(actual) == version
        expected = [(kind, name, table, ' '.join(sql.split()))
                    for kind, name, table, sql in actual if sql is not None and not name.startswith('sqlite_')]
        assert catalog.normalized_schema(version) == expected
        copy = catalog.schema_rows(version)
        copy.clear()
        assert catalog.schema_rows(version) == actual


def test_native_identity_is_exact_and_not_accepted_as_non_native(tmp_path):
    catalog = importlib.import_module('cn_contract.storage_schema')
    with closing(old_database(tmp_path/'old.db')) as connection:
        connection.execute('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)')
        actual = rows(connection)
        assert catalog.schema_rows('intake-v1', native=True) == actual
        assert catalog.identify_schema(actual, native=True) == 'intake-v1'
        with pytest.raises(ValueError): catalog.identify_schema(actual)


@pytest.mark.parametrize('damage', ['unknown', 'missing_trigger', 'missing_table'])
def test_unknown_or_partial_schema_is_rejected(tmp_path, damage):
    catalog = importlib.import_module('cn_contract.storage_schema')
    with closing(old_database(tmp_path/'old.db')) as connection:
        sql = {'unknown': 'CREATE TABLE unexpected (id TEXT)',
               'missing_trigger': 'DROP TRIGGER immutable_intake_revisions_update',
               'missing_table': 'DROP TABLE intake_revisions'}[damage]
        connection.execute(sql)
        with pytest.raises(ValueError): catalog.identify_schema(rows(connection))


@pytest.mark.parametrize('version', ['pre-intake', 'intake-v1'])
def test_isolated_upgrade_reaches_current_and_preserves_old_rows(tmp_path, version):
    catalog = importlib.import_module('cn_contract.storage_schema')
    migrations = importlib.import_module('cn_contract.schema_migrations')
    with closing(old_database(tmp_path/'old.db', version)) as connection:
        before = connection.execute('SELECT * FROM users').fetchall()
        migrations.upgrade_database(connection)
        assert rows(connection) == catalog.schema_rows(catalog.CURRENT_VERSION)
        assert connection.execute('SELECT * FROM users').fetchall() == before
        first = rows(connection)
        migrations.upgrade_database(connection)
        assert rows(connection) == first


def test_entire_isolated_chain_rolls_back_on_second_step_failure(tmp_path, monkeypatch):
    migrations = importlib.import_module('cn_contract.schema_migrations')
    with closing(old_database(tmp_path/'old.db', 'pre-intake')) as connection:
        before = rows(connection)
        original = migrations.statements_for
        monkeypatch.setattr(migrations, 'statements_for', lambda version:
                            (*original(version), 'INVALID SQL') if version == 'assistant-v1' else original(version))
        with pytest.raises(sqlite3.Error): migrations.upgrade_database(connection)
        assert rows(connection) == before
        assert not connection.in_transaction


def test_isolated_upgrade_rejects_active_transaction_without_committing_it(tmp_path):
    migrations = importlib.import_module('cn_contract.schema_migrations')
    with closing(old_database(tmp_path/'old.db')) as connection:
        connection.execute("UPDATE users SET username='not-committed'")
        with pytest.raises(ValueError): migrations.upgrade_database(connection)
        assert connection.in_transaction
        connection.rollback()
        assert connection.execute('SELECT username FROM users').fetchone() == ('old-user',)
