"""Application-owned execution over real synthetic records, without provider I/O."""
import asyncio
import importlib.util
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import world


def manager(world):
    name = 'cn_contract.assistant.task_manager'
    assert importlib.util.find_spec(name) is not None, 'application-scoped GenerationTasks is required'
    from cn_contract.assistant.task_manager import GenerationTasks
    return GenerationTasks(world[0], world[-1])


async def finished(tasks):
    async with asyncio.timeout(3):
        while tasks.active_count:
            await asyncio.sleep(0)
        # Deliver done callbacks as well as the provider's completed await.
        await asyncio.sleep(0)


def read(world, identifier, actor=None):
    with world[0].session() as db:
        return attempts.read_attempt(actor or world[1], identifier, db)


def test_submit_commits_before_dispatch_and_replay_never_dispatches_twice(world):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    original = runtime.provider.generate
    committed = []
    async def probe(value, **kwargs):
        # A separate connection sees committed input before any provider work.
        with database.session() as db:
            committed.append(db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')))
        return await original(value, **kwargs)
    runtime.provider.generate = probe
    async def scenario():
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        assert first.state == 'reserved' and not runtime.provider.calls
        assert tasks.submit(actor, conversation.scope.conversation_id, request).id == first.id
        await finished(tasks)
        result = tasks.submit(actor, conversation.scope.conversation_id, request)
        assert result.state == 'received' and result.output.review_status == 'unverified'
        assert committed == [1] and len(runtime.provider.calls) == 1
        assert tasks.active_count == 0 and tasks.accepting and tasks.last_error is None
        await tasks.close()
    asyncio.run(scenario())


def test_immediate_close_seals_unsent_task_without_entering_runner(world):
    _, actor, conversation, request, runtime = world
    tasks = manager(world)
    async def scenario():
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        await tasks.close()
        result = read(world, first.id)
        assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
        assert result.receipt.estimated_cost_usd == 0 and result.output is None
        assert not runtime.provider.calls and tasks.active_count == 0 and not tasks.accepting
    asyncio.run(scenario())


@pytest.mark.parametrize('old_kind', ['queued', 'reserved'])
def test_old_records_and_restarts_never_acquire_dispatch_eligibility(world, old_kind):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        old = (service.save_message(actor, conversation.scope.conversation_id, request, db)
               if old_kind == 'queued' else attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime))
    tasks = manager(world)
    async def scenario():
        for _ in range(2):
            tasks.start()
            if old_kind == 'queued':
                with pytest.raises(ServiceError) as failure:
                    tasks.submit(actor, conversation.scope.conversation_id, request)
                assert failure.value.code == 'STATE_CONFLICT'
            else:
                assert tasks.submit(actor, conversation.scope.conversation_id, request) == old
            await tasks.close()
        if old_kind == 'reserved':
            # Closed replay validates and returns history but cannot start work.
            assert tasks.submit(actor, conversation.scope.conversation_id, request) == old
            assert read(world, old.id).state == 'reserved'
        assert not runtime.provider.calls and tasks.active_count == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('closed', [False, True])
def test_new_submission_requires_running_lifecycle_without_partial_rows(world, closed):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    async def scenario():
        if closed:
            tasks.start()
            await tasks.close()
        with pytest.raises(ServiceError) as failure:
            tasks.submit(actor, conversation.scope.conversation_id, request)
        assert failure.value.code == 'STATE_CONFLICT'
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert not tasks.accepting and not runtime.provider.calls
    asyncio.run(scenario())


@pytest.mark.parametrize('skill', ['client_reply','material_organize','contract_review','content_draft','legal_research'])
def test_requested_skill_is_not_dispatched_as_generic_generation(world, skill):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    async def scenario():
        tasks.start()
        with pytest.raises(ServiceError) as failure:
            tasks.submit(actor, conversation.scope.conversation_id, request.model_copy(update={'requested_skill':skill}))
        assert failure.value.code == 'NOT_SUPPORTED'
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        await tasks.close()
        assert not runtime.provider.calls
    asyncio.run(scenario())


def test_four_active_tasks_bound_admission_but_not_same_key_replay(world):
    database, actor, _, request, runtime = world
    tasks = manager(world)
    with database.session() as db:
        conversations = [service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db) for _ in range(5)]
    async def scenario():
        tasks.start()
        requests = [request.model_copy(update={'request_id':uuid4(), 'expected_scope':c.scope}) for c in conversations]
        started = [tasks.submit(actor, c.scope.conversation_id, r) for c, r in zip(conversations[:4], requests[:4])]
        assert tasks.active_count == 4 and not tasks.accepting
        assert tasks.submit(actor, conversations[0].scope.conversation_id, requests[0]).id == started[0].id
        with pytest.raises(ServiceError) as failure:
            tasks.submit(actor, conversations[4].scope.conversation_id, requests[4])
        assert failure.value.code == 'ASSISTANT_BUSY' and failure.value.retryable
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 4
        await tasks.close()
        assert not runtime.provider.calls
        tasks.start()
        tasks.submit(actor, conversations[4].scope.conversation_id, requests[4])
        await finished(tasks)
        assert len(runtime.provider.calls) == 1
        await tasks.close()
    asyncio.run(scenario())


def test_same_key_in_two_managers_is_owned_only_by_first_registration(world):
    _, actor, conversation, request, runtime = world
    first, second = manager(world), manager(world)
    async def scenario():
        first.start(); second.start()
        original = first.submit(actor, conversation.scope.conversation_id, request)
        assert second.submit(actor, conversation.scope.conversation_id, request).id == original.id
        assert first.active_count == 1 and second.active_count == 0
        await finished(first)
        await first.close(); await second.close()
        assert len(runtime.provider.calls) == 1
    asyncio.run(scenario())


def test_dispatch_factory_failure_is_sealed_unsent_and_not_retried(world, monkeypatch, caplog):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    def failed_factory(coro, **kwargs):
        raise RuntimeError('SYNTHETIC_FACTORY_SECRET_CANARY')
    async def scenario():
        tasks.start()
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, 'create_task', failed_factory)
            with pytest.raises(ServiceError) as failure:
                tasks.submit(actor, conversation.scope.conversation_id, request)
            assert failure.value.code == 'STATE_CONFLICT'
        result = tasks.submit(actor, conversation.scope.conversation_id, request)
        assert result.state == 'failed_before_send' and result.receipt.cost_status == 'not_sent'
        assert tasks.last_error == 'GENERATION_TASK_FAILED' and tasks.active_count == 0
        assert not runtime.provider.calls
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
        await tasks.close()
    asyncio.run(scenario())
    assert 'SYNTHETIC_FACTORY_SECRET_CANARY' not in caplog.text


def test_inflight_draft_write_keeps_candidate_valid_and_response_not_logged(world, caplog):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    original = runtime.provider.generate
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(value, **kwargs):
            entered.set()
            await release.wait()
            return await original(value, **kwargs)
        runtime.provider.generate = waiting
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        await asyncio.wait_for(entered.wait(), 3)
        def write_draft():
            with database.session() as db:
                current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                service.save_draft(actor, conversation.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                    content='独立合成正在输入的新草稿'), db)
        await asyncio.wait_for(asyncio.to_thread(write_draft), 3)
        release.set()
        await finished(tasks)
        result = read(world, first.id)
        assert result.output is not None and result.output.review_status == 'unverified'
        assert result.output.candidate.text not in caplog.text
        await tasks.close()
    asyncio.run(scenario())


def test_close_cancels_network_once_even_if_shutdown_caller_is_cancelled_twice(world):
    _, actor, conversation, request, runtime = world
    tasks = manager(world)
    async def scenario():
        entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        cancellations = []
        async def waiting(value, **kwargs):
            runtime.provider.calls.append(value)
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellations.append(True)
                cancelling.set()
                await release.wait()
                raise
        runtime.provider.generate = waiting
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        await asyncio.wait_for(entered.wait(), 3)
        closing = asyncio.create_task(tasks.close())
        await asyncio.wait_for(cancelling.wait(), 3)
        assert not tasks.accepting
        closing.cancel(); await asyncio.sleep(0)
        closing.cancel(); await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(closing, 3)
        result = read(world, first.id)
        assert result.state == 'sent_unknown' and result.receipt.cost_status == 'unknown'
        assert result.output is None and result.receipt.estimated_cost_usd is None
        assert cancellations == [True] and tasks.active_count == 0
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoked_before', 'revoked_during', 'provider_exception'])
def test_task_failure_and_revocation_leave_fixed_receipts_and_cleanup(world, change, caplog):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    original = runtime.provider.generate
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(value, **kwargs):
            entered.set()
            await release.wait()
            if change == 'provider_exception':
                raise RuntimeError('SYNTHETIC_PROVIDER_SECRET_CANARY')
            return await original(value, **kwargs)
        runtime.provider.generate = waiting
        tasks.start()
        first = tasks.submit(actor, conversation.scope.conversation_id, request)
        if change != 'revoked_before':
            await asyncio.wait_for(entered.wait(), 3)
        if change.startswith('revoked'):
            with database.session() as db:
                db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
        release.set()
        await finished(tasks)
        with database.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            fresh = authenticate(token, db)
        result = read(world, first.id, fresh)
        assert result.output is None
        expected = {'revoked_before':('failed_before_send','not_sent'),
                    'revoked_during':('received','estimated'), 'provider_exception':('sent_unknown','unknown')}[change]
        assert (result.state, result.receipt.cost_status) == expected
        if change.startswith('revoked'):
            assert tasks.last_error == 'GENERATION_TASK_FAILED'
        assert tasks.active_count == 0
        await tasks.close()
    asyncio.run(scenario())
    assert 'SYNTHETIC_PROVIDER_SECRET_CANARY' not in caplog.text


@pytest.mark.parametrize('failure_kind', ['missing_policy', 'unauthorized', 'stale_scope'])
def test_failed_registration_creates_no_task_or_attempt(world, failure_kind):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    if failure_kind == 'missing_policy': runtime.policy = None
    elif failure_kind == 'unauthorized': actor = actor.model_copy(update={'session_id':uuid4()})
    else: request = request.model_copy(update={'expected_composer_revision':99})
    async def scenario():
        tasks.start()
        with pytest.raises(ServiceError):
            tasks.submit(actor, conversation.scope.conversation_id, request)
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert tasks.active_count == 0 and not runtime.provider.calls
        await tasks.close()
    asyncio.run(scenario())


def test_failed_commit_rolls_back_registration_before_any_dispatch(world):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    def fail_commit(db):
        raise RuntimeError('SYNTHETIC_COMMIT_FAILURE')
    async def scenario():
        tasks.start()
        event.listen(database.session_factory, 'before_commit', fail_commit)
        try:
            with pytest.raises(RuntimeError, match='SYNTHETIC_COMMIT_FAILURE'):
                tasks.submit(actor, conversation.scope.conversation_id, request)
        finally:
            event.remove(database.session_factory, 'before_commit', fail_commit)
        await asyncio.sleep(0)
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert not runtime.provider.calls and tasks.active_count == 0
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('failure_kind', ['claim', 'settle', 'release'])
def test_background_persistence_failure_is_observed_without_retry_or_private_log(world, failure_kind, monkeypatch, caplog):
    database, actor, conversation, request, runtime = world
    tasks = manager(world)
    failures = []
    def fail(*args, **kwargs):
        raise RuntimeError('SYNTHETIC_BACKGROUND_SECRET_CANARY')
    async def scenario():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda loop, context: failures.append(context))
        tasks.start()
        with monkeypatch.context() as patch:
            name = 'cancel_reserved_for_run' if failure_kind == 'release' else failure_kind
            patch.setattr(attempts, name, fail)
            first = tasks.submit(actor, conversation.scope.conversation_id, request)
            if failure_kind == 'release':
                await tasks.close()
            else:
                await finished(tasks)
                await tasks.close()
        result = read(world, first.id)
        expected = {'claim':'failed_before_send', 'settle':'sending', 'release':'reserved'}[failure_kind]
        assert result.state == expected
        if failure_kind == 'claim':
            assert result.receipt.cost_status == 'not_sent'
        else:
            assert result.receipt is None and result.output is None
        assert tasks.last_error == 'GENERATION_TASK_FAILED' and tasks.active_count == 0
        tasks.start()
        assert tasks.submit(actor, conversation.scope.conversation_id, request) == result
        await tasks.close()
        assert len(runtime.provider.calls) == int(failure_kind == 'settle')
        assert not failures
    asyncio.run(scenario())
    assert 'SYNTHETIC_BACKGROUND_SECRET_CANARY' not in caplog.text


def test_shutdown_releases_only_its_own_new_reservation(world):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        old = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)
        other = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    tasks = manager(world)
    async def scenario():
        tasks.start()
        new = tasks.submit(actor, other.scope.conversation_id, request.model_copy(update={
            'request_id':uuid4(), 'expected_scope':other.scope}))
        await tasks.close()
        assert read(world, old.id).state == 'reserved'
        released = read(world, new.id)
        assert released.state == 'failed_before_send' and released.receipt.cost_status == 'not_sent'
        assert not runtime.provider.calls
    asyncio.run(scenario())
