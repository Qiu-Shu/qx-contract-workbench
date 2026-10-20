"""Record the bounded independent review run against immutable input hashes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BASE = 'a4c3c6706caad31c2335b4d055240dbddbfbd372'
PRODUCTS = [
    'src/cn_contract/storage_schema.py',
    'src/cn_contract/assistant_model_schema_baseline.py',
    'src/cn_contract/schema_migrations.py',
    'src/cn_contract/storage_bootstrap.py',
    'src/cn_contract/assistant/attachment_integrity.py',
    'src/cn_contract/assistant/model_integrity.py',
    'src/cn_contract/ops/backup.py',
    'src/cn_contract/ops/workspace_backup.py',
    'src/cn_contract/web/local_server.py',
    'src/cn_contract/assistant/service.py',
    'src/cn_contract/domain.py',
    'src/cn_contract/assistant/judge_schema.py',
    'src/cn_contract/assistant/judge_integrity.py',
    'src/cn_contract/assistant/providers/judge_attempts.py',
    'src/cn_contract/assistant/providers/judge_execution.py',
    'src/cn_contract/assistant/providers/judge_policy.py',
    'src/cn_contract/assistant/providers/jev.py',
]
PROBES = ['probe_schema_glue.py', 'probe_deadline_receipt.py',
          'probe_recovery_authorization.py']


def snapshot(paths):
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def run():
    before = snapshot(PRODUCTS)
    command = [sys.executable, '-m', 'pytest']
    command.extend(str(OUT / name) for name in PROBES)
    command.extend(['-q', '--junitxml=' + str(OUT / 'final.xml')])
    env = dict(os.environ)
    env['PYTHONPATH'] = 'src;.;tests/integration'
    with (OUT / 'final.log').open('wb') as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    after = snapshot(PRODUCTS)
    cases = []
    xml = OUT / 'final.xml'
    if xml.exists():
        for item in ET.parse(xml).getroot().iter('testcase'):
            status = next((name for name in ('failure', 'error', 'skipped')
                           if item.find(name) is not None), 'passed')
            cases.append({'nodeid': item.get('classname', '') + '::' + item.get('name', ''),
                          'status': status, 'seconds': item.get('time')})
    unique = len({item['nodeid'] for item in cases})
    counts = {name: sum(item['status'] == name for item in cases)
              for name in ('passed', 'failure', 'error', 'skipped')}
    report = {
        'review': 'CH-05B independent Spec probes', 'baseline': BASE,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'workspace': str(ROOT), 'command': command, 'exit_code': result.returncode,
        'actual_test_count': len(cases), 'unique_test_count': unique, 'counts': counts,
        'product_hashes_before': before, 'product_hashes_after': after,
        'products_stable': before == after, 'testcases': cases,
        'probe_sha256': {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                         for name in PROBES},
        'network_boundary': 'Only three local synthetic loopback HTTP POSTs; no external model, key or user material.',
        'retained_red_evidence': ['deadline-red.log', 'deadline-red.xml',
                                  'cancellation-red.log', 'cancellation-red.xml'],
    }
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'exit_code': result.returncode, 'actual_test_count': len(cases),
                     'unique_test_count': unique, 'counts': counts, 'products_stable': before == after}, ensure_ascii=False))
    return result.returncode if result.returncode else (0 if before == after and len(cases) == unique == 10 else 2)


if __name__ == '__main__':
    raise SystemExit(run())
