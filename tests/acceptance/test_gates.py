"""T11 report semantics; these are not legal benchmark successes."""
from collections import Counter
from tests.unit.test_case_registry import feature,SUITE


def report():return feature('evaluate_suite','runner')(feature()(SUITE),'offline',execute=False)


def test_missing_implementation_not_pass():
    result=report()
    states={r.test_id:r.status for r in result.results}
    assert states['V1-Q06']=='NOT_IMPLEMENTED' and states['V1-Q12']=='NOT_IMPLEMENTED'
    assert states['V1-Q10']=='NOT_IMPLEMENTED' and states['NEW-12']=='NOT_IMPLEMENTED'
    assert states['V1-W06']=='NOT_IMPLEMENTED' and states['V1-S06']=='NOT_IMPLEMENTED'


def test_unsupported_auto_table_is_separate_from_guard():
    item=next(r for r in report().results if r.test_id=='AUD-T21')
    assert item.status=='NOT_SUPPORTED'
    assert item.guard_status=='NOT_RUN' and item.guard_details


def test_no_execution_cannot_be_engineering_pass():
    result=report()
    assert result.denominator==84 and len(result.results)==84 and not result.executions
    assert not any(r.status=='PASS' or r.guard_status=='PASS' for r in result.results)
    assert sum(result.counts.values())==84 and result.counts==dict(Counter(r.status for r in result.results))|{s:0 for s in result.counts if s not in Counter(r.status for r in result.results)}


def test_lawyer_gold_and_metrics_remain_pending_unknown():
    result=report()
    assert result.gold.status=='pending' and result.gold.reviewer_1 is None and result.gold.reviewer_2 is None
    assert result.gold.disagreements=='pending'
    assert all(v is None for v in result.legal_metrics.model_dump().values())
    assert result.readiness=='BLOCKED' and result.real_provider_requests==0
    assert result.cost is None and result.human_review_minutes is None


def test_once_hard_gate_failure_cannot_be_averaged_away():
    from cn_contract.domain import EvaluationCaseResult
    assess=feature('assess_readiness','runner')
    values=[EvaluationCaseResult(test_id=f'case{i}',status='PASS',details=('技术夹具',)) for i in range(83)]
    values.append(EvaluationCaseResult(test_id='hard',status='FAIL',details=('错位修改',),hard_gate=True))
    assert assess(values)=='NO_GO'


def test_hard_guard_failure_is_no_go_even_when_capability_blocked():
    from cn_contract.domain import EvaluationCaseResult
    value=EvaluationCaseResult(test_id='hard',status='BLOCKED',details=('法律批准缺失',),guard_status='FAIL',hard_gate=True)
    assert feature('assess_readiness','runner')([value])=='NO_GO'


def test_nonoffline_missing_approval_zero_execution_and_no_scores():
    for mode in ('approved_model','live_guarded'):
        result=feature('evaluate_suite','runner')(feature()(SUITE),mode,execute=False)
        assert result.mode==mode and result.real_provider_requests==0 and not result.executions
        assert all(r.status=='BLOCKED' for r in result.results)
        assert all(v is None for v in result.legal_metrics.model_dump().values())


def test_40_samples_really_parse_confirm_and_store_engineering_runs(tmp_path):
    samples=feature('load_dataset')()
    results=feature('run_samples','sample_runner')(samples,tmp_path)
    assert len(results)==40 and sum(r.run_id is not None for r in results)==40
    assert all(r.parse_status=='completed' and r.facts_confirmed>0 and r.coverage_count==18 for r in results)
    assert all(r.model_usage and r.attempts and r.evidence_ref and r.evidence_sha256 for r in results)
    assert any(r.unsupported_parts>0 for r in results)
    assert all('金标准' in ''.join(r.limitations) for r in results)
import pytest


@pytest.mark.parametrize('test_id', ['NEW-04', 'NEW-16'])
def test_actual_registry_unsafe_anchor_or_signoff_guard_failure_is_no_go(test_id):
    from cn_contract.acceptance.registry import load_cases, SUITE
    from cn_contract.acceptance.runner import evaluate_suite, assess_readiness
    from cn_contract.domain import AcceptanceStatus
    report = evaluate_suite(load_cases(SUITE), 'offline', execute=False)
    results = [r.model_copy(update={'guard_status': AcceptanceStatus.FAIL}) if r.test_id == test_id else r for r in report.results]
    assert assess_readiness(results) == 'NO_GO'
