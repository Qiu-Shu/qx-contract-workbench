"""Synthetic evidence checks are not legal quality or model acceptance."""
from copy import deepcopy
import importlib

import pytest


def api():
    return importlib.import_module('cn_contract.acceptance.contract_scoring')


@pytest.fixture
def sample():
    case = {'id': 'synthetic-lease', 'context': '虚构租赁合同，未签署', 'anchors': [
        {'id': 'a', 'quote': '承租方可提前30日书面通知解除合同。'},
        {'id': 'b', 'quote': '提前解除应支付3个月租金的费用。'},
        {'id': 'c', 'quote': '正常届满时不收取提前退出费用。'}]}
    answer = {'examined_anchor_ids': ['a', 'b', 'c'], 'formal_signoff': False,
              'legal_status': 'not_verified', 'issues': [
                  {'kind': 'exit_cost_relation', 'citations': deepcopy(case['anchors']),
                   'analysis': '提前解除与费用有关，正常届满不收取。', 'recommendation': '核对退出安排。'}]}
    expected = {'exit_cost_relation': {'required': ['a', 'b'], 'optional': ['c']}}
    return case, answer, expected


def test_relevant_supplementary_quote_is_not_a_failure(sample):
    result = api().score_contract(*sample)
    assert result['engineering_passed'] is True
    assert result['reasoning_status'] == 'pending_manual_review'
    assert result['promotion_allowed'] is False
    assert result['relations']['exit_cost_relation']['missing_anchor_ids'] == []


def test_optional_quote_can_be_omitted_without_losing_full_coverage(sample):
    sample[1]['issues'][0]['citations'].pop()
    assert api().score_contract(*sample)['engineering_passed'] is True


def test_unregistered_supplement_goes_to_review_not_false_positive(sample):
    sample[2]['exit_cost_relation']['optional'] = []
    result = api().score_contract(*sample)
    assert result['engineering_passed'] is True
    assert result['review_queue'] == [{'issue_index': 0, 'reason': 'additional_citations', 'anchor_ids': ['c']}]
    assert result['promotion_allowed'] is False


@pytest.mark.parametrize('change', ['quote', 'unknown_id', 'missing_required', 'duplicate_citation',
                                  'duplicate_kind', 'coverage', 'signoff', 'integer_bool', 'unknown_field'])
def test_invalid_evidence_is_not_hidden_by_structural_success(sample, change):
    answer = sample[1]
    item = answer['issues'][0]
    if change == 'quote': item['citations'][0]['quote'] = '虚假原文'
    elif change == 'unknown_id': item['citations'][0]['id'] = 'missing'
    elif change == 'missing_required': item['citations'].pop(0)
    elif change == 'duplicate_citation': item['citations'].append(deepcopy(item['citations'][0]))
    elif change == 'duplicate_kind': answer['issues'].append(deepcopy(item))
    elif change == 'coverage': answer['examined_anchor_ids'].pop()
    elif change == 'signoff': answer['formal_signoff'] = True
    elif change == 'integer_bool': answer['formal_signoff'] = 0
    else: answer['approved'] = True
    assert api().score_contract(*sample)['engineering_passed'] is False


def test_extra_observation_is_reviewed_and_its_quotes_are_still_checked(sample):
    extra = deepcopy(sample[1]['issues'][0]); extra['kind'] = 'obligation_direction'
    sample[1]['issues'].append(extra)
    result = api().score_contract(*sample)
    assert result['engineering_passed'] is True
    assert any(q['reason'] == 'additional_observation' for q in result['review_queue'])
    extra['citations'][0]['quote'] = 'not in source'
    assert api().score_contract(*sample)['engineering_passed'] is False


def test_empty_additional_observation_does_not_pass(sample):
    sample[1]['issues'].append({'kind': 'extra', 'citations': [], 'analysis': 'x', 'recommendation': 'y'})
    assert api().score_contract(*sample)['engineering_passed'] is False


def test_duplicate_words_at_different_positions_must_both_be_cited(sample):
    sample[0]['anchors'][2]['quote'] = sample[0]['anchors'][0]['quote']
    sample[2]['exit_cost_relation'] = {'required': ['a', 'b', 'c'], 'optional': []}
    sample[1]['issues'][0]['citations'].pop()
    result = api().score_contract(*sample)
    assert result['engineering_passed'] is False
    assert result['relations']['exit_cost_relation']['missing_anchor_ids'] == ['c']


def refutation(case, answer):
    return {'source_sha256': api().fingerprint(case), 'answer_sha256': api().fingerprint(answer),
            'issue_index': 0, 'field': 'analysis', 'claim_quote': '通知形式未明示',
            'evidence': [deepcopy(case['anchors'][0])], 'note': '源文明确记载书面通知；工程人工反证，不作法律评价。'}


def test_false_gap_has_locatable_source_refutation(sample):
    case, answer, expected = sample
    answer['issues'][0]['analysis'] = '通知形式未明示，建议补充。'
    result = api().score_contract(case, answer, expected, contradictions=[refutation(case, answer)])
    assert result['engineering_passed'] is True
    assert result['reasoning_status'] == 'contradicted'
    assert result['contradictions'][0]['claim_quote'] == '通知形式未明示'
    assert result['promotion_allowed'] is False


@pytest.mark.parametrize('change', ['source_hash', 'answer_hash', 'claim', 'evidence', 'index', 'field'])
def test_refutation_cannot_be_reused_for_other_bytes_or_fabricated(sample, change):
    case, answer, expected = sample
    answer['issues'][0]['analysis'] = '通知形式未明示。'
    note = refutation(case, answer)
    if change == 'source_hash': note['source_sha256'] = '0' * 64
    elif change == 'answer_hash': note['answer_sha256'] = '0' * 64
    elif change == 'claim': note['claim_quote'] = '该输出不存在的词'
    elif change == 'evidence': note['evidence'][0]['quote'] = '伪造反证'
    elif change == 'index': note['issue_index'] = True
    else: note['field'] = 'kind'
    with pytest.raises(ValueError): api().score_contract(case, answer, expected, contradictions=[note])


def test_invalid_or_duplicate_fixture_anchors_are_rejected(sample):
    sample[0]['anchors'].append(deepcopy(sample[0]['anchors'][0]))
    with pytest.raises(ValueError): api().score_contract(*sample)


@pytest.mark.parametrize('answer', [None, [], {'issues': None}, {'issues': [42]}])
def test_malformed_model_output_becomes_failure_not_exception(sample, answer):
    result = api().score_contract(sample[0], answer, sample[2])
    assert result['engineering_passed'] is False
    assert result['promotion_allowed'] is False
