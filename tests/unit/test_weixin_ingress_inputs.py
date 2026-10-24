"""Synthetic ingress inputs never accept caller ownership or execution capabilities."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d


def model(name):
    assert hasattr(d, name), 'D2b requires '+name
    return getattr(d,name)


def scope():
    return d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),scope_kind='conversation',
        scope_ref=None,binding_revision=1,input_revision=0,materials_revision=0)


def test_inputs_are_exact_frozen_and_have_no_caller_owned_identity():
    account=model('WeixinAccountCreateInput')(bot_account_id='synthetic-only-bot')
    peer=model('WeixinPeerBindInput')(sender_peer_id='synthetic-peer',task_binding_id=uuid4(),expected_scope=scope())
    poll=model('WeixinPollInput')(request_id=uuid4(),expected_revision=0,expected_cursor='opaque:0')
    revoke=model('WeixinRevokeInput')(reason='独立虚构撤权')
    assert account.initial_cursor == '' and peer.expected_scope == scope_from(peer)
    assert poll.expected_revision == 0 and revoke.reason == '独立虚构撤权'
    with pytest.raises(ValidationError): poll.expected_revision=1


def scope_from(peer):
    return d.ScopeSnapshot.model_validate(peer.expected_scope.model_dump())


@pytest.mark.parametrize('kind,values',[
    ('WeixinAccountCreateInput',{'bot_account_id':' padded'}),
    ('WeixinAccountCreateInput',{'bot_account_id':'bad\nidentity'}),
    ('WeixinAccountCreateInput',{'bot_account_id':'x'*257}),
    ('WeixinAccountCreateInput',{'bot_account_id':'synthetic','owner_id':str(uuid4())}),
    ('WeixinAccountCreateInput',{'bot_account_id':'synthetic','mode':'live'}),
    ('WeixinAccountCreateInput',{'bot_account_id':'synthetic','initial_cursor':3}),
    ('WeixinAccountCreateInput',{'bot_account_id':'synthetic','initial_cursor':'x'*262145}),
    ('WeixinRevokeInput',{'reason':''}),('WeixinRevokeInput',{'reason':' \n\t'}),
    ('WeixinRevokeInput',{'reason':'x'*201}),('WeixinRevokeInput',{'reason':3}),
    ('WeixinRevokeInput',{'reason':'synthetic','revoked_by':str(uuid4())}),
    ('WeixinPollInput',{'request_id':uuid4(),'expected_revision':True,'expected_cursor':''}),
    ('WeixinPollInput',{'request_id':uuid4(),'expected_revision':-1,'expected_cursor':''}),
    ('WeixinPollInput',{'request_id':uuid4(),'expected_revision':'0','expected_cursor':''}),
    ('WeixinPollInput',{'request_id':uuid4(),'expected_revision':0,'expected_cursor':False}),
    ('WeixinPollInput',{'request_id':uuid4(),'expected_revision':0,'expected_cursor':'','next_revision':1}),
    ('WeixinPeerBindInput',{'sender_peer_id':' ','task_binding_id':uuid4(),'expected_scope':scope()}),
    ('WeixinPeerBindInput',{'sender_peer_id':'peer','task_binding_id':uuid4(),'expected_scope':scope(),'account_id':uuid4()}),
],ids=[str(index) for index in range(19)])
def test_invalid_inputs_do_not_coerce_or_expand_authority(kind,values):
    with pytest.raises(ValidationError): model(kind)(**values)
