"""Independent CH-04I spec probes. All identities/data/keys are synthetic."""
import asyncio
from datetime import datetime, timedelta
import gc
import weakref
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts, registry as registry_module
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError
from tests.integration.test_native_model_control import native, world, configure, enqueue, SyntheticProvider


def blocked(operation):
    with pytest.raises(ServiceError) as caught:
        operation()
    assert caught.value.code == 'BLOCKED_LIVE'


def test_production_provider_and_secret_closure_are_collectible_across_24_intents(native, monkeypatch):
    n = native
    async def forbidden(*args, **kwargs):
        raise AssertionError('No model generation is allowed in this reference probe')
    monkeypatch.setattr(DeepSeekProvider, 'generate', forbidden)
    n.control = NativeModelControl(n.database, n.registry)
    references = []
    async def scenario():
        for _ in range(24):
            n.basis = {**n.basis, 'request_id': str(uuid4())}
            payload = configure(n)
            n.control.authorize(payload)
            provider = n.registry._provider
            assert type(provider) is DeepSeekProvider
            resolver = provider._secret_resolver
            secret_dto = resolver.__closure__[0].cell_contents
            references.append((weakref.ref(provider), weakref.ref(resolver), weakref.ref(secret_dto)))
            n.control.disable()
            del provider, resolver, secret_dto
            gc.collect()
            assert all(item() is None for row in references for item in row)
        assert len(n.control._intents) == 24
        for fingerprint, token in n.control._intents.values():
            assert type(fingerprint) is str and len(fingerprint) == 64
            assert type(token) is tuple and tuple(map(type, token)) == (object, object)
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
    asyncio.run(scenario())


def test_same_provider_same_policy_aba_reconfigure_cannot_revive_marker(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        marker = n.registry.authorization_token(n.actor, n.draft.scope)
        policy = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1]
        n.registry.configure(n.providers[0])
        n.registry.grant(policy, n.actor.session_id, basis=d.MainSendApproval.model_validate(n.basis))
        new_marker = n.registry.authorization_token(n.actor, n.draft.scope)
        assert marker[0] is not new_marker[0] and marker[1] is not new_marker[1]
        blocked(lambda: n.registry.validate_authorization(n.actor, n.draft.scope, marker))
        blocked(lambda: n.control.authorize(payload))
        n.registry.validate_authorization(n.actor, n.draft.scope, new_marker)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('shape', ['none', 'list', 'short', 'long', 'epoch', 'grant', 'swapped', 'foreign'])
def test_marker_shape_or_foreign_registry_does_not_authorize(native, shape):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        marker = n.registry.authorization_token(n.actor, n.draft.scope)
        if shape == 'foreign':
            other = registry_module.MainModelRegistry()
            other.configure(n.providers[0])
            policy = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1]
            other.grant(policy, n.actor.session_id, basis=d.MainSendApproval.model_validate(n.basis))
            malformed = other.authorization_token(n.actor, n.draft.scope)
        else:
            malformed = {'none': None, 'list': list(marker), 'short': marker[:1],
                'long': (*marker, object()), 'epoch': (object(), marker[1]),
                'grant': (marker[0], object()), 'swapped': tuple(reversed(marker))}[shape]
        blocked(lambda: n.registry.validate_authorization(n.actor, n.draft.scope, malformed))
        n.registry.validate_authorization(n.actor, n.draft.scope, marker)
        assert n.control.authorize(payload) == {'status': 'authorized'}
    asyncio.run(scenario())


def test_exact_expiry_boundary_does_not_renew_or_replace_policy(native, monkeypatch):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        marker = n.registry.authorization_token(n.actor, n.draft.scope)
        policy = n.registry.resolve(n.actor, n.draft.scope).snapshot()[1]
        clock = [policy.expires_at - timedelta(microseconds=1)]
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None): return clock[0]
        monkeypatch.setattr(registry_module, 'datetime', Clock)
        n.registry.validate_authorization(n.actor, n.draft.scope, marker)
        assert n.control.authorize(payload) == {'status': 'authorized'}
        clock[0] = policy.expires_at
        blocked(lambda: n.control.authorize(payload))
        blocked(lambda: n.registry.authorization_token(n.actor, n.draft.scope))
        blocked(lambda: n.registry.validate_authorization(n.actor, n.draft.scope, marker))
        current = n.registry._grants[(n.draft.scope.workspace_id, n.actor.user_id, n.actor.session_id)][0]
        assert current is policy
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_both_new_methods_reject_absent_and_subsequent_event_loop(native):
    n = native
    async def initial():
        n.control.authorize(configure(n))
        return n.registry.authorization_token(n.actor, n.draft.scope)
    marker = asyncio.run(initial())
    def check():
        blocked(lambda: n.registry.authorization_token(n.actor, n.draft.scope))
        blocked(lambda: n.registry.validate_authorization(n.actor, n.draft.scope, marker))
    check()
    async def subsequent(): check()
    asyncio.run(subsequent())


def test_completed_receipt_existing_survives_draft_change_and_revoke_without_new_attempt(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        attempt = enqueue(n, lease)
        completed = await execute_attempt(n.actor, attempt.id, n.database, lease)
        assert completed.output is not None and completed.output.review_status == 'unverified'
        with n.database.session() as db:
            view = service.read_conversation(n.actor, n.draft.scope.conversation_id, db)
            service.save_draft(n.actor, view.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content='另一条完全合成草稿'), db)
        n.control.revoke({'session_token': n.token})
        for _ in range(3): assert n.control.authorize(payload) == {'status': 'existing'}
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] is None
        with n.database.session() as db:
            assert attempts.read_attempt(n.actor, attempt.id, db) == completed
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 1
        assert len(n.providers[0].calls) == 1
    asyncio.run(scenario())


def test_cancelled_inflight_after_disable_keeps_unknown_receipt_and_releases_lease(native):
    n = native
    async def scenario():
        entered = asyncio.Event()
        never = asyncio.Event()
        refs = []
        class Pending(SyntheticProvider):
            async def generate(self, request, *, expected_config=None):
                entered.set()
                await never.wait()
                raise AssertionError('Never release this synthetic call')
        def factory(config, resolver):
            provider = Pending(config)
            provider.resolver = resolver
            refs.extend((weakref.ref(provider), weakref.ref(resolver)))
            return provider
        n.control = NativeModelControl(n.database, n.registry, provider_factory=factory)
        n.control.authorize(configure(n))
        lease = n.registry.resolve(n.actor, n.draft.scope)
        attempt = enqueue(n, lease)
        lease_ref = weakref.ref(lease)
        task = asyncio.create_task(execute_attempt(n.actor, attempt.id, n.database, lease))
        await asyncio.wait_for(entered.wait(), 3)
        del lease
        n.control.disable()
        gc.collect()
        assert lease_ref() is not None and all(ref() is not None for ref in refs)
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
        del task
        await asyncio.sleep(0)
        gc.collect()
        assert lease_ref() is None and all(ref() is None for ref in refs)
        with n.database.session() as db:
            result = attempts.read_attempt(n.actor, attempt.id, db)
            assert result.state == 'sent_unknown' and result.output is None
            assert result.receipt.cost_status == 'unknown'
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
    asyncio.run(scenario())
