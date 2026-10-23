"""Profile-specific permits through synthetic identities and loopback HTTP."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_preparation
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.security import ServiceError
from cn_contract.assistant import profile_preparation_service, service
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.integration.test_assistant_profile_trusted_preparation import source
from tests.integration.test_assistant_profile_sources import state
from tests.integration.test_assistant_storage import workspace
from tests.unit.test_assistant_profile_codec import fixture, response
from tests.unit.test_assistant_profile_preparation import basis, draft, saved
from tests.unit.test_assistant_context_codec import fixture as context_fixture
from tests.unit.test_library_records import citation_container, synthetic_citation


def permission(actor, approval, **changes):
    values = dict(policy_id=uuid4(), workspace_id=approval.expected_scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(config())),
        allowed_content_sha256s=(profile_preparation.basis_digest(approval),),
        max_total_usd='1', max_calls=1, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    return d.MainModelPolicy(**(values | changes))


def setup(provider, approval=None):
    approval = approval or basis()
    actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
    registry = MainModelRegistry()
    registry.configure(provider)
    policy = permission(actor, approval)
    registry.grant(policy, actor.session_id, basis=approval)
    return registry, actor, policy


def prepared(approval=None):
    return profile_preparation.prepare(*saved(), approval or basis(), config(), composer_revision=4)


def local_provider():
    return DeepSeekProvider.for_synthetic_loopback(config(),
        lambda: pytest.fail('rejected input accessed credentials'), 'http://127.0.0.1:1/chat/completions')


@contextmanager
def blocked(code='BLOCKED_LIVE'):
    with pytest.raises(ServiceError) as failure:
        yield
    assert failure.value.code == code


def context_request(rounds=False):
    from cn_contract.assistant.providers.rounds_codec import build_basis_rounds
    # Keep identities shared so purpose rejection is not masked by another workspace.
    record = citation_container(synthetic_citation(), 'saved').model_copy(update={'scope':basis().expected_scope})
    _, records, request = context_fixture(configured=config(), records=(record,))
    if rounds:
        approval = request.basis
        request = request.model_copy(update={'basis':build_basis_rounds(approval.request_id, request.manifest,
            approval.expected_scope, approval.expected_composer_revision, config(), records)})
    return request


def test_explicit_complete_profile_permit_sends_one_exact_request():
    _, request = fixture()
    value = prepared(basis(project_intake=True))
    with server(response(request)) as (url, received, _):
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
        async def scenario():
            registry, actor, _ = setup(provider, value.basis)
            lease = registry.resolve(actor, value.request.scope)
            lease.check_profile_submission(actor, draft(), value.basis)
            lease.check_profile_execution(actor, value.basis.request_id, value)
            reply = await lease.provider.generate_profile(value, expected_config=config())
            assert reply.output.text == '请核对借款及付款材料。'
            assert reply.output.profile_patch.changes[0].verification == 'unverified'
            assert reply.usage.total_tokens == 42
        asyncio.run(scenario())
        assert len(received) == 1
        assert received[0]['body'] == value.wire_payload_json.encode('utf-8')


def test_sqlite_trusted_preparation_connects_to_permission_and_loopback_without_business_writes(source):
    database, actor, conversation, submission = source
    registry = MainModelRegistry()
    with database.session() as db:
        approval = profile_preparation_service.build_profile_basis(actor, conversation.scope.conversation_id,
            submission, db, config=config(), project_intake=True)
    # Use a source-free synthetic candidate for this distinct actual saved message.
    with server(response(fixture()[1], {'text':'合成待核回复', 'citations':[], 'profile_changes':[]})) as (url, received, _):
        provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
        registry.configure(provider)
        registry.grant(permission(actor, approval), actor.session_id, basis=approval)
        async def scenario():
            lease = registry.resolve(actor, approval.expected_scope)
            lease.check_profile_submission(actor, submission, approval)
            with database.session() as db:
                run = service.save_message(actor, conversation.scope.conversation_id, submission, db)
            before = state(database)
            with database.session() as db:
                value = profile_preparation_service.prepare_profile(actor, run.id, approval, db, config=config())
            lease.check_profile_execution(actor, submission.request_id, value)
            reply = await lease.provider.generate_profile(value, expected_config=config())
            assert reply.output.text == '合成待核回复'
            assert reply.output.profile_patch.changes == ()
            assert state(database) == before
            with database.session() as db:
                assert service.get_run(actor, run.id, db).state == 'queued'
            return value
        value = asyncio.run(scenario())
        assert len(received) == 1
        assert received[0]['body'] == value.wire_payload_json.encode('utf-8')
        assert json.loads(json.loads(received[0]['body'])['messages'][1]['content']) == {'content':submission.content}


@pytest.mark.parametrize('change', ['content_key', 'wire_key', 'extra_key', 'calls', 'workspace',
                                  'config', 'expired', 'no_method'])
def test_grant_requires_complete_unique_basis_key_current_config_and_one_call(change):
    provider = local_provider()
    registry = MainModelRegistry()
    actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
    approval = basis()
    changes = {'content_key':{'allowed_content_sha256s':(approval.content_sha256,)},
        'wire_key':{'allowed_content_sha256s':(approval.wire_sha256,)},
        'extra_key':{'allowed_content_sha256s':(profile_preparation.basis_digest(approval), '0'*64)},
        'calls':{'max_calls':2}, 'workspace':{'workspace_id':uuid4()},
        'config':{'config_sha256':'0'*64},
        'expired':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}}
    if change == 'no_method':
        provider = SimpleNamespace(config=config(), generate=provider.generate, generate_profile=None)
    registry.configure(provider)
    with blocked():
        registry.grant(permission(actor, approval, **changes.get(change, {})), actor.session_id, basis=approval)


@pytest.mark.parametrize('change', ['profile_revision', 'intake_target', 'intake_revision', 'project_intake',
                                  'request_id', 'scope', 'composer', 'content'])
def test_same_wire_or_new_content_cannot_reuse_a_different_profile_plan(change):
    approval = basis(expected_intake_id=uuid4(), expected_intake_revision=1)
    submission = draft()
    revised = approval.model_copy(update={'profile_revision':{'base_profile_revision':1},
        'intake_target':{'expected_intake_id':uuid4()}, 'intake_revision':{'expected_intake_revision':2},
        'project_intake':{'project_intake':True}, 'request_id':{'request_id':uuid4()},
        'scope':{'expected_scope':approval.expected_scope.model_copy(update={'binding_revision':2})},
        'composer':{'expected_composer_revision':4}, 'content':{}}[change])
    if change == 'content':
        submission = submission.model_copy(update={'content':'另一个合成咨询'})
    async def scenario():
        registry, actor, _ = setup(local_provider(), approval)
        lease = registry.resolve(actor, approval.expected_scope)
        with blocked():
            lease.check_profile_submission(actor, submission, revised)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['request_id', 'scope', 'composer', 'content', 'skill', 'attachment'])
def test_original_submission_must_match_even_if_given_the_granted_basis(change):
    changes = {'request_id':{'request_id':uuid4()},
        'scope':{'expected_scope':draft().expected_scope.model_copy(update={'input_revision':2})},
        'composer':{'expected_composer_revision':4}, 'content':{'content':'另一合成事实'},
        'skill':{'requested_skill':'client_reply'}, 'attachment':{'attachment_ids':(uuid4(),)}}
    async def scenario():
        registry, actor, _ = setup(local_provider())
        lease = registry.resolve(actor, basis().expected_scope)
        with blocked():
            lease.check_profile_submission(actor, draft().model_copy(update=changes[change]), basis())
    asyncio.run(scenario())


@pytest.mark.parametrize('grant_kind', ['ungranted', 'plain', 'approval', 'context', 'rounds'])
def test_other_grant_purposes_cannot_authorize_any_profile_entry(grant_kind):
    async def scenario():
        actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
        value = prepared()
        registry = MainModelRegistry()
        registry.configure(local_provider())
        approval = None
        key = value.basis.content_sha256
        if grant_kind == 'approval':
            approval = d.MainSendApproval(request_id=value.basis.request_id, expected_scope=value.basis.expected_scope,
                expected_composer_revision=3, content_sha256=key)
        elif grant_kind in ('context', 'rounds'):
            approval = context_request(grant_kind == 'rounds').basis
            key = approval.manifest_sha256
        if grant_kind != 'ungranted':
            policy = permission(actor, value.basis, allowed_content_sha256s=(key,),
                                workspace_id=(approval.expected_scope if approval else value.basis.expected_scope).workspace_id)
            registry.grant(policy, actor.session_id, basis=approval)
        scope = approval.expected_scope if approval else value.basis.expected_scope
        lease = registry.resolve(actor, scope)
        with blocked():
            lease.check_profile_submission(actor, draft(), value.basis)
        with blocked():
            lease.check_profile_execution(actor, value.basis.request_id, value)
        with blocked():
            await lease.provider.generate_profile(value, expected_config=config())
    asyncio.run(scenario())


def test_profile_grant_cannot_enter_plain_context_or_rounds_paths():
    from cn_contract.assistant.providers.rounds_codec import prepare_rounds
    async def scenario():
        value = prepared()
        registry, actor, _ = setup(local_provider())
        lease = registry.resolve(actor, value.request.scope)
        plain = d.MainRequest(**{key:getattr(value.request, key) for key in
            ('run_id', 'message_id', 'scope', 'content', 'source_sha256')})
        context = context_request()
        rounds = context_request(True)
        with blocked():
            lease.check_draft(actor, value.basis.expected_scope, 3, value.basis.content_sha256)
        with blocked():
            lease.check_submission(actor, draft())
        with blocked():
            lease.check_execution(actor, value.basis.request_id, plain)
        with blocked():
            await lease.provider.generate(plain)
        with blocked():
            lease.check_context_submission(actor, d.MainContextSubmission(
                request_id=context.basis.request_id, expected_scope=context.basis.expected_scope,
                expected_composer_revision=context.basis.expected_composer_revision,
                content=context.manifest.question,
                citation_ids=tuple(item.saved_citation_id for item in context.basis.source_bindings)), context.basis)
        with blocked():
            lease.check_execution(actor, context.basis.request_id, context)
        with blocked():
            await lease.provider.generate(context)
        with blocked():
            await lease.provider.generate_rounds(prepare_rounds(rounds, 1, (), config()))
        with blocked():
            lease.granted_context_format()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['actor', 'session', 'workspace', 'request', 'raw_request', 'bad_dto', 'expected_config'])
def test_execution_boundary_rejects_wrong_identity_or_incomplete_prepared_data(change):
    async def scenario():
        value = prepared()
        registry, actor, _ = setup(local_provider())
        lease = registry.resolve(actor, value.request.scope)
        caller = actor.model_copy(update={('user_id' if change == 'actor' else 'session_id'):uuid4()}) if change in ('actor', 'session') else actor
        if change == 'workspace':
            value = value.model_copy(update={'request':value.request.model_copy(update={
                'scope':value.request.scope.model_copy(update={'workspace_id':uuid4()})})})
        elif change == 'bad_dto':
            value = value.model_copy(update={'composer_revision':'private malformed text'})
        with blocked():
            if change == 'expected_config':
                await lease.provider.generate_profile(value, expected_config=config(timeout_seconds=5))
            else:
                lease.check_profile_execution(caller, uuid4() if change == 'request' else value.basis.request_id,
                                              value.request if change == 'raw_request' else value)
    asyncio.run(scenario())


def test_self_consistent_forged_wire_and_current_template_change_are_rebuilt(monkeypatch):
    from cn_contract.assistant.providers import profile_codec
    value = prepared()
    wire = json.loads(value.wire_payload_json)
    wire['messages'][1]['content'] = json.dumps({'content':'未授权的替换正文'})
    altered_wire = json.dumps(wire, ensure_ascii=False, separators=(',', ':'))
    approval = value.basis.model_copy(update={'wire_sha256':sha256(altered_wire.encode()).hexdigest(),
                                            'wire_bytes':len(altered_wire.encode())})
    forged = d.MainProfilePreparedInput.model_validate(value.model_dump(mode='python') |
        {'basis':approval, 'wire_payload_json':altered_wire})
    async def scenario():
        registry, actor, _ = setup(local_provider(), approval)
        lease = registry.resolve(actor, value.request.scope)
        with blocked():
            lease.check_profile_execution(actor, approval.request_id, forged)
        with blocked():
            await lease.provider.generate_profile(forged)
        registry, actor, _ = setup(local_provider())
        lease = registry.resolve(actor, value.request.scope)
        monkeypatch.setattr(profile_codec, '_SYSTEM', profile_codec._SYSTEM+' changed synthetic template')
        with blocked():
            lease.check_profile_execution(actor, value.basis.request_id, value)
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['plan', 'plain', 'context'])
def test_policy_id_tombstone_prevents_new_purpose_or_plan(change):
    async def scenario():
        approval = basis()
        registry, actor, policy = setup(local_provider(), approval)
        lease = registry.resolve(actor, approval.expected_scope)
        if change == 'plan':
            revised = basis(project_intake=True)
            key = profile_preparation.basis_digest(revised)
        elif change == 'plain':
            revised, key = None, approval.content_sha256
        else:
            revised = context_request().basis
            key = revised.manifest_sha256
        changed = policy.model_copy(update={'allowed_content_sha256s':(key,),
            'workspace_id':revised.expected_scope.workspace_id if revised else approval.expected_scope.workspace_id})
        with blocked('VERSION_CONFLICT'):
            registry.grant(changed, actor.session_id, basis=revised)
        lease.check_profile_submission(actor, draft(), approval)
    asyncio.run(scenario())


def expire(monkeypatch, policy):
    from cn_contract.assistant.providers import registry as registry_module, policy as policy_module
    class Clock:
        @staticmethod
        def now(_timezone):
            return policy.expires_at + timedelta(seconds=1)
    monkeypatch.setattr(registry_module, 'datetime', Clock)
    monkeypatch.setattr(policy_module, 'datetime', Clock)


def invalidate(change, registry, actor, provider, policy, monkeypatch):
    if change == 'revoke':
        registry.revoke(actor.session_id)
    elif change == 'regrant':
        registry.revoke(actor.session_id)
        registry.grant(policy, actor.session_id, basis=basis())
    elif change == 'configure':
        registry.configure(provider)
    elif change == 'config_in_place':
        object.__setattr__(provider.config, 'timeout_seconds', 31)
    elif change == 'expired':
        expire(monkeypatch, policy)
    elif change == 'template':
        from cn_contract.assistant.providers import profile_codec
        monkeypatch.setattr(profile_codec, '_SYSTEM', profile_codec._SYSTEM+' changed synthetic template')


@pytest.mark.parametrize('change', ['revoke', 'regrant', 'configure', 'config_in_place', 'expired'])
def test_old_lease_never_survives_grant_or_configuration_change(change, monkeypatch):
    async def scenario():
        provider = local_provider()
        registry, actor, policy = setup(provider)
        lease = registry.resolve(actor, basis().expected_scope)
        registry.grant(policy, actor.session_id, basis=basis())
        lease.check_profile_submission(actor, draft(), basis())
        invalidate(change, registry, actor, provider, policy, monkeypatch)
        with blocked():
            lease.check_profile_submission(actor, draft(), basis())
        with blocked():
            await lease.provider.generate_profile(prepared())
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoke', 'config_in_place', 'expired', 'template'])
def test_transport_rechecks_full_profile_permission_after_secret_resolution(change, monkeypatch):
    _, request = fixture()
    keys = []
    with server(response(request)) as (url, received, _):
        async def scenario():
            def secret():
                keys.append(True)
                invalidate(change, registry, actor, provider, policy, monkeypatch)
                return KEY
            provider = DeepSeekProvider.for_synthetic_loopback(config(), secret, url)
            registry, actor, policy = setup(provider)
            lease = registry.resolve(actor, basis().expected_scope)
            reply = await lease.provider.generate_profile(prepared())
            assert reply.state == 'failed_before_send' and reply.error_code == 'BLOCKED_LIVE'
            assert reply.usage is None and reply.output is None
        asyncio.run(scenario())
        assert keys == [True] and received == []


@pytest.mark.parametrize('change', ['revoke', 'regrant', 'configure', 'config_in_place', 'expired', 'template'])
def test_late_loopback_response_keeps_usage_but_cannot_adopt_output(change, monkeypatch):
    _, request = fixture()
    with server(response(request), pause=.15) as (url, received, seen):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            registry, actor, policy = setup(provider)
            lease = registry.resolve(actor, basis().expected_scope)
            task = asyncio.create_task(lease.provider.generate_profile(prepared()))
            for _ in range(100):
                if seen.is_set():
                    break
                await asyncio.sleep(.005)
            assert seen.is_set()
            invalidate(change, registry, actor, provider, policy, monkeypatch)
            reply = await task
            assert reply.state == 'received' and reply.error_code == 'BLOCKED_LIVE'
            assert reply.output is None and reply.usage.total_tokens == 42
            assert reply.provider_request_id == 'synthetic-response-1'
        asyncio.run(scenario())
        assert len(received) == 1


def test_wrapper_discards_late_candidate_even_if_provider_ignores_preflight():
    from cn_contract.assistant.providers.profile_codec import decode_response
    async def scenario():
        class Provider:
            config = config()
            generate = local_provider().generate
            async def generate_profile(self, request, *, expected_config, preflight):
                assert request == fixture()[1] and expected_config == config()
                registry.revoke(actor.session_id)
                return decode_response(response(request), request, expected_config, KEY)
        registry, actor, _ = setup(Provider())
        lease = registry.resolve(actor, basis().expected_scope)
        reply = await lease.provider.generate_profile(prepared())
        assert reply.state == 'received' and reply.error_code == 'BLOCKED_LIVE'
        assert reply.output is None and reply.usage.total_tokens == 42
        assert reply.provider_request_id == 'synthetic-response-1'
    asyncio.run(scenario())


def test_profile_lease_cannot_move_to_another_event_loop():
    registry, actor, _ = setup(local_provider())
    async def first():
        lease = registry.resolve(actor, basis().expected_scope)
        lease.check_profile_execution(actor, basis().request_id, prepared())
        return lease
    lease = asyncio.run(first())
    async def second():
        with blocked():
            lease.check_profile_execution(actor, basis().request_id, prepared())
        with blocked():
            await lease.provider.generate_profile(prepared())
    asyncio.run(second())
