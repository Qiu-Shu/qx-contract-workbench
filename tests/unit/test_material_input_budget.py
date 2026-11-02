"""Wire and durable envelope have separate unchanged UTF-8 byte budgets."""
import pytest

from cn_contract import domain as d
from cn_contract.assistant import case_evidence, material_codec as codec
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.review.model_adapter import MAX_RAW_BYTES, strict_json
from tests.unit.test_contract_live_method import sample, request


def input_with_padding(length, max_output_tokens=1000):
    manifest, selection, config = sample('case')
    config = config.model_copy(update={'max_output_tokens': max_output_tokens})
    ref = manifest.sources[0].reference
    quote = '独立虚构边界材料："引号"\\路径\n🧪' + 'x' * length
    anchor = ref.anchor.model_copy(update={'quote': quote, 'quote_sha256': sha(quote),
        'start': 0, 'end': len(quote)})
    ref = ref.model_copy(update={'anchor': anchor})
    manifest = manifest.model_copy(update={
        'sources': (d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref),),
        'case_method': case_evidence.select_method('case', '整理时间线', method_id='case-evidence-v1')})
    basis = codec.build_basis(selection, manifest, config)
    value = request(basis)
    # Independently serialize the complete public DTO, not just the wire body.
    prepared = d.MainMaterialPreparedInput(request=value,
        wire_payload_json=codec.json_bytes(codec.build_request(value, config)).decode('utf-8'))
    return value, config, prepared


def boundary_input(target):
    _, _, baseline = input_with_padding(100000)
    padding = 100000 + (target - len(encoded(baseline).encode('utf-8'))) // 2
    value, config, prepared = input_with_padding(padding)
    if len(encoded(prepared).encode('utf-8')) == target - 1:
        # One extra source byte occurs twice; one fewer token-count digit occurs once.
        value, config, prepared = input_with_padding(padding + 1, max_output_tokens=999)
    assert len(encoded(prepared).encode('utf-8')) == target
    assert len(prepared.wire_payload_json.encode('utf-8')) < config.max_input_bytes
    return value, config, prepared


@pytest.mark.parametrize('offset', [-1, 0])
def test_prepared_input_at_or_below_persisted_limit_can_be_read_back(offset):
    value, config, expected = boundary_input(MAX_RAW_BYTES + offset)
    actual = codec.prepare(value, config)
    assert actual == expected
    assert d.MainMaterialPreparedInput.model_validate(strict_json(encoded(actual))) == actual


def test_full_input_one_byte_over_limit_is_rejected_even_when_wire_and_characters_fit():
    value, config, oversized = boundary_input(MAX_RAW_BYTES + 1)
    assert len(encoded(oversized)) < MAX_RAW_BYTES
    with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
        codec.prepare(value, config)
