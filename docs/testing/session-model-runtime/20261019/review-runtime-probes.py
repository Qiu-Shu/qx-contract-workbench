"""Independent local application/ledger probes; fake provider, no HTTP transport."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import SyntheticProvider, world


def registry_for(runtime, actor):
    registry = MainModelRegistry()
    registry.configure(runtime.provider)
    registry.grant(runtime.policy, actor.session_id)
    return registry


def another_conversation(database, actor, request):
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
    return conversation, request.model_copy(update={
        'request_id': uuid4(), 'expected_scope': conversation.scope, 'expected_composer_revision': 0})


async def finish(tasks):
    for _ in range(30):
        if not tasks.active_count:
            return
        await asyncio.sleep(0)
    raise AssertionError('synthetic tasks failed to finish')


def test_same_user_other_session_cannot_enqueue_with_borrowed_lease(world):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        other = authenticate(token, db)
    async def scenario():
        registry = registry_for(runtime, actor)
        registry.grant(runtime.policy, other.session_id)
        lease = registry.resolve(actor, conversation.scope)
        with database.session() as db:
            with pytest.raises(ServiceError) as failure:
                attempts.enqueue_generation(other, conversation.scope.conversation_id, request, db, lease)
            assert failure.value.code == 'BLOCKED_LIVE'
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert runtime.provider.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoke-regrant', 'same-config-reconfigure'])
def test_aba_before_claim_never_resolves_again_or_sends(world, change):
    database, actor, conversation, request, runtime = world
    async def scenario():
        registry = registry_for(runtime, actor)
        resolves = []
        original = registry.resolve
        def observed(*args):
            resolves.append(args)
            return original(*args)
        registry.resolve = observed
        tasks = GenerationTasks(database, registry)
        tasks.start()
        view = tasks.submit(actor, conversation.scope.conversation_id, request)
        if change == 'revoke-regrant':
            registry.revoke(actor.session_id)
        else:
            registry.configure(runtime.provider)
        registry.grant(runtime.policy, actor.session_id)
        await finish(tasks)
        assert len(resolves) == 1
        assert runtime.provider.calls == []
        with database.session() as db:
            result = attempts.read_attempt(actor, view.id, db)
            assert result.state == 'failed_before_send'
            assert result.receipt.cost_status == 'not_sent'
            assert result.output is None
        await tasks.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoke-regrant', 'new-provider-same-config'])
def test_aba_during_provider_keeps_old_receipt_without_publishing(world, change):
    database, actor, conversation, request, runtime = world
    async def scenario():
        registry = registry_for(runtime, actor)
        lease = registry.resolve(actor, conversation.scope)
        with database.session() as db:
            view = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, lease)
        entered, release = asyncio.Event(), asyncio.Event()
        original = runtime.provider.generate
        async def held(request, *, expected_config=None):
            entered.set()
            await release.wait()
            return await original(request, expected_config=expected_config)
        runtime.provider.generate = held
        task = asyncio.create_task(execute_attempt(actor, view.id, database, lease))
        await entered.wait()
        replacement = SyntheticProvider(runtime.provider.config)
        if change == 'revoke-regrant':
            registry.revoke(actor.session_id)
        else:
            registry.configure(replacement)
        registry.grant(runtime.policy, actor.session_id)
        release.set()
        result = await task
        assert len(runtime.provider.calls) == 1
        assert replacement.calls == []
        assert result.state == 'received'
        assert result.receipt.cost_status == 'estimated'
        assert result.receipt.usage.total_tokens == 30
        assert result.output is None
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
    asyncio.run(scenario())


def test_cross_thread_and_other_loop_mutation_rejected_without_damaging_live_grant(world):
    _, actor, conversation, _, runtime = world
    async def scenario():
        registry = registry_for(runtime, actor)
        lease = registry.resolve(actor, conversation.scope)
        def foreign_thread():
            operations = [lambda: registry.configure(None), lambda: registry.revoke(actor.session_id),
                lambda: registry.grant(runtime.policy, actor.session_id),
                lambda: registry.resolve(actor, conversation.scope),
                lambda: lease.snapshot_for(actor, conversation.scope)]
            for operation in operations:
                with pytest.raises(ServiceError) as failure:
                    operation()
                assert failure.value.code == 'BLOCKED_LIVE'
            async def other_loop():
                with pytest.raises(ServiceError) as failure:
                    registry.revoke(actor.session_id)
                assert failure.value.code == 'BLOCKED_LIVE'
            asyncio.run(other_loop())
        await asyncio.to_thread(foreign_thread)
        assert lease.snapshot_for(actor, conversation.scope) == runtime.snapshot()
        assert runtime.provider.calls == []
    asyncio.run(scenario())


def test_revocation_immediately_after_claim_does_not_release_unknown_budget(world, monkeypatch):
    database, actor, conversation, request, runtime = world
    async def scenario():
        registry = registry_for(runtime, actor)
        lease = registry.resolve(actor, conversation.scope)
        with database.session() as db:
            view = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, lease)
        original = attempts.claim
        def revoke_after_claim(*args, **kwargs):
            claimed = original(*args, **kwargs)
            registry.revoke(actor.session_id)
            return claimed
        monkeypatch.setattr(attempts, 'claim', revoke_after_claim)
        result = await execute_attempt(actor, view.id, database, lease)
        assert result.state == 'sent_unknown'
        assert result.receipt.cost_status == 'unknown'
        assert result.output is None
        assert runtime.provider.calls == []
        with database.session() as db:
            cost, calls = attempts._budget(runtime.policy, db)
            assert cost == view.reserved_usd and calls == 1
    asyncio.run(scenario())


def test_new_registry_cannot_reuse_durable_policy_id_with_higher_budget(world):
    database, actor, conversation, request, runtime = world
    async def scenario():
        registry = registry_for(runtime, actor)
        lease = registry.resolve(actor, conversation.scope)
        with database.session() as db:
            view = attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, lease)
        await execute_attempt(actor, view.id, database, lease)
        replacement = MainModelRegistry()
        replacement.configure(runtime.provider)
        replacement.grant(runtime.policy.model_copy(update={'max_calls': 6}), actor.session_id)
        second, second_request = another_conversation(database, actor, request)
        tasks = GenerationTasks(database, replacement)
        tasks.start()
        with pytest.raises(ServiceError) as failure:
            tasks.submit(actor, second.scope.conversation_id, second_request)
        assert failure.value.code == 'VERSION_CONFLICT'
        assert len(runtime.provider.calls) == 1 and tasks.active_count == 0
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
        await tasks.close()
    asyncio.run(scenario())
