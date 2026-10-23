"""Synthetic offline approval descriptions, never permissions or database writes."""
import importlib
import hashlib
import json
from decimal import Decimal, localcontext
from uuid import UUID

import pytest

from cn_contract import domain as d
from tests.unit.test_assistant_profile_codec import fixture
from tests.integration.test_assistant_main_provider import config


def api():
    return importlib.import_module('cn_contract.assistant.providers.profile_preparation')


def draft(request=None):
    request = request or fixture()[1]
    scope = request.scope.model_copy(update={'input_revision': request.scope.input_revision - 1})
    return d.AssistantMessageInput(request_id=UUID(int=9), expected_scope=scope,
        expected_composer_revision=3, content=request.content)


def basis(request=None, **plan):
    request = request or fixture()[1]
    return api().build_basis(draft(request), config(), base_profile_revision=request.base_profile_revision,
        **plan)


def saved(request=None):
    request = request or fixture()[1]
    message = fixture(request.content)[0].messages[0].model_copy(update={
        'id': request.message_id, 'source_revision': request.source_revision})
    run = d.AssistantRunView(id=request.run_id, message_id=message.id, request_id=UUID(int=9),
        request_sha256='0'*64, scope=request.scope, state='queued', requested_skill=None,
        selected_provider=None, selected_model=None, cancel_requested=False,
        created_at=message.created_at, events=())
    return run, message


def test_prepared_input_binds_complete_wire_and_local_save_plan():
    _, request = fixture()
    approval = basis(request, project_intake=True)
    prepared = api().prepare(*saved(request), approval, config(), composer_revision=4)
    assert prepared.basis == approval and prepared.request == request
    assert type(prepared.request) is d.MainProfileRequest
    assert approval.purpose == 'reply_and_profile_draft'
    assert (approval.handler_id, approval.handler_version) == ('profile.save', '1')
    assert approval.project_intake is True
    assert approval.expected_intake_id is None and approval.expected_intake_revision is None
    assert prepared.composer_revision == 4


def test_same_outbound_wire_different_local_plan_has_different_permission_key():
    plain, projected = basis(), basis(project_intake=True)
    assert plain.wire_sha256 == projected.wire_sha256
    assert api().basis_digest(plain) != api().basis_digest(projected)


@pytest.mark.parametrize('field,value', [('source_revision', 2), ('content', '不同的文字'), ('role', 'assistant')])
def test_stale_or_wrong_message_cannot_reuse_basis(field, value):
    _, request = fixture()
    run, message = saved(request)
    with pytest.raises(ValueError):
        api().prepare(run, message.model_copy(update={field: value}), basis(request), config(), composer_revision=4)


def test_changed_composer_version_cannot_reuse_basis():
    _, request = fixture()
    with pytest.raises(ValueError):
        api().prepare(*saved(request), basis(request), config(), composer_revision=5)


def test_wire_is_exact_c1_utf8_and_contains_no_local_save_metadata():
    from cn_contract.assistant.providers.profile_codec import build_request
    from cn_contract.assistant.providers.deepseek_protocol import json_bytes
    _, request = fixture('合成资料：甲🙂说“500元”。\n另行核对。')
    approval = basis(request, expected_intake_id=UUID(int=12), expected_intake_revision=7)
    prepared = api().prepare(*saved(request), approval, config(), composer_revision=4)
    wire = prepared.wire_payload_json.encode('utf-8')
    assert wire == json_bytes(build_request(request, config()))
    assert approval.wire_bytes == len(wire) > len(prepared.wire_payload_json)
    assert approval.wire_sha256 == hashlib.sha256(wire).hexdigest()
    assert json.loads(json.loads(wire)['messages'][1]['content']) == {'content': request.content}
    assert str(approval.expected_intake_id) not in prepared.wire_payload_json
    assert str(request.scope.workspace_id) not in prepared.wire_payload_json
    assert 'project_intake' not in prepared.wire_payload_json and 'reply_and_profile_draft' not in prepared.wire_payload_json


@pytest.mark.parametrize('change', [
    {'base_profile_revision': 1}, {'expected_intake_id': UUID(int=12), 'expected_intake_revision': 1},
    {'project_intake': True},
])
def test_valid_local_plan_changes_require_distinct_entire_basis_digest(change):
    original = basis()
    revised = d.MainProfileSendBasis.model_validate(original.model_dump(mode='python') | change)
    assert original.wire_sha256 == revised.wire_sha256
    assert api().basis_digest(original) != api().basis_digest(revised)
    serialized = original.model_dump_json()
    assert api().basis_digest(d.MainProfileSendBasis.model_validate_json(serialized)) == api().basis_digest(original)


@pytest.mark.parametrize('field,value', [
    ('system_sha256', '0'*64), ('config_sha256', '0'*64), ('wire_sha256', '0'*64),
    ('content_sha256', '0'*64), ('wire_bytes', 1), ('expected_composer_revision', 4),
    ('request_id', UUID(int=18)),
])
def test_changed_basis_cannot_prepare_same_saved_submission(field, value):
    approval = basis().model_copy(update={field: value})
    with pytest.raises(ValueError):
        api().prepare(*saved(), approval, config(), composer_revision=4)


@pytest.mark.parametrize('field,value', [
    ('purpose', 'reply_only'), ('input_format', 'plain-text-v1'),
    ('template_version', 'profile-text-system-v2'), ('handler_id', 'legal_library.search'),
    ('handler_version', '2'), ('project_intake', 1), ('base_profile_revision', True),
    ('expected_composer_revision', '3'), ('wire_bytes', True),
    ('expected_intake_id', UUID(int=12)), ('expected_intake_revision', 1),
    ('manual_edits', ()),
])
def test_invalid_or_expanded_basis_is_rejected_even_when_constructed(field, value):
    raw = basis().model_dump(mode='python') | {field: value}
    with pytest.raises(ValueError):
        d.MainProfileSendBasis.model_validate(raw)
    # Bypass object construction deliberately, then exercise the public boundary.
    constructed = d.MainProfileSendBasis.model_construct(**raw)
    if field != 'manual_edits':  # extra='forbid' model_construct drops extra keys.
        with pytest.raises(ValueError):
            api().prepare(*saved(), constructed, config(), composer_revision=4)


@pytest.mark.parametrize('field,value', [
    ('workspace_id', UUID(int=18)), ('conversation_id', UUID(int=18)),
    ('binding_revision', 2), ('input_revision', 3), ('materials_revision', 1),
    ('scope_kind', 'intake'),
])
def test_run_scope_cannot_change_any_other_boundary(field, value):
    run, message = saved()
    run = run.model_copy(update={'scope': run.scope.model_copy(update={field: value})})
    with pytest.raises(ValueError):
        api().prepare(run, message, basis(), config(), composer_revision=4)


@pytest.mark.parametrize('change', [
    {'request_id': UUID(int=18)}, {'message_id': UUID(int=18)}, {'requested_skill': 'content_draft'},
])
def test_run_must_match_saved_user_message_and_original_submission(change):
    run, message = saved()
    with pytest.raises(ValueError):
        api().prepare(run.model_copy(update=change), message, basis(), config(), composer_revision=4)


def test_intake_scope_requires_its_exact_target_even_without_projection():
    _, request = fixture()
    request = request.model_copy(update={'scope': request.scope.model_copy(update={
        'scope_kind': 'intake', 'scope_ref': UUID(int=12)})})
    for plan in ({}, {'expected_intake_id': UUID(int=13), 'expected_intake_revision': 1}):
        with pytest.raises(ValueError):
            basis(request, **plan)
    approval = basis(request, expected_intake_id=UUID(int=12), expected_intake_revision=1)
    assert approval.project_intake is False
    assert api().prepare(*saved(request), approval, config(), composer_revision=4).request.scope == request.scope


@pytest.mark.parametrize('change', [
    {'model': 'deepseek-pro'}, {'max_output_tokens': 123}, {'timeout_seconds': 31},
    {'input_usd_per_million': Decimal('0.4')}, {'price_reference': 'different synthetic quote'},
])
def test_changed_configuration_invalidates_basis_even_if_wire_unchanged(change):
    with pytest.raises(ValueError):
        api().prepare(*saved(), basis(), config().model_copy(update=change), composer_revision=4)


def test_current_template_change_invalidates_prepared_input(monkeypatch):
    from cn_contract.assistant.providers import profile_codec
    approval = basis()
    monkeypatch.setattr(profile_codec, '_SYSTEM', profile_codec._SYSTEM + ' changed synthetic template')
    with pytest.raises(ValueError):
        api().prepare(*saved(), approval, config(), composer_revision=4)


def test_entire_wire_budget_accepts_exact_limit_and_rejects_one_byte_less():
    required = basis().wire_bytes
    exact = config().model_copy(update={'max_input_bytes': required})
    approval = api().build_basis(draft(), exact, base_profile_revision=0)
    assert api().prepare(*saved(), approval, exact, composer_revision=4).basis.wire_bytes == required
    with pytest.raises(ValueError):
        api().build_basis(draft(), exact.model_copy(update={'max_input_bytes': required - 1}), base_profile_revision=0)


@pytest.mark.parametrize('change', [
    {'requested_skill': 'client_reply'}, {'attachment_ids': (UUID(int=22),)},
    {'content': '  '}, {'content': 123},
])
def test_only_explicit_current_text_supported(change):
    with pytest.raises(ValueError):
        api().build_basis(draft().model_copy(update=change), config(), base_profile_revision=0)


def test_full_basis_revalidation_and_digest_ignore_decimal_context():
    approval = basis()
    with localcontext() as context:
        context.prec = 2
        assert basis() == approval
        assert api().basis_digest(basis()) == api().basis_digest(approval)
    bad = approval.model_copy(update={'expected_scope': approval.expected_scope.model_copy(update={'input_revision': True})})
    with pytest.raises(ValueError):
        api().basis_digest(bad)


def test_serialized_prepared_wire_cannot_be_substituted():
    prepared = api().prepare(*saved(), basis(), config(), composer_revision=4)
    raw = prepared.model_dump(mode='python')
    raw['wire_payload_json'] += ' '
    with pytest.raises(ValueError):
        d.MainProfilePreparedInput.model_validate(raw)
    raw = prepared.model_dump(mode='python')
    raw['request']['base_profile_revision'] = 1
    with pytest.raises(ValueError):
        d.MainProfilePreparedInput.model_validate(raw)


def test_basis_cannot_be_used_as_existing_registry_permission_or_ledger_format():
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from cn_contract.assistant.providers.registry import MainModelRegistry
    from cn_contract.assistant.providers.policy import sha, encoded
    from cn_contract.assistant.providers.attempts import _input
    from cn_contract.security import ServiceError
    approval = basis()
    registry = MainModelRegistry()
    calls = []
    registry.configure(SimpleNamespace(config=config(), generate=lambda *args: calls.append(args)))
    policy = d.MainModelPolicy(policy_id=UUID(int=26), workspace_id=approval.expected_scope.workspace_id,
        actor_id=UUID(int=27), config_sha256=sha(encoded(config())),
        allowed_content_sha256s=(api().basis_digest(approval),), max_total_usd='1', max_calls=1,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    with pytest.raises(ServiceError) as failure:
        registry.grant(policy, UUID(int=28), basis=approval)
    assert failure.value.code == 'BLOCKED_LIVE' and calls == []
    # The ledger now supports complete prepared inputs. Neither an empty object
    # nor an offline description alone becomes a valid persisted submission.
    for raw in ('{}', encoded(approval)):
        with pytest.raises(ValueError):
            _input({'input_format': 'profile-text-v1', 'input_json': raw})
    prepared = api().prepare(*saved(), approval, config(), composer_revision=4)
    assert _input({'input_format':'profile-text-v1', 'input_json':encoded(prepared)}) == prepared
