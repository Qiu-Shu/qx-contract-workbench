"""Synthetic application-service tests; no real provider/account is used."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.local_server import initialize_workspace


class SyntheticProvider:
    def __init__(self, config):
        self.config = config
        self.calls = []

    async def generate(self, request, *, expected_config=None):
        self.calls.append(request)
        return d.MainReply(state='received', provider_request_id='fictional-response',
            usage=d.MainUsage(prompt_tokens=20, completion_tokens=10, total_tokens=30),
            output=d.MainCandidate(text='独立虚构回复，请律师核对。', citations=(
                d.MainCitation(message_id=request.message_id, quote_sha256=request.source_sha256),)))


@pytest.fixture
def world(tmp_path):
    root = tmp_path/'合成生成工作区'
    initialize_workspace(root, 'lawyer', 'fixture123', data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected', load_settings(), initialize_schema=False)
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    request = d.AssistantMessageInput(request_id=uuid4(), expected_scope=conversation.scope,
        expected_composer_revision=0, content='完全合成问题：请整理虚构的交货咨询。')
    config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='synthetic-ceiling')
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=conversation.scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(config)), allowed_content_sha256s=(sha(request.content),),
        max_total_usd='1', max_calls=5, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    runtime = MainModelRuntime(SyntheticProvider(config), policy)
    yield database, actor, conversation, request, runtime
    database.engine.dispose()


def test_explicit_generation_preserves_input_and_records_candidate_once(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation, read_attempt
    from cn_contract.assistant.runner import execute_attempt
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        first = enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
    assert first.state == 'reserved' and first.receipt is None and first.output is None
    completed = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    assert completed.state == 'received'
    assert completed.receipt.estimated_cost_usd == Decimal('0.000018')
    assert completed.receipt.cost_status == 'estimated'
    assert completed.output.review_status == 'unverified' and completed.output.audience == 'internal'
    with database.session() as db:
        assert enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime) == completed
        assert read_attempt(actor, first.id, db) == completed
        messages = service.read_conversation(actor, conversation.scope.conversation_id, db).messages
        assert len(messages) == 1 and messages[0].content == request.content
    assert asyncio.run(execute_attempt(actor, first.id, database, runtime)) == completed
    assert len(runtime.provider.calls) == 1


def enqueue(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        return enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)


@pytest.mark.parametrize('change', ['disabled', 'missing', 'expired', 'actor', 'workspace', 'configuration', 'content'])
def test_no_approved_policy_keeps_original_draft_and_sends_nothing(world, change):
    database, actor, conversation, request, runtime = world
    if change == 'disabled':
        runtime.provider.config = runtime.provider.config.model_copy(update={'enabled':False})
    elif change == 'missing':
        runtime.policy = None
    else:
        values = {'expired':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)},
            'actor':{'actor_id':uuid4()}, 'workspace':{'workspace_id':uuid4()},
            'configuration':{'config_sha256':'0'*64}, 'content':{'allowed_content_sha256s':('0'*64,)}}
        runtime.policy = runtime.policy.model_copy(update=values[change])
    with pytest.raises(ServiceError, match='request') as failure:
        enqueue(world)
    assert failure.value.code == 'BLOCKED_LIVE'
    with database.session() as db:
        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
    assert current.messages == () and current.scope.input_revision == 0
    assert runtime.provider.calls == []


def test_legacy_queued_is_not_adopted_and_same_key_changed_body_is_rejected(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        service.save_message(actor, conversation.scope.conversation_id, request, db)
        with pytest.raises(ServiceError) as failure:
            enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
    assert failure.value.code == 'STATE_CONFLICT' and not runtime.provider.calls


def test_replay_different_content_or_policy_does_not_change_receipt(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation, read_attempt
    database, actor, conversation, request, runtime = world
    first = enqueue(world)
    with database.session() as db:
        with pytest.raises(ServiceError) as failure:
            enqueue_generation(actor, conversation.scope.conversation_id,
                request.model_copy(update={'content':'另一条合成消息'}), db, runtime)
        assert failure.value.code == 'VERSION_CONFLICT'
        runtime.policy = runtime.policy.model_copy(update={'max_calls':6})
        with pytest.raises(ServiceError) as failure:
            enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
        assert failure.value.code == 'VERSION_CONFLICT'
        assert read_attempt(actor, first.id, db) == first


def test_concurrent_execute_claims_only_once(world):
    from cn_contract.assistant.runner import execute_attempt
    database, actor, _, _, runtime = world
    first = enqueue(world)
    original = runtime.provider.generate
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(request, **kwargs):
            entered.set()
            await release.wait()
            return await original(request, **kwargs)
        runtime.provider.generate = waiting
        first_task = asyncio.create_task(execute_attempt(actor, first.id, database, runtime))
        await asyncio.wait_for(entered.wait(), 3)
        second = await execute_attempt(actor, first.id, database, runtime)
        assert second.state == 'sending' and second.receipt is None
        release.set()
        result = await first_task
        assert result.output is not None
    asyncio.run(scenario())
    assert len(runtime.provider.calls) == 1


@pytest.mark.parametrize('outcome', ['timeout', 'unknown_usage', 'invalid_output', 'unsent'])
def test_response_accounting_does_not_invent_zero_or_retry(world, outcome):
    from cn_contract.assistant.runner import execute_attempt
    database, actor, _, _, runtime = world
    first = enqueue(world)
    calls = []
    async def generate(request, **kwargs):
        calls.append(request)
        if outcome == 'timeout':
            raise TimeoutError('SYNTHETIC_PRIVATE_ERROR_CANARY')
        if outcome == 'unknown_usage':
            return d.MainReply(state='received', output=d.MainCandidate(text='合成候选'))
        if outcome == 'unsent':
            return d.MainReply(state='failed_before_send', error_code='BLOCKED_LIVE')
        return d.MainReply(state='received', usage=d.MainUsage(prompt_tokens=20,completion_tokens=10,total_tokens=30),
            error_code='MODEL_OUTPUT_INVALID')
    runtime.provider.generate = generate
    result = asyncio.run(execute_attempt(actor, first.id, database, runtime))
    assert asyncio.run(execute_attempt(actor, first.id, database, runtime)) == result
    assert len(calls) == 1
    if outcome in {'timeout','unknown_usage'}:
        assert result.receipt.cost_status == 'unknown' and result.receipt.estimated_cost_usd is None
    elif outcome == 'unsent':
        assert result.receipt.cost_status == 'not_sent' and result.receipt.estimated_cost_usd == 0
    else:
        assert result.receipt.cost_status == 'estimated' and result.receipt.estimated_cost_usd == Decimal('0.000018')
    assert (result.output is not None) == (outcome == 'unknown_usage')
    assert 'SYNTHETIC_PRIVATE_ERROR_CANARY' not in result.model_dump_json()


@pytest.mark.parametrize('change', ['cancel','scope','policy','config','invalid_config','session'])
def test_changes_during_network_keep_receipt_but_discard_candidate(world, change):
    from cn_contract.assistant.runner import execute_attempt
    from cn_contract.assistant.providers.attempts import read_attempt
    database, actor, conversation, _, runtime = world
    first = enqueue(world)
    original = runtime.provider.generate
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(request, **kwargs):
            entered.set()
            await release.wait()
            return await original(request, **kwargs)
        runtime.provider.generate = waiting
        task = asyncio.create_task(execute_attempt(actor, first.id, database, runtime))
        await asyncio.wait_for(entered.wait(), 3)
        # This independent connection must complete while the provider still awaits.
        def mutate():
            with database.session() as db:
                current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                service.save_draft(actor, conversation.scope.conversation_id,
                    d.AssistantDraftInput(expected_scope=current.scope,
                        expected_composer_revision=current.composer_revision, content='网络等待中继续记笔记'), db)
                if change == 'cancel':
                    service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
                elif change == 'scope':
                    db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),
                               {'id':str(conversation.scope.conversation_id)})
                elif change == 'session':
                    db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
        await asyncio.wait_for(asyncio.to_thread(mutate), 3)
        if change == 'policy':
            runtime.policy = None
        if change == 'config':
            runtime.provider.config = runtime.provider.config.model_copy(update={'enabled':False})
        if change == 'invalid_config':
            runtime.provider.config = runtime.provider.config.model_copy(update={'max_input_bytes':-1})
        release.set()
        if change == 'session':
            with pytest.raises(ServiceError) as failure:
                await task
            assert failure.value.code == 'AUTHORIZATION_REQUIRED'
        else:
            result = await task
            assert result.receipt.estimated_cost_usd == Decimal('0.000018')
            assert result.output is None
    asyncio.run(scenario())
    with database.session() as db:
        token, _ = login('lawyer','fixture123',db)
        fresh = authenticate(token,db)
        result = read_attempt(fresh,first.id,db)
    assert result.output is None and result.receipt.cost_status == 'estimated'
    assert len(runtime.provider.calls) == 1


def test_budget_and_call_limit_are_atomic_across_conversations(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation
    database, actor, first, request, runtime = world
    runtime.policy = runtime.policy.model_copy(update={'max_calls':1})
    with database.session() as db:
        second = service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
    barrier = Barrier(2)
    def submit(conversation):
        barrier.wait(timeout=5)
        candidate = request.model_copy(update={'request_id':uuid4(), 'expected_scope':conversation.scope})
        try:
            with database.session() as db:
                return enqueue_generation(actor,conversation.scope.conversation_id,candidate,db,runtime).state
        except ServiceError as failure:
            return failure.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(submit,(first,second)))
    assert sorted(result) == ['CALL_LIMIT_EXCEEDED','reserved']


def test_insufficient_budget_has_no_partial_message_even_if_error_is_caught(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation
    database, actor, conversation, request, runtime = world
    runtime.policy = runtime.policy.model_copy(update={'max_total_usd':Decimal('0.000001')})
    with database.session() as db:
        with pytest.raises(ServiceError) as failure:
            enqueue_generation(actor,conversation.scope.conversation_id,request,db,runtime)
        assert failure.value.code == 'BUDGET_EXCEEDED'
        assert service.read_conversation(actor,conversation.scope.conversation_id,db).messages == ()


@pytest.mark.parametrize('claimed', [False,True])
def test_restart_recovery_never_dispatches_reserved_or_sending(world, claimed):
    from cn_contract.assistant.providers.attempts import claim, recover_attempts, read_attempt
    from cn_contract.assistant.runner import execute_attempt
    database, actor, _, _, runtime = world
    first = enqueue(world)
    if claimed:
        with database.session() as db:
            assert claim(actor,first.id,db,runtime) is not None
    with database.session() as db:
        assert recover_attempts(db) == 1
        assert recover_attempts(db) == 0
        result = read_attempt(actor,first.id,db)
    assert result.state == ('sent_unknown' if claimed else 'failed_before_send')
    assert result.receipt.cost_status == ('unknown' if claimed else 'not_sent')
    assert asyncio.run(execute_attempt(actor,first.id,database,runtime)) == result
    assert not runtime.provider.calls


def test_task_cancellation_preserves_unknown_receipt(world):
    from cn_contract.assistant.providers.attempts import read_attempt
    from cn_contract.assistant.runner import execute_attempt
    database,actor,_,_,runtime = world
    first = enqueue(world)
    async def scenario():
        entered=asyncio.Event()
        async def wait_forever(request, **kwargs):
            entered.set()
            await asyncio.Event().wait()
        runtime.provider.generate=wait_forever
        task=asyncio.create_task(execute_attempt(actor,first.id,database,runtime))
        await asyncio.wait_for(entered.wait(),3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    with database.session() as db:
        result=read_attempt(actor,first.id,db)
    assert result.state == 'sent_unknown' and result.receipt.estimated_cost_usd is None


def test_over_budget_receipt_blocks_already_reserved_second_attempt(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation
    from cn_contract.assistant.providers.policy import reservation
    from cn_contract.assistant.runner import execute_attempt
    database,actor,conversation,request,runtime=world
    runtime.policy=runtime.policy.model_copy(update={'max_total_usd':reservation(runtime.provider.config)*2})
    first=enqueue(world)
    with database.session() as db:
        second=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        pending=enqueue_generation(actor,second.scope.conversation_id,
            request.model_copy(update={'request_id':uuid4(),'expected_scope':second.scope}),db,runtime)
    calls=[]
    async def expensive(_, **kwargs):
        calls.append(True)
        return d.MainReply(state='received',usage=d.MainUsage(prompt_tokens=1000000,completion_tokens=0,total_tokens=1000000),
            error_code='MODEL_OUTPUT_INVALID')
    runtime.provider.generate=expensive
    result=asyncio.run(execute_attempt(actor,first.id,database,runtime))
    assert result.receipt.estimated_cost_usd == Decimal('0.3')
    blocked=asyncio.run(execute_attempt(actor,pending.id,database,runtime))
    assert len(calls)==1
    assert blocked.state=='failed_before_send' and blocked.output is None


def test_cancel_before_claim_releases_unused_call_and_budget(world):
    from cn_contract.assistant.providers.attempts import enqueue_generation,read_attempt
    database,actor,conversation,request,runtime=world
    runtime.policy=runtime.policy.model_copy(update={'max_calls':1})
    first=enqueue(world)
    with database.session() as db:
        service.cancel_run(actor,first.run_id,d.AssistantCancelInput(request_id=uuid4()),db)
        cancelled=read_attempt(actor,first.id,db)
        assert cancelled.state=='failed_before_send'
        assert cancelled.receipt.cost_status=='not_sent'
        latest=service.read_conversation(actor,conversation.scope.conversation_id,db)
        second=enqueue_generation(actor,conversation.scope.conversation_id,request.model_copy(update={
            'request_id':uuid4(),'expected_scope':latest.scope,'expected_composer_revision':latest.composer_revision}),db,runtime)
    assert second.state=='reserved' and not runtime.provider.calls


def test_usage_above_reserved_envelope_keeps_receipt_without_adopting_candidate(world):
    from cn_contract.assistant.runner import execute_attempt
    database,actor,_,_,runtime=world
    first=enqueue(world)
    original=runtime.provider.generate
    async def expensive(request, **kwargs):
        reply=await original(request, **kwargs)
        return reply.model_copy(update={'usage':d.MainUsage(prompt_tokens=1000000,completion_tokens=0,total_tokens=1000000)})
    runtime.provider.generate=expensive
    result=asyncio.run(execute_attempt(actor,first.id,database,runtime))
    assert result.receipt.estimated_cost_usd == Decimal('0.3')
    assert result.output is None


def test_changed_wire_contract_before_claim_sends_nothing(world, monkeypatch):
    from cn_contract.assistant.providers import policy
    from cn_contract.assistant.runner import execute_attempt
    database,actor,_,_,runtime=world
    first=enqueue(world)
    original=policy.build_request
    def altered(request,config):
        result=original(request,config)
        result['messages'][0]['content']+='合成契约版本变动'
        return result
    monkeypatch.setattr(policy,'build_request',altered)
    result=asyncio.run(execute_attempt(actor,first.id,database,runtime))
    assert result.state=='failed_before_send' and result.receipt.cost_status=='not_sent'
    assert not runtime.provider.calls


@pytest.mark.parametrize('after_enqueue', [False, True])
def test_local_only_material_never_acquires_external_permission(world, after_enqueue):
    from io import BytesIO
    from cn_contract.assistant import attachments
    from cn_contract.assistant.providers.attempts import enqueue_generation
    from cn_contract.assistant.runner import execute_attempt
    from tests.integration.test_assistant_attachments import sample
    import hashlib
    database,actor,conversation,request,runtime=world
    first=enqueue(world) if after_enqueue else None
    with database.session() as db:
        current=service.read_conversation(actor,conversation.scope.conversation_id,db)
    raw=sample()
    database._assistant_synthetic_hashes=frozenset({hashlib.sha256(raw).hexdigest()})
    attachment=attachments.ingest_attachment(actor,conversation.scope.conversation_id,
        d.AssistantAttachmentInput(request_id=uuid4(),expected_scope=current.scope,
            original_name='仅本机合成材料.docx',mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),BytesIO(raw),database=database)
    assert attachment.attachment.policy.external_processing is False
    if first:
        result=asyncio.run(execute_attempt(actor,first.id,database,runtime))
        assert result.state=='failed_before_send'
    else:
        with database.session() as db:
            current=service.read_conversation(actor,conversation.scope.conversation_id,db)
            with pytest.raises(ServiceError) as failure:
                enqueue_generation(actor,conversation.scope.conversation_id,request.model_copy(update={
                    'expected_scope':current.scope,'expected_composer_revision':current.composer_revision}),db,runtime)
            assert failure.value.code=='BLOCKED_LIVE'
            assert not current.messages
    assert not runtime.provider.calls
