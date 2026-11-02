"""New presentation revision, retaining immutable v1 request and result behavior."""
import pytest

from cn_contract.assistant import material_codec as codec, trademark_triage as method
from tests.helpers.trademark_triage import draft_for, manifest_for
from tests.unit.test_contract_live_method import sample


def test_new_trademark_method_is_a_bound_revision_and_does_not_touch_quoted_words():
    manifest = manifest_for(texts=('原件写有respondent留空，仅为待审原文。', '虚构乙否认参照标识。'))
    snapshot = method.select_method('case', manifest.question)
    assert snapshot.method_id == 'trademark-triage-v5'
    manifest = manifest.model_copy(update={'trademark_triage': snapshot})
    value = draft_for(manifest)
    value['factors'][0]['unresolved'] = ['未见对方权利材料，respondent留空；不推断无权。']
    value['gaps'] = ['没有直接使用记录，holder留空；尚待核验。']
    result = method.candidate(value, manifest)
    assert '未见对方权利材料，被主张方暂无已引述线索；不推断无权。' in result.text
    assert '没有直接使用记录，权利方暂无已引述线索；尚待核验。' in result.text
    assert '原件写有respondent留空，仅为待审原文。' in result.text
    assert result.trademark_triage.factors[0].unresolved == tuple(value['factors'][0]['unresolved'])
    assert codec.validate_manifest_candidate(result, manifest) == result


def test_old_trademark_snapshot_retains_request_and_unedited_presentation():
    manifest = manifest_for()
    old = method.select_method('case', manifest.question, method_id='trademark-triage-v1')
    assert old.method_id == 'trademark-triage-v1'
    assert old.method_sha256 == '7ad93dc0b7707585c2da0d9723fc57aa540974122e37f43c54546b1276248cfa'
    manifest = manifest.model_copy(update={'trademark_triage': old})
    value = draft_for(manifest)
    value['gaps'] = ['holder留空；历史原始待核文字。']
    result = method.candidate(value, manifest)
    assert 'holder留空；历史原始待核文字。' in result.text
    _, selection, config = sample('case')
    basis = codec.build_basis(selection, manifest, config)
    assert codec.rebuild_basis(basis, config) == basis
    assert codec.build_manifest_request(manifest, config)['messages'][0]['content'] == method.SYSTEM


@pytest.mark.parametrize('method_id,other_id', [
    (a,b) for a in ('trademark-triage-v1','trademark-triage-v2','trademark-triage-v3','trademark-triage-v4','trademark-triage-v5')
    for b in ('trademark-triage-v1','trademark-triage-v2','trademark-triage-v3','trademark-triage-v4','trademark-triage-v5') if a!=b])
def test_trademark_revision_cannot_borrow_another_revision_hash(method_id,other_id):
    other = method.select_method('case', '请做商标初筛。', method_id=other_id)
    forged = other.model_copy(update={'method_id': method_id})
    with pytest.raises(ValueError):
        method.method_system(forged)
