"""Replay the fixed synthetic pilot fixture offline, without a model or key."""
import argparse
import hashlib
import json
from pathlib import Path

from cn_contract.acceptance.contract_scoring import VERSION, fingerprint, score_contract

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/contract_scoring/pilot-v1.json'


def replay():
    raw = FIXTURE.read_bytes()
    fixture = json.loads(raw)
    if (fixture['version'] != 'synthetic-pilot-replay-v1' or fixture['evaluation_role'] != 'seen_replay'
            or fixture['synthetic_only'] is not True):
        raise ValueError('only the registered synthetic replay is supported')
    cases = {case['id']: case for case in fixture['cases']}
    results = []
    for record in fixture['records']:
        case = cases[record['case_id']]
        result = score_contract(case, record['answer'], fixture['expectations'][case['id']],
                                contradictions=record['contradictions'])
        results.append({'id': record['id'], 'phase': record['phase'],
                        'source_sha256': fingerprint(case), 'answer_sha256': fingerprint(record['answer']),
                        'legacy_grade': record['legacy_grade'], 'current': result})
    return {'scorer_version': VERSION, 'fixture_sha256': hashlib.sha256(raw).hexdigest(),
            'evaluation_role': 'seen_replay', 'posthoc': True, 'new_model_requests': 0,
            'fresh_holdout_count': 0, 'model_quality_improvement': None, 'promotion_allowed': False,
            'summary': {'outputs': len(results),
                        'legacy_strict_passed': sum(r['legacy_grade']['all_checks_passed'] for r in results),
                        'engineering_passed': sum(r['current']['engineering_passed'] for r in results),
                        'manual_contradictions': sum(len(r['current']['contradictions']) for r in results),
                        'reasoning_pending': sum(r['current']['reasoning_status'] == 'pending_manual_review' for r in results),
                        'review_queue_items': sum(len(r['current']['review_queue']) for r in results)},
            'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report['summary'], ensure_ascii=False))
    print('Seen-output diagnostics only; no new model requests or production approval.')


if __name__ == '__main__':
    main()
