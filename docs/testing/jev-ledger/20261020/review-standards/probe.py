"""Independent Standards checks for CH-05B; synthetic localhost data only."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace
from typing import get_args
from uuid import uuid4

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tests/integration'))
from test_assistant_generation import world
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import jev_codec, judge_attempts, judge_execution
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, encoded, sha
from cn_contract.security import ServiceError
from cn_contract.storage_schema import schema_rows


@pytest.fixture(autouse=True)
def external_network_denied(monkeypatch):
    connect, connect_ex, lookup = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
    blocked = []
    def guard(method):
        def invoke(sock, address):
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return method(sock, address)
            blocked.append(True)
            raise AssertionError('External networking is forbidden')
        return invoke
    def local_lookup(host, *args, **kwargs):
        if host not in ('127.0.0.1', b'127.0.0.1', '::1', b'::1'):
            blocked.append(True)
            raise AssertionError('External DNS is forbidden')
        return lookup(host, *args, **kwargs)
    monkeypatch.setattr(socket.socket, 'connect', guard(connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guard(connect_ex))
    monkeypatch.setattr(socket, 'getaddrinfo', local_lookup)
    yield
    assert blocked == []


def setup(world, endpoint):
    database, actor, conversation, message, main_runtime = world
    with database.session() as db:
        run = service.save_message(actor, conversation.scope.conversation_id, message, db)
    config = d.JevConfig(enabled=True)
    secret_reads = []
    def secret():
        secret_reads.append(True)
        return 'INDEPENDENT_SYNTHETIC_JUDGE_TOKEN_ONLY'
    runtime = JudgeRuntime(JevProvider.for_synthetic_loopback(config, secret, endpoint))
    with database.session() as db:
        request = judge_attempts.request_for_run(actor, run.id, db, config)
    policy = d.JudgePolicy(policy_id=uuid4(), workspace_id=request.scope.workspace_id,
        actor_id=actor.user_id, session_id=actor.session_id, config_sha256=sha(encoded(config)),
        permissions=(d.JudgePermission(local_request_id=request.local_request_id,
            purpose=request.purpose, input_hash=jev_codec.input_hash(request, config)),),
        reserved_usd='0.031', max_total_usd='0.031', max_calls=1,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=2))
    return SimpleNamespace(database=database, actor=actor, run=run, request=request,
        config=config, runtime=runtime, policy=policy, secret_reads=secret_reads,
        main_runtime=main_runtime)


@contextmanager
def waiting_server():
    entered, release = Event(), Event()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            entered.set()
            release.wait(3)
            options = body['questions']['primary_intent']['criteria']
            response = {'model': 'jev-1.13.0', 'answers': {'primary_intent': {
                'type': 'choice', 'choice': 'client_reply', 'confidence': 1,
                'probabilities': {key: int(key == 'client_reply') for key in options}}},
                'usage': {'input_tokens': 19, 'output_tokens': None}}
            raw = json.dumps(response).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(endpoint=f'http://127.0.0.1:{server.server_port}/v1/systemone',
            entered=entered, release=release, calls=calls)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_waiting_http_releases_write_transaction_and_never_changes_main_run(world):
    with waiting_server() as remote:
        n = setup(world, remote.endpoint)
        n.runtime.grant(n.policy)
        with n.database.session() as db:
            before = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                {'id': str(n.run.id)}).mappings().one())
            events_before = db.scalar(text('SELECT count(*) FROM assistant_run_events'))
            attempt = judge_attempts.reserve(n.actor, n.run.id, db, n.runtime)
        def independent_writer():
            with n.database.session() as db:
                db.execute(text('UPDATE assistant_conversations SET display_title=:title WHERE id=:id'),
                    {'title': '独立写事务已完成', 'id': str(n.request.scope.conversation_id)})
            assert not remote.release.is_set()
            return True
        async def scenario():
            task = asyncio.create_task(judge_execution.execute_attempt(
                n.actor, attempt.id, n.database, n.runtime))
            try:
                deadline = asyncio.get_running_loop().time()+1.5
                while not remote.entered.is_set() and not task.done():
                    assert asyncio.get_running_loop().time() < deadline
                    await asyncio.sleep(.003)
                assert remote.entered.is_set() and not task.done()
                assert await asyncio.wait_for(asyncio.to_thread(independent_writer), timeout=.5)
                assert not task.done()
                remote.release.set()
                result = await task
                replay = await judge_execution.execute_attempt(n.actor, attempt.id, n.database, n.runtime)
                assert result == replay
                return result
            finally:
                remote.release.set()
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        result = asyncio.run(scenario())
    assert result.state == 'received' and result.receipt.result.status == 'ok'
    assert result.receipt.occupied_usd == Decimal('0.031') and result.receipt.cost_status == 'unknown'
    assert result.receipt.result.usage.output_tokens is None and len(remote.calls) == 1
    assert n.secret_reads == [True]
    with n.database.session() as db:
        after = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
            {'id': str(n.run.id)}).mappings().one())
        assert before == after
        assert db.scalar(text('SELECT count(*) FROM assistant_run_events')) == events_before
        for table in ('assistant_runs', 'assistant_judge_attempts', 'assistant_judge_receipts', 'assistant_judge_decisions'):
            assert db.scalar(text('SELECT count(*) FROM '+table)) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
        assert judge_attempts.recover_attempts(db) == 0


def test_default_deny_and_main_authorization_are_not_judge_permission(world):
    n = setup(world, 'http://127.0.0.1:12345/v1/systemone')
    with n.database.session() as db:
        before = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
            {'id': str(n.run.id)}).mappings().one())
        for runtime in (None, JudgeRuntime(), n.runtime, n.main_runtime):
            with pytest.raises(ServiceError):
                judge_attempts.reserve(n.actor, n.run.id, db, runtime)
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts')) == 0
        assert dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
            {'id': str(n.run.id)}).mappings().one()) == before
    assert n.secret_reads == []


def test_frozen_main_schema_equals_actual_baseline_and_judge_is_only_additive():
    source = subprocess.check_output(['git', 'show',
        'a4c3c6706caad31c2335b4d055240dbddbfbd372:src/cn_contract/assistant/model_schema.py'], cwd=ROOT)
    namespace = {}
    exec(compile(source, '<trusted-baseline-model-schema>', 'exec'), namespace)
    historical = tuple(namespace['expected_objects']())
    from cn_contract.assistant_model_schema_baseline import ASSISTANT_MODEL_V1_ROWS
    assert historical == ASSISTANT_MODEL_V1_ROWS
    for native in (False, True):
        old = set(schema_rows('assistant-model-v1', native=native))
        current = set(schema_rows('assistant-judge-v1', native=native))
        assert old < current
        added_tables = {row[1] for row in current-old if row[0] == 'table'}
        assert added_tables == {'assistant_judge_attempts', 'assistant_judge_receipts', 'assistant_judge_decisions'}
