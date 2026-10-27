"""Replay saved synthetic model outputs with no model, secrets or network."""
import json
from pathlib import Path
import subprocess
import sys

from cn_contract.acceptance.contract_scoring import score_contract

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'tests/fixtures/contract_scoring/pilot-v1.json'


def test_real_observed_lease_output_no_longer_fails_for_useful_quote():
    fixture = json.loads(FIXTURE.read_bytes())
    case = next(c for c in fixture['cases'] if c['id'] == 'case-04')
    record = next(r for r in fixture['records'] if r['phase'] == 'baseline-holdout' and r['case_id'] == case['id'])
    assert record['legacy_grade']['all_checks_passed'] is False
    assert record['legacy_grade']['errors'] == ['relationship anchors']
    result = score_contract(case, record['answer'], fixture['expectations'][case['id']])
    assert result['engineering_passed'] is True
    assert result['reasoning_status'] == 'pending_manual_review'


def test_actual_false_gap_is_bound_to_observed_output_and_evidence():
    fixture = json.loads(FIXTURE.read_bytes())
    case = next(c for c in fixture['cases'] if c['id'] == 'case-02')
    record = next(r for r in fixture['records'] if r['phase'] == 'composed-dev' and r['case_id'] == case['id'])
    assert record['legacy_grade']['all_checks_passed'] is True
    result = score_contract(case, record['answer'], fixture['expectations'][case['id']],
                            contradictions=record['contradictions'])
    assert result['reasoning_status'] == 'contradicted'
    assert result['promotion_allowed'] is False


def test_replay_cli_preserves_existing_report_and_labels_posthoc(tmp_path):
    output = tmp_path / 'report.json'
    command = [sys.executable, '-X', 'utf8', 'scripts/contract_pilot_replay.py', '--output', str(output)]
    response = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert response.returncode == 0, response.stderr
    before = output.read_bytes()
    report = json.loads(before)
    assert report['summary'] == {'outputs': 16, 'legacy_strict_passed': 12, 'engineering_passed': 16,
                                  'manual_contradictions': 1, 'reasoning_pending': 15, 'review_queue_items': 3}
    assert report['posthoc'] is True
    assert report['new_model_requests'] == report['fresh_holdout_count'] == 0
    assert report['model_quality_improvement'] is None and report['promotion_allowed'] is False
    retry = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    assert retry.returncode != 0 and output.read_bytes() == before
