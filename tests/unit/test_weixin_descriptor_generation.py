"""Compact immutable links bind the existing source and historical target."""
from uuid import uuid4

from pydantic import ValidationError
import pytest

from cn_contract import domain as d
from cn_contract.record_codec import sha


def model():
    assert hasattr(d,'WeixinDescriptorGeneration'),'D2g5b needs a centralized immutable descriptor generation'
    return d.WeixinDescriptorGeneration


def values(**changes):
    row=dict(descriptor_id=uuid4(),generation_id=uuid4(),generation_sha256='a'*64,task_binding_id=uuid4(),
        scope_sha256='b'*64,payload_sha256='c'*64)
    row.update(changes)
    encoded={key:str(value) for key,value in row.items()}
    return dict(**row,provenance_sha256=sha(encoded))


def test_seven_field_link_is_frozen_and_canonical_roundtrip():
    value=model()(**values())
    assert len(value.model_dump())==7
    assert model().model_validate_json(value.model_dump_json())==value
    with pytest.raises(ValidationError):value.generation_id=uuid4()


@pytest.mark.parametrize('field',['descriptor_id','generation_id','task_binding_id','generation_sha256','scope_sha256','payload_sha256'])
def test_hash_covers_every_parent_and_payload(field):
    value=values();value[field]=uuid4() if field.endswith('_id') else 'f'*64
    with pytest.raises(ValidationError):model()(**value)


@pytest.mark.parametrize('field',['generation_sha256','scope_sha256','payload_sha256','provenance_sha256'])
def test_digest_format_is_strict_even_when_recomputed(field):
    value=values();value[field]='not-a-digest'
    with pytest.raises(ValidationError):model()(**value)


@pytest.mark.parametrize('extra',['scope','created_at','generation','account_id','peer','can_dispatch','mode'])
def test_link_cannot_add_body_time_or_execution_authority(extra):
    with pytest.raises(ValidationError):model()(**values(),**{extra:'unsupported'})
