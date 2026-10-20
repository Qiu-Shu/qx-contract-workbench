"""Synthetic native Jev approval: exact saved draft, one slot, no provider call."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
import gc
import json
from types import SimpleNamespace
from uuid import UUID, uuid4
import weakref

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_judge_control import NativeJudgeControl
from cn_contract.assistant.providers import jev_codec, judge_attempts
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, sha
from cn_contract.security import ServiceError, authenticate, login, revoke_session
from tests.integration.test_assistant_generation import world


SECRET = 'SYNTHETIC_NATIVE_JEV_APPROVAL_TOKEN_ONLY'


@pytest.fixture
def native(world):
    database, _, conversation, request, _ = world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        draft = service.save_draft(actor, conversation.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=conversation.scope, expected_composer_revision=0,
                content=request.content), db)
    request = request.model_copy(update={'expected_scope': draft.scope,
        'expected_composer_revision': draft.composer_revision})
    return SimpleNamespace(database=database, actor=actor, token=token, draft=draft, request=request,
        runtime=JudgeRuntime(), basis={'request_id': str(request.request_id),
            'expected_scope': draft.scope.model_dump(mode='json'),
            'expected_composer_revision': draft.composer_revision, 'content_sha256': sha(request.content),
            'purpose': 'primary_intent'})


def configuration(n):
    n.control = NativeJudgeControl(n.runtime, database=n.database)
    ack = n.control.configure({'config': {'enabled': True}, 'secret': SECRET})
    return {'session_token': n.token, 'expected_config_version': ack['config_version'],
        'basis': n.basis, 'max_total_usd': '0.031', 'valid_for_seconds': 120}


@contextmanager
def denied(code=None):
    with pytest.raises(ServiceError) as error:
        yield
    if code is not None:
        assert error.value.code == code
    assert str(error.value) in ('request not authorized', 'request blocked')
    assert SECRET not in str(error.value)


def next_payload(n, payload):
    with n.database.session() as db:
        conversation = service.create_conversation(n.actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        draft = service.save_draft(n.actor, conversation.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=conversation.scope, expected_composer_revision=0,
                content=n.request.content), db)
    return {**payload, 'basis': {**payload['basis'], 'request_id': str(uuid4()),
        'expected_scope': draft.scope.model_dump(mode='json'), 'expected_composer_revision': draft.composer_revision}}


def reserve(n):
    with n.database.session() as db:
        run = service.save_message(n.actor, n.draft.scope.conversation_id, n.request, db)
        attempt = judge_attempts.reserve(n.actor, run.id, db, n.runtime)
    return run, attempt


def expire(n, monkeypatch):
    from cn_contract.assistant import native_judge_control
    from cn_contract.assistant.providers import judge_policy
    expires = n.runtime.policy.expires_at
    class Future(datetime):
        @classmethod
        def now(cls, tz=None): return expires+timedelta(seconds=1)
    monkeypatch.setattr(native_judge_control, 'datetime', Future)
    monkeypatch.setattr(judge_policy, 'datetime', Future)


def test_approval_hash_matches_actual_saved_full_request_and_is_single_call(native):
    n = native
    async def scenario():
        payload = configuration(n)
        assert n.control.authorize(payload) == {'status': 'authorized'}
        policy = n.runtime.policy
        assert policy.max_calls == 1 and policy.reserved_usd == policy.max_total_usd == Decimal('0.031')
        assert policy.session_id == n.actor.session_id and policy.actor_id == n.actor.user_id
        assert policy.recipient == 'https://api.typesafe.ai/v1/systemone'
        assert len(policy.permissions) == 1
        with n.database.session() as db:
            run = service.save_message(n.actor, n.draft.scope.conversation_id, n.request, db)
            actual = judge_attempts.request_for_run(n.actor, run.id, db, n.runtime.configuration())
            assert actual.text == n.request.content and actual.local_request_id == n.request.request_id
            assert actual.scope.input_revision == n.draft.scope.input_revision+1
            assert actual.scope.model_dump(exclude={'input_revision'}) == n.draft.scope.model_dump(exclude={'input_revision'})
            assert policy.permissions[0].input_hash == jev_codec.input_hash(actual, n.runtime.configuration())
            assert policy.permissions[0].input_hash != n.basis['content_sha256']
            assert n.runtime.snapshot_for(n.actor, actual)[1] == policy
            attempt = judge_attempts.reserve(n.actor, run.id, db, n.runtime)
            assert attempt.state == 'reserved' and attempt.reserved_usd == Decimal('0.031')
        assert n.control.authorize(payload) == {'status': 'existing'}
        assert n.runtime.policy == policy
    asyncio.run(scenario())


def test_unreserved_permission_is_released_after_its_matching_main_run_is_cancelled(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        with n.database.session() as db:
            run = service.save_message(n.actor, n.draft.scope.conversation_id, n.request, db)
            cancelled = service.cancel_run(n.actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
            assert cancelled.state == 'cancelled'
        assert n.control.authorize(next_payload(n, payload)) == {'status': 'authorized'}
    asyncio.run(scenario())


@pytest.mark.parametrize('state', ['reserved', 'sending'])
def test_expired_permission_cannot_cover_another_request_until_old_attempt_finishes(native, monkeypatch, state):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        _, attempt = reserve(n)
        if state == 'sending':
            with n.database.session() as db:
                assert judge_attempts.claim(n.actor, attempt.id, db, n.runtime) is not None
        expire(n, monkeypatch)
        with denied('STATE_CONFLICT'):
            n.control.authorize(next_payload(n, payload))
    asyncio.run(scenario())


@pytest.mark.parametrize('mutation', ['revoke', 'configure'])
def test_clearing_runtime_does_not_hide_a_persisted_sending_attempt(native, mutation):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        _, attempt = reserve(n)
        with n.database.session() as db:
            assert judge_attempts.claim(n.actor, attempt.id, db, n.runtime) is not None
        if mutation == 'revoke': n.control.revoke({'session_token': n.token})
        else:
            ack = n.control.configure({'config': {'enabled': True}, 'secret': SECRET+'NEW'})
            payload = {**payload, 'expected_config_version': ack['config_version']}
        assert n.runtime.policy is None
        with denied('STATE_CONFLICT'):
            n.control.authorize(next_payload(n, payload))
    asyncio.run(scenario())


def test_failed_commit_never_publishes_permission_and_same_intent_can_retry(native, monkeypatch):
    n = native
    async def scenario():
        payload = configuration(n)
        original_session = n.database.session
        @contextmanager
        def failed_commit():
            with original_session() as db:
                yield db
                assert n.runtime.policy is None
                raise RuntimeError('SYNTHETIC_COMMIT_FAILURE')
        with monkeypatch.context() as patch:
            patch.setattr(n.database, 'session', failed_commit)
            with denied('BLOCKED_LIVE'):
                n.control.authorize(payload)
        assert n.runtime.policy is None
        assert n.control.authorize(payload) == {'status': 'authorized'}
    asyncio.run(scenario())


def test_same_request_is_idempotent_without_renewal_and_cannot_change_budget_or_lifetime(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        first = n.runtime.policy
        assert n.control.authorize(payload) == {'status': 'authorized'}
        assert n.runtime.policy is first
        for change in ({'max_total_usd': '0.032'}, {'valid_for_seconds': 121}):
            with denied('VERSION_CONFLICT'): n.control.authorize({**payload, **change})
        assert n.runtime.policy is first
    asyncio.run(scenario())


def test_unpersisted_grant_blocks_new_requests_until_expiry_but_expiry_never_revives_old_intent(native, monkeypatch):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        next_request = next_payload(n, payload)
        with denied('STATE_CONFLICT'): n.control.authorize(next_request)
        expire(n, monkeypatch)
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
        assert n.control.authorize(next_request) == {'status': 'authorized'}
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
    asyncio.run(scenario())


@pytest.mark.parametrize('state', ['received', 'not_sent', 'sent_unknown'])
def test_only_a_finished_auxiliary_attempt_releases_the_slot_without_rewriting_its_history(native, state):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        run, attempt = reserve(n)
        with n.database.session() as db:
            if state == 'not_sent':
                assert judge_attempts.cancel_reserved_for_run(run.id, db) == 1
            else:
                token, request, config = judge_attempts.claim(n.actor, attempt.id, db, n.runtime)
                result = d.JudgeResult(status='failed', reason_code='provider_error', evidence=state,
                    local_request_id=request.local_request_id, scope=request.scope,
                    input_hash=jev_codec.input_hash(request, config), elapsed_ms=1)
                judge_attempts.settle(n.actor, attempt.id, token, result, db, n.runtime)
            before = judge_attempts.read_attempt(n.actor, attempt.id, db)
        assert before.state == state
        assert n.control.authorize(next_payload(n, payload)) == {'status': 'authorized'}
        current = n.runtime.policy
        assert n.control.authorize(payload) == {'status': 'existing'}
        assert n.runtime.policy is current
        with n.database.session() as db:
            assert judge_attempts.read_attempt(n.actor, attempt.id, db) == before
    asyncio.run(scenario())


def test_mismatched_terminal_main_run_without_auxiliary_attempt_does_not_release_approval(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        with n.database.session() as db:
            run = service.save_message(n.actor, n.draft.scope.conversation_id,
                n.request.model_copy(update={'content': '不同的合成文字，不能冒用原批准。'}), db)
            service.cancel_run(n.actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
        with denied('STATE_CONFLICT'): n.control.authorize(next_payload(n, payload))
    asyncio.run(scenario())


@pytest.mark.parametrize('operation', ['revoke', 'configure', 'disable'])
def test_revocation_or_configuration_change_cannot_restore_a_previous_intent(native, operation):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        if operation == 'revoke':
            assert n.control.revoke({'session_token': n.token}) == {'status': 'revoked'}
        elif operation == 'disable': n.control.disable()
        else: n.control.configure({'config': {'enabled': True}, 'secret': SECRET})
        assert n.runtime.policy is None
        with denied(): n.control.authorize(payload)
        if operation != 'revoke':
            ack = n.control.configure({'config': {'enabled': True}, 'secret': SECRET})
            with denied('VERSION_CONFLICT'):
                n.control.authorize({**payload, 'expected_config_version': ack['config_version']})
        assert n.runtime.policy is None
    asyncio.run(scenario())


@pytest.mark.parametrize('other_user', [False, True])
def test_revoke_cannot_clear_another_session_permission(native, other_user):
    from cn_contract.security import provision_user
    n = native
    with n.database.session() as db:
        username = 'lawyer'
        if other_user:
            username = 'other-synthetic'
            provision_user(username, 'fixture123', {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True)
        other_token, _ = login(username, 'fixture123', db)
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        permission = n.runtime.policy
        with denied('CROSS_MATTER_DENIED'): n.control.revoke({'session_token': other_token})
        assert n.runtime.policy is permission
        assert n.control.revoke({'session_token': n.token}) == {'status': 'revoked'}
        assert n.control.revoke({'session_token': n.token}) == {'status': 'revoked'}
    asyncio.run(scenario())


@pytest.mark.parametrize('mutation', ['composer', 'hash', 'scope', 'same-text-save'])
def test_current_saved_draft_must_match_the_complete_basis(native, mutation):
    n = native
    async def scenario():
        payload = configuration(n)
        basis = dict(payload['basis'])
        if mutation == 'composer': basis['expected_composer_revision'] += 1
        elif mutation == 'hash': basis['content_sha256'] = '0'*64
        elif mutation == 'scope': basis['expected_scope'] = {**basis['expected_scope'], 'materials_revision': 1}
        else:
            n.control.authorize(payload)
            with n.database.session() as db:
                service.save_draft(n.actor, n.draft.scope.conversation_id,
                    d.AssistantDraftInput(expected_scope=n.draft.scope,
                        expected_composer_revision=n.draft.composer_revision, content=n.request.content), db)
        with denied(): n.control.authorize({**payload, 'basis': basis})
    asyncio.run(scenario())


def test_existing_run_is_historical_only_after_service_restart_and_checks_original_composer_digest(native):
    n = native
    async def scenario():
        payload = configuration(n)
        with n.database.session() as db:
            service.save_message(n.actor, n.draft.scope.conversation_id, n.request, db)
        assert n.control.authorize(payload) == {'status': 'existing'}
        assert n.runtime.policy is None
        bad = {**payload, 'basis': {**payload['basis'], 'expected_composer_revision': n.draft.composer_revision+1}}
        with denied('VERSION_CONFLICT'): n.control.authorize(bad)
        assert n.runtime.policy is None
    asyncio.run(scenario())


@pytest.mark.parametrize('method', ['authorize', 'revoke'])
def test_database_is_required_for_authorization_and_revocation(native, method):
    n = native
    async def scenario():
        payload = configuration(n)
        control = NativeJudgeControl(JudgeRuntime())
        with denied('BLOCKED_LIVE'):
            getattr(control, method)(payload if method == 'authorize' else {'session_token': n.token})
    asyncio.run(scenario())


def test_lightweight_tombstones_do_not_retain_retired_provider_secret_or_draft(native):
    n = native
    async def scenario():
        payload = configuration(n)
        retired = []
        for _ in range(12):
            n.control.authorize(payload)
            retired.append(weakref.ref(n.runtime.provider))
            ack = n.control.configure({'config': {'enabled': True}, 'secret': SECRET+'NEW'})
            payload = {**payload, 'expected_config_version': ack['config_version'],
                'basis': {**payload['basis'], 'request_id': str(uuid4())}}
        n.control.disable(); gc.collect()
        assert all(reference() is None for reference in retired)
        # The lifetime contract intentionally audits the retained tombstone values.
        assert len(n.control._intents) == 12
        assert all(isinstance(key, UUID) and len(value) == 2 and isinstance(value[0], str)
            and len(value[0]) == 64 and isinstance(value[1], UUID) for key, value in n.control._intents.items())
        assert SECRET not in repr(n.control._intents) and n.request.content not in repr(n.control._intents)
        assert n.token not in repr(d.NativeJudgeAuthorization.model_validate(payload))
        assert n.token not in repr(d.NativeJudgeRevoke(session_token=n.token))
    asyncio.run(scenario())


@pytest.mark.parametrize('field,value', [
    ('max_total_usd', 'NaN'), ('max_total_usd', 'Infinity'), ('max_total_usd', 0.5),
    ('max_total_usd', '0'), ('max_total_usd', '0.0000000000001'),
    ('valid_for_seconds', 0), ('valid_for_seconds', 901), ('valid_for_seconds', True),
    ('expected_config_version', 'not-a-uuid'), ('unexpected', SECRET),
])
def test_invalid_approval_limits_fail_closed_without_diagnostics_or_grant(native, field, value, recwarn):
    n = native
    async def scenario():
        payload = configuration(n)
        with denied('BLOCKED_LIVE'): n.control.authorize({**payload, field: value})
        assert n.runtime.policy is None
    asyncio.run(scenario())
    assert list(recwarn) == []


@pytest.mark.parametrize('change', [{'purpose': 'citation_check'}, {'explicit_skill': 'contract_review'},
    {'attachment_ids': [str(uuid4())]}])
def test_only_primary_intent_without_explicit_skill_or_material_fields_is_accepted(native, change):
    n = native
    async def scenario():
        payload = configuration(n)
        with denied('BLOCKED_LIVE'):
            n.control.authorize({**payload, 'basis': {**payload['basis'], **change}})
        assert n.runtime.policy is None
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['archived', 'revoked-session', 'restored', 'disabled', 'version'])
def test_current_database_and_configuration_must_still_permit_authorization(native, change):
    n = native
    async def scenario():
        payload = configuration(n)
        with n.database.session() as db:
            if change == 'archived':
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                    {'at': '2026-10-20T00:00:00+00:00', 'id': str(n.draft.scope.conversation_id)})
            elif change == 'revoked-session': revoke_session(n.actor.session_id, db)
            elif change == 'restored':
                from cn_contract.ops.storage import RestoreFenceRow
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='0'*64,
                    manifest_sha256='1'*64, payload='{}'))
        if change == 'disabled':
            ack = n.control.configure({'config': {'enabled': False}, 'secret': SECRET})
            payload['expected_config_version'] = ack['config_version']
        elif change == 'version': payload['expected_config_version'] = str(uuid4())
        with denied(): n.control.authorize(payload)
        assert n.runtime.policy is None
    asyncio.run(scenario())


def test_authorization_reauthenticates_and_refuses_foreign_owned_conversation(native):
    from cn_contract.security import provision_user
    n = native
    with n.database.session() as db:
        provision_user('other-synthetic', 'fixture123', {d.Role.HANDLING_LAWYER}, db,
            local_workbench_password=True)
        other_token, _ = login('other-synthetic', 'fixture123', db)
    async def scenario():
        payload = configuration(n)
        for token in (other_token, 'not-a-valid-session'):
            with denied(): n.control.authorize({**payload, 'session_token': token})
        assert n.runtime.policy is None
    asyncio.run(scenario())


def test_local_attachment_prevents_authorization_even_with_fresh_scope(native):
    from io import BytesIO
    import hashlib
    from cn_contract.assistant import attachments
    from tests.integration.test_assistant_attachments import sample
    n = native
    raw = sample()
    n.database._assistant_synthetic_hashes = frozenset({hashlib.sha256(raw).hexdigest()})
    attachments.ingest_attachment(n.actor, n.draft.scope.conversation_id,
        d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=n.draft.scope,
            original_name='合成材料.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=n.database)
    async def scenario():
        payload = configuration(n)
        with n.database.session() as db:
            current = service.read_conversation(n.actor, n.draft.scope.conversation_id, db)
        payload['basis'] = {**payload['basis'], 'expected_scope': current.scope.model_dump(mode='json'),
            'expected_composer_revision': current.composer_revision}
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
        assert n.runtime.policy is None
    asyncio.run(scenario())


def test_authorize_and_revoke_require_the_bound_application_loop(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        current = n.runtime.policy
        def wrong_thread():
            for method, value in ((n.control.authorize, payload), (n.control.revoke, {'session_token': n.token})):
                with denied('BLOCKED_LIVE'): method(value)
        await asyncio.to_thread(wrong_thread)
        assert n.runtime.policy is current
        return payload
    payload = asyncio.run(scenario())
    async def other_loop():
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
        with denied('BLOCKED_LIVE'): n.control.revoke({'session_token': n.token})
    asyncio.run(other_loop())


def test_regranting_same_policy_cannot_revive_native_authorization_identity(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        current = n.runtime.policy
        n.runtime.revoke()
        n.runtime.grant(current)
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
    asyncio.run(scenario())


def test_pending_attempt_blocks_other_sessions_after_revocation(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        reserve(n)
        n.control.revoke({'session_token': n.token})
        with n.database.session() as db:
            token, _ = login('lawyer', 'fixture123', db)
            actor = authenticate(token, db)
            conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            draft = service.save_draft(actor, conversation.scope.conversation_id,
                d.AssistantDraftInput(expected_scope=conversation.scope, expected_composer_revision=0,
                    content=n.request.content), db)
        fresh = {**payload, 'session_token': token, 'basis': {**payload['basis'], 'request_id': str(uuid4()),
            'expected_scope': draft.scope.model_dump(mode='json'), 'expected_composer_revision': draft.composer_revision}}
        with denied('STATE_CONFLICT'): n.control.authorize(fresh)
        assert n.runtime.policy is None
    asyncio.run(scenario())


def test_native_authorization_and_revocation_make_no_provider_call_or_sensitive_database_write(native, monkeypatch):
    from cn_contract.assistant.providers.jev import JevProvider
    n = native
    calls = []
    async def unexpected(*args, **kwargs):
        calls.append(True)
        raise AssertionError('provider must not run during native approval')
    monkeypatch.setattr(JevProvider, 'judge', unexpected)
    async def scenario():
        payload = configuration(n)
        ack = n.control.authorize(payload)
        assert set(ack) == {'status'}
        reserve(n)
        assert n.control.revoke({'session_token': n.token}) == {'status': 'revoked'}
        with n.database.engine.connect() as db:
            dump = '\n'.join(db.connection.driver_connection.iterdump())
        assert SECRET not in dump and n.token not in dump
        assert calls == []
    asyncio.run(scenario())


def test_expiry_immediately_after_publication_cannot_erase_intent_or_renew_same_request(native, monkeypatch):
    from datetime import timezone
    from cn_contract.assistant import native_judge_control
    from cn_contract.assistant.providers import judge_policy
    n = native
    now = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return now
    monkeypatch.setattr(native_judge_control, 'datetime', Clock)
    monkeypatch.setattr(judge_policy, 'datetime', Clock)
    async def scenario():
        payload = {**configuration(n), 'valid_for_seconds': 1}
        original = n.runtime.grant
        def grant_then_pause(policy):
            nonlocal now
            identity = original(policy)
            now += timedelta(seconds=2)
            return identity
        monkeypatch.setattr(n.runtime, 'grant', grant_then_pause)
        try:
            first = n.control.authorize(payload)
        except ServiceError:
            first = None
        original_policy = n.runtime.policy
        with denied('BLOCKED_LIVE'): n.control.authorize(payload)
        assert n.runtime.policy is original_policy
        assert first == {'status': 'authorized'}
    asyncio.run(scenario())


def test_runtime_grant_returns_its_fixed_identity_and_changes_it_only_on_new_grants(native):
    n = native
    async def scenario():
        payload = configuration(n)
        n.control.authorize(payload)
        current = n.runtime.policy
        request = d.JudgeRequest(local_request_id=n.request.request_id,
            scope=n.draft.scope.model_copy(update={'input_revision': n.draft.scope.input_revision+1}),
            purpose='primary_intent', text=n.request.content)
        identity = n.runtime.snapshot_for(n.actor, request)[2]
        assert n.runtime.grant(current) == identity
        n.runtime.revoke()
        replacement = n.runtime.grant(current)
        assert isinstance(replacement, UUID) and replacement != identity
        assert replacement == n.runtime.snapshot_for(n.actor, request)[2]
    asyncio.run(scenario())
