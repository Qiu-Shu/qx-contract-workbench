"""Post-hoc real-response regressions; no model calls or legal approval."""
from copy import deepcopy
from decimal import localcontext
import json
from pathlib import Path

import pytest

from cn_contract.acceptance.contract_calculation_gate import check_calculations
from cn_contract.acceptance.contract_scoring import fingerprint

FIXTURES = Path(__file__).parents[1] / 'fixtures/contract_calculation'
DATA = json.loads((FIXTURES / 'responses.json').read_text(encoding='utf-8'))
PLANS = json.loads((FIXTURES / 'plans.json').read_text(encoding='utf-8'))


def sample(label='validation-r1-C4-n17'):
    r = next(r for r in DATA['records'] if r['label'] == label)
    return deepcopy(DATA['cases'][r['case_id']]), deepcopy(r['answer']), deepcopy(PLANS.get(r['case_id']))


def test_real_arithmetic_label_conflict_is_blocked_without_rewriting():
    case, answer, plan = sample()
    before = deepcopy((case, answer, plan))
    report = check_calculations(case, answer, plan)
    q2 = report['checks']['q2']
    assert q2['status'] == 'blocked'
    assert q2['computed_verdict'] == 'refuted'
    assert q2['calculations'][0]['value'] == '970.20'
    assert 'verdict_mismatch' in q2['errors']
    assert not report['math_stage_passed'] and not report['promotion_allowed']
    assert report['answer_sha256'] == fingerprint(answer)
    assert (case, answer, plan) == before


def test_correct_arithmetic_control_and_noncalculation_remain_distinct():
    case, answer, plan = sample()
    answer['checks'][1]['verdict'] = 'refuted'
    report = check_calculations(case, answer, plan)
    assert report['math_stage_passed']
    assert report['checks']['q1']['status'] == 'consistent'
    assert report['checks']['q4']['status'] == 'not_covered'
    assert report['manual_review_required'] and report['reasoning_status'] == 'pending_manual_review'


@pytest.mark.parametrize('candidate', ['C3', 'C4'])
def test_real_missing_denominator_and_classification_sources(candidate):
    report = check_calculations(*sample(f'validation-r1-{candidate}-n18'))
    assert 'evidence_incomplete' in report['checks']['q4']['errors']
    assert report['checks']['q4']['computed_verdict'] == 'refuted'


def test_real_extra_field_blocks_even_with_other_correct_checks():
    report = check_calculations(*sample('validation-r1-C3-n20'))
    assert 'answer_schema' in report['errors']
    assert report['checks']['q1']['status'] == 'blocked'
    assert not report['math_stage_passed']


@pytest.mark.parametrize('label', [f'final-r{r}-{c}-n12' for r in (1, 2) for c in ('C2', 'C3')])
def test_real_compound_amount_claim(label):
    report = check_calculations(*sample(label))
    q2 = report['checks']['q2']
    assert q2['computed_verdict'] == 'supported'
    assert [c['value'] for c in q2['calculations']] == ['23256.00', '4651.20']
    assert 'verdict_mismatch' in q2['errors']


def test_no_plan_is_not_a_pass():
    report = check_calculations(*sample('validation-r1-C4-n19'))
    assert not report['math_stage_passed']
    assert all(c['status'] == 'not_covered' for c in report['checks'].values())


@pytest.mark.parametrize('mutation', ['case', 'claim', 'binding', 'target', 'unit', 'float',
                                     'nan', 'large', 'facts', 'unknown', 'evidence'])
def test_plan_drift_and_unbounded_or_untrusted_inputs_rejected(mutation):
    case, answer, plan = sample()
    p = plan['checks'][0]['comparisons'][0]
    if mutation == 'case': case['context'] += '修改'
    if mutation == 'claim': plan['checks'][0]['claim_quote'] += '修改'
    if mutation == 'binding': next(iter(p['bindings'].values()))[0]['text'] = '不存在的数字'
    if mutation == 'target': p['target']['text'] = '不存在的金额'
    if mutation == 'unit': p['target']['unit'] = 'USD'
    if mutation == 'float': p['inputs'][0]['value'] = 84.0
    if mutation == 'nan': p['inputs'][0]['value'] = 'NaN'
    if mutation == 'large': p['inputs'][0]['value'] = '1e999999'
    if mutation == 'facts': p['inputs'][0]['fact_ids'] = ['not-approved']
    if mutation == 'unknown': p['expected_verdict'] = 'supported'
    if mutation == 'evidence': plan['checks'][0]['evidence_options'] = [['a1']]
    with pytest.raises(ValueError): check_calculations(case, answer, plan)


def test_ast_depth_bounded_before_pydantic_recursion():
    case, answer, plan = sample()
    ast = {'kind': 'variable', 'name': 'count'}
    for _ in range(40):
        ast = {'kind': 'binary', 'operator': 'add', 'left': ast,
               'right': {'kind': 'literal', 'value': '0'}}
    plan['checks'][0]['comparisons'][0]['formula']['ast'] = ast
    with pytest.raises(ValueError): check_calculations(case, answer, plan)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'quote', 'signoff', 'legal', 'top', 'verdict', 'type'])
def test_malformed_model_outputs_fail_closed(mutation):
    case, answer, plan = sample()
    if mutation == 'missing': answer['checks'].pop()
    if mutation == 'duplicate': answer['checks'].append(deepcopy(answer['checks'][0]))
    if mutation == 'quote': answer['checks'][0]['citations'][0]['quote'] += '假话'
    if mutation == 'signoff': answer['formal_signoff'] = 0
    if mutation == 'legal': answer['legal_status'] = 'verified'
    if mutation == 'top': answer['approved'] = True
    if mutation == 'verdict': answer['checks'][0]['verdict'] = []
    if mutation == 'type': answer = []
    report = check_calculations(case, answer, plan)
    assert 'answer_schema' in report['errors'] and not report['math_stage_passed']


def test_ambient_decimal_context_cannot_change_replay():
    args = sample()
    expected = check_calculations(*args)
    with localcontext() as ctx:
        ctx.prec = 2
        assert check_calculations(*args) == expected


def test_finite_intermediate_precision_never_passes_silently():
    case, answer, plan = sample()
    # Deliberately changed trusted formula yields a recurring Decimal result.
    plan['checks'][0]['comparisons'][0]['formula']['ast']['operator'] = 'divide'
    report = check_calculations(case, answer, plan)
    assert 'calculation_precision_limited' in report['checks']['q1']['errors']
    assert report['checks']['q1']['computed_verdict'] is None
    assert not report['math_stage_passed']


def test_cyclic_model_output_is_reported_as_invalid():
    case, answer, plan = sample()
    answer['cycle'] = answer
    report = check_calculations(case, answer, plan)
    assert report['errors'] == ['answer_schema'] and report['answer_sha256'] is None


def test_invalid_unicode_model_string_is_reported_as_invalid():
    case, answer, plan = sample()
    answer['checks'][0]['explanation'] = '\ud800'
    report = check_calculations(case, answer, plan)
    assert report['errors'] == ['answer_schema'] and report['answer_sha256'] is None
