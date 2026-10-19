"""Independent CH-04I Standards probes: synthetic state, no model/network I/O."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gc
import json
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from uuid import uuid4
import weakref

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import registry as registry_module
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import world

OUT = Path(__file__).resolve().parent
SYNTHETIC_SECRET = 'INDEPENDENT_REVIEW_SYNTHETIC_SECRET_012345'


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    def denied(*args, **kwargs):
        raise AssertionError('Network is prohibited in this independent probe')
    def local_only(method):
        def invoke(sock, address):
            # Windows asyncio uses socketpair's loopback self-pipe internally.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return method(sock, address)
            return denied()
        return invoke
    monkeypatch.setattr(socket.socket, 'connect', local_only(original_connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', local_only(original_connect_ex))
    monkeypatch.setattr(socket, 'getaddrinfo', denied)


@contextmanager
def blocked(code='BLOCKED_LIVE'):
    with pytest.raises(ServiceError) as result:
        yield
    assert result.value.code == code
    assert str(result.value) in ('request blocked', 'request not authorized')


class ProbeProvider:
    def __init__(self, config, resolver=None):
        self.config = config
        self.resolver = resolver
        self.calls = []

    async def generate(self, request, *, expected_config=None):
        self.calls.append(True)
        raise AssertionError('Generation is not part of these authorization probes')


@pytest.fixture
def r():
    config = d.MainModelConfig(enabled=True, model='deepseek-flash',
        input_usd_per_million='0.3', output_usd_per_million='1.2',
        price_reference='independent synthetic ceiling')
    actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=1, materials_revision=0)
    content = '独立合成授权引用探针。'
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(config)),
        allowed_content_sha256s=(sha(content),), max_total_usd='1', max_calls=1,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=2))
    provider = ProbeProvider(config)
    registry = MainModelRegistry()
    registry.configure(provider)
    registry.grant(policy, actor.session_id)
    return SimpleNamespace(config=config, actor=actor, scope=scope, content=content,
        policy=policy, provider=provider, registry=registry)


@pytest.fixture
def n(world):
    database, _, conversation, request, runtime = world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        draft = service.save_draft(actor, conversation.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=conversation.scope,
                expected_composer_revision=0, content=request.content), db)
    references = []
    call_ledgers = []
    def factory(config, resolver):
        provider = ProbeProvider(config, resolver)
        references.append((weakref.ref(provider), weakref.ref(resolver)))
        call_ledgers.append(provider.calls)
        return provider
    registry = MainModelRegistry()
    control = NativeModelControl(database, registry, provider_factory=factory)
    return SimpleNamespace(database=database, actor=actor, session_token=token, draft=draft,
        config=runtime.provider.config, registry=registry, control=control,
        references=references, call_ledgers=call_ledgers)


def configure(n):
    return n.control.configure({'config': n.config.model_dump(mode='json'),
        'secret': SYNTHETIC_SECRET})['config_version']


def approval(n, version):
    return {'session_token': n.session_token, 'expected_config_version': version,
        'basis': {'request_id': str(uuid4()), 'expected_scope': n.draft.scope.model_dump(mode='json'),
            'expected_composer_revision': n.draft.composer_revision,
            'content_sha256': sha(n.draft.draft_input)},
        'max_total_usd': '1', 'valid_for_seconds': 120}


def test_twelve_intents_keep_tombstones_but_release_retired_providers_and_resolvers(n):
    async def scenario():
        policies = []
        for _ in range(12):
            payload = approval(n, configure(n))
            assert n.control.authorize(payload) == {'status': 'authorized'}
            assert n.control.authorize(payload) == {'status': 'authorized'}
            lease = n.registry.resolve(n.actor, n.draft.scope)
            policies.append(weakref.ref(lease.snapshot()[1]))
            del lease
            gc.collect()
            assert all(ref() is None for pair in n.references[:-1] for ref in pair)
            assert all(ref() is None for ref in policies[:-1])
        assert n.control.disable() == {'status': 'disabled'}
        gc.collect()
        assert all(ref() is None for pair in n.references for ref in pair)
        assert all(ref() is None for ref in policies)
        assert len(n.control._intents) == 12
        for fingerprint, token in n.control._intents.values():
            assert type(fingerprint) is str and len(fingerprint) == 64
            assert type(token) is tuple and len(token) == 2
            assert all(type(identity) is object and gc.get_referents(identity) == [] for identity in token)
        new_version = configure(n)
        with blocked('VERSION_CONFLICT'):
            n.control.authorize({**payload, 'expected_config_version': new_version})
        n.control.disable()
        assert all(calls == [] for calls in n.call_ledgers)
        (OUT/'review-standards-lifetime-measurements.json').write_text(json.dumps({
            'authorized_intents_retained': 12, 'retired_providers_collected': 12,
            'retired_secret_resolvers_collected': 12, 'retired_policies_collected': 12,
            'provider_generate_calls': 0, 'external_network_attempts': 0}, indent=2), encoding='utf-8')
    asyncio.run(scenario())


def test_active_lease_retains_fixed_provider_until_released_but_cannot_send_after_replace(n):
    async def scenario():
        payload = approval(n, configure(n))
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        provider_ref, resolver_ref = n.references[0]
        configure(n)
        gc.collect()
        assert provider_ref() is not None and resolver_ref() is not None
        with blocked():
            lease.snapshot()
        with blocked():
            await lease.provider.generate(None)
        assert all(calls == [] for calls in n.call_ledgers)
        del lease
        gc.collect()
        assert provider_ref() is None and resolver_ref() is None
        n.control.disable()
    asyncio.run(scenario())


@pytest.mark.parametrize('operation', ['revoke_regrant', 'same_config', 'disable_reconfigure', 'replacement_grant'])
def test_generation_changes_never_resurrect_token_even_with_identical_policy(r, operation):
    async def scenario():
        token = r.registry.authorization_token(r.actor, r.scope)
        r.registry.grant(r.policy, r.actor.session_id)
        r.registry.validate_authorization(r.actor, r.scope, token)
        assert r.registry.authorization_token(r.actor, r.scope) == token
        if operation == 'revoke_regrant':
            r.registry.revoke(r.actor.session_id)
        elif operation == 'same_config':
            r.registry.configure(r.provider)
        elif operation == 'disable_reconfigure':
            r.registry.configure(None)
            r.registry.configure(r.provider)
        else:
            r.registry.grant(r.policy.model_copy(update={'policy_id': uuid4()}), r.actor.session_id)
        r.registry.grant(r.policy, r.actor.session_id)
        with blocked():
            r.registry.validate_authorization(r.actor, r.scope, token)
        r.registry.validate_authorization(r.actor, r.scope,
            r.registry.authorization_token(r.actor, r.scope))
        assert r.provider.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary', ['workspace', 'user', 'session', 'registry'])
def test_granted_other_identity_cannot_reuse_a_token(r, boundary):
    async def scenario():
        token = r.registry.authorization_token(r.actor, r.scope)
        actor, scope, registry = r.actor, r.scope, r.registry
        if boundary == 'workspace':
            scope = scope.model_copy(update={'workspace_id': uuid4()})
        elif boundary in ('user', 'session'):
            actor = actor.model_copy(update={boundary+'_id': uuid4()})
        else:
            registry = MainModelRegistry()
            registry.configure(r.provider)
        policy = r.policy.model_copy(update={'policy_id': uuid4(),
            'workspace_id': scope.workspace_id, 'actor_id': actor.user_id})
        registry.grant(policy, actor.session_id)
        with blocked():
            registry.validate_authorization(actor, scope, token)
        registry.validate_authorization(actor, scope, registry.authorization_token(actor, scope))
        r.registry.validate_authorization(r.actor, r.scope, token)
        assert r.provider.calls == []
    asyncio.run(scenario())


def test_token_functions_bind_loop_reject_sync_and_cross_loop_without_mutating_grant(r):
    with blocked():
        r.registry.authorization_token(r.actor, r.scope)
    async def first():
        token = r.registry.authorization_token(r.actor, r.scope)
        def other_loop():
            async def attempt():
                with blocked():
                    r.registry.authorization_token(r.actor, r.scope)
                with blocked():
                    r.registry.validate_authorization(r.actor, r.scope, token)
            asyncio.run(attempt())
        await asyncio.to_thread(other_loop)
        r.registry.validate_authorization(r.actor, r.scope, token)
        return token
    token = asyncio.run(first())
    with blocked():
        r.registry.validate_authorization(r.actor, r.scope, token)
    async def second():
        with blocked():
            r.registry.authorization_token(r.actor, r.scope)
        with blocked():
            r.registry.validate_authorization(r.actor, r.scope, token)
    asyncio.run(second())
    assert r.provider.calls == []


def test_invalid_tokens_and_failed_configuration_do_not_change_current_authorization(r):
    class HostileTuple(tuple):
        def __getitem__(self, key):
            raise AssertionError('Untrusted tuple subclass must not be dereferenced')
    async def scenario():
        token = r.registry.authorization_token(r.actor, r.scope)
        for bad in (None, '', [], (), (object(),), (object(), object()),
                (token[0], object()), (object(), token[1]), HostileTuple(token)):
            with blocked():
                r.registry.validate_authorization(r.actor, r.scope, bad)
        with blocked():
            r.registry.configure(object())
        r.registry.validate_authorization(r.actor, r.scope, token)
        r.provider.config = r.config.model_copy(update={'model': 'deepseek-v4-pro'})
        with blocked():
            r.registry.authorization_token(r.actor, r.scope)
        with blocked():
            r.registry.validate_authorization(r.actor, r.scope, token)
        r.provider.config = r.config
        r.registry.validate_authorization(r.actor, r.scope, token)
        assert r.provider.calls == []
    asyncio.run(scenario())


def test_current_policy_expiry_is_rechecked_without_renewal(n, monkeypatch):
    async def scenario():
        payload = approval(n, configure(n))
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        policy = lease.snapshot()[1]
        token = n.registry.authorization_token(n.actor, n.draft.scope)
        assert n.control.authorize(payload) == {'status': 'authorized'}
        assert lease.snapshot()[1].expires_at == policy.expires_at
        class AfterExpiry:
            @staticmethod
            def now(tz):
                return policy.expires_at+timedelta(microseconds=1)
        monkeypatch.setattr(registry_module, 'datetime', AfterExpiry)
        with blocked():
            n.registry.authorization_token(n.actor, n.draft.scope)
        with blocked():
            n.registry.validate_authorization(n.actor, n.draft.scope, token)
        with blocked():
            n.control.authorize(payload)
        assert len(n.control._intents) == 1
        assert all(calls == [] for calls in n.call_ledgers)
    asyncio.run(scenario())


def test_no_current_grant_or_configuration_cannot_mint_validation_identity(r):
    async def scenario():
        r.registry.revoke(r.actor.session_id)
        with blocked():
            r.registry.authorization_token(r.actor, r.scope)
        assert r.registry.resolve(r.actor, r.scope).snapshot()[1] is None
        r.registry.configure(None)
        with blocked():
            r.registry.authorization_token(r.actor, r.scope)
        assert r.registry.resolve(r.actor, r.scope) is None
        assert r.provider.calls == []
    asyncio.run(scenario())
