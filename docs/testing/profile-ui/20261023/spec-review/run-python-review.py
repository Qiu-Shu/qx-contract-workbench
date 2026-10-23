"""Complete only the independent Python probes after correcting local runner paths."""
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
initial = here / 'initial-runner'
initial.mkdir(exist_ok=True)
for name in ('python.xml', 'commands.json', 'inputs-before.json'):
    target = initial / name
    if not target.exists():
        target.write_bytes((here / name).read_bytes())
(initial / 'failure.md').write_text(
    'Initial review runner exited 1: the Python probe failed collection because '
    'tests/integration was absent from PYTHONPATH (ModuleNotFoundError: test_assistant_storage). '
    'Child stdout then caused a UTF-8 reader UnicodeDecodeError and the runner raised '
    'TypeError while concatenating None stdout. The initial Python child exit code '
    'was not recorded; its JUnit records one collection error and no executed test cases. '
    'The independent Node stage completed before that failure: exit 0, three passes. '
    'This is a review-harness failure, not a product result. No product changes were made.\n',
    encoding='utf-8')
old = json.loads((here / 'inputs-before.json').read_text('utf-8'))
files = sorted(set(old) | {str(Path(__file__).relative_to(root))})
def hashes():
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
def save(name, value):
    (here / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
before = hashes()
save('completion-inputs-before.json', before)
command = [sys.executable, '-X', 'utf8', '-m', 'pytest', str(here / 'test_history_spec.py'),
           '-q', '-W', 'error', '--basetemp=' + str(here / '合成隔离-02'),
           '--junitxml=' + str(here / 'python.xml')]
env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
           PYTHONPATH=os.pathsep.join(str(root / p) for p in ('src', '.', 'tests/integration', 'tests/unit')))
save('completion-command.json', {'cwd': str(root), 'argv': command,
     'env': {k: env[k] for k in ('PYTHONUTF8', 'PYTHONIOENCODING', 'PYTHONPATH')}})
start = time.monotonic()
result = subprocess.run(command, cwd=root, env=env, capture_output=True)
elapsed = time.monotonic() - start
(here / 'python.log').write_bytes(result.stdout + result.stderr)
(here / 'python-exitcode.txt').write_text(str(result.returncode), encoding='utf-8')
after = hashes()
save('completion-inputs-after.json', after)
results = []
for label in ('node', 'python'):
    cases = ET.parse(here / (label + '.xml')).findall('.//testcase')
    results.append({'name': label, 'exit_code': int((here / (label + '-exitcode.txt')).read_text()),
        'cases': len(cases), 'failures': sum(c.find('failure') is not None for c in cases),
        'errors': sum(c.find('error') is not None for c in cases),
        'skipped': sum(c.find('skipped') is not None for c in cases)})
summary = {'results': results, 'python_elapsed_seconds': round(elapsed, 3),
    'initial_runner_exit_code': 1, 'initial_python_child_exit_code': None,
    'initial_python_collection_errors': 1,
    'input_count': len(before), 'completion_inputs_stable': before == after,
    'original_inputs_stable': all(after[p] == digest for p, digest in old.items()),
    'changed': [p for p in before if before[p] != after[p]],
    'real_model': False, 'actual_windows': False, 'full_author_suites': False}
save('summary.json', summary)
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(int(result.returncode != 0 or before != after))
