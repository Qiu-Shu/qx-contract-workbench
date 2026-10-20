"""One generation task, two independent synthetic ledgers; no external provider."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts, judge_attempts, jev_codec
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, encoded, sha
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_task_manager import finished
from tests.integration.test_jev_provider import envelope, raw, server


def judge(world, *, url='http://127.0.0.1:12345/v1/systemone', config=None):
    _, actor, conversation, request, _ = world
    config = config or d.JevConfig(enabled=True)
    value = d.JudgeRequest(local_request_id=request.request_id,
        scope=conversation.scope.model_copy(update={'input_revision':conversation.scope.input_revision+1}),
        purpose='primary_intent', text=request.content)
    provider = JevProvider.for_synthetic_loopback(config, lambda:'SYNTHETIC_STAGE_SECRET_12345', url)
    runtime = JudgeRuntime(provider)
    runtime.grant(d.JudgePolicy(policy_id=uuid4(), workspace_id=value.scope.workspace_id,
        actor_id=actor.user_id, session_id=actor.session_id, config_sha256=sha(encoded(config)),
        permissions=(d.JudgePermission(local_request_id=value.local_request_id, purpose=value.purpose,
            input_hash=jev_codec.input_hash(value, config)),), reserved_usd='.02', max_total_usd='.04',
        max_calls=2, expires_at=datetime.now(timezone.utc)+timedelta(minutes=5)))
    return runtime, value


def result(request, config, *, status='ok'):
    fields = dict(local_request_id=request.local_request_id, scope=request.scope,
        input_hash=jev_codec.input_hash(request, config), elapsed_ms=1)
    if status == 'ok':
        return d.JudgeResult(**fields, status='ok', evidence='received', model='jev-1.13.0',
            answers={'primary_intent':d.JudgeChoice(**envelope(request)['answers']['primary_intent'])})
    return d.JudgeResult(**fields, status=status, evidence='sent_unknown', reason_code={
        'failed':'provider_error', 'invalid':'invalid_response', 'timed_out':'timeout'}[status])


def rows(database, table):
    with database.session() as db:
        return [dict(row) for row in db.execute(text('SELECT * FROM '+table)).mappings().all()]


def test_single_task_commits_both_ledgers_then_judge_post_then_original_main(world):
    database, actor, conversation, request, main = world
    _, value = judge(world)
    with server(raw(envelope(value))) as (url, calls, _):
        auxiliary, _ = judge(world, url=url)
        tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
        original = main.provider.generate
        order = []
        async def generate(value, **kwargs):
            assert len(rows(database, 'assistant_judge_receipts')) == 1
            assert len(rows(database, 'assistant_judge_decisions')) == 1
            order.append('main')
            return await original(value, **kwargs)
        main.provider.generate = generate
        async def scenario():
            tasks.start()
            attempt = tasks.submit(actor, conversation.scope.conversation_id, request)
            assert tasks.active_count == 1 and not calls and not main.provider.calls
            assert len(rows(database, 'assistant_runs')) == 1
            assert len(rows(database, 'assistant_model_attempts')) == 1
            assert len(rows(database, 'assistant_judge_attempts')) == 1
            assert tasks.submit(actor, conversation.scope.conversation_id, request).id == attempt.id
            await finished(tasks)
            assert tasks.submit(actor, conversation.scope.conversation_id, request).state == 'received'
            assert len(calls) == len(main.provider.calls) == 1 and order == ['main']
            assert rows(database, 'assistant_judge_attempts')[0]['run_id'] == str(attempt.run_id)
            assert tasks.last_error is None
            await tasks.close()
        asyncio.run(scenario())


@pytest.mark.parametrize('missing', ['none', 'unconfigured', 'no-policy', 'wrong-hash'])
def test_main_permission_never_opens_optional_judge_without_exact_independent_permission(world, missing):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    if missing == 'none':auxiliary = None
    elif missing == 'unconfigured':auxiliary = JudgeRuntime()
    elif missing == 'no-policy':auxiliary.revoke()
    else:
        policy = auxiliary.policy
        auxiliary.grant(policy.model_copy(update={'policy_id':uuid4(), 'permissions':(
            policy.permissions[0].model_copy(update={'input_hash':'0'*64}),)}))
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert len(main.provider.calls) == 1 and not rows(database, 'assistant_judge_attempts')
        assert tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('status', ['failed', 'invalid', 'timed_out'])
def test_optional_provider_outcomes_keep_receipt_and_continue_main(world, status):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    async def answer(value, *, expected_config, preflight):
        assert preflight(value, expected_config) is None
        return result(value, expected_config, status=status)
    auxiliary.provider.judge = answer
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert len(main.provider.calls) == 1 and len(rows(database, 'assistant_judge_receipts')) == 1
        assert rows(database, 'assistant_judge_attempts')[0]['state'] == 'sent_unknown'
        assert not rows(database, 'assistant_judge_decisions') and tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


def test_optional_budget_exhaustion_does_not_roll_back_approved_main(world, monkeypatch):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    monkeypatch.setattr(judge_attempts, '_budget', lambda *_:(Decimal('.04'), 2))
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert len(main.provider.calls) == 1 and not rows(database, 'assistant_judge_attempts')
        assert tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['store', 'dto', 'version', 'budget-code', 'rollback-budget',
    'rollback-blocked', 'rollback-return'])
def test_optional_store_or_integrity_failure_cannot_be_hidden_as_missing_permission(world, monkeypatch, failure):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    def invalid(actor, run, db, runtime, **kwargs):
        if failure.startswith('rollback'):db.rollback()
        if failure == 'rollback-return':return None
        if failure == 'store':raise RuntimeError('SYNTHETIC_STORE_FAILURE')
        if failure == 'dto':
            judge_attempts.model(d.JudgePolicy, '{"synthetic_corrupt_record":true}')
        raise ServiceError({'version':'VERSION_CONFLICT', 'budget-code':'BUDGET_EXCEEDED', 'rollback-budget':'BUDGET_EXCEEDED',
            'rollback-blocked':'BLOCKED_LIVE'}[failure], 409)
    monkeypatch.setattr(judge_attempts, 'reserve', invalid)
    async def scenario():
        tasks.start()
        with pytest.raises((ServiceError, RuntimeError)):
            tasks.submit(actor, conversation.scope.conversation_id, request)
        assert not rows(database, 'assistant_messages')
        assert not rows(database, 'assistant_model_attempts')
        assert not rows(database, 'assistant_judge_attempts')
        assert tasks.active_count == 0 and not main.provider.calls
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('factory_failure', [False, True])
def test_unstarted_optional_and_main_reservations_are_both_released(world, monkeypatch, factory_failure):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    def failed_factory(*args, **kwargs):raise RuntimeError('SYNTHETIC_FACTORY_FAILURE')
    async def scenario():
        tasks.start()
        if factory_failure:
            with monkeypatch.context() as patch:
                patch.setattr(asyncio, 'create_task', failed_factory)
                with pytest.raises(ServiceError):tasks.submit(actor, conversation.scope.conversation_id, request)
        else:
            tasks.submit(actor, conversation.scope.conversation_id, request)
        await tasks.close()
        assert rows(database, 'assistant_model_attempts')[0]['state'] == 'failed_before_send'
        assert rows(database, 'assistant_judge_attempts')[0]['state'] == 'not_sent'
        assert len(rows(database, 'assistant_judge_receipts')) == 1
        assert not main.provider.calls and tasks.active_count == 0
    asyncio.run(scenario())


def test_close_while_optional_send_is_inflight_retains_unknown_cost_and_never_starts_main(world):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        entered = asyncio.Event()
        async def wait(value, *, expected_config, preflight):
            assert preflight(value, expected_config) is None
            entered.set()
            await asyncio.Event().wait()
        auxiliary.provider.judge = wait
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await asyncio.wait_for(entered.wait(), 3)
        await tasks.close()
        assert rows(database, 'assistant_judge_attempts')[0]['state'] == 'sent_unknown'
        assert rows(database, 'assistant_model_attempts')[0]['state'] == 'failed_before_send'
        receipt = judge_attempts.model(d.JudgeReceipt, rows(database, 'assistant_judge_receipts')[0]['receipt_json'])
        assert receipt.cost_status == 'unknown' and receipt.occupied_usd == Decimal('.02')
        assert not main.provider.calls and tasks.active_count == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['cancel', 'scope', 'main-policy', 'session'])
def test_main_claim_rechecks_original_authority_after_optional_wait(world, change):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def wait(value, *, expected_config, preflight):
            assert preflight(value, expected_config) is None
            entered.set()
            await release.wait()
            return result(value, expected_config)
        auxiliary.provider.judge = wait
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        await asyncio.wait_for(entered.wait(), 3)
        if change == 'main-policy':main.policy = None
        else:
            with database.session() as db:
                if change == 'cancel':
                    service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
                elif change == 'scope':
                    db.execute(text('UPDATE assistant_conversations SET materials_revision=materials_revision+1 WHERE id=:id'),
                        {'id':str(conversation.scope.conversation_id)})
                else:
                    db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
        release.set()
        await finished(tasks)
        assert not main.provider.calls
        assert rows(database, 'assistant_model_attempts')[0]['state'] == 'failed_before_send'
        assert rows(database, 'assistant_judge_attempts')[0]['state'] == 'received'
        assert len(rows(database, 'assistant_judge_receipts')) == 1
        if change != 'main-policy':assert not rows(database, 'assistant_judge_decisions')
        await tasks.close()
    asyncio.run(scenario())


def test_optional_wait_has_no_transaction_and_cannot_reselect_changed_main_runtime(world):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def wait(value, *, expected_config, preflight):
            assert preflight(value, expected_config) is None
            entered.set()
            await release.wait()
            return result(value, expected_config)
        auxiliary.provider.judge = wait
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await asyncio.wait_for(entered.wait(), 3)
        tasks.runtime = None
        def independent_draft_write():
            with database.session() as db:
                current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                service.save_draft(actor, conversation.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                    content='下一条独立合成草稿'), db)
        await asyncio.wait_for(asyncio.to_thread(independent_draft_write), 3)
        release.set()
        await finished(tasks)
        assert len(main.provider.calls) == 1 and tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


def test_old_main_attempt_never_gains_a_new_optional_attempt_or_task(world):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    with database.session() as db:
        old = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, main)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        assert tasks.submit(actor, conversation.scope.conversation_id, request) == old
        assert tasks.active_count == 0 and not rows(database, 'assistant_judge_attempts')
        await tasks.close()
        assert not main.provider.calls
    asyncio.run(scenario())


def test_explicit_skill_keeps_existing_unsupported_contract_even_with_judge_permission(world):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        with pytest.raises(ServiceError) as denied:
            tasks.submit(actor, conversation.scope.conversation_id,
                request.model_copy(update={'requested_skill':'client_reply'}))
        assert denied.value.code == 'NOT_SUPPORTED'
        assert not rows(database, 'assistant_messages') and not rows(database, 'assistant_judge_attempts')
        await tasks.close()
    asyncio.run(scenario())


def test_optional_settlement_storage_failure_stops_main_and_keeps_recovery_marker(world, monkeypatch):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    async def answer(value, *, expected_config, preflight):return result(value, expected_config)
    def failed_settlement(*args, **kwargs):raise RuntimeError('SYNTHETIC_STORE_FAILURE')
    auxiliary.provider.judge = answer
    monkeypatch.setattr(judge_attempts, 'settle', failed_settlement)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert not main.provider.calls and tasks.last_error == 'GENERATION_TASK_FAILED'
        assert rows(database, 'assistant_judge_attempts')[0]['state'] == 'sending'
        assert rows(database, 'assistant_model_attempts')[0]['state'] == 'failed_before_send'
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('invalid', [False, object(), JudgeRuntime])
def test_optional_runtime_rejects_untrusted_assembly_even_without_a_main_runtime(world, invalid):
    from fastapi import FastAPI
    from cn_contract.web.assistant_generation import attach_generation
    with pytest.raises(TypeError):GenerationTasks(world[0], world[-1], judge_runtime=invalid)
    with pytest.raises(TypeError):attach_generation(FastAPI(), world[0], judge_runtime=invalid)


def test_native_application_factory_passes_same_optional_runtime_without_granting(world):
    from cn_contract.web.local_server import build_local_app
    database, _, _, _, main = world
    auxiliary = JudgeRuntime()
    root = database.storage_root.parent
    app = build_local_app(root, data_parent=root.parent, assistant_model_runtime=main,
        assistant_judge_runtime=auxiliary)
    try:
        assert app.state.assistant_generation_tasks.judge_runtime is auxiliary
        assert auxiliary.policy is None and auxiliary.provider is None
    finally:
        app.state.database.engine.dispose()


def test_input_supported_by_main_but_over_optional_wire_limit_skips_only_judge(world):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world, config=d.JevConfig(enabled=True, max_input_bytes=1))
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert len(main.provider.calls) == 1 and not rows(database, 'assistant_judge_attempts')
        assert tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


def test_existing_generation_route_uses_optional_runtime_without_an_http_permission_route(world):
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from cn_contract.security import authenticate
    from cn_contract.web.local_server import build_local_app
    from tests.integration.test_assistant_generation_routes import signin, save_draft, wait_attempt
    database, _, conversation, request, main = world
    auxiliary, _ = judge(world)
    async def answer(value, *, expected_config, preflight):
        assert preflight(value, expected_config) is None
        return result(value, expected_config)
    auxiliary.provider.judge = answer
    root = database.storage_root.parent
    app = build_local_app(root, data_parent=root.parent, assistant_model_runtime=main,
        assistant_judge_runtime=auxiliary)
    with TestClient(app) as client:
        headers = signin(client)
        with database.session() as db:
            actor = authenticate(client.cookies.get('qx_session'), db)
        auxiliary.grant(auxiliary.policy.model_copy(update={'policy_id':uuid4(), 'session_id':actor.session_id}))
        http = SimpleNamespace(client=client, headers=headers, body=request.model_dump(mode='json'),
            url='/api/assistant/conversations/'+str(conversation.scope.conversation_id))
        save_draft(http)
        response = client.post(http.url+'/generations', headers=headers, json=http.body)
        assert response.status_code == 202, response.text
        assert wait_attempt(http, response.json()['id'])['state'] == 'received'
        assert len(main.provider.calls) == 1 and len(rows(database, 'assistant_judge_receipts')) == 1
        assert len(rows(database, 'assistant_judge_decisions')) == 1
        assert all('judge' not in route.path for route in app.routes)


@pytest.mark.parametrize('point', ['configuration', 'snapshot'])
def test_permission_expiring_during_admission_never_rolls_back_approved_main(world, monkeypatch, point):
    from cn_contract.assistant.providers import judge_policy
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    original = auxiliary.snapshot_for if point == 'snapshot' else auxiliary.configuration
    expired = False
    at = datetime.now(timezone.utc)
    class Clock:
        @staticmethod
        def now(tz):return at + (timedelta(minutes=10) if expired else timedelta())
    def snapshot(*args):
        nonlocal expired
        value = original(*args)
        expired = True
        return value
    monkeypatch.setattr(judge_policy, 'datetime', Clock)
    monkeypatch.setattr(auxiliary, 'snapshot_for' if point == 'snapshot' else 'configuration', snapshot)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        tasks.submit(actor, conversation.scope.conversation_id, request)
        await finished(tasks)
        assert len(main.provider.calls) == 1 and tasks.last_error is None
        assert all(row['state'] == 'not_sent' for row in rows(database, 'assistant_judge_attempts'))
        await tasks.close()
    asyncio.run(scenario())


def test_corrupt_judge_readback_after_insert_rolls_back_both_new_ledgers(world, monkeypatch):
    database, actor, conversation, request, main = world
    auxiliary, _ = judge(world)
    original = judge_attempts._row
    def bad_readback(*args):
        row = dict(original(*args))
        row['request_json'] = '{"synthetic_corrupt_record":true}'
        return row
    monkeypatch.setattr(judge_attempts, '_row', bad_readback)
    tasks = GenerationTasks(database, main, judge_runtime=auxiliary)
    async def scenario():
        tasks.start()
        with pytest.raises(ServiceError) as failure:
            tasks.submit(actor, conversation.scope.conversation_id, request)
        assert failure.value.code == 'BLOCKED_LIVE'
        assert not rows(database, 'assistant_messages')
        assert not rows(database, 'assistant_model_attempts')
        assert not rows(database, 'assistant_judge_attempts')
        assert tasks.active_count == 0 and not main.provider.calls
        await tasks.close()
    asyncio.run(scenario())
