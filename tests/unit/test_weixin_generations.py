"""Immutable cross-conversation generation records do not enable runtime dispatch."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d, 'WeixinPeerGeneration'), 'D2f needs immutable target-generation records'
    return d.WeixinPeerGeneration


def values(**changes):
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=0, materials_revision=0).model_dump(mode='json')
    row = dict(id=str(uuid4()), root_mapping_id=str(uuid4()), generation=1, request_id=str(uuid4()),
        actor_id=str(uuid4()), task_binding_id=str(uuid4()), scope=scope, scope_sha256=sha(scope),
        previous_generation_sha256=None, previous_scope_sha256='a'*64, checkpoint_revision=0,
        created_at='2026-10-24T16:00:00Z', reason='独立虚构跨对话目标记录')
    row.update(changes)
    return {**row, 'generation_sha256':sha(row)}


@pytest.mark.parametrize('number', [1, 2])
def test_generation_roundtrip_is_frozen_and_includes_complete_hash(number):
    row = values(generation=number, previous_generation_sha256=None if number == 1 else 'b'*64)
    value = model()(**row)
    assert model().model_validate_json(value.model_dump_json()) == value
    assert len(value.model_dump()) == 14
    with pytest.raises(ValidationError):
        value.generation = number+1
    row['generation_sha256'] = 'f'*64
    with pytest.raises(ValidationError):
        model()(**row)


@pytest.mark.parametrize('change', [
    {'generation':0}, {'generation':True}, {'generation':'1'}, {'checkpoint_revision':-1},
    {'checkpoint_revision':False}, {'checkpoint_revision':'0'}, {'created_at':'2026-10-24'},
    {'created_at':'2026-10-24T16:00:00+08:00'}, {'previous_generation_sha256':'b'*64},
    {'generation':2}, {'scope_sha256':'f'*64}, {'previous_scope_sha256':'x'*64},
    {'reason':''}, {'reason':' '}, {'reason':' surrounding '}, {'reason':'x'*201},
    {'account_id':str(uuid4())}, {'new_peer_id':'unsupported'},
])
def test_generation_rejects_implicit_numbering_broken_hashes_or_extra_authority(change):
    with pytest.raises(ValidationError):
        model()(**values(**change))
