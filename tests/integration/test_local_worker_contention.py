import json
import sqlite3
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
from tests.integration.test_local_workbench import local, login, PASSWORD
from tests.integration.test_local_materials import new_local_case, independent_docx
from cn_contract.documents.ingest import DOCX_MIME


def test_worker_survives_real_database_lock_then_processes_new_upload(local, monkeypatch):
    from cn_contract.web import demo_server
    module, root = local
    module.initialize_workspace(root, 'local-lawyer', PASSWORD)
    ready, run_claim, died = (threading.Event() for _ in range(3))
    errors = []
    original = demo_server.run_next_job
    def gated_claim(database):
        ready.set()
        assert run_claim.wait(25)
        return original(database)
    def capture_error(args):
        errors.append({'type':type(args.exc_value).__name__, 'error':str(args.exc_value),
            'thread':args.thread.name})
        died.set()
    monkeypatch.setattr(demo_server, 'run_next_job', gated_claim)
    monkeypatch.setattr(threading, 'excepthook', capture_error)
    app = module.build_local_app(root)
    with TestClient(app) as client:
        assert ready.wait(3)
        headers = login(client)
        matter = new_local_case(client, headers)
        with sqlite3.connect(root/'workbench.db') as blocker:
            blocker.execute('BEGIN IMMEDIATE')
            began = time.monotonic()
            run_claim.set()
            died.wait(17)
            lock_duration = time.monotonic() - began
            blocker.rollback()
        uploaded = client.post(f'/api/matters/{matter}/documents',
            headers={**headers, 'Idempotency-Key':'post-lock-upload'},
            files={'file':('fiction.docx', independent_docx(), DOCX_MIME)},
            data={'baseline_view':'original', 'local_processing_confirmed':'yes', 'local_policy_id':'local-workpaper-v1'})
        assert uploaded.status_code == 202, uploaded.text
        deadline = time.monotonic()+2
        status = None
        while time.monotonic() < deadline:
            status = client.get('/api/jobs/'+uploaded.json()['job_id']).json()['state']
            if status == 'completed': break
            time.sleep(.1)
        result = {'held_real_sqlite_lock_seconds':round(lock_duration,3), 'errors':errors,
            'worker_alive_after_unlock':app.state.worker_thread.is_alive(),
            'upload_after_unlock_http':uploaded.status_code, 'job_after_unlock':status}
        assert app.state.worker_thread.is_alive(), result
        assert status == 'completed', result


def test_worker_does_not_hide_non_busy_database_failure(monkeypatch):
    import pytest
    from sqlalchemy.exc import OperationalError
    from cn_contract.web import jobs
    original = sqlite3.OperationalError('independent fictional failure')
    original.sqlite_errorcode = sqlite3.SQLITE_IOERR
    failure = OperationalError('fictional statement', {}, original)
    def fail(database): raise failure
    monkeypatch.setattr(jobs, 'claim_next_job', fail)
    with pytest.raises(OperationalError) as observed:
        jobs.run_next_job(object())
    assert observed.value is failure
