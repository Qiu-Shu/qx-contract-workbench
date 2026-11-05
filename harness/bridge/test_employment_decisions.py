"""Employment checklist: real case-bound quotes, conditional routes, no inferred money."""
import importlib.util
from pathlib import Path

import pytest
from business_store import CaseStore
from employment_review import calculate_employment_amount
from reader import parse


def api():
    path = Path(__file__).with_name('employment_decisions.py')
    assert path.exists(), 'source-bound employment decision checklist is missing'
    spec = importlib.util.spec_from_file_location('employment_decisions', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_case(tmp_path, text, name='source.txt'):
    cases = CaseStore(tmp_path)
    cid = cases.create('合成劳动条件审查')['id']
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    cases.store.register(name)
    parse(cases.store, name)
    cases.link_materials(cid, [name])
    material = cases.read_material(cid, name)
    return cases, cid, {'path': name, 'quote': text,
                       'sha256': material['sha256'], 'chunk': material['chunks'][0]['ordinal']}


def test_uninterviewed_quote_is_saved_without_inventing_other_evidence_status(tmp_path):
    quote = 'HR有匿名投诉未访谈。工资及解除日未提供。'
    cases, cid, ref = source_case(tmp_path, quote)
    result = api().assess_employment_termination(cases, cid, [ref], request_id='review-1')
    saved = cases.read_note(cid, result['id'])
    assert saved['kind'] == 'employment_review' and saved['review_status'] == 'unverified'
    assert quote in saved['content']
    assert saved['citations'][0]['quote'] == quote
    assert saved['citations'][0]['status'] == 'matched'
    assert '未访谈则无调查证据' not in saved['content']
    assert '不推定其他调查证据存在或不存在' in saved['content']
    assert result['legal_entitlement_verified'] is False
    assert result['calculation'] == {'performed': False, 'amount': None, 'compensation_months': None}
    assert len(cases.get(cid)['notes']) == 1


def test_routes_preserve_notice_choice_agreement_initiator_and_unlawful_prerequisite(tmp_path):
    cases, cid, ref = source_case(tmp_path, '公司拟解除，尚未确定采用哪种路径。')
    result = api().assess_employment_termination(cases, cid, [ref])
    routes = {r['id']: r for r in result['paths']}
    assert set(routes) == {'mutual_employer', 'mutual_worker', 'worker_resignation',
                           'worker_article38', 'employer_article39', 'article40_notice',
                           'article40_pay', 'article41', 'fixed_term_expiry', 'unlawful'}
    assert '提前三十日' in routes['article40_notice']['conditions']
    assert '不因第40条本身再加一个月' in routes['article40_notice']['payment']
    assert '额外支付一个月工资' in routes['article40_pay']['conditions']
    assert '上一个月' in routes['article40_pay']['payment']
    assert '用人单位提出' in routes['mutual_employer']['conditions']
    assert '不能仅因协商一致认定法定N' in routes['mutual_worker']['payment']
    assert '违法解除或终止' in routes['unlawful']['conditions']
    assert '不再另加同一解除的经济补偿' in routes['unlawful']['payment']
    assert all(r['assessment'] == 'not_assessed' for r in routes.values())
    saved = cases.export_snapshot(cid)['notes'][0]['content']
    assert all(r['conditions'] in saved and r['payment'] in saved for r in routes.values())


@pytest.mark.parametrize('quote', [
    '双方确认已培训，确实未调岗；培训后考核结果暂未交来。',
    '双方确认未培训，但已调到适配岗位；HR保管两次考核。',
    '是否培训或调岗未知；解除是否发生未知；未结工资情况未知。',
    '双方确认未结工资6000元，其他款项待核。',
])
def test_positive_negative_and_unknown_statements_remain_quotes_not_model_verdicts(tmp_path, quote):
    cases, cid, ref = source_case(tmp_path, quote)
    result = api().assess_employment_termination(cases, cid, [ref])
    saved = cases.export_snapshot(cid)['notes'][0]
    assert quote in saved['content'] and saved['citations'][0]['quote'] == quote
    assert result['selected_path'] is None
    assert all(r['assessment'] == 'not_assessed' for r in result['paths'])


@pytest.mark.parametrize('changes', [
    {'quote': '没有调查证据'}, {'sha256': '0' * 64}, {'chunk': 100},
    {'confirmed': True}, {'state': True}, {'path': ''}, {'quote': True}, {'chunk': True},
])
def test_unbound_or_self_confirmed_input_is_rejected_without_saving(tmp_path, changes):
    cases, cid, ref = source_case(tmp_path, '匿名投诉未访谈。')
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, cid, [{**ref, **changes}])
    assert cases.get(cid)['notes'] == []


def test_one_bad_quote_cannot_partially_save_other_quotes(tmp_path):
    cases, cid, ref = source_case(tmp_path, '原文只说未访谈。')
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, cid, [ref, {**ref, 'quote': '未结工资6000'}])
    assert cases.get(cid)['notes'] == []


def test_cross_case_and_changed_sources_cannot_be_accepted_as_bound_facts(tmp_path):
    cases, cid, ref = source_case(tmp_path, '原文只说未访谈。')
    other = cases.create('另案')['id']
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, other, [ref])
    (tmp_path / 'source.txt').write_text('来源已改。', encoding='utf-8')
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, cid, [ref])
    assert not cases.get(cid)['notes'] and not cases.get(other)['notes']


@pytest.mark.parametrize('name', ['drafts/opinion.txt', 'DrAfTs/opinion.txt'])
def test_model_draft_cannot_be_recycled_as_original_case_source(tmp_path, name):
    cases, cid, ref = source_case(tmp_path, '没有调查证据。', name)
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, cid, [ref])
    assert cases.get(cid)['notes'] == []


@pytest.mark.parametrize('citations', [[], [{}] * 31, True, [{'path': 'x', 'quote': '字' * 5001}]])
def test_invalid_or_oversized_requests_are_atomic(tmp_path, citations):
    cases = CaseStore(tmp_path); cid = cases.create('合成限额案')['id']
    with pytest.raises(ValueError):
        api().assess_employment_termination(cases, cid, citations)
    assert cases.get(cid)['notes'] == []


def test_retry_and_correction_preserve_old_notes_and_export_ready_current_note(tmp_path):
    cases, cid, ref = source_case(tmp_path, '调查材料待核。')
    a = api()
    first = a.assess_employment_termination(cases, cid, [ref], request_id='one')
    assert a.assess_employment_termination(cases, cid, [ref], request_id='one')['id'] == first['id']
    later = a.assess_employment_termination(cases, cid, [ref], supersedes=first['id'])
    assert first['id'] != later['id']
    assert cases.read_note(cid, first['id'])['id'] == first['id']
    assert [n['id'] for n in cases.export_snapshot(cid)['notes']] == [later['id']]
    conflict = a.assess_employment_termination(cases, cid, [ref], supersedes=first['id'])
    assert conflict['recorded'] is False and 'id' not in conflict


def test_no_money_from_partial_inputs_but_explicit_scenario_arithmetic_still_works(tmp_path):
    cases, cid, ref = source_case(tmp_path, '2003年入职，到手28000；解除日、法定工资基数未知。')
    result = api().assess_employment_termination(cases, cid, [ref])
    assert result['calculation']['amount'] is None
    assert result['calculation']['compensation_months'] is None
    # The separate existing calculator handles only a user's explicit numerical scenario.
    a = calculate_employment_amount('7200.01', '3.5', '1', '合成明确情景，资格另审')
    b = calculate_employment_amount('7200.01', '3.5', '2', '同一未舍入基数年限，互斥情景')
    assert a['amount'] == '25200.04' and b['amount'] == '50400.07'
    assert a['legal_entitlement_verified'] is False
    with pytest.raises(ValueError):
        calculate_employment_amount('28000', '', '2', '没有给定年限，不能补成12')


def test_source_change_during_save_rolls_back_the_entire_strict_review(tmp_path, monkeypatch):
    cases, cid, ref = source_case(tmp_path, '原文：访谈尚未完成，其他调查证据未知。')
    original_add = cases._add_note

    def change_source_then_save(*args, **kwargs):
        (tmp_path / 'source.txt').write_text('并发编辑后的另一个版本。', encoding='utf-8')
        # Keep the real insert and its citation validation; only inject the intervening file edit.
        return original_add(*args, **kwargs)

    monkeypatch.setattr(cases, '_add_note', change_source_then_save)
    with pytest.raises(ValueError, match='保存期间|本批未保存'):
        api().assess_employment_termination(cases, cid, [ref], request_id='concurrent-change')
    assert cases.get(cid)['notes'] == []
    assert cases.export_snapshot(cid)['notes'] == []


@pytest.mark.parametrize('missing', ['sha256', 'chunk'])
def test_version_and_chunk_are_required_not_inferred_from_latest_source(tmp_path, missing):
    cases, cid, ref = source_case(tmp_path, '培训已经完成；是否仍不能胜任未知。')
    ref.pop(missing)
    with pytest.raises(ValueError, match='sha256|chunk|片段|版本'):
        api().assess_employment_termination(cases, cid, [ref])
    assert cases.get(cid)['notes'] == []


def test_partial_quote_keeps_full_context_in_saved_note_and_tool_return(tmp_path):
    context = '员工已经完成针对岗位的培训，但没有调岗；培训后考核结果未知。'
    cases, cid, ref = source_case(tmp_path, context)
    ref['quote'] = '没有调岗'
    result = api().assess_employment_termination(cases, cid, [ref])
    note = cases.export_snapshot(cid)['notes'][0]
    assert context in note['content']
    assert result['source_contexts'][0]['context'] == context
    assert result['source_contexts'][0]['citation']['quote'] == '没有调岗'
    assert result['source_contexts'][0]['citation']['sha256'] == ref['sha256']
    assert result['source_contexts'][0]['citation']['chunk'] == ref['chunk']


def test_summary_does_not_reinterpret_case_facts_or_turn_rule_checklist_into_verdict(tmp_path):
    cases, cid, ref = source_case(tmp_path, '已收到通知，已培训，考核结果未提供；拟选择代通知金分支。')
    result = api().assess_employment_termination(cases, cid, [ref])
    summary = result['user_summary']
    assert '程序未判断任何路径成立或不成立' in summary
    assert '未确定实际应付款、补偿月份或最晚通知日' in summary
    assert '已保存' in summary
    assert '未具备' not in summary and '无解除通知' not in summary and '尚未选定' not in summary
    assert result['selected_path'] is None


def test_conflicting_correction_summary_cannot_claim_saved(tmp_path):
    cases, cid, ref = source_case(tmp_path, '调查材料待核。'); a = api()
    first = a.assess_employment_termination(cases, cid, [ref])
    a.assess_employment_termination(cases, cid, [ref], supersedes=first['id'])
    conflict = a.assess_employment_termination(cases, cid, [ref], supersedes=first['id'])
    assert conflict['recorded'] is False
    assert '未保存' in conflict['user_summary'] and '已保存' not in conflict['user_summary']
