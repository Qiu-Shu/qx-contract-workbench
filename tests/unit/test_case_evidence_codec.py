"""Literal synthetic sources test quote binding, not legal entailment."""
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import case_evidence, material_codec as codec
from cn_contract.assistant.providers.policy import encoded, sha
from tests.unit.test_contract_live_method import sample, request


def fixture(texts=('2026年1月12日甲称收货。', '物流记载2026年1月13日签收。')):
    manifest, selection, config = sample('case')
    sources = []
    for i, text in enumerate(texts):
        ref = manifest.sources[0].reference
        anchor = ref.anchor.model_copy(update={'id':uuid4(), 'element_id':f'p{i}',
            'quote':text, 'quote_sha256':sha(text), 'start':0, 'end':len(text)})
        ref = ref.model_copy(update={'anchor':anchor})
        sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref))
    manifest = manifest.model_copy(update={'sources':tuple(sources),
        'case_method':case_evidence.select_method('case', '整理时间线')})
    basis = codec.build_basis(selection, manifest, config)
    data = dict(format_version='case-evidence-v1', quotes=[dict(id=f'q{i}', source_id=s.source_id,
        start=0, end=len(texts[i]), exact_quote=texts[i]) for i,s in enumerate(sources)],
        statements=[], timeline=[dict(id=f'e{i}', event_text=text, raw_date='', quote_ids=[f'q{i}'],
            conflict_group=None, uncertainty='待核原件') for i,text in enumerate(texts)], gaps=['签收人身份尚待核实'])
    return request(basis), config, data


def decode(req, config, data):
    raw = json.dumps(dict(id='synthetic-case-evidence', object='chat.completion', created=1, model=config.model,
        usage=dict(prompt_tokens=20, completion_tokens=10, total_tokens=30),
        choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=json.dumps(data)))])).encode()
    return codec.decode(raw, req, config, 'SYNTHETIC_CASE_EVIDENCE_KEY')


def test_conflicting_dates_remain_separate_unverified_rows_with_exact_quotes():
    req, cfg, data = fixture()
    for i, date in enumerate(('2026年1月12日', '2026年1月13日')):
        data['timeline'][i].update(raw_date=date, conflict_group='delivery')
    output = decode(req, cfg, data).output
    assert output is not None
    assert len(output.case_evidence.timeline) == 2
    assert '2026年1月12日' in output.text and '2026年1月13日' in output.text
    assert '冲突组 delivery' in output.text and '待律师核实' in output.text
    assert set(output.citations) == {s.source_id for s in req.basis.manifest.sources}


def test_one_event_retains_multiple_sources_without_merging_same_day_events():
    req, cfg, data = fixture(('2026-01-12甲付款。', '回单记载2026-01-12付款。', '2026-01-12乙发货。'))
    data['timeline'] = [dict(id='paid', event_text='付款说法', raw_date='2026-01-12',
        quote_ids=['q0','q1'], conflict_group=None, uncertainty='待核对账户'),
        dict(id='sent', event_text='发货说法', raw_date='2026-01-12', quote_ids=['q2'],
        conflict_group=None, uncertainty='待核对物流')]
    output = decode(req, cfg, data).output
    assert output is not None
    assert [t.id for t in output.case_evidence.timeline] == ['paid', 'sent']
    assert output.case_evidence.timeline[0].quote_ids == ('q0','q1')


def test_undated_event_does_not_invent_or_infer_a_date():
    req, cfg, data = fixture(('乙称已经还款，未提交凭证。',))
    output = decode(req, cfg, data).output
    assert output is not None
    assert output.case_evidence.timeline[0].raw_date == ''
    assert '日期未明' in output.text


def test_legal_analysis_and_proposed_text_keep_review_labels_and_opposing_sources():
    req, cfg, data = fixture()
    data['timeline'] = []
    data['statements'] = [dict(kind='legal_analysis', text='法律依据需检索核验，不能据此认定违约。',
        support=['q0'], opposing=['q1'], unresolved=['尚未核实法律效力']),
        dict(kind='proposed_text', text='请求【待补】，事实待核。', support=['q0'], opposing=[], unresolved=[])]
    output = decode(req, cfg, data).output
    assert output is not None
    assert '法律分析（依据及适用待核）' in output.text and '拟写文书（未签发）' in output.text
    assert '相反来源' in output.text


@pytest.mark.parametrize('mutation', ['quote', 'offset', 'source', 'inline', 'missing_ref', 'date', 'law_verified', 'duplicate', 'unused'])
def test_invalid_evidence_is_rejected_without_discarding_usage(mutation):
    req, cfg, data = fixture()
    if mutation == 'quote': data['quotes'][0]['exact_quote'] = '甲已确认收货。'
    elif mutation == 'offset': data['quotes'][0]['start'] = 1
    elif mutation == 'source': data['quotes'][0]['source_id'] = 'f'*64
    elif mutation == 'inline': data['timeline'][0]['event_text'] += '['+'f'*64+']'
    elif mutation == 'missing_ref': data['timeline'][0]['quote_ids'] = ['absent']
    elif mutation == 'date': data['timeline'][0]['raw_date'] = '2026-01-20'
    elif mutation == 'law_verified': data['verified'] = True
    elif mutation == 'duplicate': data['timeline'][1]['id'] = 'e0'
    elif mutation == 'unused': data['timeline'].pop()
    result = decode(req, cfg, data)
    assert result.output is None and result.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.usage.total_tokens == 30


def test_old_text_only_output_cannot_downgrade_a_new_method_request():
    req, cfg, _ = fixture()
    result = decode(req, cfg, dict(text='旧格式绕过', citations=[req.basis.manifest.sources[0].source_id]))
    assert result.output is None


def test_canonical_result_cannot_be_changed_after_decoding():
    req, cfg, data = fixture()
    candidate = decode(req, cfg, data).output
    assert candidate is not None
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(candidate.model_copy(update={'text':'伪造已确认事实'}), req.basis.manifest)
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(candidate, req.basis.manifest.model_copy(update={'case_method':None}))


@pytest.mark.parametrize('question,selected', [
    ('不用写文书，只梳理证据', False), ('不需要起诉状，先分析证据', False),
    ('不要文书，请整理时间线', True), ('不做时间线，但起草答辩状', True),
    ('请整理时间线，不用写文书', True), ('暂不生成时间线', False),
])
def test_method_selection_respects_each_requested_or_negated_deliverable(question, selected):
    assert (case_evidence.select_method('case', question) is not None) == selected


@pytest.mark.parametrize('kind', ['source_statement','inference','proposed_text'])
def test_knowledge_cannot_be_used_as_evidence_for_nonlegal_statements(kind):
    req, _, data = fixture(('虚构参考资料说法',))
    source = req.basis.manifest.sources[0]
    manifest = req.basis.manifest.model_copy(update={'sources':(), 'knowledge':SimpleNamespace(
        passages=[SimpleNamespace(source_id=source.source_id, text='虚构参考资料说法')])})
    data['timeline'] = []
    data['statements'] = [dict(kind=kind,text='候选说法',support=['q0'],opposing=[],unresolved=['待核'])]
    with pytest.raises(ValueError):
        case_evidence.candidate(data, manifest)
    data['statements'][0]['kind'] = 'legal_analysis'
    assert '依据及适用待核' in case_evidence.candidate(data, manifest).text


def test_inline_citations_cannot_borrow_another_statements_sources():
    req, _, data = fixture()
    data['timeline'] = []
    data['statements'] = [dict(kind='source_statement', text='甲称收货['+data['quotes'][1]['source_id']+']',
        support=['q0'],opposing=[],unresolved=[]), dict(kind='legal_analysis', text='待核法律分析',
        support=['q1'],opposing=[],unresolved=['待检索'])]
    with pytest.raises(ValueError):
        case_evidence.candidate(data, req.basis.manifest)
