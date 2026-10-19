"""Trusted session grants through the local HTTP app and synthetic loopback only."""
import asyncio
from contextlib import contextmanager
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Event, Thread
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import task_manager
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, estimated_cost, reservation, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.ops import workspace_backup
from cn_contract.security import authenticate, provision_user
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import (
    boot, count, save_draft, signin, wait_attempt,
)


SYNTHETIC_KEY = 'SYNTHETIC_ONLY_SESSION_RUNTIME_NOT_A_REAL_SECRET_12345'


@contextmanager
def loopback(*, delayed=False):
    """A real random-port HTTP peer; no external endpoint or real material."""
    received, errors = [], []
    release, seen = Event(), Event()
    if not delayed:
        release.set()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                raw = self.rfile.read(int(self.headers['Content-Length']))
                wire = json.loads(raw)
                source = json.loads(wire['messages'][1]['content'])
                received.append({'path':self.path, 'headers':dict(self.headers), 'wire':wire})
                seen.set()
                if not release.wait(8):
                    errors.append('synthetic response gate timed out')
                    return
                candidate = {'text':'独立虚构候选，待律师核对。', 'citations':[{
                    'message_id':source['message_id'], 'quote_sha256':source['quote_sha256']}]}
                body = json.dumps({'id':'synthetic-session-response', 'object':'chat.completion',
                    'created':1, 'model':wire['model'], 'choices':[{'index':0,
                    'finish_reason':'stop', 'message':{'role':'assistant',
                    'content':json.dumps(candidate, ensure_ascii=False)}, 'logprobs':None}],
                    'usage':{'prompt_tokens':30, 'completion_tokens':12, 'total_tokens':42}},
                    ensure_ascii=False).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # A shutdown deliberately cancels an already sent request.
            except Exception as exc:
                errors.append(type(exc).__name__)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    worker = Thread(target=server.serve_forever, kwargs={'poll_interval':.02}, daemon=True)
    worker.start()
    try:
        yield SimpleNamespace(url=f'http://127.0.0.1:{server.server_port}/chat/completions',
            received=received, release=release, seen=seen)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(2)
        assert not worker.is_alive()
        assert errors == []


def configured(world, peer):
    provider = DeepSeekProvider.for_synthetic_loopback(
        world[4].provider.config, lambda:SYNTHETIC_KEY, peer.url)
    registry = MainModelRegistry()
    registry.configure(provider)
    return registry, provider


def http_actor(http):
    with http.database.session() as db:
        return authenticate(http.client.cookies.get('qx_session'), db)


def grant(http, registry, policy):
    actor = http_actor(http)
    http.client.portal.call(registry.grant, policy, actor.session_id)
    return actor


def capability(http):
    response = http.client.get(http.url+'/generation-capability')
    assert response.status_code == 200, response.text
    return response.json()['state']


def submit(http):
    response = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
    assert response.status_code == 202, response.text
    return response.json()


def session_view(http):
    return {'cookies':dict(http.client.cookies), 'headers':dict(http.headers),
            'url':http.url, 'body':dict(http.body)}


def select_session(http, session):
    http.client.cookies.clear()
    http.client.cookies.update(session['cookies'])
    http.headers, http.url, http.body = session['headers'], session['url'], dict(session['body'])


def new_conversation(http):
    response = http.client.post('/api/assistant/conversations', headers=http.headers,
        json={'request_id':str(uuid4())})
    assert response.status_code == 201, response.text
    view = response.json()
    http.url = '/api/assistant/conversations/'+view['scope']['conversation_id']
    http.body = {**http.body, 'request_id':str(uuid4()), 'expected_scope':view['scope'],
                 'expected_composer_revision':view['composer_revision']}
    save_draft(http)


def wait_calls(peer, number):
    deadline = time.monotonic()+3
    while len(peer.received) < number and time.monotonic() < deadline:
        time.sleep(.01)
    assert len(peer.received) == number


def aba(http, registry, provider, policy, actor, kind):
    def change():
        if kind == 'configuration':
            registry.configure(None)
            registry.configure(provider)
        else:
            registry.revoke(actor.session_id)
        registry.grant(policy, actor.session_id)
    http.client.portal.call(change)


def test_local_http_registry_requires_the_actual_login_session(world, tmp_path):
    registry = MainModelRegistry()
    registry.configure(world[4].provider)
    registry.grant(world[4].policy, world[1].session_id)
    with boot(world, tmp_path, runtime=registry) as http:
        save_draft(http)
        assert http_actor(http).session_id != world[1].session_id
        assert capability(http) == 'unapproved'
        grant(http, registry, world[4].policy)
        assert capability(http) == 'ready'
        assert world[4].provider.calls == []


@pytest.mark.parametrize('second_user', ['lawyer', 'other'])
def test_a_grant_never_makes_another_user_or_login_session_ready(world, tmp_path, second_user):
    if second_user == 'other':
        with world[0].session() as db:
            provision_user('other', 'fixture123', {d.Role.HANDLING_LAWYER}, db,
                local_workbench_password=True)
    with loopback() as peer:
        registry, _ = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            first_actor = grant(http, registry, world[4].policy)
            first = session_view(http)
            assert capability(http) == 'ready'
            http.headers = signin(http.client, second_user)
            second_actor = http_actor(http)
            assert first_actor.session_id != second_actor.session_id
            assert (first_actor.user_id == second_actor.user_id) == (second_user == 'lawyer')
            new_conversation(http)
            assert capability(http) == 'unapproved'
            denied = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
            assert denied.status_code == 403 and denied.json()['code'] == 'BLOCKED_LIVE'
            second_policy = world[4].policy.model_copy(update={
                'policy_id':uuid4(), 'actor_id':second_actor.user_id})
            grant(http, registry, second_policy)
            assert capability(http) == 'ready'
            select_session(http, first)
            assert capability(http) == 'ready'
            assert count(http.database) == 0 and peer.received == []


def test_http_authorized_loopback_payload_and_receipt_are_sent_exactly_once(world, tmp_path):
    with loopback() as peer:
        registry, provider = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            grant(http, registry, world[4].policy)
            assert capability(http) == 'ready' and peer.received == []
            first = submit(http)
            completed = wait_attempt(http, first['id'])
            replay = submit(http)
            assert replay['id'] == first['id']
            found = http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
            assert found.status_code == 200 and found.json()['id'] == first['id']
            assert completed['state'] == 'received'
            assert completed['receipt']['cost_status'] == 'estimated'
            assert Decimal(completed['receipt']['estimated_cost_usd']) == estimated_cost(30,12,provider.config)
            assert completed['output']['audience'] == 'internal'
            assert completed['output']['review_status'] == 'unverified'
            assert count(http.database) == count(http.database,'assistant_messages') == 1
            assert len(peer.received) == 1
            request = peer.received[0]
            assert request['path'] == '/chat/completions'
            assert request['headers']['Authorization'] == 'Bearer '+SYNTHETIC_KEY
            wire = request['wire']
            assert set(wire) == {'model','messages','max_tokens','stream','thinking','response_format'}
            assert wire['model'] == provider.config.model
            assert wire['max_tokens'] == provider.config.max_output_tokens
            assert wire['stream'] is False and wire['thinking'] == {'type':'disabled'}
            assert wire['response_format'] == {'type':'json_object'}
            assert [message['role'] for message in wire['messages']] == ['system','user']
            source = json.loads(wire['messages'][1]['content'])
            assert set(source) == {'content','message_id','quote_sha256'}
            assert source['content'] == http.body['content']
            assert source['quote_sha256'] == sha(http.body['content'])
            assert completed['output']['candidate']['citations'] == [{
                'message_id':source['message_id'], 'quote_sha256':source['quote_sha256']}]
            serialized = json.dumps(wire)
            assert str(world[2].scope.workspace_id) not in serialized
            assert str(world[2].scope.conversation_id) not in serialized
            assert SYNTHETIC_KEY not in serialized+json.dumps(completed)


@pytest.mark.parametrize('limit', ['calls', 'amount'])
def test_shared_policy_budget_survives_second_session_and_reauthorization(world, tmp_path, limit):
    with loopback() as peer:
        registry, provider = configured(world, peer)
        policy = world[4].policy.model_copy(update=(
            {'max_calls':1} if limit == 'calls' else {'max_total_usd':reservation(provider.config)}))
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            grant(http, registry, policy)
            first = submit(http)
            assert wait_attempt(http,first['id'])['state'] == 'received'
            http.headers = signin(http.client)
            new_conversation(http)
            actor = grant(http, registry, policy)
            assert capability(http) == 'budget_exhausted'
            http.client.portal.call(registry.revoke, actor.session_id)
            grant(http, registry, policy)
            assert capability(http) == 'budget_exhausted'
            denied = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
            assert denied.status_code == 403
            assert denied.json()['code'] == ('CALL_LIMIT_EXCEEDED' if limit == 'calls' else 'BUDGET_EXCEEDED')
            assert count(http.database) == 1 and len(peer.received) == 1


@pytest.mark.parametrize('kind', ['configuration', 'grant'])
def test_queued_lease_cannot_revive_after_aba(world, tmp_path, monkeypatch, kind):
    entered, release = Event(), Event()
    execute = task_manager.execute_attempt

    async def before_claim(*args):
        entered.set()
        while not release.is_set():
            await asyncio.sleep(.005)
        return await execute(*args)

    monkeypatch.setattr(task_manager, 'execute_attempt', before_claim)
    with loopback() as peer:
        registry, provider = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            actor = grant(http, registry, world[4].policy)
            try:
                first = submit(http)
                assert entered.wait(2)
                aba(http, registry, provider, world[4].policy, actor, kind)
                release.set()
                result = wait_attempt(http, first['id'])
                assert result['state'] == 'failed_before_send' and result['output'] is None
                assert result['receipt']['cost_status'] == 'not_sent'
                assert Decimal(result['receipt']['estimated_cost_usd']) == 0
                assert peer.received == []
            finally:
                release.set()


@pytest.mark.parametrize('kind', ['configuration', 'grant'])
def test_sending_lease_aba_keeps_old_receipt_but_discards_output(world, tmp_path, kind):
    with loopback(delayed=True) as peer:
        registry, provider = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            actor = grant(http, registry, world[4].policy)
            try:
                first = submit(http)
                wait_calls(peer, 1)
                aba(http, registry, provider, world[4].policy, actor, kind)
                peer.release.set()
                result = wait_attempt(http, first['id'])
                assert result['state'] == 'received' and result['output'] is None
                assert result['receipt']['provider_request_id'] == 'synthetic-session-response'
                assert result['receipt']['usage']['total_tokens'] == 42
                assert result['receipt']['cost_status'] == 'estimated'
                assert Decimal(result['receipt']['estimated_cost_usd']) == estimated_cost(30,12,provider.config)
                assert submit(http)['id'] == first['id']
                assert len(peer.received) == 1
            finally:
                peer.release.set()


def test_revoking_one_session_does_not_discard_another_concurrent_reply(world, tmp_path):
    with loopback(delayed=True) as peer:
        registry, _ = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            actor_a = grant(http, registry, world[4].policy)
            first = submit(http)
            first_session = session_view(http)
            http.headers = signin(http.client)
            new_conversation(http)
            grant(http, registry, world[4].policy)
            second = submit(http)
            second_session = session_view(http)
            try:
                wait_calls(peer, 2)
                http.client.portal.call(registry.revoke, actor_a.session_id)
                peer.release.set()
                assert wait_attempt(http,second['id'])['output']['review_status'] == 'unverified'
                select_session(http, first_session)
                assert wait_attempt(http,first['id'])['output'] is None
                select_session(http, second_session)
                assert count(http.database) == 2 and len(peer.received) == 2
            finally:
                peer.release.set()


def test_replacing_configuration_while_sending_keeps_original_price_basis(world, tmp_path):
    with loopback(delayed=True) as peer:
        registry, original = configured(world, peer)
        replacement_config = original.config.model_copy(update={
            'input_usd_per_million':Decimal('30'), 'output_usd_per_million':Decimal('120')})
        replacement = DeepSeekProvider.for_synthetic_loopback(
            replacement_config, lambda:SYNTHETIC_KEY, peer.url)
        replacement_policy = world[4].policy.model_copy(update={
            'policy_id':uuid4(), 'config_sha256':sha(encoded(replacement_config))})
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            actor = grant(http, registry, world[4].policy)
            try:
                first = submit(http)
                wait_calls(peer, 1)
                http.client.portal.call(registry.configure, replacement)
                http.client.portal.call(registry.grant, replacement_policy, actor.session_id)
                peer.release.set()
                result = wait_attempt(http, first['id'])
                assert result['state'] == 'received' and result['output'] is None
                assert result['receipt']['cost_status'] == 'estimated'
                estimate = Decimal(result['receipt']['estimated_cost_usd'])
                assert estimate == estimated_cost(30,12,original.config)
                assert estimate != estimated_cost(30,12,replacement_config)
                assert len(peer.received) == 1
            finally:
                peer.release.set()


def test_cancelled_registry_attempt_preserves_receipt_without_resending(world, tmp_path):
    with loopback(delayed=True) as peer:
        registry, _ = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            grant(http, registry, world[4].policy)
            try:
                first = submit(http)
                wait_calls(peer, 1)
                response = http.client.post('/api/assistant/runs/'+first['run_id']+'/cancel',
                    headers=http.headers, json={'request_id':str(uuid4())})
                assert response.status_code == 200, response.text
                peer.release.set()
                result = wait_attempt(http, first['id'])
                assert result['state'] == 'received' and result['output'] is None
                assert result['receipt']['cost_status'] == 'estimated'
                found = http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
                assert found.status_code == 200 and found.json()['id'] == first['id']
                assert len(peer.received) == 1
            finally:
                peer.release.set()


@pytest.mark.parametrize('claimed', [False, True])
def test_restart_has_no_grants_and_never_dispatches_old_attempts(world, tmp_path, claimed):
    with loopback() as peer:
        registry, provider = configured(world, peer)
        with boot(world, tmp_path, runtime=registry) as http:
            save_draft(http)
            actor = grant(http, registry, world[4].policy)

            def leave_durable_marker():
                request = d.AssistantMessageInput.model_validate(http.body)
                lease = registry.resolve(actor, request.expected_scope)
                with http.database.session() as db:
                    attempt = attempts.enqueue_generation(actor,request.expected_scope.conversation_id,request,db,lease)
                    if claimed:
                        assert attempts.claim(actor,attempt.id,db,lease) is not None
                    return str(attempt.id)

            identifier = http.client.portal.call(leave_durable_marker)
            assert peer.received == []
        restarted = MainModelRegistry()
        restarted.configure(provider)
        with boot(world, tmp_path, runtime=restarted) as http:
            save_draft(http)
            assert capability(http) == 'unapproved'
            response = http.client.get('/api/assistant/attempts/'+identifier)
            assert response.status_code == 200
            result = response.json()
            assert result['state'] == ('sent_unknown' if claimed else 'failed_before_send')
            assert result['receipt']['cost_status'] == ('unknown' if claimed else 'not_sent')
            assert result['output'] is None
            http.body['request_id'] = str(uuid4())
            denied = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
            assert denied.status_code == 403 and denied.json()['code'] == 'BLOCKED_LIVE'
            assert count(http.database) == 1 and peer.received == []


def test_restored_quarantine_denies_generation_even_with_current_session_grant(world, tmp_path):
    root = Path(world[0].engine.url.database).parent
    archive = tmp_path/'synthetic-session-registry.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    with loopback() as peer:
        registry, _ = configured(world, peer)
        with boot(world,tmp_path,runtime=registry,root=Path(restored['restored_root'])) as http:
            grant(http,registry,world[4].policy)
            assert capability(http) == 'restored_read_only'
            denied = http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
            assert denied.status_code == 409
            assert count(http.database) == 0 and peer.received == []
