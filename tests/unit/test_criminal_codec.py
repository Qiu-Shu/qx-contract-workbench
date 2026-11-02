from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import material_codec as codec
from tests.helpers.criminal_analysis import draft_for, manifest_for, response
from tests.unit.test_contract_live_method import request, sample


def fixture():
    from cn_contract.assistant.criminal_analysis import select_method
    manifest = manifest_for()
    manifest = manifest.model_copy(update={'criminal_analysis':select_method('case', manifest.question, manifest.sources)})
    _, selection, config = sample('case')
    selection = selection.model_copy(update={'parent_business_run_id':manifest.parent_business_run_id,
        'expected_scope':selection.expected_scope.model_copy(update={
            'conversation_id':manifest.sources[0].reference.conversation_id, 'input_revision':1})})
    return request(codec.build_basis(selection, manifest, config)), config


def test_criminal_packet_and_candidate_roundtrip_keep_method_evidence_and_fixed_text():
    req, cfg = fixture()
    assert codec.rebuild_basis(req.basis, cfg) == req.basis
    wire = codec.build_request(req, cfg)
    assert 'criminal-analysis-v1' in wire['messages'][0]['content']
    output = codec.decode(response(draft_for(req.basis.manifest)), req, cfg, 'synthetic-key').output
    assert output is not None and output.criminal_analysis is not None
    assert codec.validate_manifest_candidate(output, req.basis.manifest) == output
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(output.model_copy(update={'text':'已作有罪认定'}), req.basis.manifest)
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(output, req.basis.manifest.model_copy(update={'criminal_analysis':None}))


@pytest.mark.parametrize('damage', ['quote','stage','approval','evidence','legacy','hearing'])
def test_rejected_model_data_keeps_known_usage(damage):
    req, cfg = fixture()
    value = draft_for(req.basis.manifest)
    if damage == 'quote': value['quotes'][0]['exact_quote'] = '虚构的另一句话'
    if damage == 'stage': value['stage'] = 'prosecution'
    if damage == 'approval': value['redacted'] = True
    if damage == 'evidence': value['elements'][0]['evidence_ids'] = ['e3']
    if damage == 'legacy': value = {'text':'未经结构核对', 'citations':[req.basis.manifest.sources[0].source_id]}
    if damage == 'hearing': value['hearing_turns'] = []
    result = codec.decode(response(value), req, cfg, 'synthetic-key')
    assert result.output is None and result.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.usage.total_tokens == 42


@pytest.mark.parametrize('damage', ['stage','policy','workflow','case_method'])
def test_wire_rejects_forged_policy_stage_or_conflicting_protocol(damage):
    req, cfg = fixture()
    manifest = req.basis.manifest
    if damage == 'stage':
        manifest = manifest.model_copy(update={'criminal_analysis':manifest.criminal_analysis.model_copy(update={'stage':'trial'})})
    if damage == 'policy':
        manifest = manifest.model_copy(update={'criminal_analysis':manifest.criminal_analysis.model_copy(update={'material_policy':'approved'})})
    if damage == 'workflow': manifest = manifest.model_copy(update={'workflow':'court'})
    if damage == 'case_method':
        from cn_contract.assistant.case_evidence import select_method
        manifest = manifest.model_copy(update={'case_method':select_method('case','整理时间线')})
    with pytest.raises(ValueError):
        codec.build_manifest_request(manifest, cfg)
