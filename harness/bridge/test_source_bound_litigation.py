"""Synthetic real cases and DOCX: no model calls or credentials."""
import importlib
from pathlib import Path

import pytest
from docx import Document
from business_store import CaseStore
from reader import parse


def build(*args, **kwargs):
    assert importlib.util.find_spec('source_bound_litigation'), 'source-bound builder missing'
    return importlib.import_module('source_bound_litigation').build_source_bound_litigation(*args, **kwargs)


def text(path):
    return '\n'.join(p.text for p in Document(path).paragraphs)


def link(cases, cid, name, value):
    source = cases.root / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(value, encoding='utf-8')
    cases.store.register(name)
    parse(cases.store, name)
    material = cases.link_materials(cid, [name])['materials'][0]
    return {'path': name, 'quote': value, 'sha256': material['sha256'], 'chunk': 0}


@pytest.fixture
def sample(tmp_path):
    cases = CaseStore(tmp_path)
    cid = cases.create('合成材料案')['id']
    ref = link(cases, cid, '事项摘要.txt', '银禾拟向澄江主张货款。价款96000元，已收31000元。案号和客户知悉情况未说明。')
    return cases, cid, ref


def args(sample):
    cases, cid, ref = sample
    return cases, cid, 'civil_complaint', '待核稿.docx', [{'section': 'facts', 'citation': ref}]


def calculation(ref, total='96000元', paid='31000元'):
    return [{'minuend': {'citation': ref, 'amount': total},
             'subtrahends': [{'citation': ref, 'amount': paid}]}]


@pytest.mark.parametrize('kind', ['civil_complaint', 'civil_defense',
                                 'evidence_list', 'cross_examination', 'labor_arbitration', 'lawyer_letter'])
def test_exact_source_draft_has_body_audit_and_no_added_client_or_procedure(sample, kind):
    cases, cid, ref = sample
    result = build(cases, cid, kind, '稿.docx', [{'section': 'facts', 'citation': ref}], calculation(ref))
    body = text(result['path'])
    assert ref['quote'] in body and ref['path'] in body
    assert '65000元' in body and '68000元' not in body
    assert ('案号：' in body) == (kind != 'lawyer_letter')
    assert '待核' in body
    assert '尚未立案' not in body and '原告知悉' not in body and '有限公司' not in body
    assert '委托人陈述' not in body and '待核对后另行提交' not in body
    assert result['calculations'][0]['result_yuan'] == '65000'
    assert ref['sha256'] in text(result['internal_path'])
    assert result['ready_to_submit'] is False and result['legal_verified'] is False
    assert result['body_text'] == body
    assert result['completion_status'] == 'partial' and result['pending_work']


@pytest.mark.parametrize('extra', [{'text': '原告已知悉风险'}, {'role': '甲有限公司'},
                                  {'heading': '本案尚未立案'}, {'authorized': True}])
def test_free_assertions_are_rejected_without_outward_file(sample, extra):
    argv = list(args(sample)); argv[-1][0].update(extra)
    with pytest.raises(ValueError): build(*argv)
    assert not list(sample[0].root.glob('drafts/*.docx'))


@pytest.mark.parametrize('change', [{'quote': '原告已知悉风险'}, {'sha256': '0' * 64},
                                   {'chunk': 99}, {'chunk': True}, {'source_kind': 'model_draft'},
                                   {'status': 'unmatched'}, {'start': 1, 'end': 4}])
def test_invalid_citation_fails_closed(sample, change):
    argv = list(args(sample)); argv[-1][0]['citation'] = {**sample[2], **change}
    with pytest.raises(ValueError): build(*argv)
    assert not list(sample[0].root.glob('drafts/*.docx'))


def test_cross_case_missing_changed_and_obsolete_sources_fail(sample):
    cases, cid, ref = sample
    other = cases.create('别案')['id']
    with pytest.raises(ValueError): build(cases, other, *args(sample)[2:])
    source = cases.root / ref['path']
    source.write_text('新版金额100元', encoding='utf-8')
    with pytest.raises(ValueError): build(*args(sample))
    link(cases, cid, ref['path'], '新版金额100元')
    with pytest.raises(ValueError): build(*args(sample))
    source.unlink()
    with pytest.raises(ValueError): build(*args(sample))
    assert not list(cases.root.glob('drafts/*.docx'))


def test_registered_draft_is_not_source(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, 'drafts/旧稿.txt', '原告已知悉风险。')
    with pytest.raises(ValueError):
        build(cases, cid, 'civil_complaint', '新稿.docx', [{'section': 'facts', 'citation': ref}])
    assert not list(cases.root.glob('drafts/*.docx'))


@pytest.mark.parametrize('total,paid', [('6000元', '31000元'), ('96000', '31000元'),
                                      ('96000万元', '31000元'), ('96,00元', '31000元'),
                                      ('NaN元', '31000元')])
def test_amount_must_be_complete_source_currency_token(sample, total, paid):
    with pytest.raises(ValueError): build(*args(sample), calculations=calculation(sample[2], total, paid))
    assert not list(sample[0].root.glob('drafts/*.docx'))


def test_quote_slice_cannot_turn_larger_number_into_smaller_amount(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '数字.txt', '价款196000元，已付31000元。')
    sliced = {**ref, 'quote': '96000元'}
    with pytest.raises(ValueError): build(cases, cid, 'civil_complaint', '数字稿.docx',
        [{'section': 'facts', 'citation': ref}], calculation(sliced, '96000元', '96000元'))
    assert not list(cases.root.glob('drafts/*.docx'))


def test_repeated_money_inside_one_quote_requires_narrower_source(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '歧义金额.txt', '价款100元；争议费用100元；已付20元。')
    with pytest.raises(ValueError):
        build(cases, cid, 'civil_complaint', '金额.docx', [{'section': 'facts', 'citation': ref}],
              calculation(ref, '100元', '20元'))
    assert not list(cases.root.glob('drafts/*.docx'))


@pytest.mark.parametrize('source,total,paid,want', [
    ('总额9.6万元，已付31,000元。', '9.6万元', '31,000元', '65000'),
    ('总额1.01元，已付0.10元。', '1.01元', '0.10元', '0.91'),
    ('总额1元，已付2元。', '1元', '2元', '-1')])
def test_decimal_units_and_negative_difference_are_arithmetic_only(sample, source, total, paid, want):
    cases, cid, _ = sample; ref = link(cases, cid, '金额.txt', source)
    result = build(cases, cid, 'civil_complaint', '金额稿.docx',
        [{'section': 'facts', 'citation': ref}], calculation(ref, total, paid))
    assert result['calculations'][0]['result_yuan'] == want
    body = text(result['path'])
    assert want + '元' in body and '到期应付' not in body


def test_repeat_generation_preserves_original_and_existing_draft(sample):
    cases, _, ref = sample; source = cases.root / ref['path']; original = source.read_bytes()
    one = build(*args(sample)); saved = Path(one['path']).read_bytes()
    two = build(*args(sample))
    assert one['path'] != two['path'] and Path(one['path']).read_bytes() == saved
    assert source.read_bytes() == original


def test_two_payment_difference_and_conditional_deduction_are_separate_arithmetic(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '多笔.txt', '总额125000元，已付35000元和18000元，争议退货12000元。')
    first = {'minuend': {'citation': ref, 'amount': '125000元'},
             'subtrahends': [{'citation': ref, 'amount': '35000元'}, {'citation': ref, 'amount': '18000元'}]}
    second = {**first, 'subtrahends': [*first['subtrahends'], {'citation': ref, 'amount': '12000元'}]}
    result = build(cases, cid, 'civil_complaint', '多笔稿.docx', [{'section': 'facts', 'citation': ref}], [first, second])
    assert [r['result_yuan'] for r in result['calculations']] == ['72000', '60000']
    assert ref['quote'] in result['body_text']


def test_same_source_payment_cannot_be_deducted_twice(sample):
    rows = calculation(sample[2]); rows[0]['subtrahends'] *= 2
    with pytest.raises(ValueError): build(*args(sample), calculations=rows)
    assert not list(sample[0].root.glob('drafts/*.docx'))


@pytest.mark.parametrize('source,amount', [('价款0.001元，已付1元。', '0.001元'),
                                         ('价款-96000元，已付1元。', '96000元'),
                                         ('价款1e5元，已付1元。', '5元'),
                                         ('价款负100元，已付1元。', '100元'),
                                         ('价款负 100元，已付1元。', '100元')])
def test_subcent_and_signed_substring_cannot_silently_become_positive_yuan(sample, source, amount):
    cases, cid, _ = sample; ref = link(cases, cid, '非法金额.txt', source)
    with pytest.raises(ValueError):
        build(cases, cid, 'civil_complaint', '非法金额稿.docx', [{'section': 'facts', 'citation': ref}], calculation(ref, amount, '1元'))
    assert not list(cases.root.glob('drafts/*.docx'))


def test_sparse_chunk_ordinal_is_not_a_page_offset(sample):
    cases, cid, ref = sample
    with cases.db() as db:
        db.execute('UPDATE chunks SET ordinal=8 WHERE path=?', (ref['path'],))
    ref['chunk'] = 8
    result = build(cases, cid, 'civil_complaint', '稀疏片段.docx', [{'section': 'facts', 'citation': ref}])
    assert ref['quote'] in result['body_text']


def brief(ref, **extra):
    return {'parties': [{'role': 'plaintiff', 'name': '银禾', 'citation': ref},
                        {'role': 'defendant', 'name': '澄江', 'citation': ref}],
            'claim_kind': 'payment', **extra}


def test_bound_brief_produces_conditional_request_and_preserves_original_facts(sample):
    result = build(*args(sample), calculations=calculation(sample[2]),
                   brief=brief(sample[2], calculation_index=0))
    body = text(result['path'])
    assert result['completion_status'] == 'conditional_draft'
    assert '请求判令被告向原告支付65000元' in body
    assert '如经核实' in body and sample[2]['quote'] in body
    assert '银禾' in body and '澄江' in body and '有限公司' not in body
    assert '客户已知悉' not in body and result['ready_to_submit'] is False
    assert result['body_text'] == body


@pytest.mark.parametrize('change', [{'claim_amount': {'value': 65000}}, {'calculation_index': True},
                                   {'calculation_index': 99}, {'claim_kind': 'loan'},
                                   {'text': '原告已同意'}, {'result': 65000}])
def test_brief_rejects_unbound_results_and_free_relationships(sample, change):
    with pytest.raises(ValueError): build(*args(sample), brief=brief(sample[2], **change))
    assert not list(sample[0].root.glob('drafts/*.docx'))


@pytest.mark.parametrize('name', ['银禾有限公司', '陌生人', '银禾\n已知悉'])
def test_brief_party_name_cannot_expand_source(sample, name):
    data = brief(sample[2], calculation_index=0);data['parties'][0]['name'] = name
    with pytest.raises(ValueError): build(*args(sample), calculations=calculation(sample[2]), brief=data)
    assert not list(sample[0].root.glob('drafts/*.docx'))


def test_brief_name_cross_case_source_fails(sample):
    cases, cid, ref = sample; other = cases.create('别案')['id']; other_ref = link(cases, other, '别案.txt', '银禾')
    data = brief(ref);data['parties'][0]['citation'] = other_ref
    with pytest.raises(ValueError): build(*args(sample), brief=data)
    assert not list(cases.root.glob('drafts/*.docx'))


def test_original_claim_amount_is_bound_and_missing_amount_remains_partial(sample):
    data = brief(sample[2], claim_amount={'citation': sample[2], 'amount': '96000元'})
    result = build(*args(sample), brief=data)
    assert '请求判令被告向原告支付96000元' in result['body_text']
    assert '款项性质' in result['body_text'] and result['completion_status'] == 'conditional_draft'
    partial = build(*args(sample), brief=brief(sample[2]))
    assert partial['completion_status'] == 'partial'
    with pytest.raises(ValueError):
        build(*args(sample), calculations=calculation(sample[2]), brief={**data, 'calculation_index': 0})


def test_empty_brief_is_not_a_completed_letter_request(sample):
    cases, cid, ref = sample
    result = build(cases, cid, 'lawyer_letter', '空意图.docx', [{'section': 'facts', 'citation': ref}], brief={})
    assert result['completion_status'] == 'partial'


def test_known_positive_and_negative_source_states_survive_conditional_template(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '明确状态.txt', '银禾已收到应诉通知，案号为甲123；明确尚未收到起诉状，其他材料状态未知。')
    result = build(cases, cid, 'civil_defense', '状态稿.docx', [{'section': 'facts', 'citation': ref}],
                   brief={'parties': [{'role': 'defendant', 'name': '银禾', 'citation': ref}]})
    assert ref['quote'] in result['body_text']
    assert '尚未立案' not in result['body_text'] and '尚未收到全部证据' not in result['body_text']


@pytest.mark.parametrize('kind', ['civil_defense', 'representation', 'lawyer_letter'])
def test_finite_templates_supply_readable_requests_without_acceptance_or_submission(sample, kind):
    cases, cid, ref = sample
    mapping = {'plaintiff': 'client', 'defendant': 'recipient'} if kind == 'lawyer_letter' else {}
    data = brief(ref)
    for party in data['parties']: party['role'] = mapping.get(party['role'], party['role'])
    excerpts = [{'section': 'facts', 'citation': ref}]
    if kind == 'representation':
        excerpts.append({'section': 'requests', 'citation': ref})
    result = build(cases, cid, kind, '条件稿.docx', excerpts, brief=data)
    body = result['body_text']
    assert result['completion_status'] == 'conditional_draft'
    assert '拟请求事项：【待承办人' not in body
    assert '我方愿意' not in body and '已提交并经核对' not in body
    assert ref['quote'] in body
    if kind == 'lawyer_letter':
        assert '核对下列材料' in body and '本所已受托' not in body
        assert '受理机关：' not in body and '案号：' not in body
    elif kind == 'civil_defense':
        assert '不据收款数额承认债务' in body
    else:
        assert '拟主张' in body and '已完成法律审查' not in body


def test_ambiguous_quote_requires_verified_offsets(sample):
    cases, cid, _ = sample; ref = link(cases, cid, '重复.txt', '价款10元。价款10元。')
    ref['quote'] = '价款10元。'
    with pytest.raises(ValueError): build(cases, cid, 'civil_complaint', '重复稿.docx', [{'section': 'facts', 'citation': ref}])
    ref.update(start=0, end=6)
    result = build(cases, cid, 'civil_complaint', '定位稿.docx', [{'section': 'facts', 'citation': ref}])
    assert ref['quote'] in text(result['path'])


@pytest.mark.parametrize('after_publish', [1, 2])
def test_source_change_during_publication_never_leaves_outward_draft(sample, monkeypatch, after_publish):
    assert importlib.util.find_spec('source_bound_litigation'), 'source-bound builder missing'
    module = importlib.import_module('source_bound_litigation'); real = module._publish; calls = 0
    def publish(*a):
        nonlocal calls
        result = real(*a); calls += 1
        if calls == after_publish: (sample[0].root / sample[2]['path']).write_text('并发改动', encoding='utf-8')
        return result
    monkeypatch.setattr(module, '_publish', publish)
    with pytest.raises(ValueError): build(*args(sample))
    assert not [p for p in sample[0].root.glob('drafts/*.docx') if '内部' not in p.name]


@pytest.mark.parametrize('selected,data', [
    (['requests', 'facts'], None), (['requests', 'facts'], {}),
    (['facts'], {'claim_kind': 'undetermined'}),
    (['requests'], {'claim_kind': 'undetermined'})])
def test_representation_requires_conditional_brief_claim_and_basis(sample, selected, data):
    cases, cid, ref = sample
    with pytest.raises(ValueError, match='代理意见'):
        build(cases, cid, 'representation', '空代理.docx',
              [{'section': section, 'citation': ref} for section in selected], brief=data)
    assert not list(cases.root.glob('drafts/*.docx'))


def test_representation_preserves_proposal_counter_basis_and_complete_internal_context(sample):
    cases, cid, _ = sample
    source = '拟主张按约定承担修复费用。原件仅写维修方案另议；不得据此认定双方已约定费用分担。'
    ref = link(cases, cid, '维修争议.txt', source)
    request = {**ref, 'quote': '拟主张按约定承担修复费用。'}
    fact = {**ref, 'quote': '原件仅写维修方案另议'}
    result = build(cases, cid, 'representation', '代理.docx',
                   [{'section': 'requests', 'citation': request}, {'section': 'facts', 'citation': fact}],
                   brief={'claim_kind': 'undetermined'})
    assert result['completion_status'] == 'conditional_draft'
    assert request['quote'] in text(result['path']) and fact['quote'] in text(result['path'])
    assert source in text(result['internal_path'])
    assert result['source_contexts'] == [{'path': ref['path'], 'sha256': ref['sha256'], 'chunk': 0, 'text': source}]
    assert result['selected_sections']['requests'] == 1 and result['selected_sections']['facts'] == 1
    assert result['missing_sections'] == ['parties', 'sections']
    assert '待审条件请求' in result['user_summary'] and '已确认' not in result['user_summary']


def test_partial_summary_reports_only_selected_sections_and_no_unselected_claim(sample):
    result = build(*args(sample))
    assert result['selected_sections'] == {'parties': 0, 'requests': 0, 'facts': 1, 'sections': 0}
    assert result['missing_sections'] == ['parties', 'requests', 'sections']
    assert '部分完成' in result['user_summary'] and '未形成条件请求' in result['user_summary']
    assert '未选入的观点不代表已写入正文' in result['user_summary']


def test_internal_context_includes_brief_and_arithmetic_only_sources(sample):
    cases, cid, ref = sample
    other = link(cases, cid, '金额约束.txt', '价款20元，已付3元；费用另议。')
    result = build(*args(sample), calculations=calculation(other, '20元', '3元'),
                   brief=brief(ref, calculation_index=0))
    assert {row['path'] for row in result['source_contexts']} == {ref['path'], other['path']}
    assert other['quote'] in text(result['internal_path'])


def test_missing_roles_are_diagnostic_even_when_source_has_proposed_issuer(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '拟函.txt', '松林拟请碧溪律所起草给云川的函件，委托尚未签署。')
    result = build(cases, cid, 'lawyer_letter', '拟函.docx', [{'section': 'facts', 'citation': ref}],
                   brief={'parties': [{'role': 'client', 'name': '松林', 'citation': ref},
                                      {'role': 'recipient', 'name': '云川', 'citation': ref}]})
    assert result['missing_roles'] == ['issuer']
    assert '本稿未填写角色：拟发函人' in result['user_summary']
    assert '不表示原材料没有该信息或授权不存在' in result['user_summary']
    assert '拟发函人（身份与角色对应待核）：【名称未填】' in result['body_text']


def test_unsigned_proposed_law_firm_can_be_preserved_without_claiming_authorization(sample):
    cases, cid, _ = sample
    ref = link(cases, cid, '拟委托.txt', '松林拟请碧溪律所起草给云川的函件，委托尚未签署。')
    parties = [{'role': role, 'name': name, 'citation': ref} for role, name in
               [('client', '松林'), ('issuer', '碧溪律所'), ('recipient', '云川')]]
    result = build(cases, cid, 'lawyer_letter', '拟律所.docx', [{'section': 'facts', 'citation': ref}],
                   brief={'parties': parties})
    assert result['missing_roles'] == []
    assert '拟发函人（身份与角色对应待核）：碧溪律所' in text(result['path'])
    assert '本所已受托' not in result['body_text'] and '委托及发函权限待核' in result['body_text']


def test_no_brief_missing_roles_remain_diagnostic_not_new_blocker(sample):
    result = build(*args(sample))
    assert result['completion_status'] == 'partial'
    assert result['missing_roles'] == ['plaintiff', 'defendant']
    assert '拟原告、拟被告' in result['user_summary']


def test_calculation_index_nested_in_claim_amount_has_precise_repair_error(sample):
    with pytest.raises(ValueError, match=r'brief\.calculation_index'):
        build(*args(sample), calculations=calculation(sample[2]),
              brief=brief(sample[2], claim_amount={'calculation_index': 0}))
    assert not list(sample[0].root.glob('drafts/*.docx'))


def test_v7_truncated_opponent_claim_is_not_displayed_as_independent_statement(sample):
    cases, cid, _ = sample
    sentence = '接待记录：岚序公司拟向竹岸公司主张已结算价款84000元，已收26000元；岚序负责人确认先主张账面差额，暂不主张利息。'
    source = '全部虚构，供隔离实测。' + sentence + '内部讨论另存，不应因本次摘句外放。'
    ref = link(cases, cid, '截句回归.txt', source)
    selected = {**ref, 'quote': '竹岸公司主张已结算价款84000元'}
    result = build(cases, cid, 'civil_complaint', '截句稿.docx', [{'section': 'facts', 'citation': selected}],
                   calculation(ref, '84000元', '26000元'), brief={'calculation_index': 0})
    paragraphs = [p.text for p in Document(result['path']).paragraphs]
    assert sentence in paragraphs and selected['quote'] not in paragraphs
    assert '内部讨论另存' not in result['body_text']
    assert result['calculations'][0]['result_yuan'] == '58000'
    assert result['excerpts'][0]['citation']['quote'] == selected['quote']
    assert selected['quote'] in result['internal_text']
    assert result['excerpts'][0]['contextual_quote'] == sentence
    span = result['excerpts'][0]['contextual_span']
    assert source[span['start']:span['end']] == sentence


@pytest.mark.parametrize('source,quote,want', [
    ('甲向乙主张返还物品。下一独立句。', '乙主张返还物品', '甲向乙主张返还物品。'),
    ('前句！未确认乙已收到款项；付款方仍有争议。后句？', '乙已收到款项', '未确认乙已收到款项；付款方仍有争议。'),
    ('首句。完整句无需扩展。下一句。', '完整句无需扩展。', '完整句无需扩展。'),
    ('首句。最后一项：甲未同意任何付款', '同意任何付款', '最后一项：甲未同意任何付款'),
    ('私密前行\n甲否认，乙已履行仍待核\n私密后行', '乙已履行', '甲否认，乙已履行仍待核'),
    ('首句。甲主张返还；乙否认。补充条件另核。末句。', '乙否认。补充条件', '甲主张返还；乙否认。补充条件另核。')])
def test_display_quote_restores_sentence_prefix_and_stops_at_boundaries(sample, source, quote, want):
    cases, cid, _ = sample
    ref = link(cases, cid, '句界.txt', source)
    result = build(cases, cid, 'civil_complaint', '句界稿.docx',
                   [{'section': 'facts', 'citation': {**ref, 'quote': quote}}])
    row = result['excerpts'][0]
    assert row['contextual_quote'] == want
    # Windows text files may contain CRLF; positions belong to the parsed chunk,
    # matching the existing citation offsets, not the fixture's LF-only string.
    parsed_source = cases.read_material(cid, ref['path'], start=0, limit=1)['chunks'][0]['text']
    assert parsed_source[row['contextual_span']['start']:row['contextual_span']['end']] == want
    assert want in [p.text for p in Document(result['path']).paragraphs]
    assert row['citation']['quote'] == quote
    if quote != want:
        assert quote not in [p.text for p in Document(result['path']).paragraphs]
