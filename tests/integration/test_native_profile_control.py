"""Private profile authorization with synthetic persisted state and local transport."""
import asyncio
from datetime import timedelta
from io import BytesIO
import json
from threading import Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import profile_preparation_service, profile_store, service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts, profile_preparation
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.desktop_control import NativeControlHandler, ParentControlChannel, PROTOCOL, parse_control_line
from cn_contract.intake import service as intake
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import authenticate, login, provision_user, revoke_session
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, server
from tests.integration.test_assistant_profile_execution import archive_response, profile_world
from tests.integration.test_native_model_control import denied
from tests.unit.test_desktop_control_protocol import LocalControl

SECRET = 'SYNTHETIC_PROFILE_CONTROL_NOT_A_REAL_KEY_78901'


@pytest.fixture
def native_profile(profile_world):
    database, _, view, request = profile_world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        basis = profile_preparation_service.build_profile_basis(actor, view.scope.conversation_id,
            request, db, config=config(), project_intake=True)
    endpoints, secrets = [], []
    def factory(configuration, resolver):
        def secret():
            secrets.append(True)
            return resolver()
        return DeepSeekProvider.for_synthetic_loopback(configuration, secret,
            endpoints[0] if endpoints else 'http://127.0.0.1:1/chat/completions')
    registry = MainModelRegistry()
    return SimpleNamespace(database=database, actor=actor, token=token, view=view, request=request,
        basis=basis, registry=registry, secrets=secrets, endpoints=endpoints,
        control=NativeModelControl(database, registry, provider_factory=factory))


def configure(n, *, enabled=True):
    result = n.control.configure({'config': config().model_copy(update={'enabled': enabled}).model_dump(mode='json'),
                                  'secret': SECRET})
    return {'session_token': n.token, 'basis': n.basis.model_dump(mode='json'), 'max_total_usd': '1',
            'valid_for_seconds': 120, 'expected_config_version': result['config_version']}


def authorize(n, payload):
    assert callable(getattr(n.control, 'authorize_profile', None)), 'private profile authorization is missing'
    return n.control.authorize_profile(payload)


def enqueue(n):
    lease = n.registry.resolve(n.actor, n.view.scope)
    with n.database.session() as db:
        attempt = attempts.enqueue_profile(n.actor, n.view.scope.conversation_id,
            n.request, db, lease, project_intake=True)
    return attempt, lease


def change_baseline(n, change):
    with n.database.session() as db:
        if change == 'profile':
            profile_store._commit(n.actor, d.ProfileCommitInput(request_id=uuid4(),
                patch=d.ProfilePatch(scope=n.view.scope, base_profile_revision=0),
                manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'合成人工档案'}),)),
                d.ProfileSourceSnapshot(scope=n.view.scope), db)
        elif change == 'intake_revision':
            intake.save(n.basis.expected_intake_id, d.IntakeUpdateInput(expected_revision=1,
                draft=d.IntakeDraft(title='合成接待的新版本')), n.actor, db)
        else:
            target = intake.create(d.IntakeCreateInput(request_id=uuid4(),
                draft=d.IntakeDraft(title='合成保存目标')), n.actor, db)
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:target WHERE id=:id'),
                {'target': str(target.id), 'id': str(n.view.scope.conversation_id)})


def test_native_profile_authorization_reuses_one_grant_and_existing_completed_request(native_profile):
    n = native_profile
    with server(archive_response()) as (url, received, _):
        async def scenario():
            n.endpoints.append(url)
            payload = configure(n)
            assert authorize(n, payload) == {'status': 'authorized'}
            policy = n.registry.resolve(n.actor, n.view.scope).snapshot()[1]
            assert policy.max_calls == 1
            assert policy.allowed_content_sha256s == (profile_preparation.basis_digest(n.basis),)
            assert authorize(n, payload) == {'status': 'authorized'}
            assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] == policy
            first, lease = enqueue(n)
            with n.database.session() as db:
                current = service.read_conversation(n.actor, n.view.scope.conversation_id, db)
                service.save_draft(n.actor, n.view.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                    content='等待时的新合成草稿'), db)
            assert authorize(n, payload) == {'status': 'existing'}
            completed = await execute_attempt(n.actor, first.id, n.database, lease)
            assert completed.state == 'received' and completed.output is not None
            assert authorize(n, payload) == {'status': 'existing'}
            assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] == policy
            with n.database.session() as db:
                assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 1
                assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 1
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 1
                assert service.read_conversation(n.actor, n.view.scope.conversation_id, db).draft_input == '等待时的新合成草稿'
        asyncio.run(scenario())
        assert len(received) == 1 and n.secrets == [True]


@pytest.mark.parametrize('existing_grant', [False, True])
@pytest.mark.parametrize('change', ['profile', 'target', 'intake_revision'])
def test_current_save_baseline_is_rebuilt_before_new_or_repeated_authorization(native_profile, existing_grant, change):
    n = native_profile
    async def scenario():
        if change == 'intake_revision':
            change_baseline(n, 'target')
            with n.database.session() as db:
                n.basis = profile_preparation_service.build_profile_basis(n.actor, n.view.scope.conversation_id,
                    n.request, db, config=config(), project_intake=True)
        payload = configure(n)
        if existing_grant:
            authorize(n, payload)
        change_baseline(n, change)
        with denied():
            authorize(n, payload)
        with n.database.session() as db:
            assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0
            assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
        if not existing_grant:
            assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] is None
        assert n.secrets == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoke', 'configure', 'expired', 'session', 'restored', 'disabled', 'archived'])
def test_authorization_tombstone_cannot_be_revived(native_profile, change, monkeypatch):
    n = native_profile
    async def scenario():
        payload = configure(n)
        authorize(n, payload)
        policy = n.registry.resolve(n.actor, n.view.scope).snapshot()[1]
        if change == 'revoke':
            n.control.revoke({'session_token': n.token})
        elif change == 'configure':
            payload['expected_config_version'] = configure(n)['expected_config_version']
        elif change == 'disabled':
            n.control.disable()
        elif change == 'expired':
            from cn_contract.assistant.providers import registry
            class Future:
                @staticmethod
                def now(_timezone):
                    return policy.expires_at + timedelta(seconds=1)
            monkeypatch.setattr(registry, 'datetime', Future)
        else:
            with n.database.session() as db:
                if change == 'session':
                    revoke_session(n.actor.session_id, db)
                elif change == 'restored':
                    db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='0'*64,
                        manifest_sha256='1'*64, payload='{}'))
                else:
                    db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                        {'at': '2026-10-23T00:00:00+00:00', 'id': str(n.view.scope.conversation_id)})
        with denied():
            authorize(n, payload)
        with n.database.session() as db:
            assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
        assert n.secrets == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['extra', 'rounds', 'coerced_duration', 'plan', 'wire', 'budget', 'disabled_config'])
def test_strict_native_payload_and_unapproved_basis_do_not_grant(native_profile, change):
    n = native_profile
    async def scenario():
        payload = configure(n, enabled=change != 'disabled_config')
        if change == 'extra':
            payload['policy'] = {}
        elif change == 'rounds':
            payload['max_rounds'] = 1
        elif change == 'coerced_duration':
            payload['valid_for_seconds'] = '120'
        elif change == 'plan':
            payload['basis']['base_profile_revision'] += 1
        elif change == 'wire':
            payload['basis']['wire_sha256'] = '0'*64
        elif change == 'budget':
            payload['max_total_usd'] = '0.000000000001'
        with denied():
            authorize(n, payload)
        assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] is None
        assert n.secrets == []
    asyncio.run(scenario())


def test_profile_and_plain_authorizations_cannot_be_interchanged(native_profile):
    n = native_profile
    async def scenario():
        payload = configure(n)
        plain = payload | {'basis': dict(request_id=str(n.request.request_id),
            expected_scope=n.request.expected_scope.model_dump(mode='json'),
            expected_composer_revision=n.request.expected_composer_revision,
            content_sha256=sha(n.request.content))}
        n.control.authorize(plain)
        with denied():
            authorize(n, payload)
        with denied():
            enqueue(n)
        n.request = n.request.model_copy(update={'request_id': uuid4()})
        n.basis = n.basis.model_copy(update={'request_id': n.request.request_id})
        payload['basis'] = n.basis.model_dump(mode='json')
        assert authorize(n, payload) == {'status': 'authorized'}
        lease = n.registry.resolve(n.actor, n.view.scope)
        with denied():
            lease.check_submission(n.actor, n.request)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['plain', 'missing_attempt', 'basis', 'config', 'digest', 'message', 'session',
                                    'format', 'scope', 'actor', 'run_digest'])
def test_existing_request_requires_exact_original_profile_registration(native_profile, change):
    n = native_profile
    async def scenario():
        payload = configure(n)
        if change == 'missing_attempt':
            with n.database.session() as db:
                service.save_message(n.actor, n.view.scope.conversation_id, n.request, db)
        elif change == 'plain':
            n.control.authorize(payload | {'basis': dict(request_id=str(n.request.request_id),
                expected_scope=n.request.expected_scope.model_dump(mode='json'),
                expected_composer_revision=n.request.expected_composer_revision,
                content_sha256=sha(n.request.content))})
            with n.database.session() as db:
                attempts.enqueue_generation(n.actor, n.view.scope.conversation_id, n.request, db,
                    n.registry.resolve(n.actor, n.view.scope))
        else:
            authorize(n, payload)
            first, _ = enqueue(n)
            with n.database.session() as db:
                if change in ('basis', 'config', 'digest', 'format'):
                    row = attempts._row(first.id, db)
                    column, value = 'request_sha256', '0'*64
                    if change == 'basis':
                        prepared = attempts._input(row)
                        changed = prepared.basis.model_copy(update={'project_intake': False})
                        column, value = 'input_json', encoded(prepared.model_copy(update={'basis': changed}))
                    elif change == 'config':
                        column, value = 'config_json', encoded(config(timeout_seconds=5))
                    elif change == 'format':
                        column, value = 'input_format', 'plain-text-v1'
                    db.execute(text('DROP TRIGGER immutable_assistant_model_input'))
                    db.execute(text(f'UPDATE assistant_model_attempts SET {column}=:value WHERE id=:id'),
                        {'value': value, 'id': str(first.id)})
                elif change == 'message':
                    db.execute(text('DROP TRIGGER immutable_assistant_messages_update'))
                    db.execute(text("UPDATE assistant_messages SET content='变更的合成原话' WHERE id=(SELECT message_id FROM assistant_runs WHERE id=:id)"),
                        {'id': str(first.run_id)})
                elif change == 'session':
                    token, _ = login('lawyer', 'fixture123', db)
                    payload['session_token'] = token
                else:
                    row = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'),
                        {'id': str(first.run_id)}).mappings().one()
                    column, value = 'request_sha256', '0'*64
                    if change == 'scope':
                        column = 'scope_snapshot'
                        value = encoded(d.ScopeSnapshot.model_validate_json(row[column]).model_copy(
                            update={'materials_revision': 99}))
                    elif change == 'actor':
                        column = 'actor_id'
                        value = str(provision_user('synthetic-other', 'synthetic-password',
                            {'handling_lawyer'}, db))
                    db.execute(text('DROP TRIGGER immutable_assistant_run_input'))
                    db.execute(text(f'UPDATE assistant_runs SET {column}=:value WHERE id=:id'),
                        {'value': value, 'id': str(first.run_id)})
        # A new control instance has no intent cache to mask persisted-input checks.
        n.control = NativeModelControl(n.database, n.registry, provider_factory=n.control._provider_factory)
        payload['expected_config_version'] = configure(n)['expected_config_version']
        with denied():
            authorize(n, payload)
        assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] is None
        assert n.secrets == []
    asyncio.run(scenario())


def test_existing_after_control_restart_or_revoke_never_creates_a_new_grant(native_profile):
    n = native_profile
    async def scenario():
        payload = configure(n)
        authorize(n, payload)
        first, _ = enqueue(n)
        n.control.revoke({'session_token': n.token})
        assert authorize(n, payload) == {'status': 'existing'}
        n.control = NativeModelControl(n.database, n.registry, provider_factory=n.control._provider_factory)
        payload = configure(n)
        assert authorize(n, payload) == {'status': 'existing'}
        assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] is None
        with denied():
            enqueue(n)
        with n.database.session() as db:
            assert attempts.read_attempt(n.actor, first.id, db).state == 'reserved'
            assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 1
        assert n.secrets == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['version', 'other_conversation', 'draft', 'reconstructed_boolean'])
def test_current_native_identity_and_draft_are_required(native_profile, change):
    n = native_profile
    async def scenario():
        payload = configure(n)
        if change == 'version':
            payload['expected_config_version'] = str(uuid4())
        elif change == 'other_conversation':
            payload['basis']['expected_scope']['conversation_id'] = str(uuid4())
        elif change == 'reconstructed_boolean':
            value = d.NativeProfileAuthorization.model_validate(payload)
            payload = value.model_copy(update={'basis': value.basis.model_copy(update={'project_intake': 'true'})})
        else:
            with n.database.session() as db:
                service.save_draft(n.actor, n.view.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=n.view.scope, expected_composer_revision=n.view.composer_revision,
                    content='授权前另存的合成草稿'), db)
        with denied():
            authorize(n, payload)
        assert n.registry.resolve(n.actor, n.view.scope).snapshot()[1] is None
        assert n.secrets == []
    asyncio.run(scenario())


@pytest.mark.parametrize('ack', [{'status': 'authorized', 'secret': 'synthetic'}, {'status': 'pending'}, {}])
def test_profile_pipe_rejects_non_whitelisted_acknowledgements(ack):
    async def scenario():
        main = LocalControl()
        main.authorize_profile = lambda payload: ack
        channel = ParentControlChannel(BytesIO(), 'synthetic', lambda **v: None, lambda: None)
        channel.bind(NativeControlHandler(main, LocalControl()))
        with pytest.raises(ValueError, match='CONTROL_REJECTED'):
            await channel._dispatch('authorize_profile', {})
    asyncio.run(scenario())


def test_private_profile_pipe_round_trip_returns_only_fixed_acknowledgement(native_profile):
    n = native_profile
    async def scenario():
        payload = configure(n)
        frame = json.dumps(dict(event='model-control', protocol=PROTOCOL, nonce='synthetic',
            sequence=1, operation='authorize_profile', payload=payload))+'\n'
        assert parse_control_line(frame, 'synthetic', 1) == ('authorize_profile', payload)
        outputs, exited, stopped = [], [], []
        channel = ParentControlChannel(BytesIO(frame.encode()), 'synthetic', lambda **v: outputs.append(v),
            lambda: stopped.append(True), fatal=exited.append)
        channel.bind(NativeControlHandler(n.control, LocalControl()))
        worker = Thread(target=channel.watch)
        worker.start()
        while worker.is_alive():
            await asyncio.sleep(.001)
        worker.join()
        assert exited == [] and stopped == [True]
        assert outputs == [dict(event='model-control-result', protocol=PROTOCOL, nonce='synthetic',
            sequence=1, ok=True, status='authorized')]
        assert n.registry.configuration() is None and n.secrets == []
    asyncio.run(scenario())
