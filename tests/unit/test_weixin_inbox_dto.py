"""Credential-free snapshots have exact source identities and no task capabilities."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d


def model(name):
    assert hasattr(d, name), 'D2a requires the credential-free ' + name
    return getattr(d, name)


def account(**changes):
    return dict(id=uuid4(), workspace_id=uuid4(), owner_id=uuid4(),
        bot_account_id='synthetic-bot-account', mode='synthetic', initial_cursor='opaque:start',
        checkpoint_revision=0, upstream_cursor='opaque:start', created_at=datetime.now(timezone.utc),
        revoked_at=None, revoked_by=None, revoke_reason=None, **changes)


def descriptor(**changes):
    value = dict(id=uuid4(), poll_id=uuid4(), ordinal=1, sender_peer_id='synthetic-peer',
        upstream_message_id='18446744073709551615', source_event_id='wx1:'+'a'*64,
        source_sha256='b'*64, status='accepted_pending_dispatch', reason=None,
        mapping_id=uuid4(), prior_descriptor_id=None,
        payload=d.TaskInboxEventInput(event_id='wx1:'+'a'*64, text='独立虚构合同说明'))
    value.update(changes)
    return value


def test_account_snapshot_is_exact_frozen_synthetic_and_utc():
    value = model('WeixinAccountSnapshot')(**account())
    assert value.mode == 'synthetic' and value.upstream_cursor == 'opaque:start'
    assert value.created_at.utcoffset().total_seconds() == 0
    with pytest.raises(ValidationError): value.checkpoint_revision = 9


@pytest.mark.parametrize('field,value', [
    ('bot_account_id',' synthetic-bot'),('bot_account_id','bad\npeer'),
    ('bot_account_id','x'*257),('mode','live'),('checkpoint_revision',True),
    ('initial_cursor',3),('upstream_cursor','x'*262145),('created_at','2026-10-24'),
    ('revoked_at',datetime.now(timezone.utc)),('revoked_by',uuid4()),('revoke_reason','reason'),
], ids=['identity-space','identity-control','identity-long','live-mode','bool-revision',
    'numeric-cursor','long-cursor','naive-time','partial-revoked-at','partial-revoked-by','partial-reason'])
def test_account_rejects_coercion_inexact_identity_and_partial_revocation(field,value):
    values=account(); values[field]=value
    with pytest.raises(ValidationError): model('WeixinAccountSnapshot')(**values)


@pytest.mark.parametrize('changes', [
    {'upstream_message_id':'01'}, {'upstream_message_id':'18446744073709551616'},
    {'upstream_message_id':1}, {'sender_peer_id':None}, {'source_event_id':'generic-id'},
    {'status':'accepted_pending_dispatch','mapping_id':None},
    {'status':'accepted_pending_dispatch','reason':'replayed'},
    {'status':'blocked','reason':'message_invalid'},
    {'status':'blocked','payload':None,'reason':None},
    {'status':'duplicate','payload':None,'reason':'replayed'},
    {'status':'blocked','payload':None,'reason':'credential-secret'},
])
def test_descriptor_rejects_partial_source_and_contradictory_outcomes(changes):
    with pytest.raises(ValidationError): model('WeixinInboxDescriptor')(**descriptor(**changes))


@pytest.mark.parametrize('payload', [
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',task_id=uuid4()),
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',start_new=True),
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',media=(
        d.TaskMediaInput(media_id='source',name='虚构.docx',mime='application/pdf'),)),
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',media=(
        d.TaskMediaInput(media_id='source',name='虚构.pdf',mime='application/pdf',status='unsupported'),)),
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',media=(
        d.TaskMediaInput(media_id='source',name='虚构.pdf',mime='application/pdf',attachment_id=uuid4()),)),
    d.TaskInboxEventInput(event_id='wx1:'+'a'*64,text='虚构',reply_to_event_id='unscoped'),
])
def test_accepted_descriptor_cannot_carry_execution_or_attachment_capabilities(payload):
    with pytest.raises(ValidationError): model('WeixinInboxDescriptor')(**descriptor(payload=payload))


def test_blocked_without_source_and_duplicate_are_explicit_nonpayload_outcomes():
    blocked=model('WeixinInboxDescriptor')(**descriptor(sender_peer_id=None,
        upstream_message_id=None,source_event_id=None,payload=None,mapping_id=None,
        status='blocked',reason='message_invalid'))
    duplicate=model('WeixinInboxDescriptor')(**descriptor(payload=None,status='duplicate',
        reason='replayed',prior_descriptor_id=uuid4()))
    assert blocked.payload is duplicate.payload is None


def test_poll_requires_complete_ordered_descriptor_list_and_exact_hash():
    from cn_contract.record_codec import sha
    kind=model('WeixinPollReceipt')
    item=model('WeixinInboxDescriptor')(**descriptor())
    values=dict(id=item.poll_id,account_id=uuid4(),request_id=uuid4(),request_sha256='c'*64,
        response_sha256='d'*64,expected_revision=0,next_revision=1,expected_cursor='opaque:a',
        next_cursor='opaque:b',descriptor_count=1,created_at=datetime.now(timezone.utc),descriptors=(item,))
    canonical=dict(values); canonical['receipt_sha256']='0'*64
    with pytest.raises(ValidationError): kind(**canonical)
    serialized={**values,'created_at':values['created_at'].isoformat().replace('+00:00','Z'),
        'id':str(values['id']),'account_id':str(values['account_id']),'request_id':str(values['request_id']),
        'descriptors':[item.model_dump(mode='json')]}
    valid=kind(**values,receipt_sha256=sha(serialized))
    assert valid.descriptor_count == len(valid.descriptors) == 1
    with pytest.raises(ValidationError): kind(**{**valid.model_dump(),'descriptor_count':0})
    with pytest.raises(ValidationError): kind(**{**valid.model_dump(),'next_revision':2})


def test_mapping_scope_hash_and_revocation_reason_are_not_coerced_or_trimmed():
    from cn_contract.record_codec import sha
    at=datetime.now(timezone.utc)
    scope=d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),scope_kind='conversation',
        scope_ref=None,binding_revision=1,input_revision=0,materials_revision=0)
    values=dict(id=uuid4(),account_id=uuid4(),sender_peer_id='synthetic-peer',task_binding_id=uuid4(),
        scope=scope,scope_sha256=sha(scope.model_dump(mode='json')),created_at=at)
    assert model('WeixinPeerBindingSnapshot')(**values).scope == scope
    with pytest.raises(ValidationError): model('WeixinPeerBindingSnapshot')(**{**values,'scope_sha256':'a'*64})
    with pytest.raises(ValidationError): model('WeixinPeerBindingSnapshot')(**values,
        revoked_at=at,revoked_by=uuid4(),revoke_reason='   ')
