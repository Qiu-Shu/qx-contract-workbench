"""Bounded-rounds loop: synthetic loopback wire, fixed tools, persisted stops.

All providers, identities, secrets and library records are fictional; the
loopback server answers per round by inspecting the immutable wire it gets.
"""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import model_integrity, service
from cn_contract.assistant import research as research_service
from cn_contract.assistant.context_preview import assemble_context
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.providers.rounds_codec import build_basis_rounds
from cn_contract.assistant.rounds_runner import execute_context_run
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.local_server import initialize_workspace
from tests.integration.test_assistant_context_backup import corrupt
from tests.integration.test_assistant_context_send import context_world
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_main_provider import raw
from tests.integration.test_assistant_research_service import request
from tests.integration.test_assistant_task_manager import finished

SECRET = 'SYNTHETIC_ROUNDS_NOT_A_REAL_KEY_09876'


def rounds_envelope(content, *, usage=None):
    return {'id': 'synthetic-rounds-response', 'object': 'chat.completion', 'created': 1,
        'model': 'deepseek-flash', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps(content, ensure_ascii=False)},
            'logprobs': None}],
        'usage': usage or {'prompt_tokens': 40, 'completion_tokens': 20, 'total_tokens': 60}}


@contextmanager
def rounds_server(answer):
    """Loopback answering per request; answer(body) -> envelope dict."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            received.append(body)
            payload = raw(answer(json.loads(body)))
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()

    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    instance.daemon_threads = True
    thread = Thread(target=instance.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{instance.server_port}/chat/completions', received
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(2)


def plan_content(calls):
    return {'tool_plan': {'calls': calls}}


def search_call(text_query='目标租赁'):
    return {'tool': 'legal_library.search', 'query': {'text': text_query}}


@pytest.fixture
def rounds_world(tmp_path, library):
    """Native workspace with saved citations, a draft and a v2 rounds basis."""
    root = tmp_path/'合成多轮工作区'
    initialize_workspace(root, 'lawyer', 'fixture123', data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected',
                        load_settings(), initialize_schema=False)
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(
            actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        queued = research_service.enqueue_research(actor, conversation.scope.conversation_id,
            request(conversation), db)
    result = research_service.execute_research(actor, queued.run.id, database,
                                               LegalLibraryAdapter(library[0]))
    ids = result.receipts[0].result.citation_ids
    assert ids
    with database.session() as db:
        view = service.read_conversation(actor, conversation.scope.conversation_id, db)
        view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content=' 请结合所选合成片段继续检索后给出待核候选。 '), db)
        row = service._owned(actor, view.scope.conversation_id, db)
        config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
            output_usd_per_million='1.2', price_reference='synthetic-rounds-ceiling')
        submission = d.MainContextSubmission(request_id=uuid4(), expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, content=view.draft_input,
            citation_ids=ids)
        scope, manifest, records = assemble_context(actor, row, submission.citation_ids, db,
                                                    question=submission.content)
        basis = build_basis_rounds(submission.request_id, manifest, scope,
                                   submission.expected_composer_revision, config, records)
    yield SimpleNamespace(database=database, actor=actor, token=token, view=view,
        submission=submission, basis=basis, scope=scope, manifest=manifest, config=config,
        library_root=library[0], research_run_id=queued.run.id)
    database.engine.dispose()


def grant(n, registry, max_calls, max_total_usd='1'):
    """Grant a v2 policy inside the current event loop; no run is registered."""
    provider = n.providers[-1]
    registry.configure(provider)
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=n.scope.workspace_id,
        actor_id=n.actor.user_id, config_sha256=sha(encoded(n.config)),
        allowed_content_sha256s=(n.basis.manifest_sha256,), max_total_usd=max_total_usd,
        max_calls=max_calls, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    registry.grant(policy, n.actor.session_id, basis=n.basis)
    return registry.resolve(n.actor, n.scope)


def drive(n, registry, max_calls, max_total_usd='1'):
    """Grant a v2 policy and register round 1 inside the current event loop."""
    lease = grant(n, registry, max_calls, max_total_usd)
    with n.database.session() as db:
        attempt = attempts.enqueue_context(n.actor, n.scope.conversation_id, n.submission, db, lease)
    assert attempt.input_format == 'library-context-v2' and attempt.state == 'reserved'
    return lease, attempt


def default_script(n):
    source = n.manifest.sources[0]

    def answer(body):
        if len(body['messages']) == 2:
            return rounds_envelope(plan_content([search_call()]))
        return rounds_envelope({'text': '结合两轮合成资料的待核候选，请律师核对。',
            'citations': [{'saved_citation_id': str(source.saved_citation_id),
                           'quote_sha256': source.quote_sha256}]})
    return answer


def integrity_ok(database):
    with database.session() as db:
        model_integrity.validate_model_records(db)


@pytest.mark.parametrize('budget', ['1', None])
def test_bounded_two_round_run_completes_with_persisted_chain(rounds_world, budget):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2, max_total_usd=budget)
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.state == 'received' and final.output is not None
            assert final.output.review_status == 'unverified'
            assert len(received) == 2
            first_wire = json.loads(received[0])
            second_wire = json.loads(received[1])
            assert len(first_wire['messages']) == 2
            roles = [message['role'] for message in second_wire['messages']]
            assert roles == ['system', 'user', 'assistant', 'user']
            # Round 2 replays the exact persisted plan and the receipt projection.
            expected_plan = d.MainContextToolPlan(calls=(d.MainContextToolCall(
                tool='legal_library.search',
                query=d.AssistantLibraryQuery(text='目标租赁')),))
            assert json.loads(second_wire['messages'][2]['content']) == {
                'tool_plan': expected_plan.model_dump(mode='json')}
            results = json.loads(second_wire['messages'][3]['content'])['tool_results']
            assert len(results) == 1 and results[0]['tool'] == 'legal_library.search'
            with n.database.session() as db:
                rows = db.execute(text('''SELECT round_no,state,input_format FROM assistant_model_attempts
                    WHERE run_id=:run ORDER BY round_no'''), {'run': str(attempt.run_id)}).all()
                assert rows == [(1, 'received', 'library-context-v2'),
                                (2, 'received', 'library-context-v2')]
                events = service.read_events(n.actor, attempt.run_id, db)
                assert [event.event_type for event in events.events] == [
                    'message.accepted', 'model.reserved', 'model.started', 'model.finished',
                    'model.tool_plan', 'tool.before', 'model.reserved', 'model.started',
                    'model.finished']
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_handler_receipts')) >= 1
                run = service.get_run(n.actor, attempt.run_id, db)
                assert run.state == 'completed'
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_rounds_replay_is_idempotent_without_resend(rounds_world):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.output is not None
            with n.database.session() as db:
                # Replays return the round-1 registration view, byte-identical.
                first = attempts.read_attempt(n.actor, attempt.id, db)
                again = attempts.enqueue_context(n.actor, n.scope.conversation_id,
                                                 n.submission, db, lease)
            assert again == first
            assert len(received) == 2
    asyncio.run(scenario())


def test_task_manager_dispatches_v2_runs_through_the_bounded_loop(rounds_world):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease = grant(n, registry, 2)
            tasks = GenerationTasks(n.database, lease,
                                    library_adapter=LegalLibraryAdapter(n.library_root))
            tasks.start()
            try:
                submitted = tasks.submit_context(n.actor, n.scope.conversation_id, n.submission)
                await finished(tasks)
                assert tasks.last_error is None
            finally:
                await tasks.close()
            assert submitted.input_format == 'library-context-v2'
            assert len(received) == 2
            with n.database.session() as db:
                assert service.get_run(n.actor, submitted.run_id, db).state == 'completed'
            integrity_ok(n.database)
    asyncio.run(scenario())


@pytest.mark.parametrize('forged', ['random', 'cross_run'])
def test_forged_or_cross_run_tool_reference_stops_bounded(rounds_world, forged):
    n = rounds_world
    n.providers = []
    reference = str(uuid4()) if forged == 'random' else str(n.submission.citation_ids[0])

    def answer(body):
        return rounds_envelope(plan_content([
            {'tool': 'legal_library.read_original', 'saved_citation_id': reference}]))

    async def scenario():
        with rounds_server(answer) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.state == 'received' and final.output is None
            assert len(received) == 1
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                events = service.read_events(n.actor, attempt.run_id, db)
                kinds = [event.event_type for event in events.events]
                assert kinds[-1] == 'model.bounded_stop'
                stop = json.loads(db.execute(text('''SELECT payload_json FROM assistant_run_events
                    WHERE event_type='model.bounded_stop' ''')).mappings().one()['payload_json'])
                assert stop == {'attempt_id': str(attempt.id), 'reason': 'tool_rejected'}
                # No receipt was ever published for the rejected reference.
                assert db.scalar(text('''SELECT COUNT(*) FROM assistant_handler_receipts
                    WHERE run_id=:run AND event_seq > 0 AND handler_id='legal_library.read_original'
                    '''), {'run': str(attempt.run_id)}) == 0
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_rounds_exhausted_stops_before_further_tools(rounds_world):
    n = rounds_world
    n.providers = []

    def answer(body):
        return rounds_envelope(plan_content([search_call()]))

    async def scenario():
        with rounds_server(answer) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.output is None
            # Both granted rounds were sent; the second plan ran no tools.
            assert len(received) == 2
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                assert db.scalar(text('''SELECT COUNT(*) FROM assistant_run_events
                    WHERE run_id=:run AND event_type='tool.before' '''), {'run': str(attempt.run_id)}) == 1
                stop = json.loads(db.execute(text('''SELECT payload_json FROM assistant_run_events
                    WHERE event_type='model.bounded_stop' ''')).mappings().one()['payload_json'])
                assert stop['reason'] == 'rounds_exhausted'
                rows = db.execute(text('''SELECT round_no FROM assistant_model_attempts
                    WHERE run_id=:run'''), {'run': str(attempt.run_id)}).all()
                assert rows == [(1,), (2,)]
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_eighth_tool_is_the_last_and_the_ninth_stops_the_run(rounds_world):
    n = rounds_world
    n.providers = []

    def answer(body):
        if len(body['messages']) == 2:
            return rounds_envelope(plan_content([search_call() for _ in range(8)]))
        return rounds_envelope(plan_content([search_call()]))

    async def scenario():
        with rounds_server(answer) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 3)
            await execute_context_run(n.actor, attempt.id, n.database, lease,
                                      LegalLibraryAdapter(n.library_root))
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                assert db.scalar(text('''SELECT COUNT(*) FROM assistant_run_events
                    WHERE run_id=:run AND event_type='tool.before' '''), {'run': str(attempt.run_id)}) == 8
                stop = json.loads(db.execute(text('''SELECT payload_json FROM assistant_run_events
                    WHERE event_type='model.bounded_stop' ''')).mappings().one()['payload_json'])
                assert stop['reason'] == 'tool_limit'
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_revoke_between_rounds_fails_closed_without_resend(rounds_world):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            first = await execute_attempt(n.actor, attempt.id, n.database, lease)
            assert first.state == 'received' and first.output is None
            registry.revoke(n.actor.session_id)
            # The re-entered loop occupies round 2; claim abandons it unsent.
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.state == 'failed_before_send'
            assert len(received) == 1
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                rows = db.execute(text('''SELECT round_no,state FROM assistant_model_attempts
                    WHERE run_id=:run ORDER BY round_no'''), {'run': str(attempt.run_id)}).all()
                assert rows == [(1, 'received'), (2, 'failed_before_send')]
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_recovery_seals_a_paused_rounds_run_without_resend(rounds_world):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            first = await execute_attempt(n.actor, attempt.id, n.database, lease)
            assert first.state == 'received'
            with n.database.session() as db:
                # Crash window: plan persisted, run paused between rounds.
                assert attempts.recover_attempts(db) == 0
                assert service.get_run(n.actor, attempt.run_id, db).state == 'interrupted'
                assert attempts.recover_attempts(db) == 0
            # A re-entered loop never dispatches against the sealed run.
            view = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                             LegalLibraryAdapter(n.library_root))
            assert view.state == 'received' and view.output is None
            assert len(received) == 1
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'interrupted'
                again = attempts.enqueue_context(n.actor, n.scope.conversation_id,
                                                 n.submission, db, lease)
            assert again.id == attempt.id
            assert len(received) == 1
            integrity_ok(n.database)
    asyncio.run(scenario())


@pytest.mark.parametrize('mutation', ['unknown_tool', 'nine_calls', 'plan_and_text'])
def test_invalid_plan_shapes_fail_the_run_without_tools(rounds_world, mutation):
    n = rounds_world
    n.providers = []

    def answer(body):
        if mutation == 'unknown_tool':
            return rounds_envelope(plan_content([{'tool': 'evil.shell', 'query': {}}]))
        if mutation == 'nine_calls':
            return rounds_envelope(plan_content([search_call() for _ in range(9)]))
        return rounds_envelope({'text': '合成候选', 'citations': [],
                                'tool_plan': {'calls': [search_call()]}})

    async def scenario():
        with rounds_server(answer) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            final = await execute_context_run(n.actor, attempt.id, n.database, lease,
                                              LegalLibraryAdapter(n.library_root))
            assert final.state == 'received' and final.output is None
            assert final.receipt.error_code == 'MODEL_OUTPUT_INVALID'
            assert len(received) == 1
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                assert db.scalar(text('''SELECT COUNT(*) FROM assistant_run_events
                    WHERE run_id=:run AND event_type IN ('tool.before','model.tool_plan')'''),
                    {'run': str(attempt.run_id)}) == 0
            integrity_ok(n.database)
    asyncio.run(scenario())


def test_v1_run_receiving_a_plan_is_invalid_output(context_world):
    database, actor, view, submission, _, runtime = context_world
    with database.session() as db:
        attempt = attempts.enqueue_context(actor, view.scope.conversation_id, submission, db, runtime)
        token, prepared, _ = attempts.claim(actor, attempt.id, db, runtime)
        assert type(prepared) is d.MainContextPreparedInput
        reply = d.MainContextReply(state='received', provider_request_id='fictional-plan',
            usage=d.MainUsage(prompt_tokens=40, completion_tokens=20, total_tokens=60),
            tool_plan=d.MainContextToolPlan(calls=(d.MainContextToolCall(
                tool='legal_library.search', query=d.AssistantLibraryQuery(text='目标租赁')),)))
        attempts.settle(actor, attempt.id, token, reply, db, runtime)
        result = attempts.read_attempt(actor, attempt.id, db)
        assert result.state == 'received' and result.output is None
        assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
        assert service.get_run(actor, attempt.run_id, db).state == 'failed'
        assert db.scalar(text('''SELECT COUNT(*) FROM assistant_run_events
            WHERE event_type='model.tool_plan' ''')) == 0
    integrity_ok(database)


def test_budget_exhaustion_between_rounds_stops_bounded(rounds_world):
    n = rounds_world
    n.providers = []
    # Round 1 reports cap-sized usage; the granted budget covers one round only.
    full_usage = {'prompt_tokens': n.config.max_input_bytes, 'completion_tokens': n.config.max_output_tokens,
        'total_tokens': n.config.max_input_bytes+n.config.max_output_tokens}

    def answer(body):
        if len(body['messages']) == 2:
            return rounds_envelope(plan_content([search_call()]), usage=full_usage)
        return rounds_envelope({'text': '不应到达的合成第二轮候选', 'citations': []})

    async def scenario():
        with rounds_server(answer) as (url, received):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            from cn_contract.assistant.providers.policy import reservation
            lease, attempt = drive(n, registry, 2, max_total_usd=reservation(n.config))
            await execute_context_run(n.actor, attempt.id, n.database, lease,
                                      LegalLibraryAdapter(n.library_root))
            assert len(received) == 1
            with n.database.session() as db:
                assert service.get_run(n.actor, attempt.run_id, db).state == 'failed'
                stop = json.loads(db.execute(text('''SELECT payload_json FROM assistant_run_events
                    WHERE event_type='model.bounded_stop' ''')).mappings().one()['payload_json'])
                assert stop == {'attempt_id': str(attempt.id), 'reason': 'budget_exhausted'}
                assert db.scalar(text('''SELECT COUNT(*) FROM assistant_model_attempts
                    WHERE run_id=:run'''), {'run': str(attempt.run_id)}) == 1
            integrity_ok(n.database)
    asyncio.run(scenario())


@pytest.mark.parametrize('tamper', ['drop_plan_event', 'rewrite_plan', 'extra_tool_event',
                                    'forged_stop', 'intermediate_output'])
def test_multi_round_archive_tampering_is_rejected(rounds_world, tamper):
    n = rounds_world
    n.providers = []

    async def scenario():
        with rounds_server(default_script(n)) as (url, _):
            n.providers.append(DeepSeekProvider.for_synthetic_loopback(n.config, lambda: SECRET, url))
            registry = MainModelRegistry()
            lease, attempt = drive(n, registry, 2)
            await execute_context_run(n.actor, attempt.id, n.database, lease,
                                      LegalLibraryAdapter(n.library_root))
    asyncio.run(scenario())
    with n.database.session() as db:
        model_integrity.validate_model_records(db)
    if tamper == 'drop_plan_event':
        corrupt(n.database, 'assistant_run_events',
                "DELETE FROM assistant_run_events WHERE event_type='model.tool_plan'")
    elif tamper == 'rewrite_plan':
        with n.database.session() as db:
            payload = json.loads(db.execute(text('''SELECT payload_json FROM assistant_run_events
                WHERE event_type='model.tool_plan' ''')).mappings().one()['payload_json'])
            payload['plan']['calls'][0]['query']['text'] = '篡改后的合成检索词'
        corrupt(n.database, 'assistant_run_events',
                "UPDATE assistant_run_events SET payload_json=? WHERE event_type='model.tool_plan'",
                (json.dumps(payload, ensure_ascii=False, separators=(',', ':')),))
    elif tamper == 'extra_tool_event':
        with n.database.session() as db:
            last = db.scalar(text('SELECT MAX(seq) FROM assistant_run_events'))
            payload = db.scalar(text('''SELECT payload_json FROM assistant_run_events
                WHERE event_type='tool.before' '''))
        corrupt(n.database, 'assistant_run_events',
                '''INSERT INTO assistant_run_events
                (run_id,seq,event_type,audience,payload_json,created_at)
                SELECT run_id,?,event_type,audience,payload_json,created_at
                FROM assistant_run_events WHERE event_type='tool.before' ''' , (last + 1,))
    elif tamper == 'forged_stop':
        with n.database.session() as db:
            run_id, attempt_id, last = db.execute(text('''SELECT run_id,id,
                (SELECT MAX(seq) FROM assistant_run_events) FROM assistant_model_attempts
                ORDER BY round_no DESC LIMIT 1''')).one()
        payload = json.dumps({'attempt_id': attempt_id, 'reason': 'tool_limit'},
                             ensure_ascii=False, separators=(',', ':'))
        corrupt(n.database, 'assistant_run_events',
                '''INSERT INTO assistant_run_events
                (run_id,seq,event_type,audience,payload_json,created_at) VALUES (?,?,?,?,?,?)''',
                (run_id, last + 1, 'model.bounded_stop', 'internal', payload,
                 '2026-01-01T00:00:09+00:00'))
    else:
        with n.database.session() as db:
            row = db.execute(text('''SELECT o.* FROM assistant_model_outputs o
                JOIN assistant_model_attempts a ON a.id=o.attempt_id AND a.round_no=2
                ''')).mappings().one()
            first = db.execute(text('''SELECT * FROM assistant_model_attempts
                WHERE round_no=1''')).mappings().one()
        corrupt(n.database, 'assistant_model_outputs',
                '''UPDATE assistant_model_outputs SET attempt_id=? WHERE id=?''',
                (first['id'], row['id']))
    with n.database.session() as db, pytest.raises(ValueError, match='ASSISTANT_MODEL_INTEGRITY'):
        model_integrity.validate_model_records(db)
