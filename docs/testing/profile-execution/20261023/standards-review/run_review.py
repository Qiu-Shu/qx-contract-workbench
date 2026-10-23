"""Freeze hashes around the independent synthetic review probe run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

root = Path.cwd()
evidence = root / '.local/profile-execution-20261023/standards-review'
baseline = '9a0d2df3767dc8252f1530be4f949583fd250af2'


def snapshot():
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard']).decode().split('\0')
    wanted = {p for p in paths if p and (p.startswith(('src/', 'tests/', 'config/', 'scripts/'))
              or p in ('pyproject.toml', 'requirements.txt', 'CONTRIBUTING.md', 'AGENTS.md',
                       'docs/plans/2026-10-23-profile-execution.md'))}
    wanted.add('.local/profile-execution-20261023/standards-review/test_standards_probe.py')
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(wanted) if (root / p).is_file()}


started = datetime.now(timezone.utc).isoformat()
before = snapshot()
(evidence / 'inputs-before.json').write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding='utf-8')
command = [sys.executable, '-X', 'utf8', '-m', 'pytest',
           '.local/profile-execution-20261023/standards-review/test_standards_probe.py',
           '-q', '--tb=short', '--basetemp=.local/profile-execution-20261023/standards-review/temp-final',
           '--junitxml=.local/profile-execution-20261023/standards-review/final.xml']
environment = dict(os.environ)
environment['PYTHONPATH'] = str(root / 'tests/integration') + os.pathsep + environment.get('PYTHONPATH', '')
with (evidence / 'final.log').open('w', encoding='utf-8') as stream:
    result = subprocess.run(command, cwd=root, env=environment, stdout=stream, stderr=subprocess.STDOUT)
after = snapshot()
(evidence / 'inputs-after.json').write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding='utf-8')
suites = ET.parse(evidence / 'final.xml').getroot()
counts = {k: sum(int(suite.get(k, 0)) for suite in suites.iter('testsuite'))
          for k in ('tests', 'failures', 'errors', 'skipped')}
report = dict(baseline=baseline, started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
              command=command, cwd=str(root), exit_code=result.returncode, counts=counts,
              input_count=len(before), inputs_stable=before == after,
              changed_inputs=sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p)))
(evidence / 'run-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(result.returncode or (0 if before == after else 3))
