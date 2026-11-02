"""New-method wiring with synthetic statements; does not measure model reasoning."""
import pytest
from cn_contract import domain as d
from cn_contract.assistant import trademark_triage as method, material_codec as codec
from cn_contract.assistant.providers.policy import sha
from tests.helpers.trademark_triage import manifest_for, draft_for
from tests.unit.test_contract_live_method import sample

def current():
    manifest=manifest_for(texts=('虚构甲称允许乙使用“桐岑记”，出具者身份未核。',
        '虚构补充说明称乙许可甲使用，未交代具体标的。'))
    return manifest.model_copy(update={'trademark_triage':method.select_method(
        'case',manifest.question,method_id='trademark-triage-v5')})

def test_current_method_is_frozen_to_wire_and_rebuilds_without_default_dependency(monkeypatch):
    manifest=current()
    assert method.select_method('case',manifest.question)==manifest.trademark_triage
    _,selection,config=sample('case')
    basis=codec.build_basis(selection,manifest,config)
    wire=codec.build_manifest_request(manifest,config)
    assert wire['messages'][0]['content']==method.SYSTEM_V5
    assert basis.system_sha256==manifest.trademark_triage.method_sha256==sha(method.SYSTEM_V5)
    assert method.SYSTEM_V5 != method.SYSTEM_V4
    monkeypatch.setattr(method,'CURRENT_METHOD_ID','trademark-triage-v99')
    assert codec.rebuild_basis(basis,config)==basis
    assert codec.build_manifest_request(manifest,config)==wire

def test_v5_retains_neutral_structure_original_quotes_and_literal_scope():
    manifest=current();raw=draft_for(manifest)
    for f in raw['factors']:f.update(holder=[],respondent=[],neutral=[])
    raw['factors'][0]['neutral']=[dict(text='两份陈述方向不同，第二份对象未说明，是否同一关系待核。',quote_ids=['q1','q2'])]
    raw['gaps']=['Neutral留空；此句仅检验既有呈现兼容，不证明模型会判断来源。']
    candidate=method.candidate(raw,manifest)
    assert candidate.trademark_triage.format_version=='trademark-triage-v2'
    assert candidate.trademark_triage.factors[0].neutral[0].quote_ids==('q1','q2')
    assert not candidate.trademark_triage.factors[0].holder
    assert 'Neutral留空' not in candidate.text
    assert all(q['exact_quote'] in candidate.text for q in raw['quotes'])
    assert candidate.text.count('引文材料：独立虚构商标材料.docx｜解析版本1｜原件SHA-256 '+ 'a'*64)==2
    assert codec.validate_manifest_candidate(d.MainMaterialCandidate.model_validate_json(candidate.model_dump_json()),manifest)==candidate

@pytest.mark.parametrize('damage',['borrow_v4_hash','message_source','stale_parse_source','altered_quote','missing_neutral','old_format'])
def test_v5_keeps_immutable_version_and_current_document_guards(damage):
    manifest=current();raw=draft_for(manifest)
    if damage=='borrow_v4_hash':
        old=method.select_method('case',manifest.question,method_id='trademark-triage-v4')
        manifest=manifest.model_copy(update={'trademark_triage':old.model_copy(update={'method_id':'trademark-triage-v5'})})
    elif damage=='message_source':raw['quotes'][0]['source_id']=manifest.sources[0].source_id
    elif damage=='stale_parse_source':
        source=manifest.sources[1]
        changed=source.reference.model_copy(update={'parse_revision':2})
        from cn_contract.assistant.providers.policy import encoded
        raw['quotes'][0]['source_id']=sha(encoded(changed))
    elif damage=='altered_quote':raw['quotes'][0]['exact_quote']='另一份说法'
    elif damage=='missing_neutral':raw['factors'][0].pop('neutral')
    elif damage=='old_format':raw['format_version']='trademark-triage-v1'
    with pytest.raises(ValueError):method.candidate(raw,manifest)

@pytest.mark.parametrize('question',['暂时不分析商标，只接收材料。','若以后需要商标初筛，再联系我。','“请做商标初筛”只是原文。'])
def test_v5_does_not_treat_negation_condition_or_quote_as_current_authority(question):
    assert method.select_method('case',question,method_id='trademark-triage-v5') is None

@pytest.mark.parametrize('label',['只是原文','仅是引用','仅为转述'])
def test_v5_explicit_bracketed_source_cannot_fall_back_to_ordinary_case(label):
    question='【请做商标初筛】'+label+'。'
    with pytest.raises(ValueError,match='MATERIAL_INSTRUCTION_CONFLICT'):
        method.select_method('case',question,method_id='trademark-triage-v5')
    old=method.select_method('case',question,method_id='trademark-triage-v4')
    assert (old is not None)==(label=='只是原文')

@pytest.mark.parametrize('question',['【任务】请做商标初筛。','【请做商标初筛】只是原文。现在请做商标初筛。'])
def test_v5_bracketed_heading_or_separate_request_remains_actionable(question):
    assert method.select_method('case',question,method_id='trademark-triage-v5').method_id=='trademark-triage-v5'

@pytest.mark.parametrize('field,value',[('attachment_id',None),('original_sha256','f'*64),('parse_revision',2),('result_sha256','f'*64)])
def test_v5_render_defensively_rejects_unvalidated_model_copy(field,value):
    from uuid import uuid4
    manifest=current();raw=draft_for(manifest)
    wrong=manifest.materials[0].model_copy(update={field:uuid4() if value is None else value})
    manifest=manifest.model_copy(update={'materials':(wrong,)})
    with pytest.raises(ValueError,match='TRADEMARK_REFERENCE_INVALID'):
        method.candidate(raw,manifest)

@pytest.mark.parametrize('field,value',[('attachment_id',None),('original_sha256','f'*64),('parse_revision',2),('result_sha256','f'*64)])
def test_manifest_input_validation_rejects_material_source_mismatch(field,value):
    from uuid import uuid4
    payload=current().model_dump(mode='python')
    payload['materials'][0][field]=uuid4() if value is None else value
    with pytest.raises(ValueError,match='MATERIAL_MANIFEST_INVALID'):
        d.MainMaterialManifest.model_validate(payload)

def test_v5_quote_labels_bind_each_document_to_its_own_name_and_parse_version():
    from uuid import uuid4
    from cn_contract.assistant.providers.policy import encoded
    payload=current().model_dump(mode='python')
    attachment=uuid4()
    second=dict(payload['materials'][0],attachment_id=attachment,name='独立虚构更正记录.docx',
        original_sha256='c'*64,parse_revision=3,result_sha256='d'*64)
    payload['materials']=(*payload['materials'],second)
    ref=payload['sources'][2]['reference']
    ref.update(attachment_id=attachment,original_sha256='c'*64,parse_revision=3,result_sha256='d'*64)
    ref['anchor']['document_version_id']=attachment
    payload['sources'][2]['source_id']=sha(encoded(d.ProfileDocumentRef.model_validate(ref)))
    manifest=d.MainMaterialManifest.model_validate(payload)
    candidate=method.candidate(draft_for(manifest),manifest)
    lines=candidate.text.splitlines()
    for quote,material in zip(candidate.trademark_triage.quotes,manifest.materials):
        line=f'{quote.id} [{quote.source_id}] 字符{quote.start}–{quote.end}：{quote.exact_quote}'
        assert lines[lines.index(line)+1]==f'引文材料：{material.name}｜解析版本{material.parse_revision}｜原件SHA-256 {material.original_sha256}'

@pytest.mark.parametrize('question',['【整理时间线】只是原文。','【会议纪要】只是原文。',
    '【请做商标初筛】只是原文。现在请整理案件。'])
def test_v5_source_label_does_not_block_other_case_work_or_select_quoted_ip(question):
    assert method.select_method('case',question,method_id='trademark-triage-v5') is None

@pytest.mark.parametrize('question',['【请做商标初筛】：只是原文。',
    '【请做商标初筛】只是原文。附件见后。','【请做商标初筛】：只是原文。附件见后。',
    '【请做商标初筛】只是原文。合同审查意见见附件。',
    '【请做商标初筛】只是原文。【整理时间线】只是原文。'])
def test_v5_source_only_ip_colon_or_tail_is_not_current_authority(question):
    with pytest.raises(ValueError,match='MATERIAL_INSTRUCTION_CONFLICT'):
        method.select_method('case',question,method_id='trademark-triage-v5')

def test_v5_explicit_collection_after_bracketed_source_remains_held():
    assert method.select_method('case','【请做商标初筛】只是原文。暂时不分析，只接收材料。',
        method_id='trademark-triage-v5') is None

@pytest.mark.parametrize('short',['请按此初筛。','请按上述筛查。','照此办理。'])
def test_v5_ambiguous_anaphora_needs_explicit_business_topic(short):
    with pytest.raises(ValueError,match='MATERIAL_INSTRUCTION_CONFLICT'):
        method.select_method('case','【请做商标初筛】只是原文。'+short,method_id='trademark-triage-v5')

