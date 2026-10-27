"""Read-only replay of sealed synthetic fixtures. No provider or credential imports."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from cn_contract.acceptance.contract_calculation_gate import check_calculations

FIXTURES = ROOT / 'tests/fixtures/contract_calculation'


def replay():
    manifest = json.loads((FIXTURES / 'manifest.json').read_text(encoding='utf-8'))
    loaded = {}
    for name in ('plans.json', 'responses.json'):
        raw = (FIXTURES / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['sha256'][name]:
            raise ValueError(f'Frozen fixture changed: {name}')
        loaded[name] = json.loads(raw)
    data, plans = loaded['responses.json'], loaded['plans.json']
    if data['synthetic_only'] is not True or data['post_hoc'] is not True:
        raise ValueError('Only post-hoc synthetic replay permitted')
    results = []
    counts, reasons = Counter(), Counter()
    for record in data['records']:
        report = check_calculations(data['cases'][record['case_id']], record['answer'], plans.get(record['case_id']))
        for check in report['checks'].values():
            counts[check['status']] += 1
            reasons.update(check['errors'])
        results.append({'label': record['label'], 'model': record['model'],
                        'original_source_sha256': record['source_sha256'], 'report': report})
    return {'version': 'post-hoc-calculation-replay-v1', 'fixture_sha256': manifest['sha256'],
            'records': len(results), 'unique_cases': len(data['cases']), 'check_statuses': dict(counts),
            'blocked_check_reasons': dict(reasons), 'results': results,
            'new_model_requests': 0, 'new_model_cost_cny': '0', 'post_hoc': True,
            'fresh_holdout_cases': 0, 'model_quality_improvement': None,
            'promotion_allowed': False, 'manual_review_required': True,
            'scope': 'Curated arithmetic/evidence checks only; neither plan semantics nor narrative truth is automatically verified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay()
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(result, output, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k != 'results'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
