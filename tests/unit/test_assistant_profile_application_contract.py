"""Synthetic API boundaries keep save intent separate from execution authority."""
from uuid import UUID

import pytest

from cn_contract import domain as d
from tests.unit.test_assistant_profile_preparation import basis, draft


def selection():
    message = draft()
    return dict(request_id=message.request_id, expected_scope=message.expected_scope,
                expected_composer_revision=message.expected_composer_revision)


def test_profile_preview_selection_does_not_accept_caller_text_or_permission():
    value = d.MainProfileSelection(**selection())
    assert value.project_intake is False
    for key, extra in [('content', 'caller text'), ('policy', {}), ('base_profile_revision', 19)]:
        with pytest.raises(ValueError):
            d.MainProfileSelection(**selection(), **{key: extra})


@pytest.mark.parametrize('flag', [0, 1, 'true', 'false', None])
def test_profile_projection_cannot_be_coerced_from_a_non_boolean(flag):
    with pytest.raises(ValueError):
        d.MainProfileSelection(**selection(), project_intake=flag)
    with pytest.raises(ValueError):
        d.MainProfileSubmission(**draft().model_dump(), project_intake=flag)


def test_profile_submission_preserves_original_message_without_promoting_old_input():
    message = draft()
    value = d.MainProfileSubmission(**message.model_dump(), project_intake=True)
    assert d.AssistantMessageInput.model_validate(value.model_dump(exclude={'project_intake'})) == message
    with pytest.raises(ValueError):
        d.AssistantMessageInput.model_validate(value.model_dump())
    with pytest.raises(ValueError):
        d.MainProfileSubmission(**message.model_dump(), policy_id=UUID(int=17))


def test_native_profile_authorization_requires_complete_purpose_basis_and_hides_session():
    values = dict(session_token='synthetic-session', expected_config_version=UUID(int=42),
                  basis=basis(), max_total_usd='1', valid_for_seconds=120)
    value = d.NativeProfileAuthorization(**values)
    assert value.basis.purpose == 'reply_and_profile_draft'
    assert 'synthetic-session' not in repr(value)
    with pytest.raises(ValueError):
        d.NativeProfileAuthorization(**values, max_rounds=2)
    with pytest.raises(ValueError):
        d.NativeModelAuthorization(**values)
    for field, changed in [('valid_for_seconds', True), ('valid_for_seconds', 901), ('max_total_usd', '0')]:
        with pytest.raises(ValueError):
            d.NativeProfileAuthorization(**{**values, field: changed})
