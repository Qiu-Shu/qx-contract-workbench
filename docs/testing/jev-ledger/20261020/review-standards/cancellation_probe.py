"""Independent post-decode cancellation contract; synthetic localhost only."""
import asyncio
from contextlib import contextmanager
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import httpx2
import pytest
from sqlalchemy import text

from probe import external_network_denied, setup, world
from cn_contract.assistant.providers import judge_attempts, judge_execution


@contextmanager
def received_server():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *_):
            pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(body)
            options = body['questions']['primary_intent']['criteria']
            raw = json.dumps({'model': 'jev-1.13.0', 'answers': {'primary_intent': {
                'type': 'choice', 'choice': 'client_reply', 'confidence': 1,
                'probabilities': {key: int(key == 'client_reply') for key in options}}},
                'usage': {'input_tokens': 23, 'output_tokens': 7}}).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('x-typesafe-request-id', 'standards-cancel-after-decode')
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/systemone', calls
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


def test_decoded_receipt_survives_cleanup_cancel_without_adoption_or_retry(world, monkeypatch):
    with received_server() as (endpoint, calls):
        n = setup(world, endpoint)
        n.runtime.grant(n.policy)
        with n.database.session() as db:
            attempt = judge_attempts.reserve(n.actor, n.run.id, db, n.runtime)
            run_before = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                {'id': str(n.run.id)}).mappings().one())
            events_before = db.scalar(text('SELECT count(*) FROM assistant_run_events'))
        async def scenario():
            cleanup_entered, release_cleanup = asyncio.Event(), asyncio.Event()
            original_exit = httpx2.AsyncClient.__aexit__
            async def held_exit(client, *args):
                cleanup_entered.set()
                try:
                    await release_cleanup.wait()
                finally:
                    await original_exit(client, *args)
            monkeypatch.setattr(httpx2.AsyncClient, '__aexit__', held_exit)
            task = asyncio.create_task(judge_execution.execute_attempt(
                n.actor, attempt.id, n.database, n.runtime))
            try:
                await asyncio.wait_for(cleanup_entered.wait(), timeout=1.5)
                assert len(calls) == 1 and not task.done()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert task.cancelled()
                with n.database.session() as db:
                    received = judge_attempts.read_attempt(n.actor, attempt.id, db)
                replay = await judge_execution.execute_attempt(n.actor, attempt.id, n.database, n.runtime)
                assert received == replay
                return received
            finally:
                release_cleanup.set()
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
        received = asyncio.run(scenario())
    assert received.state == 'received'
    assert received.receipt.result.evidence == 'received'
    assert received.receipt.result.status != 'ok'
    assert received.receipt.result.answers == {} and received.decision is None
    assert received.receipt.result.usage.input_tokens == 23
    assert received.receipt.result.usage.output_tokens == 7
    assert received.receipt.result.provider_request_id == 'standards-cancel-after-decode'
    assert received.receipt.occupied_usd == Decimal('0.031')
    assert received.receipt.cost_status == 'unknown'
    assert len(calls) == 1 and n.secret_reads == [True]
    with n.database.session() as db:
        assert dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
            {'id': str(n.run.id)}).mappings().one()) == run_before
        assert db.scalar(text('SELECT count(*) FROM assistant_run_events')) == events_before
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_receipts')) == 1
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_decisions')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
