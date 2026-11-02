"""Versioned complete history preserves legacy JSON and independent byte limits."""
from uuid import UUID

import pytest
from cn_contract import domain as d
from cn_contract.assistant import material_codec as codec
from cn_contract.assistant.providers.policy import encoded, sha
from tests.unit.test_material_wire_capacity import fictional_manifest
from tests.unit.test_material_input_budget import boundary_input


def manifest_at(size, version='contract-full-text-v1'):
    manifest, _ = fictional_manifest(1)
    source = manifest.sources[0]
    ref = source.reference.model_copy(update={'source_revision':3})
    source = d.MainMaterialSource(source_id=sha(encoded(ref)),reference=ref)
    count = 10000 if size > 60000 else 5000
    pair = [dict(message_id=str(UUID(int=i+1)),role=role,source_revision=1,content='中'*count)
        for i,role in enumerate(('user','assistant'))]
    pair[1]['content'] += 'x' * (size-len(codec.json_bytes(pair)))
    assert len(codec.json_bytes(pair)) == size
    value = manifest.model_dump(mode='python') | {'sources':(source,*manifest.sources[1:]),
        'conversation_history':pair}
    if version is not None:
        value['history_format'] = version
    return value


@pytest.mark.parametrize('size', [65535,65536])
def test_new_contract_history_accepts_complete_pair_up_to_its_exact_utf8_limit(size):
    value = manifest_at(size)
    actual = d.MainMaterialManifest.model_validate(value)
    assert len(codec.json_bytes([item.model_dump(mode='json') for item in actual.conversation_history])) == size


@pytest.mark.parametrize('size,version', [(65537,'contract-full-text-v1'),(32769,None)])
def test_history_rejects_one_byte_over_its_versioned_limit(size,version):
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(manifest_at(size,version))


def test_legacy_manifest_still_has_no_new_field_and_accepts_exact_old_limit():
    actual = d.MainMaterialManifest.model_validate(manifest_at(32768,None))
    assert 'history_format' not in actual.model_dump(mode='json')


@pytest.mark.parametrize('workflow,version', [('case','contract-full-text-v1'),
    ('sales','contract-full-text-v1'),('court','contract-full-text-v1'),('contract','unknown')])
def test_history_version_does_not_expand_other_workflows(workflow,version):
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(manifest_at(32768,version) | {'workflow':workflow})


def test_new_format_keeps_per_message_character_limit():
    value = manifest_at(32768)
    value['conversation_history'][1]['content'] = 'x'*20001
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(value)


@pytest.mark.parametrize('offset', [-1,0,1])
def test_preview_checks_exact_durable_envelope_even_when_wire_fits(offset):
    request, config, _ = boundary_input(262144+offset)
    basis = request.basis
    selection = d.MainMaterialSelection.model_validate(basis.model_dump(include=set(d.MainMaterialSelection.model_fields)))
    if offset > 0:
        with pytest.raises(ValueError,match='MATERIAL_INPUT_TOO_LARGE'):
            codec.build_preview_basis(selection,basis.manifest,config)
    else:
        assert codec.build_preview_basis(selection,basis.manifest,config) == basis
