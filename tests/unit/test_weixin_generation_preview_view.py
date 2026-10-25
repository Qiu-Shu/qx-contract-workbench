"""Generation previews are immutable translations, never runtime permissions."""
from uuid import uuid4

from pydantic import ValidationError
import pytest

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d,'WeixinGenerationPreview'), 'D2g5a needs a centralized preview-only DTO'
    return d.WeixinGenerationPreview


def values(generation=0):
    scope=d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),binding_revision=1,input_revision=0,materials_revision=0)
    head=d.WeixinGenerationHeadView(generation=generation,generation_sha256='a'*64 if generation else None,
        scope=scope,scope_sha256=sha(scope.model_dump(mode='json')),checkpoint_revision=2)
    local=d.WeixinOfflineScope(bot_account_id='synthetic-preview-bot',sender_peer_id='synthetic-preview-peer',
        owner_id=uuid4(),session_id=uuid4(),binding_id=uuid4(),expected_scope=scope,task_cursor=3,upstream_cursor='opaque:before')
    plan=d.WeixinOfflinePlan(scope=local,response_sha256='b'*64,next_upstream_cursor='opaque:after',batch=None,event_payload_hashes={})
    return dict(head=head,plan=plan)


@pytest.mark.parametrize('generation',[0,1,2])
def test_preview_has_four_frozen_fields_and_roundtrips(generation):
    value=model()(**values(generation))
    assert set(value.model_dump())=={'mode','state','head','plan'}
    assert value.mode=='synthetic' and value.state=='preview_only'
    assert model().model_validate_json(value.model_dump_json())==value
    with pytest.raises(ValidationError):value.state='current'


@pytest.mark.parametrize('change',[{'mode':'live'},{'state':'accepted'},{'can_dispatch':True},
    {'request_id':str(uuid4())},{'receipt_sha256':'c'*64},{'generation':1}])
def test_preview_cannot_claim_acceptance_receipt_or_runtime_authority(change):
    with pytest.raises(ValidationError):model()(**values(),**change)


def test_head_and_translated_target_scope_must_match_exactly():
    original=values(2);other=values(2)
    with pytest.raises(ValidationError):model()(head=original['head'],plan=other['plan'])


@pytest.mark.parametrize('field',['binding_revision','input_revision','materials_revision'])
def test_same_conversation_different_revision_cannot_match_preview_head(field):
    original=values();scope=original['head'].scope.model_copy(update={field:9})
    changed=original['head'].model_copy(update={'scope':scope,'scope_sha256':sha(scope.model_dump(mode='json'))})
    with pytest.raises(ValidationError):model()(head=changed,plan=original['plan'])
