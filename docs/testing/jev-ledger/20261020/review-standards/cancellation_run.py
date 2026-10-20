"""Capture the one newly relevant cancellation contract, preserving prior runs."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
prefix = out/'cancellation-final'
prior = json.loads((out/'standards-final.json').read_text(encoding='utf-8'))
def hashes():
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in prior['source_after']}
before = hashes()
command = [str(root/'.venv/Scripts/python.exe'), '-m', 'pytest', str(out/'cancellation_probe.py'),
    '-q', '-p', 'no:cacheprovider', '--basetemp='+str(out/'tmp-cancellation-final'),
    '--junitxml='+str(prefix)+'.xml']
assert not Path(str(prefix)+'.json').exists(), 'Preserve prior evidence; choose a new label.'
with Path(str(prefix)+'.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
after = hashes()
Path(str(prefix)+'.exit').write_text(str(result.returncode)+'\n', encoding='ascii')
record = {'command': command, 'workspace': str(root), 'time_utc': datetime.now(timezone.utc).isoformat(),
    'exit_code': result.returncode, 'source_before': before, 'source_after': after,
    'source_stable': before == after,
    'changed_since_previous': [name for name in before if before[name] != prior['source_after'][name]]}
Path(str(prefix)+'.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'exit_code': result.returncode, 'source_stable': before == after,
    'changed_since_previous': record['changed_since_previous']}))
print(json.dumps(Path(str(prefix)+'.log').read_text(encoding='utf-8'), ensure_ascii=True))
sys.exit(result.returncode)
