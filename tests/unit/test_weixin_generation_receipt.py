"""A history receipt is a minimal projection, never current transport authority."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d, 'WeixinGenerationReceiptView'), 'D2g2 needs a private bounded HTTP receipt'
    return d.WeixinGenerationReceiptView


def values(**changes):
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=0, materials_revision=0)
    return {**dict(generation=1, request_id=uuid4(), scope=scope, scope_sha256=sha(scope.model_dump(mode='json')),
        previous_generation_sha256=None, previous_scope_sha256='a'*64, checkpoint_revision=0,
        created_at='2026-10-25T06:50:00Z', generation_sha256='b'*64), **changes}


@pytest.mark.parametrize('number', [1, 2])
def test_receipt_is_frozen_and_only_exposes_fixed_historical_metadata(number):
    value = model()(**values(generation=number, previous_generation_sha256=None if number == 1 else 'c'*64))
    assert value.mode == 'synthetic' and value.state == 'history_only'
    assert model().model_validate_json(value.model_dump_json()) == value
    assert len(value.model_dump()) == 11
    with pytest.raises(ValidationError):
        value.state = 'current'


@pytest.mark.parametrize('changes', [
    {'mode':'live'}, {'state':'current'}, {'state':'paused'}, {'generation':0}, {'generation':True},
    {'generation':'1'}, {'checkpoint_revision':-1}, {'checkpoint_revision':False},
    {'scope_sha256':'c'*64}, {'generation_sha256':'x'*64}, {'previous_generation_sha256':'c'*64},
    {'generation':2}, {'created_at':'2026-10-25T06:50:00'}, {'actor_id':str(uuid4())},
    {'root_mapping_id':str(uuid4())}, {'task_binding_id':str(uuid4())}, {'reason':'private user input'},
    {'account_id':str(uuid4())}, {'bot_account_id':'private bot'}, {'sender_peer_id':'private peer'},
])
def test_receipt_rejects_invented_authority_private_fields_and_inconsistent_scope(changes):
    with pytest.raises(ValidationError):
        model()(**values(**changes))
