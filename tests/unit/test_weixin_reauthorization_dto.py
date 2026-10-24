"""Explicit scope refreshes are immutable, bounded and hash-bound local authority."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.record_codec import sha


def scope():
    return d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),
        binding_revision=1,input_revision=1,materials_revision=0)


def models():
    assert hasattr(d,'WeixinPeerRefreshInput'), 'D2d needs explicit refresh input'
    assert hasattr(d,'WeixinPeerScopeGrant'), 'D2d needs an immutable authorization receipt'
    return d.WeixinPeerRefreshInput,d.WeixinPeerScopeGrant


def request(**changes):
    values=dict(request_id=uuid4(),expected_grant_revision=0,expected_scope_sha256='a'*64,
        expected_scope=scope(),reason='explicit fictional scope refresh')
    return {**values,**changes}


def grant(**changes):
    value=scope().model_dump(mode='json')
    values={key:str(uuid4()) for key in ('id','mapping_id','request_id','actor_id')}
    values.update(revision=1,previous_scope_sha256='a'*64,scope=value,scope_sha256=sha(value),
        checkpoint_revision=0,created_at='2026-10-24T14:35:00Z',reason='explicit fictional scope refresh')
    values.update(changes)
    return {**values,'grant_sha256':sha(values)}


def test_refresh_input_and_grant_round_trip_are_frozen():
    input_model,grant_model=models()
    assert input_model(**request()).expected_grant_revision==0
    value=grant_model(**grant())
    assert grant_model.model_validate_json(value.model_dump_json())==value
    with pytest.raises(ValidationError):value.revision=2


@pytest.mark.parametrize('change',[
    {'expected_grant_revision':True},{'expected_grant_revision':-1},
    {'expected_grant_revision':'1'},{'expected_scope_sha256':'x'*64},
    {'reason':''},{'reason':' '},{'reason':' surrounding '},{'reason':'a'*201},
    {'actor_id':str(uuid4())},{'expires_at':'2099-01-01T00:00:00Z'},
])
def test_input_rejects_implicit_or_caller_owned_authority(change):
    with pytest.raises(ValidationError):models()[0](**request(**change))


@pytest.mark.parametrize('change',[
    {'revision':0},{'revision':True},{'checkpoint_revision':-1},{'checkpoint_revision':True},
    {'created_at':'2026-10-24'},{'created_at':'2026-10-24T14:35:00+08:00'},
    {'scope_sha256':'0'*64},{'previous_scope_sha256':'x'*64},
    {'reason':' trailing '},{'account_id':str(uuid4())},
])
def test_grant_rejects_tampered_or_expanded_fields(change):
    with pytest.raises(ValidationError):models()[1](**grant(**change))


def test_grant_hash_covers_every_fixed_field():
    values=grant();values['grant_sha256']='0'*64
    with pytest.raises(ValidationError):models()[1](**values)
