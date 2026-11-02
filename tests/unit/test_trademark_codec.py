import pytest

from cn_contract.assistant import material_codec as codec
from tests.helpers.case_evidence import response
from tests.unit.test_contract_live_method import request, sample


def fixture():
    from cn_contract.assistant.trademark_triage import select_method
    from tests.helpers.trademark_triage import manifest_for
    manifest = manifest_for()
    manifest = manifest.model_copy(update={'trademark_triage':select_method('case', manifest.question)})
    _, selection, config = sample('case')
    selection = selection.model_copy(update={'parent_business_run_id':manifest.parent_business_run_id,
        'expected_scope':selection.expected_scope.model_copy(update={
            'conversation_id':manifest.sources[0].reference.conversation_id, 'input_revision':1})})
    return request(codec.build_basis(selection, manifest, config)), config


def test_trademark_wire_output_and_readback_keep_exact_method_and_quotes():
    from tests.helpers.trademark_triage import draft_for
    req, cfg = fixture()
    assert codec.rebuild_basis(req.basis, cfg) == req.basis
    wire = codec.build_request(req, cfg)
    assert '当前方法 trademark-triage-v5' in wire['messages'][0]['content']
    assert 'format_version固定trademark-triage-v2。' in wire['messages'][0]['content']
    output = codec.decode(response(draft_for(req.basis.manifest)), req, cfg, 'synthetic-key').output
    assert output is not None and output.trademark_triage is not None
    assert codec.validate_manifest_candidate(output, req.basis.manifest) == output
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(output.model_copy(update={'text':'已认定侵权'}), req.basis.manifest)
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(output, req.basis.manifest.model_copy(update={'trademark_triage':None}))


@pytest.mark.parametrize('damage', ['quote','conclusion','approval','missing_factor','legacy','hearing'])
def test_invalid_factors_are_rejected_without_losing_usage(damage):
    from tests.helpers.trademark_triage import draft_for
    req, cfg = fixture()
    value = draft_for(req.basis.manifest)
    if damage == 'quote': value['quotes'][0]['exact_quote'] = '没有读到的文本'
    if damage == 'conclusion': value['conclusion'] = '侵权成立'
    if damage == 'approval': value['approved'] = True
    if damage == 'missing_factor': value['factors'].pop()
    if damage == 'legacy': value = {'text':'旧文本代替因素表', 'citations':[req.basis.manifest.sources[0].source_id]}
    if damage == 'hearing': value['hearing_turns'] = []
    result = codec.decode(response(value), req, cfg, 'synthetic-key')
    assert result.output is None and result.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.usage.total_tokens == 42


@pytest.mark.parametrize('damage', ['source','hash','right_type','workflow','case_method'])
def test_wire_rejects_forged_method_or_conflicting_workflow(damage):
    req, cfg = fixture()
    manifest = req.basis.manifest
    changes = {'source':{'source_reference':'unverified'},'hash':{'method_sha256':'a'*64},'right_type':{'right_type':'patent'}}
    if damage in changes:
        manifest = manifest.model_copy(update={'trademark_triage':manifest.trademark_triage.model_copy(update=changes[damage])})
    if damage == 'workflow': manifest = manifest.model_copy(update={'workflow':'court'})
    if damage == 'case_method':
        from cn_contract.assistant.case_evidence import select_method
        manifest = manifest.model_copy(update={'case_method':select_method('case','整理时间线')})
    with pytest.raises(ValueError):
        codec.build_manifest_request(manifest, cfg)
