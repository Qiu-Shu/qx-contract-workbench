"""Synthetic authorization lifetime tests; reference collection, not process RSS."""
import asyncio
from datetime import datetime, timedelta
import gc
import json
import weakref
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import registry as registry_module
from cn_contract.assistant.runner import execute_attempt
from tests.integration.test_native_model_control import (
    SyntheticProvider, configure, denied, enqueue, native, world,
)


def test_disabled_authorization_history_does_not_retain_provider_or_secret_resolver(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        provider = weakref.ref(n.providers[0])
        resolver = weakref.ref(n.providers[0].synthetic_resolver)
        n.providers.clear()
        n.control.disable()
        gc.collect()
        assert provider() is None
        assert resolver() is None
    asyncio.run(scenario())


def test_current_idempotent_retry_survives_lease_collection_without_renewing_expiry(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        policy_id, expiry = lease.snapshot()[1].policy_id, lease.snapshot()[1].expires_at
        previous = weakref.ref(lease)
        del lease
        gc.collect()
        assert previous() is None
        for _ in range(3):
            assert n.control.authorize(payload) == {'status': 'authorized'}
            gc.collect()
        policy = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1]
        assert (policy.policy_id, policy.expires_at, policy.max_calls) == (policy_id, expiry, 1)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_replacement_grant_releases_old_policy_and_does_not_resurrect_old_intent(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        previous = weakref.ref(n.registry.resolve(n.actor, n.draft.scope).snapshot()[1])
        replacement = {**payload, 'basis': {**payload['basis'], 'request_id': str(uuid4())}}
        assert n.control.authorize(replacement) == {'status': 'authorized'}
        gc.collect()
        assert previous() is None
        with denied(): n.control.authorize(payload)
        assert n.control.authorize(replacement) == {'status': 'authorized'}
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_revoke_then_identical_policy_regrant_never_revives_native_intent(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        policy = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1]
        basis = d.MainSendApproval.model_validate(payload['basis'])
        n.control.revoke({'session_token': n.token})
        n.registry.grant(policy, n.actor.session_id, basis=basis)
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] == policy
        with denied(): n.control.authorize(payload)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_expired_intent_cannot_be_renewed_after_lease_collection(native, monkeypatch):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        expiry = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1].expires_at
        gc.collect()
        class Future(datetime):
            @classmethod
            def now(cls, tz=None): return expiry + timedelta(seconds=1)
        monkeypatch.setattr(registry_module, 'datetime', Future)
        for _ in range(2):
            with denied(): n.control.authorize(payload)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('dimension', ['user_id', 'session_id', 'workspace_id'])
def test_lightweight_authorization_identity_is_bound_to_user_session_and_workspace(native, dimension):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        token = n.registry.authorization_token(n.actor, n.draft.scope)
        actor, scope = n.actor, n.draft.scope
        if dimension == 'workspace_id': scope = scope.model_copy(update={dimension: uuid4()})
        else: actor = actor.model_copy(update={dimension: uuid4()})
        with denied(): n.registry.validate_authorization(actor, scope, token)
        n.registry.validate_authorization(n.actor, n.draft.scope, token)
    asyncio.run(scenario())


def test_lightweight_authorization_identity_rechecks_provider_config_and_event_loop(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        token = n.registry.authorization_token(n.actor, n.draft.scope)
        def other_thread():
            with denied(): n.registry.validate_authorization(n.actor, n.draft.scope, token)
        await asyncio.to_thread(other_thread)
        provider = n.providers[0]
        provider.config = provider.config.model_copy(update={'timeout_seconds': 31})
        with denied(): n.control.authorize(payload)
        assert provider.calls == []
    asyncio.run(scenario())


def test_registered_request_stays_existing_after_revoke_without_reviving_a_grant(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        enqueue(n, lease)
        n.control.revoke({'session_token': n.token})
        del lease
        gc.collect()
        assert n.control.authorize(payload) == {'status': 'existing'}
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] is None
        changed = {**payload, 'basis': {**payload['basis'], 'content_sha256': '0'*64}}
        with denied(): n.control.authorize(changed)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_sending_task_keeps_its_provider_until_receipt_finishes_then_releases_it(native):
    n = native
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        references = []
        class PausingProvider(SyntheticProvider):
            async def generate(self, request, *, expected_config=None):
                entered.set()
                await release.wait()
                return await super().generate(request, expected_config=expected_config)
        def factory(config, resolver):
            provider = PausingProvider(config)
            provider.synthetic_resolver = resolver
            references.append((weakref.ref(provider), weakref.ref(resolver)))
            return provider
        n.control = NativeModelControl(n.database, n.registry, provider_factory=factory)
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        attempt = enqueue(n, lease)
        task = asyncio.create_task(execute_attempt(n.actor, attempt.id, n.database, lease))
        await asyncio.wait_for(entered.wait(), 3)
        del lease
        n.control.disable()
        gc.collect()
        assert references[0][0]() is not None
        release.set()
        completed = await task
        assert completed.receipt.state == 'received'
        assert completed.receipt.cost_status == 'estimated'
        assert completed.output is None
        del task
        await asyncio.sleep(0)
        gc.collect()
        assert all(ref() is None for ref in references[0])
    asyncio.run(scenario())


def test_repeated_configure_grant_cycles_release_retired_objects_and_keep_replay_tombstones(native):
    n = native
    async def scenario():
        rounds = 32
        references, payloads, live_counts = [], [], []
        for _ in range(rounds):
            n.basis = {**n.basis, 'request_id': str(uuid4())}
            payload = configure(n)
            n.control.authorize(payload)
            payloads.append(payload)
            references.append((weakref.ref(n.providers[-1]), weakref.ref(n.providers[-1].synthetic_resolver),
                weakref.ref(n.registry.resolve(n.actor, n.draft.scope).snapshot()[1])))
            n.providers.clear()
            gc.collect()
            counts = [sum(refs[index]() is not None for refs in references) for index in range(3)]
            live_counts.append(counts)
            assert counts == [1, 1, 1]
        n.control.disable()
        gc.collect()
        final = [sum(refs[index]() is not None for refs in references) for index in range(3)]
        assert final == [0, 0, 0]
        replacement = configure(n)
        for payload in payloads:
            with denied():
                n.control.authorize({**payload, 'expected_config_version': replacement['expected_config_version']})
        n.providers.clear()
        n.control.disable()
        print(json.dumps({'synthetic_rounds': rounds, 'tracked': ['provider', 'secret_resolver', 'policy'],
            'live_after_each_replacement': live_counts, 'live_after_disable': final,
            'old_intents_rejected_after_new_config': len(payloads), 'rss_measured': False}))
    asyncio.run(scenario())
