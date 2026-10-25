"""Two synthetic probes for the actual native preflight helper; no product edits."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import sqlalchemy
from sqlalchemy import event, text

from cn_contract.ops import backup
from cn_contract.web import workspace_upgrade
from tests.integration.test_assistant_judge_schema import old_db


ROOT = Path.cwd()
OUT = Path(__file__).resolve().parent
DATA = OUT/'independent-standards-probe-data'
DATA.mkdir(exist_ok=False)
SOURCES = ('src/cn_contract/web/workspace_upgrade.py', 'src/cn_contract/ops/backup.py',
           'src/cn_contract/ops/file_paths.py')
before = {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
real_create = sqlalchemy.create_engine
real_references = backup._file_references
outcomes = []


def sample(name, *, wal=False):
    path = DATA/name
    with closing(old_db(path, 'weixin-generations-v1', True)) as db:
        db.execute("INSERT INTO local_workspace_identity VALUES ('10000000-0000-4000-8000-000000000001')")
        db.execute("INSERT INTO users VALUES ('20000000-0000-4000-8000-000000000001','synthetic-before','unused','[]',0)")
        db.commit()
        if wal:
            assert db.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
    return path


def run_probe(name, path, callback, *, failure=False):
    connections, disposed, closed = [], [], []
    def traced_engine(*args, **kwargs):
        engine = real_create(*args, **kwargs)
        event.listen(engine, 'connect', lambda connection, _: connections.append(connection))
        event.listen(engine, 'close', lambda connection, _: closed.append(connection))
        event.listen(engine, 'engine_disposed', lambda _: disposed.append(True))
        return engine
    sqlalchemy.create_engine = traced_engine
    backup._file_references = callback
    try:
        try:
            workspace_upgrade._validate_history(path)
            assert not failure
        except ValueError as error:
            assert failure and str(error) == 'WORKSPACE_DATABASE_MISMATCH'
        assert len(connections) == len(closed) == len(disposed) == 1
        try:
            connections[0].execute('SELECT 1')
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError('disposed preflight DBAPI connection remained open')
        outcomes.append({'probe': name, 'passed': True, 'engine_disposed': True,
                         'dbapi_connection_closed': True})
    finally:
        sqlalchemy.create_engine = real_create
        backup._file_references = real_references


wal_path = sample('synthetic literal%23 # WAL.db', wal=True)
observed = []
def wal_snapshot(records):
    assert records.connection().connection.driver_connection.in_transaction
    assert real_references(records) == []
    first = records.scalar(text('SELECT username FROM users'))
    with closing(sqlite3.connect(wal_path, timeout=1)) as writer:
        writer.execute("UPDATE users SET username='synthetic-after'")
        writer.commit()
    second = records.scalar(text('SELECT username FROM users'))
    assert first == second == 'synthetic-before'
    observed.append([first, second])
run_probe('actual WAL writer commits while preflight retains its explicit read snapshot', wal_path, wal_snapshot)
with closing(sqlite3.connect(wal_path)) as check:
    assert check.execute('SELECT username FROM users').fetchone() == ('synthetic-after',)

failure_path = sample('synthetic disposal failure.db')
failure_before = sha256(failure_path.read_bytes()).hexdigest()
def reject_after_real_validation(records):
    assert records.connection().connection.driver_connection.in_transaction
    assert real_references(records) == []
    raise ValueError('independent synthetic validation rejection')
run_probe('validation failure closes the actual read transaction and disposes its engine',
          failure_path, reject_after_real_validation, failure=True)
assert sha256(failure_path.read_bytes()).hexdigest() == failure_before

after = {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in SOURCES}
assert before == after
result = {'exit_code': 0, 'probe_count': len(outcomes), 'outcomes': outcomes,
          'wal_snapshot_observed': observed, 'source_before': before, 'source_after': after,
          'source_stable': before == after, 'scope': 'synthetic standalone probes only; no pytest groups rerun'}
(OUT/'independent-standards-probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
