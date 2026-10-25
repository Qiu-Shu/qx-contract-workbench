"""Only complete historical CAS snapshots may leave the local head projection."""
from uuid import uuid4

from pydantic import ValidationError
import pytest

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d,'WeixinGenerationHeadView'), 'D2g3 needs the seven-field historical head'
    return d.WeixinGenerationHeadView


def values(**changes):
    scope=d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),binding_revision=1,input_revision=0,materials_revision=0)
    return {**dict(generation=0,generation_sha256=None,scope=scope,
        scope_sha256=sha(scope.model_dump(mode='json')),checkpoint_revision=2),**changes}


@pytest.mark.parametrize('number',[0,1,3])
def test_head_is_frozen_seven_fields_and_history_only(number):
    value=model()(**values(generation=number,generation_sha256='a'*64 if number else None))
    assert set(value.model_dump())=={'mode','state','generation','generation_sha256','scope','scope_sha256','checkpoint_revision'}
    assert value.mode=='synthetic' and value.state=='history_only'
    assert model().model_validate_json(value.model_dump_json())==value
    with pytest.raises(ValidationError): value.generation=9


@pytest.mark.parametrize('change',[
    {'generation':-1},{'generation':False},{'generation':'0'},{'checkpoint_revision':-1},
    {'checkpoint_revision':True},{'checkpoint_revision':'2'},{'generation':1},
    {'generation_sha256':'a'*64},{'generation_sha256':'x'*64},{'scope_sha256':'b'*64},
    {'mode':'live'},{'state':'current'},{'can_append':True},{'account_id':str(uuid4())},
    {'root_mapping_id':str(uuid4())},{'task_binding_id':str(uuid4())},{'actor_id':str(uuid4())},
    {'reason':'private text'},{'bot_account_id':'private bot'},{'sender_peer_id':'private peer'},
])
def test_head_rejects_incomplete_cas_invented_authority_and_private_metadata(change):
    with pytest.raises(ValidationError): model()(**values(**change))
