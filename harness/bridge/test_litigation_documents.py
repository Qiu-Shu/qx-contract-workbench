"""Real synthetic case -> grounded DOCX; no model, credentials or real materials."""
from pathlib import Path
import importlib
import pytest
from docx import Document
from business_store import CaseStore
from reader import parse


@pytest.fixture
def sample(tmp_path):
    cases = CaseStore(tmp_path)
    cid = cases.create('合成货款案', '原告')['id']
    source = tmp_path / '合成陈述.txt'
    source.write_text('甲称：乙尚欠货款35000元。是否已核账不详。', encoding='utf-8')
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    ref = {'path': source.name, 'quote': '乙尚欠货款35000元', 'chunk': 0}
    return cases, cid, source, ref


def generate(*args):
    assert importlib.util.find_spec('litigation_documents'), 'Missing litigation document implementation'
    return importlib.import_module('litigation_documents').generate_litigation_document(*args)


def content(path):
    return '\n'.join(p.text for p in Document(path).paragraphs)


@pytest.mark.parametrize('kind', ['civil_complaint', 'civil_defense', 'representation',
                                 'evidence_list', 'cross_examination', 'labor_arbitration', 'lawyer_letter'])
def test_all_document_types_preserve_unverified_claim_and_make_real_words(sample, kind):
    cases, cid, source, ref = sample
    data = {'parties': [{'role': '原告', 'text': '甲（身份待核）'}],
            'requests': [{'text': '请求支付货款35000元', 'citations': [ref]}],
            'facts': [{'text': '甲称乙尚欠货款35000元，核账情况不详。', 'citations': [ref]}]}
    result = generate(cases, cid, kind, kind+'.docx', data)
    assert Path(result['path']).is_file() and Path(result['internal_path']).is_file()
    body = content(result['path'])
    assert '核账情况不详' in body and '待核' in body
    assert source.name not in body and source.name in content(result['internal_path'])
    assert result['citation_checks'][1]['citations'][0]['status'] == 'matched'
    assert result['sources'][0]['sha256'] == cases.materials(cid)[0]['sha256']
    assert result['status'] == 'draft' and result['ready_to_submit'] is False


def test_mismatch_retains_body_and_never_overwrites(sample):
    cases, cid, source, ref = sample
    ref['quote'] = '乙承认欠款90000元'
    data = {'facts': [{'text': '乙承认欠款90000元（模型待核稿）', 'citations': [ref]}]}
    first = generate(cases, cid, 'civil_complaint', '原稿.docx', data)
    original = Path(first['path']).read_bytes()
    second = generate(cases, cid, 'civil_complaint', '原稿.docx', data)
    assert first['path'] != second['path'] and Path(first['path']).read_bytes() == original
    assert '90000元' in content(first['path']) and '逐字引文' in str(first['pending_checks'])


def test_other_case_rejected_before_any_output(sample):
    cases, cid, source, ref = sample
    other = cases.create('另一合成案')['id']
    with pytest.raises(ValueError):
        generate(cases, other, 'civil_complaint', '越界.docx', {'facts':[{'text':'转入', 'citations':[ref]}]})
    assert not (cases.root / 'drafts').exists()


def test_changed_source_is_not_certified(sample):
    cases, cid, source, ref = sample
    source.write_text('原件已经变化', encoding='utf-8')
    result = generate(cases, cid, 'civil_defense', '答辩.docx', {'facts':[{'text':'保留原说法', 'citations':[ref]}]})
    assert result['citation_checks'][0]['status'] == 'unverified'
    assert result['sources'][0]['changed'] is True


def test_model_draft_cannot_become_evidence(sample):
    cases, cid, source, ref = sample
    (cases.root/'drafts').mkdir()
    draft = cases.root/'drafts'/'模型.txt'
    draft.write_text('模型称欠款10万元', encoding='utf-8')
    cases.store.register('drafts/模型.txt'); parse(cases.store, 'drafts/模型.txt')
    cases.link_materials(cid, ['drafts/模型.txt'])
    result = generate(cases, cid, 'civil_complaint', '诉状.docx', {'facts':[{'text':'模型称欠款10万元', 'citations':[{'path':'drafts/模型.txt','quote':'欠款10万元'}]}]})
    assert result['citation_checks'][0]['status'] == 'unverified'
    assert '草稿不能作为来源证据' in str(result['pending_checks'])


def test_unknown_letter_mandate_does_not_imply_retainer(sample):
    cases, cid, source, ref = sample
    result = generate(cases, cid, 'lawyer_letter', '函.docx', {'mandate':{'client':'甲','issuer':'拟发函律所','recipient':'乙'}, 'facts':[{'text':'本所已受托处理争议'}]})
    body = content(result['path'])
    assert '委托未核实' in body and '未授权发函' in body
    assert '委托人：甲' in body and '收函主体：乙' in body
    assert '本所已受托' not in body
    assert '本所已受托' in content(result['internal_path'])


def test_empty_data_has_useful_placeholders_and_invalid_fields_are_not_swallowed(sample):
    cases, cid, source, ref = sample
    result = generate(cases, cid, 'civil_complaint', '缺项.docx', {})
    assert '当事人' in content(result['path']) and '诉讼请求' in content(result['path'])
    with pytest.raises(ValueError): generate(cases, cid, 'civil_complaint', '../越界.docx', {})
    with pytest.raises(ValueError): generate(cases, cid, 'civil_complaint', '稿.docx', {'body':'不可静默丢弃'})


def test_matching_quote_and_authorized_flag_do_not_certify_retainer(sample):
    cases, cid, source, ref = sample
    result = generate(cases, cid, 'lawyer_letter', '授权待核函.docx', {
        'mandate': {'client': '甲', 'issuer': '拟发函律所', 'recipient': '乙',
                    'authorized': True, 'citations': [ref]},
        'facts': [{'text': '本所已受托处理争议', 'citations': [ref]}]})
    body = content(result['path'])
    assert '本所已受托' not in body
    assert '委托未核实' in body
    assert '本所已受托' in content(result['internal_path'])
    assert result['authorization_status'] == 'unverified'


def test_source_changed_after_initial_check_downgrades_body_and_return(sample):
    cases, cid, source, ref = sample
    original_materials = cases.materials

    def changes_before_final_check(*args, **kwargs):
        source.write_text('生成过程中源文件改变', encoding='utf-8')
        return original_materials(*args, **kwargs)

    cases.materials = changes_before_final_check
    result = generate(cases, cid, 'civil_complaint', '晚变化.docx', {
        'facts': [{'text': '甲称乙尚欠货款35000元', 'citations': [ref]}]})
    assert result['citation_checks'][0]['status'] == 'unverified'
    assert result['citation_checks'][0]['citations'][0]['status'] == 'unverified'
    assert '本段来源或引文尚未核对通过' in content(result['path'])
    assert '生成期间来源版本变化' in content(result['internal_path'])


def test_mandate_on_non_letter_is_rejected_without_output(sample):
    cases, cid, source, ref = sample
    with pytest.raises(ValueError, match='mandate'):
        generate(cases, cid, 'civil_complaint', '错误字段.docx', {'mandate': {'client': '甲'}})
    assert not (cases.root/'drafts').exists()


@pytest.mark.parametrize('status', ['unmatched', 'ambiguous', 'unverified'])
def test_failed_alignment_cannot_be_promoted_in_litigation_outputs(sample, status):
    cases, cid, source, ref = sample
    ref.update(status=status, start=3, end=14)
    result = generate(cases, cid, 'civil_complaint', '失败定位.docx', {
        'facts': [{'text': '保留甲的货款主张', 'citations': [ref]}]})
    row = result['citation_checks'][0]
    assert row['status'] == 'unverified' and row['citations'][0]['status'] == 'unverified'
    assert row['warnings'] and '本段来源或引文尚未核对通过' in content(result['path'])
    assert status in content(result['internal_path'])
    assert ref['start'] == 3 and ref['end'] == 14


@pytest.mark.parametrize('field', ['title', 'party-role', 'section-heading', 'signatory',
                                  'mandate-client', 'mandate-issuer', 'mandate-recipient'])
def test_letter_unverified_retainer_assertion_cannot_bypass_via_metadata(sample, field):
    cases, cid, source, ref = sample
    claim = '本所已受托处理本案'
    data = {'facts': [{'text': '客户主张货款35000元，待核', 'citations': [ref]}]}
    if field == 'party-role':
        data['parties'] = [{'role': claim, 'text': '甲'}]
    elif field == 'section-heading':
        data['sections'] = [{'heading': claim, 'text': '争议情况待核'}]
    elif field.startswith('mandate-'):
        data['mandate'] = {field.split('-')[1]: claim}
    else:
        data[field] = claim
    result = generate(cases, cid, 'lawyer_letter', '元数据授权待核.docx', data)
    assert claim not in content(result['path'])
    assert claim in content(result['internal_path'])
    assert result['authorization_status'] == 'unverified'
    assert any('委托' in warning for warning in result['pending_checks'])


@pytest.mark.parametrize('field', ['body', 'title', 'party-role', 'section-heading',
                                  'signatory', 'authority', 'case_number', 'date'])
@pytest.mark.parametrize('claim', [
    '代理人受本案一方当事人委托参与本案诉讼',
    '具体代理权限及出庭手续以已提交法院的授权材料为准',
])
def test_representation_authority_claims_stay_internal_even_with_matching_quote(sample, field, claim):
    cases, cid, source, ref = sample
    data = {'facts': [{'text': '甲主张货款35000元，待核', 'citations': [ref]}]}
    if field == 'body':
        data['facts'].append({'text': claim, 'citations': [ref]})
    elif field == 'party-role':
        data['parties'] = [{'role': claim, 'text': '甲'}]
    elif field == 'section-heading':
        data['sections'] = [{'heading': claim, 'text': '争议情况待核'}]
    else:
        data[field] = claim
    result = generate(cases, cid, 'representation', '代理权待核.docx', data)
    assert claim not in content(result['path'])
    assert claim in content(result['internal_path'])
    assert '未审核代理权' in content(result['path'])
    assert result['authorization_status'] == 'unverified'
    assert any('代理权' in warning for warning in result['pending_checks'])


def test_representation_keeps_ordinary_mandate_facts_and_adjacent_sentences(sample):
    cases, cid, source, ref = sample
    ordinary = ('争议合同属于委托合同。甲委托乙代为采购，乙是否超越合同授权范围待核。'
                '合同载明乙作为代理人接受甲委托采购设备。')
    claim = '本所已受托代理本案。'
    result = generate(cases, cid, 'representation', '委托合同争议.docx', {
        'title': '委托合同争议代理意见',
        'facts': [{'heading': '委托合同履行', 'text': ordinary + claim,
                   'citations': [ref]}]})
    body = content(result['path'])
    assert '委托合同争议代理意见' in body and '委托合同履行' in body
    assert ordinary in body and claim not in body
    assert ordinary + claim in content(result['internal_path'])
    assert result['authorization_status'] == 'unverified'
