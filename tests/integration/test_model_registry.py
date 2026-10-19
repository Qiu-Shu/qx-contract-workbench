"""Trusted runtime registry boundary with synthetic identities and providers only."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry, resolve_runtime
from cn_contract.security import ServiceError


class SyntheticProvider:
    def __init__(self, config):
        self.config = config
        self.calls = []

    async def generate(self, request, *, expected_config=None):
        self.calls.append((request, expected_config))
        return d.MainReply(state='sent_unknown', error_code='PROVIDER_ERROR')


@pytest.fixture
def world():
    config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='synthetic registry rates')
    actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=1, materials_revision=0)
    content = '独立虚构注册表测试，不含真实材料。'
    request = d.MainRequest(run_id=uuid4(), message_id=uuid4(), scope=scope,
        content=content, source_sha256=sha(content))
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(config)), allowed_content_sha256s=(sha(content),),
        max_total_usd='1', max_calls=5, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    provider = SyntheticProvider(config)
    return SimpleNamespace(config=config, actor=actor, scope=scope, request=request,
        policy=policy, provider=provider, registry=MainModelRegistry())


@contextmanager
def blocked(code='BLOCKED_LIVE'):
    with pytest.raises(ServiceError) as failure:
        yield
    assert failure.value.code == code
    assert str(failure.value) in ('request not authorized', 'request blocked')


def test_empty_configured_and_granted_resolution_never_sends_implicitly(world):
    async def scenario():
        assert resolve_runtime(None, world.actor, world.scope) is None
        assert world.registry.resolve(world.actor, world.scope) is None
        world.registry.configure(world.provider)
        unapproved = resolve_runtime(world.registry, world.actor, world.scope)
        assert unapproved.snapshot_for(world.actor, world.scope) == (world.config, None)
        world.registry.grant(world.policy, world.actor.session_id)
        lease = world.registry.resolve(world.actor, world.scope)
        assert lease.snapshot_for(world.actor, world.scope) == (world.config, world.policy)
        assert world.provider.calls == []
        await lease.provider.generate(world.request, expected_config=world.config)
        assert world.provider.calls == [(world.request, world.config)]
    asyncio.run(scenario())


def test_legacy_runtime_is_returned_unchanged_and_snapshot_for_uses_snapshot(world):
    runtime = MainModelRuntime(world.provider, world.policy)
    assert resolve_runtime(runtime, world.actor, world.scope) is runtime
    assert runtime.snapshot_for(world.actor, world.scope) == runtime.snapshot()


def test_sync_initial_assembly_is_allowed_but_first_resolution_requires_running_loop(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    with blocked():
        world.registry.resolve(world.actor, world.scope)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        assert lease.snapshot() == (world.config, world.policy)
    asyncio.run(scenario())


@pytest.mark.parametrize('other', ['user', 'session', 'workspace'])
def test_grants_and_lease_identity_are_isolated_on_all_three_identity_dimensions(world, other):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        actor, scope = world.actor, world.scope
        lease = world.registry.resolve(actor, scope)
        if other == 'workspace':
            scope = scope.model_copy(update={'workspace_id': uuid4()})
        else:
            actor = actor.model_copy(update={f'{other}_id': uuid4()})
        assert world.registry.resolve(actor, scope).snapshot_for(actor, scope) == (world.config, None)
        with blocked():
            lease.snapshot_for(actor, scope)
        with blocked():
            resolve_runtime(lease, actor, scope)
        assert lease.snapshot_for(world.actor, world.scope)[1] == world.policy
        assert world.provider.calls == []
    asyncio.run(scenario())


def test_lease_identity_does_not_freeze_message_or_material_revisions(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        changed = world.scope.model_copy(update={'input_revision': 5, 'materials_revision': 4,
            'binding_revision': 2, 'conversation_id': uuid4()})
        assert lease.snapshot_for(world.actor, changed)[1] == world.policy
    asyncio.run(scenario())


def test_current_identical_grant_is_idempotent_but_revoke_then_regrant_never_revives_old_lease(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        world.registry.grant(world.policy, world.actor.session_id)
        assert lease.snapshot()[1] == world.policy
        world.registry.revoke(world.actor.session_id)
        with blocked():
            lease.snapshot()
        world.registry.grant(world.policy, world.actor.session_id)
        with blocked():
            lease.snapshot()
        with blocked():
            await lease.provider.generate(world.request)
        assert world.provider.calls == []
        current = world.registry.resolve(world.actor, world.scope)
        assert current.snapshot()[1] == world.policy
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['same', 'off_on', 'other_then_back'])
def test_every_successful_configuration_call_invalidates_old_leases_and_clears_grants(world, change):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        if change == 'off_on':
            world.registry.configure(None)
            assert world.registry.resolve(world.actor, world.scope) is None
        elif change == 'other_then_back':
            world.registry.configure(SyntheticProvider(world.config.model_copy(update={'model': 'deepseek-v4-pro'})))
        world.registry.configure(world.provider)
        assert world.registry.resolve(world.actor, world.scope).snapshot()[1] is None
        world.registry.grant(world.policy, world.actor.session_id)
        with blocked():
            lease.snapshot()
        with blocked():
            await lease.provider.generate(world.request)
        assert world.provider.calls == []
    asyncio.run(scenario())


def test_replacement_grant_invalidates_only_its_session_and_shared_policy_ids_remain_shared(world):
    world.registry.configure(world.provider)
    second_actor = world.actor.model_copy(update={'session_id': uuid4()})
    world.registry.grant(world.policy, world.actor.session_id)
    world.registry.grant(world.policy, second_actor.session_id)
    async def scenario():
        first = world.registry.resolve(world.actor, world.scope)
        second = world.registry.resolve(second_actor, world.scope)
        replacement = world.policy.model_copy(update={'policy_id': uuid4(), 'max_calls': 2})
        world.registry.grant(replacement, world.actor.session_id)
        with blocked():
            first.snapshot()
        assert second.snapshot()[1] == world.policy
        assert second.snapshot()[1].policy_id == world.policy.policy_id
        world.registry.revoke(world.actor.session_id)
        assert second.snapshot_for(second_actor, world.scope)[1] == world.policy
        await second.provider.generate(world.request)
        assert len(world.provider.calls) == 1
    asyncio.run(scenario())


def test_policy_id_digest_ledger_survives_configure_and_revoke_and_failed_updates_preserve_grant(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        changed = world.policy.model_copy(update={'max_calls': 6})
        with blocked('VERSION_CONFLICT'):
            world.registry.grant(changed, world.actor.session_id)
        assert lease.snapshot()[1] == world.policy
        world.registry.revoke(world.actor.session_id)
        world.registry.configure(None)
        world.registry.configure(world.provider)
        with blocked('VERSION_CONFLICT'):
            world.registry.grant(changed, world.actor.session_id)
        world.registry.grant(world.policy, world.actor.session_id)
        assert world.registry.resolve(world.actor, world.scope).snapshot()[1] == world.policy
    asyncio.run(scenario())


@pytest.mark.parametrize('changes', [
    {'max_calls': 0}, {'max_calls': True}, {'max_total_usd': '0'}, {'max_total_usd': 'NaN'},
    {'allowed_content_sha256s': ()}, {'allowed_content_sha256s': ('invalid',)},
    {'allowed_content_sha256s': ('0'*64, '0'*64)}, {'config_sha256': '0'*64},
    {'expires_at': datetime(2000, 1, 1, tzinfo=timezone.utc)}, {'workspace_id': 'invalid'},
])
def test_grant_revalidates_existing_dto_and_rejects_bad_config_digest_expiry_and_limits(world, changes):
    world.registry.configure(world.provider)
    with blocked():
        world.registry.grant(world.policy.model_copy(update=changes), world.actor.session_id)
    async def scenario():
        assert world.registry.resolve(world.actor, world.scope).snapshot()[1] is None
    asyncio.run(scenario())


@pytest.mark.parametrize('session_id', [None, '', 'synthetic-not-a-session', 5])
def test_grant_and_revoke_require_canonical_session_identity(world, session_id):
    world.registry.configure(world.provider)
    with blocked():
        world.registry.grant(world.policy, session_id)
    with blocked():
        world.registry.revoke(session_id)


def test_unconfigured_or_disabled_registry_cannot_receive_grants(world):
    with blocked():
        world.registry.grant(world.policy, world.actor.session_id)
    disabled = world.config.model_copy(update={'enabled': False})
    world.registry.configure(SyntheticProvider(disabled))
    policy = world.policy.model_copy(update={'config_sha256': sha(encoded(disabled))})
    with blocked():
        world.registry.grant(policy, world.actor.session_id)


def test_failed_configuration_validation_preserves_existing_configuration_and_lease(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        for provider in [object(), SyntheticProvider(world.config.model_copy(update={'max_output_tokens': 0})),
                         SimpleNamespace(config=world.config, generate=None)]:
            with blocked():
                world.registry.configure(provider)
            assert lease.snapshot() == (world.config, world.policy)
    asyncio.run(scenario())


def test_unapproved_lease_cannot_send_or_adopt_a_new_grant(world):
    world.registry.configure(world.provider)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        with blocked():
            await lease.provider.generate(world.request)
        world.registry.grant(world.policy, world.actor.session_id)
        with blocked():
            lease.snapshot()
        assert world.provider.calls == []
    asyncio.run(scenario())


def test_provider_wrapper_checks_expected_configuration_and_allowed_request_source_before_call(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        changed_config = world.config.model_copy(update={'model': 'deepseek-v4-pro'})
        with blocked():
            await lease.provider.generate(world.request, expected_config=changed_config)
        wrong_scope = world.scope.model_copy(update={'workspace_id': uuid4()})
        for request in [world.request.model_copy(update={'scope': wrong_scope}),
                        world.request.model_copy(update={'content': 'other synthetic', 'source_sha256': sha('other synthetic')}),
                        world.request.model_copy(update={'source_sha256': '0'*64})]:
            with blocked():
                await lease.provider.generate(request)
        assert world.provider.calls == []
        await lease.provider.generate(world.request)
        assert world.provider.calls == [(world.request, world.config)]
    asyncio.run(scenario())


def test_mutated_provider_configuration_blocks_resolution_snapshot_and_call(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        world.provider.config = world.config.model_copy(update={'max_output_tokens': 123})
        for operation in [lambda: world.registry.resolve(world.actor, world.scope), lease.snapshot,
                          lambda: world.registry.grant(world.policy, world.actor.session_id)]:
            with blocked():
                operation()
        with blocked():
            await lease.provider.generate(world.request)
        assert world.provider.calls == []
    asyncio.run(scenario())


def test_fixed_provider_receives_fixed_config_during_in_flight_configuration_change(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        generate = world.provider.generate
        async def delayed(request, *, expected_config=None):
            entered.set()
            await release.wait()
            return await generate(request, expected_config=expected_config)
        world.provider.generate = delayed
        lease = world.registry.resolve(world.actor, world.scope)
        task = asyncio.create_task(lease.provider.generate(world.request))
        await asyncio.wait_for(entered.wait(), 1)
        replacement = SyntheticProvider(world.config)
        world.registry.configure(replacement)
        world.registry.grant(world.policy, world.actor.session_id)
        release.set()
        reply = await task
        assert reply.state == 'sent_unknown'
        assert world.provider.calls == [(world.request, world.config)]
        assert replacement.calls == []
        with blocked():
            lease.snapshot()
    asyncio.run(scenario())


def test_bound_registry_and_lease_reject_thread_other_loop_and_no_loop_operations(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        operations = [lambda: world.registry.configure(None),
            lambda: world.registry.grant(world.policy, world.actor.session_id),
            lambda: world.registry.revoke(world.actor.session_id),
            lambda: world.registry.resolve(world.actor, world.scope), lease.snapshot,
            lambda: lease.snapshot_for(world.actor, world.scope)]
        def wrong_thread():
            for operation in operations:
                with blocked():
                    operation()
            async def wrong_loop():
                for operation in operations:
                    with blocked():
                        operation()
                with blocked():
                    await lease.provider.generate(world.request)
            asyncio.run(wrong_loop())
        await asyncio.to_thread(wrong_thread)
        assert lease.snapshot()[1] == world.policy
        return operations
    operations = asyncio.run(scenario())
    for operation in operations:
        with blocked():
            operation()
    assert world.provider.calls == []


def test_new_registry_starts_empty_and_never_adopts_prior_registry_grants(world):
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    restarted = MainModelRegistry()
    async def scenario():
        assert restarted.resolve(world.actor, world.scope) is None
        restarted.configure(world.provider)
        assert restarted.resolve(world.actor, world.scope).snapshot()[1] is None
        with blocked():
            resolve_runtime(object(), world.actor, world.scope)
    asyncio.run(scenario())


def test_malformed_trusted_dto_does_not_emit_original_values_in_serializer_warnings(world, recwarn):
    world.registry.configure(world.provider)
    invalid = world.policy.model_copy(update={'max_total_usd': 'SYNTHETIC_PRIVATE_MARKER'})
    with blocked():
        world.registry.grant(invalid, world.actor.session_id)
    assert list(recwarn) == []


def test_policy_expiry_is_checked_again_by_snapshot_and_send(world, monkeypatch):
    from cn_contract.assistant.providers import registry as module
    world.registry.configure(world.provider)
    world.registry.grant(world.policy, world.actor.session_id)
    async def scenario():
        lease = world.registry.resolve(world.actor, world.scope)
        class Future(datetime):
            @classmethod
            def now(cls, tz=None):
                return world.policy.expires_at+timedelta(seconds=1)
        monkeypatch.setattr(module, 'datetime', Future)
        with blocked():
            lease.snapshot_for(world.actor, world.scope)
        with blocked():
            await lease.provider.generate(world.request)
        assert world.provider.calls == []
    asyncio.run(scenario())
