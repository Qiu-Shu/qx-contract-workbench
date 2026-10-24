"""Dispatch acknowledgements identify immutable receipt sources, never a mutable draft."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.record_codec import sha


def values(**changes):
    data={key:str(uuid4()) for key in ('id','descriptor_id','account_id','mapping_id','actor_id','task_binding_id','task_event_id')}
    data.update(source_event_id='wx1:'+'a'*64,payload_sha256='b'*64,expected_task_cursor=0,
        next_task_cursor=1,created_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'))
    data.update(changes)
    return {**data,'receipt_sha256':sha(data)}


def model():
    assert hasattr(d,'WeixinDispatchReceipt'), 'D2c needs a fixed source-bound acknowledgement'
    return d.WeixinDispatchReceipt


def test_complete_receipt_is_frozen_and_hash_bound_without_mutable_task_state():
    receipt=model()(**values())
    assert receipt.next_task_cursor==1 and 'task_id' not in receipt.model_dump()
    with pytest.raises(ValidationError): receipt.next_task_cursor=2


@pytest.mark.parametrize('change',[
    {'expected_task_cursor':True},{'expected_task_cursor':-1},{'next_task_cursor':0},
    {'next_task_cursor':2},{'payload_sha256':'x'*64},{'source_event_id':'other-source'},
    {'created_at':'2026-10-24'},{'actor_id':'not-a-uuid'},{'task_id':str(uuid4())},
    {'draft_state':'collecting'},
],ids=[str(i) for i in range(10)])
def test_receipt_rejects_inconsistent_or_expanded_authority(change):
    with pytest.raises(ValidationError): model()(**values(**change))


def test_receipt_rejects_tampered_hash_even_when_fields_are_well_formed():
    data=values();data['receipt_sha256']='0'*64
    with pytest.raises(ValidationError):model()(**data)
