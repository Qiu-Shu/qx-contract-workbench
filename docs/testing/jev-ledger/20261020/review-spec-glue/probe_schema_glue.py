"""Independent old-commit comparison and whole-chain rollback, no live data."""
from contextlib import closing
import sqlite3
import subprocess

import pytest

from cn_contract import schema_migrations, storage_schema

BASE='a4c3c6706caad31c2335b4d055240dbddbfbd372'


def baseline():
    source=subprocess.check_output(['git','show',BASE+':src/cn_contract/storage_schema.py'],text=True,encoding='utf-8')
    # The old import's schema producer is unchanged; avoid testing new frozen rows against themselves.
    before=subprocess.check_output(['git','show',BASE+':src/cn_contract/assistant/model_schema.py'])
    from pathlib import Path
    assert before==Path('src/cn_contract/assistant/model_schema.py').read_bytes()
    namespace={'__name__':'cn_contract._independent_old_schema','__package__':'cn_contract'}
    exec(compile(source,'git:'+BASE+':storage_schema.py','exec'),namespace)
    return namespace


@pytest.mark.parametrize('native',[False,True])
def test_all_old_schema_rows_equal_actual_baseline_commit(native):
    old=baseline()
    for version in old['VERSIONS']:
        rows=old['schema_rows'](version,native=native)
        assert storage_schema.schema_rows(version,native=native)==rows
        assert storage_schema.identify_schema(rows,native=native)==version


@pytest.mark.parametrize('native',[False,True])
def test_final_step_failure_rolls_back_entire_isolated_upgrade_chain(tmp_path,monkeypatch,native):
    old=baseline();rows=old['schema_rows']('pre-intake',native=native)
    path=tmp_path/'独立旧库.db';sentinel=tmp_path/'独立合成原件.bin'
    sentinel.write_bytes(b'IMMUTABLE_SYNTHETIC_ORIGINAL_20261020')
    with closing(sqlite3.connect(path)) as db:
        for kind in ('table','index','trigger'):
            for row in rows:
                if row[0]==kind and row[3] is not None:db.execute(row[3])
        db.commit()
        before=schema_migrations.database_rows(db)
        original=schema_migrations.statements_for
        def fail_last(version):
            value=original(version)
            return (*value,'THIS IS INTENTIONALLY INVALID SQL') if version=='assistant-judge-v1' else value
        monkeypatch.setattr(schema_migrations,'statements_for',fail_last)
        with pytest.raises(sqlite3.Error):schema_migrations.upgrade_database(db)
        assert not db.in_transaction
        assert schema_migrations.database_rows(db)==before==rows
        assert storage_schema.identify_schema(before,native=native)=='pre-intake'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert sentinel.read_bytes()==b'IMMUTABLE_SYNTHETIC_ORIGINAL_20261020'
