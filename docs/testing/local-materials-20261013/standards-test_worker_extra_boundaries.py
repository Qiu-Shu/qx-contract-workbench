import sqlite3
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from tests.integration.test_local_workbench import local, PASSWORD


def test_busy_polling_shutdown_exits_and_releases_workspace_lock(local, monkeypatch):
    from cn_contract.web import demo_server
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    ready, attempt, retry = (threading.Event() for _ in range(3))
    original = demo_server.run_next_job
    def gated(database):
        ready.set()
        assert attempt.wait(5)
        result = original(database)
        if result is None: retry.set()
        return result
    monkeypatch.setattr(demo_server, 'run_next_job', gated)
    app = module.build_local_app(root)
    @event.listens_for(app.state.database.engine, 'checkout')
    def short_test_timeout(connection, record, proxy):
        connection.execute('PRAGMA busy_timeout=50')
    client = TestClient(app)
    client.__enter__()
    try:
        assert ready.wait(3)
        with sqlite3.connect(root/'workbench.db') as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            attempt.set()
            assert retry.wait(3), 'real SQLite BUSY should return to idle polling'
            began = time.monotonic()
            client.__exit__(None,None,None)
            client = None
            assert time.monotonic()-began < 2
            assert not app.state.worker_thread.is_alive()
            with module._worker_lock(root): pass
            blocker.rollback()
    finally:
        attempt.set()
        if client is not None: client.__exit__(None,None,None)


def test_busy_before_query_claim_does_not_resend_unknown_query(tmp_path, monkeypatch):
    from cn_contract.web import jobs
    from tests.integration import test_api_query_jobs as existing
    real_run = jobs.run_next_job
    real_claim = jobs.claim_next_job
    busy_count = []
    def busy_then_original_run(database):
        original = sqlite3.OperationalError('independent synthetic SQLite contention')
        original.sqlite_errorcode = sqlite3.SQLITE_BUSY
        failure = OperationalError('BEGIN IMMEDIATE', {}, original)
        def busy(database): raise failure
        with monkeypatch.context() as scoped:
            scoped.setattr(jobs, 'claim_next_job', busy)
            assert real_run(database) is None
            busy_count.append(True)
        assert jobs.claim_next_job is real_claim
        return real_run(database)
    monkeypatch.setattr(existing, 'run_next_job', busy_then_original_run)
    existing.test_http_factory_uses_closed_transactions_and_persists_unknown(tmp_path, 'unknown')
    assert len(busy_count) == 3
