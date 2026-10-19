"""Private control service with synthetic identities, secrets and providers only."""
import asyncio
from contextlib import contextmanager
import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.policy import MainModelRuntime, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError, authenticate, login, revoke_session
from tests.integration.test_assistant_generation import SyntheticProvider, world


SECRET = 'SYNTHETIC_NATIVE_CONTROL_NOT_A_REAL_KEY_12345'


@pytest.fixture
def native(world):
    database, _, conversation, request, old_runtime = world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        draft = service.save_draft(actor, conversation.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=conversation.scope, expected_composer_revision=0,
                content=request.content), db)
    request = request.model_copy(update={'expected_scope': draft.scope,
        'expected_composer_revision': draft.composer_revision})
    providers = []
    def factory(config, resolver):
        provider = SyntheticProvider(config)
        provider.synthetic_resolver = resolver
        providers.append(provider)
        return provider
    registry = MainModelRegistry()
    control = NativeModelControl(database, registry, provider_factory=factory)
    basis = {'request_id': str(request.request_id), 'expected_scope': draft.scope.model_dump(mode='json'),
        'expected_composer_revision': draft.composer_revision, 'content_sha256': sha(request.content)}
    return SimpleNamespace(database=database, actor=actor, token=token, draft=draft, request=request,
        config=old_runtime.provider.config, providers=providers, registry=registry,
        control=control, basis=basis)


def configure(n):
    result = n.control.configure({'config': n.config.model_dump(mode='json'), 'secret': SECRET})
    assert result['status'] == 'configured'
    UUID(result['config_version'])
    return {'session_token': n.token, 'basis': n.basis, 'max_total_usd': '1',
        'valid_for_seconds': 120, 'expected_config_version': result['config_version']}


@contextmanager
def denied():
    with pytest.raises(ServiceError) as failure:
        yield
    assert str(failure.value) in ('request not authorized', 'request blocked')
    assert SECRET not in str(failure.value)


def enqueue(n, lease, request=None):
    with n.database.session() as db:
        return attempts.enqueue_generation(n.actor, n.draft.scope.conversation_id,
            request or n.request, db, lease)


def test_private_authorization_is_single_intent_and_new_draft_does_not_invalidate_sent_request(native):
    n = native
    async def scenario():
        payload = configure(n)
        assert n.control.authorize(payload) == {'status': 'authorized'}
        lease = n.registry.resolve(n.actor, n.draft.scope)
        original_policy = lease.snapshot()[1]
        assert original_policy.max_calls == 1
        assert n.control.authorize(payload) == {'status': 'authorized'}
        assert lease.snapshot()[1] == original_policy
        with n.database.session() as db:
            attempt = attempts.enqueue_generation(n.actor, n.draft.scope.conversation_id, n.request, db, lease)
            current = service.read_conversation(n.actor, n.draft.scope.conversation_id, db)
            service.save_draft(n.actor, n.draft.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                content='下一条合成草稿，保留发送中的旧请求。'), db)
        assert n.control.authorize(payload) == {'status': 'existing'}
        completed = await execute_attempt(n.actor, attempt.id, n.database, lease)
        assert completed.output is not None
        assert len(n.providers[0].calls) == 1
        assert n.control.authorize(payload) == {'status': 'existing'}
        assert enqueue(n, lease) == completed
        assert len(n.providers[0].calls) == 1
        with n.database.session() as db:
            for table in ('assistant_runs', 'assistant_model_attempts'):
                assert db.scalar(text(f'SELECT COUNT(*) FROM {table}')) == 1
            assert service.read_conversation(n.actor, n.draft.scope.conversation_id, db).draft_input.startswith('下一条')
        assert SECRET not in repr(n.control) and n.token not in repr(n.control)
    asyncio.run(scenario())


def test_configuration_versions_change_even_with_same_config_and_secret_closures_stay_fixed(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        old = n.registry.resolve(n.actor, n.draft.scope)
        with denied():
            n.control.configure({'config': n.config, 'secret': 'short'})
        assert n.control.authorize(payload) == {'status': 'authorized'}
        assert old.snapshot()[1] is not None
        replacement = n.control.configure({'config': n.config, 'secret': SECRET+'NEW'})
        assert replacement['config_version'] != payload['expected_config_version']
        assert n.providers[0].synthetic_resolver() == SECRET
        assert n.providers[1].synthetic_resolver() == SECRET+'NEW'
        with denied():
            n.control.authorize(payload)
        with denied():
            n.control.authorize({**payload, 'expected_config_version': replacement['config_version']})
        with denied():
            old.snapshot()
        assert all(provider.calls == [] for provider in n.providers)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['budget', 'duration', 'composer', 'scope', 'hash', 'session'])
def test_same_intent_cannot_change_first_authorization_parameters(native, change):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        before = lease.snapshot()[1]
        modified = {**payload, 'basis': dict(n.basis)}
        if change == 'budget': modified['max_total_usd'] = '2'
        elif change == 'duration': modified['valid_for_seconds'] = 121
        elif change == 'composer': modified['basis']['expected_composer_revision'] += 1
        elif change == 'scope':
            modified['basis']['expected_scope'] = {**n.basis['expected_scope'], 'input_revision': 5}
        elif change == 'hash': modified['basis']['content_sha256'] = '0'*64
        else:
            with n.database.session() as db:
                modified['session_token'], _ = login('lawyer', 'fixture123', db)
        with denied(): n.control.authorize(modified)
        assert lease.snapshot()[1] == before
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('operation', ['revoke', 'disable', 'configure'])
def test_unconsumed_intent_cannot_be_resurrected_after_revocation_or_configuration(native, operation):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        if operation == 'revoke':
            assert n.control.revoke({'session_token': n.token}) == {'status': 'revoked'}
        elif operation == 'disable':
            assert n.control.disable() == {'status': 'disabled'}
        else: configure(n)
        with denied(): n.control.authorize(payload)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_restarted_control_returns_existing_without_a_new_grant(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        enqueue(n, lease)
        restarted = MainModelRegistry()
        control = NativeModelControl(n.database, restarted, provider_factory=lambda config, resolver:SyntheticProvider(config))
        version = control.configure({'config': n.config, 'secret': SECRET})['config_version']
        assert control.authorize({**payload, 'expected_config_version': version}) == {'status': 'existing'}
        assert restarted.resolve(n.actor, n.draft.scope).snapshot()[1] is None
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['request_id', 'composer', 'input_revision', 'conversation', 'hash', 'skill', 'attachments'])
def test_submission_must_match_authorized_basis_without_creating_run_or_attempt(native, change):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        changed = n.request
        if change == 'request_id': changed = changed.model_copy(update={'request_id': uuid4()})
        elif change == 'composer': changed = changed.model_copy(update={'expected_composer_revision': 2})
        elif change in ('input_revision', 'conversation'):
            field = 'input_revision' if change == 'input_revision' else 'conversation_id'
            value = 3 if change == 'input_revision' else uuid4()
            changed = changed.model_copy(update={'expected_scope': n.draft.scope.model_copy(update={field: value})})
        elif change == 'hash': changed = changed.model_copy(update={'content': 'changed synthetic content'})
        elif change == 'skill': changed = changed.model_copy(update={'requested_skill': 'contract_review'})
        else: changed = changed.model_copy(update={'attachment_ids': (uuid4(),)})
        with pytest.raises((ServiceError, ValueError)):
            enqueue(n, lease, changed)
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('moment', ['claim', 'settle'])
def test_persisted_request_identity_is_checked_at_claim_and_settlement(native, moment):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        # The trusted legacy seam can prepare a different intent with the same
        # policy; immutable DB records stay intact while native basis rejects it.
        legacy = MainModelRuntime(n.providers[0], lease.snapshot()[1])
        attempt = enqueue(n, legacy, n.request.model_copy(update={'request_id': uuid4()}))
        if moment == 'settle':
            with n.database.session() as db: claimed = attempts.claim(n.actor, attempt.id, db, legacy)
            token, request, config = claimed
            reply = await lease.provider.generate(request, expected_config=config)
        if moment == 'claim':
            completed = await execute_attempt(n.actor, attempt.id, n.database, lease)
            assert completed.receipt.cost_status == 'not_sent'
            assert n.providers[0].calls == []
        else:
            with n.database.session() as db:
                attempts.settle(n.actor, attempt.id, token, reply, db, lease)
                completed = attempts.read_attempt(n.actor, attempt.id, db)
            assert completed.receipt.cost_status == 'estimated'
            assert len(n.providers[0].calls) == 1
        assert completed.output is None
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['draft', 'archived', 'revoked_session', 'restored', 'budget'])
def test_authorization_rechecks_current_database_state_and_budget(native, change):
    n = native
    async def scenario():
        payload = configure(n)
        with n.database.session() as db:
            if change == 'draft':
                service.save_draft(n.actor, n.draft.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=n.draft.scope, expected_composer_revision=n.draft.composer_revision,
                    content='changed synthetic draft'), db)
            elif change == 'archived':
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                    {'at': '2026-10-19T00:00:00+00:00', 'id': str(n.draft.scope.conversation_id)})
            elif change == 'revoked_session': revoke_session(n.actor.session_id, db)
            elif change == 'restored':
                from cn_contract.ops.storage import RestoreFenceRow
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='0'*64,
                    manifest_sha256='1'*64, payload='{}'))
            else: payload['max_total_usd'] = '0.000000000001'
        with denied(): n.control.authorize(payload)
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] is None
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('field,value', [('secret', 'has whitespace 123456789'), ('secret', 'x'*513),
    ('secret', 'x'*15), ('secret', 'synthetic-nonascii-密'), ('secret', 'synthetic-long-key\n'),
    ('endpoint', 'https://example.invalid')])
def test_configure_rejects_invalid_secret_and_unrecognized_endpoint_without_provider_call(native, field, value, recwarn):
    n = native
    async def scenario():
        payload = {'config': n.config, 'secret': SECRET}
        payload[field] = value
        with denied(): n.control.configure(payload)
        assert n.providers == []
    asyncio.run(scenario())
    assert list(recwarn) == []


@pytest.mark.parametrize('field,value', [('max_total_usd', 'NaN'), ('max_total_usd', 'Infinity'),
    ('max_total_usd', 0.5), ('valid_for_seconds', 0), ('valid_for_seconds', 901),
    ('valid_for_seconds', True), ('expected_config_version', 'not-a-uuid')])
def test_authorization_rejects_invalid_limits_without_grant_or_raw_diagnostics(native, field, value, recwarn):
    n = native
    async def scenario():
        payload = configure(n)
        payload[field] = value
        with denied(): n.control.authorize(payload)
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] is None
    asyncio.run(scenario())
    assert list(recwarn) == []


def test_sensitive_dto_repr_and_database_rows_do_not_contain_secret_or_session_token(native):
    n = native
    async def scenario():
        payload = configure(n)
        configure_dto = d.NativeModelConfigure(config=n.config, secret=SECRET)
        authorization = d.NativeModelAuthorization.model_validate(payload)
        revoke = d.NativeModelRevoke(session_token=n.token)
        assert SECRET not in repr(configure_dto)
        assert n.token not in repr(authorization) and n.token not in repr(revoke)
        result = n.control.authorize(authorization)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        enqueue(n, lease)
        assert SECRET not in json.dumps(result) and n.token not in json.dumps(result)
        with n.database.engine.connect() as db:
            dump = '\n'.join(db.connection.driver_connection.iterdump())
        assert SECRET not in dump and n.token not in dump
    asyncio.run(scenario())


def test_control_rejects_calls_outside_its_application_loop(native):
    n = native
    with denied(): n.control.disable()
    async def scenario():
        payload = configure(n)
        def wrong_thread():
            with denied(): n.control.authorize(payload)
            with denied(): n.control.disable()
        await asyncio.to_thread(wrong_thread)
        assert n.control.authorize(payload) == {'status': 'authorized'}
    asyncio.run(scenario())
    async def other_loop():
        with denied(): n.control.disable()
    asyncio.run(other_loop())


def test_authorization_never_accepts_another_users_owned_conversation(native):
    from cn_contract.security import provision_user
    n = native
    with n.database.session() as db:
        provision_user('other-synthetic', 'fixture123', {d.Role.HANDLING_LAWYER}, db,
            local_workbench_password=True)
        other_token, _ = login('other-synthetic', 'fixture123', db)
    async def scenario():
        payload = configure(n)
        with denied(): n.control.authorize({**payload, 'session_token': other_token})
        with denied(): n.control.authorize({**payload, 'session_token': 'invalid-synthetic-token'})
        assert n.registry.resolve(n.actor, n.draft.scope).snapshot()[1] is None
    asyncio.run(scenario())


def test_selected_local_only_attachment_blocks_authorization_even_with_fresh_scope(native):
    from io import BytesIO
    from cn_contract.assistant import attachments
    from tests.integration.test_assistant_attachments import sample
    import hashlib
    n = native
    raw = sample()
    n.database._assistant_synthetic_hashes = frozenset({hashlib.sha256(raw).hexdigest()})
    attachments.ingest_attachment(n.actor, n.draft.scope.conversation_id,
        d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=n.draft.scope,
            original_name='合成本机材料.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=n.database)
    async def scenario():
        payload = configure(n)
        with n.database.session() as db:
            current = service.read_conversation(n.actor, n.draft.scope.conversation_id, db)
        payload['basis'] = {**n.basis, 'expected_scope': current.scope.model_dump(mode='json'),
            'expected_composer_revision': current.composer_revision}
        with denied(): n.control.authorize(payload)
        assert n.registry.resolve(n.actor, current.scope).snapshot()[1] is None
    asyncio.run(scenario())


def test_identical_authorization_does_not_renew_expired_policy(native, monkeypatch):
    from datetime import datetime, timedelta
    from cn_contract.assistant.providers import registry as module
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        policy = lease.snapshot()[1]
        class Future(datetime):
            @classmethod
            def now(cls, tz=None): return policy.expires_at+timedelta(seconds=1)
        monkeypatch.setattr(module, 'datetime', Future)
        with denied(): n.control.authorize(payload)
        with denied(): lease.snapshot()
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_basis_cannot_change_under_same_policy_identity_and_execution_scope_is_exact(native):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        policy = lease.snapshot()[1]
        basis = d.MainSendApproval.model_validate(n.basis)
        with denied():
            n.registry.grant(policy, n.actor.session_id, basis=basis.model_copy(update={'request_id': uuid4()}))
        attempt = enqueue(n, lease)
        with n.database.session() as db:
            token, request, config = attempts.claim(n.actor, attempt.id, db, lease)
        lease.check_execution(n.actor, n.request.request_id, request)
        for scope in [n.draft.scope, request.scope.model_copy(update={'input_revision': 9}),
                      request.scope.model_copy(update={'binding_revision': 2}),
                      request.scope.model_copy(update={'materials_revision': 1})]:
            changed = request.model_copy(update={'scope': scope})
            with denied(): lease.check_execution(n.actor, n.request.request_id, changed)
            with denied(): await lease.provider.generate(changed, expected_config=config)
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_default_provider_is_fixed_deepseek_but_configuration_performs_no_model_call(native):
    from cn_contract.assistant.providers.main import DeepSeekProvider
    n = native
    registry = MainModelRegistry()
    control = NativeModelControl(n.database, registry)
    async def scenario():
        result = control.configure({'config': n.config, 'secret': SECRET})
        assert set(result) == {'status', 'config_sha256', 'config_version'}
        lease = registry.resolve(n.actor, n.draft.scope)
        assert lease.snapshot()[1] is None
        # The production factory is fixed; the public payload has no URL seam.
        assert isinstance(registry._provider, DeepSeekProvider)
        assert registry._provider.is_synthetic is False
        assert control.disable() == {'status': 'disabled'}
        assert registry.resolve(n.actor, n.draft.scope) is None
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['other-conversation', 'same-text-new-composer'])
def test_capability_rejects_current_draft_outside_approved_basis(native, change):
    from cn_contract.web.assistant_generation import _capability
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        with n.database.session() as db:
            draft = n.draft
            if change == 'other-conversation':
                draft = service.create_conversation(n.actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            draft = service.save_draft(n.actor, draft.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=draft.scope, expected_composer_revision=draft.composer_revision,
                content=n.request.content), db)
            row = service._owned(n.actor, draft.scope.conversation_id, db)
            result = _capability(n.actor, row, db, n.registry, SimpleNamespace(accepting=True))
            assert result.state == 'unapproved'
            request = n.request.model_copy(update={'expected_scope': draft.scope,
                'expected_composer_revision': draft.composer_revision})
            with denied():
                attempts.enqueue_generation(n.actor, draft.scope.conversation_id, request, db,
                    n.registry.resolve(n.actor, draft.scope))
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 0
        assert n.providers[0].calls == []
    asyncio.run(scenario())


def test_repeated_capability_reads_leave_matching_approval_unchanged_and_legacy_runtime_compatible(native):
    from cn_contract.web.assistant_generation import _capability
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        policy = lease.snapshot()[1]
        legacy = MainModelRuntime(n.providers[0], policy)
        with n.database.session() as db:
            row = service._owned(n.actor, n.draft.scope.conversation_id, db)
            for runtime in (n.registry, n.registry, legacy):
                result = _capability(n.actor, row, db, runtime, SimpleNamespace(accepting=True))
                assert result.state == 'ready'
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 0
        assert lease.snapshot()[1] == policy
        assert n.control.authorize(payload) == {'status': 'authorized'}
        assert n.providers[0].calls == []
    asyncio.run(scenario())
