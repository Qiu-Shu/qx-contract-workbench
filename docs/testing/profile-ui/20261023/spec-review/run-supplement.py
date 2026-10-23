import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

here = Path(__file__).resolve().parent
root = here.parents[2]
original = json.loads((here / 'inputs-before.json').read_text('utf-8'))
files = sorted(set(original) | {str(p.relative_to(root)) for p in here.glob('*.py')})
def hashes():
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
def save(name, value):
    (here / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
before = hashes()
save('supplement-inputs-before.json', before)
env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
    PYTHONPATH=os.pathsep.join(str(root / p) for p in ('src', '.', 'tests/integration', 'tests/unit')))
command = [sys.executable, '-X', 'utf8', '-m', 'pytest',
    str(here / 'test_history_spec.py') + '::test_receipt_survives_edit_conversion_and_new_session_without_regrant',
    '-q', '-W', 'error', '--basetemp=' + str(here / '合成隔离-03'),
    '--junitxml=' + str(here / 'supplement.xml')]
save('supplement-command.json', {'cwd': str(root), 'argv': command,
    'env': {k: env[k] for k in ('PYTHONUTF8', 'PYTHONIOENCODING', 'PYTHONPATH')}})
start = time.monotonic()
result = subprocess.run(command, cwd=root, env=env, capture_output=True)
(here / 'supplement.log').write_bytes(result.stdout + result.stderr)
(here / 'supplement-exitcode.txt').write_text(str(result.returncode), encoding='utf-8')
after = hashes()
save('supplement-inputs-after.json', after)
cases = ET.parse(here / 'supplement.xml').findall('.//testcase')
product = {p: digest for p, digest in original.items() if not p.startswith('.local')}
summary = {'exit_code': result.returncode, 'cases': len(cases),
    'failures': sum(c.find('failure') is not None for c in cases),
    'errors': sum(c.find('error') is not None for c in cases),
    'elapsed_seconds': round(time.monotonic() - start, 3),
    'input_count': len(before), 'inputs_stable': before == after,
    'product_and_contract_input_count': len(product),
    'product_and_contract_stable_since_first_run': all(after[p] == digest for p, digest in product.items()),
    'changed': [p for p in before if before[p] != after[p]],
    'fixture_correction': 'Mark already initialized synthetic database storage flags before intake conversion, as existing fixture assumes.',
    'real_model': False, 'actual_windows': False}
save('supplement-summary.json', summary)
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(int(result.returncode != 0 or before != after))
