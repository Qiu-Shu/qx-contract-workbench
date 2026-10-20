"""Capture only the three independently selected Standards probes."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[3]
out = Path(__file__).resolve().parent
label = sys.argv[1] if len(sys.argv) == 2 else 'final'
assert label in ('initial', 'final', 'corrected')
prefix = out/('standards-'+label)
temporary = out/('tmp-'+label)
assert temporary.resolve().is_relative_to(out.resolve())
def git(*args):
    return subprocess.check_output(['git', *args], cwd=root).decode('utf-8').splitlines()
files = sorted(set(git('diff', '--name-only', 'a4c3c67', '--', 'src') +
    git('ls-files', '--others', '--exclude-standard', '--', 'src')))
def hashes():
    return {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in files}
command = [str(root/'.venv/Scripts/python.exe'), '-m', 'pytest', str(out/'probe.py'), '-q',
    '-p', 'no:cacheprovider', '--basetemp='+str(temporary), '--junitxml='+str(prefix)+'.xml']
before = hashes()
with Path(str(prefix)+'.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'})
after = hashes()
Path(str(prefix)+'.exit').write_text(str(result.returncode)+'\n', encoding='ascii')
record = {'command': command, 'workspace': str(root), 'time_utc': datetime.now(timezone.utc).isoformat(),
    'exit_code': result.returncode, 'source_before': before, 'source_after': after,
    'source_stable': before == after}
Path(str(prefix)+'.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'exit_code': result.returncode, 'sources': len(files), 'source_stable': before == after}))
print(json.dumps(Path(str(prefix)+'.log').read_text(encoding='utf-8'), ensure_ascii=True))
sys.exit(result.returncode)
