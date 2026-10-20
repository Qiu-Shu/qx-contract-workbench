from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

root = Path.cwd()
out = root / '.local/library-memory-20261020'
targets = sorted({p.as_posix() for folder in ('tests/unit', 'tests/integration')
                  for p in Path(folder).glob('test_library_*.py')} | {
    'tests/integration/test_assistant_library_adapter.py',
    'tests/integration/test_assistant_library_tools.py'})

def inputs():
    paths = set(targets)
    for folder in ('src', 'config', 'tests/helpers'):
        paths.update(p.as_posix() for p in Path(folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
    paths.update(['pyproject.toml', 'requirements.lock', 'scripts/verify_defaults.py',
        'scripts/verify_sources.py', 'scripts/verify_runtime_dependencies.py', 'sources/upstream.lock.json'])
    return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}

before = inputs()
env = {**os.environ, 'PYTHONPATH':str(root/'src'), 'PYTHONUTF8':'1'}
commands = [('regression', [sys.executable, '-X', 'utf8', '-m', 'pytest', *targets, '-q',
                          '--junitxml=' + str(out/'regression.xml')])]
gates = [ ['-m','cn_contract.cli','schema','--check'], ['scripts/verify_defaults.py'],
          ['scripts/verify_sources.py','--mode','development'],
          ['scripts/verify_runtime_dependencies.py','--mode','development'] ]
commands.extend((f'gate-{i}', [sys.executable, '-X','utf8', *args]) for i,args in enumerate(gates,1))
results = []
for name, command in commands:
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    run = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')
    (out/f'{name}.log').write_text(run.stdout+run.stderr, encoding='utf-8')
    result = {'name':name, 'command':command, 'started_utc':started,
              'exit_code':run.returncode, 'seconds':round(time.monotonic()-clock, 3)}
    if name == 'regression' and (out/'regression.xml').is_file():
        suites = ET.parse(out/'regression.xml').getroot()
        result['counts'] = {k:sum(int(s.get(k, 0)) for s in suites.iter('testsuite'))
                            for k in ('tests', 'failures', 'errors', 'skipped')}
    results.append(result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
after = inputs()
report = {'results':results, 'inputs_before':before, 'inputs_after':after,
          'inputs_equal':before == after, 'input_count':len(before),
          'scope':'Local Windows Python, synthetic temporary libraries/workspaces only; no frozen/GUI/model/network or real corpus acceptance.'}
(out/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
sys.exit(0 if all(r['exit_code']==0 for r in results) and before == after else 1)
