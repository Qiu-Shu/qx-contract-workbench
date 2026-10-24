"""Explicit generation requests carry a complete caller-observed CAS boundary."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d


def model():
    assert hasattr(d, 'WeixinPeerGenerationInput'), 'D2g1 needs explicit generation CAS input'
    return d.WeixinPeerGenerationInput


def values(**changes):
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
        input_revision=0, materials_revision=0)
    return {**dict(request_id=uuid4(), expected_generation=0, expected_previous_generation_sha256=None,
        expected_previous_scope_sha256='a'*64, expected_checkpoint_revision=2, task_binding_id=uuid4(),
        expected_scope=scope, reason='独立虚构显式目标追加'), **changes}


@pytest.mark.parametrize('number', [0, 2])
def test_generation_input_roundtrip_is_frozen_and_has_only_eight_caller_fields(number):
    value = model()(**values(expected_generation=number,
        expected_previous_generation_sha256=None if number == 0 else 'b'*64))
    assert len(value.model_dump()) == 8
    assert model().model_validate_json(value.model_dump_json()) == value
    with pytest.raises(ValidationError):
        value.reason = 'changed reason'


@pytest.mark.parametrize('changes', [
    {'expected_generation':-1}, {'expected_generation':False}, {'expected_generation':'0'},
    {'expected_checkpoint_revision':-1}, {'expected_checkpoint_revision':True}, {'expected_checkpoint_revision':'2'},
    {'expected_previous_generation_sha256':'b'*64}, {'expected_generation':1},
    {'expected_previous_scope_sha256':'x'*64}, {'reason':''}, {'reason':' '}, {'reason':' reason '},
    {'reason':'x'*201}, {'reason':1}, {'actor_id':str(uuid4())}, {'created_at':'2026-10-25T00:00:00Z'},
    {'account_id':str(uuid4())}, {'generation_sha256':'c'*64},
])
def test_generation_input_rejects_coercion_incomplete_cas_and_server_authority(changes):
    with pytest.raises(ValidationError):
        model()(**values(**changes))
