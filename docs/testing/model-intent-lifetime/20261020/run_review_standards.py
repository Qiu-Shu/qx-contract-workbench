"""Capture command, exit code, source hashes and independent pytest output."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
paths = ['src/cn_contract/assistant/native_model_control.py',
    'src/cn_contract/assistant/providers/registry.py']
def hashes():
    return {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in paths}
command = [str(root/'.venv/Scripts/python.exe'), '-m', 'pytest',
    str(out/'review_standards_probe.py'), '-q', '-p', 'no:cacheprovider',
    '--basetemp='+str(out/'review-standards-tmp'),
    '--junitxml='+str(out/'review-standards.xml')]
before = hashes()
(out/'review-standards-command.json').write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding='utf-8')
with (out/'review-standards.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
        env={**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8'}, text=True, encoding='utf-8')
(out/'review-standards.exit').write_text(str(result.returncode)+'\n', encoding='ascii')
record = {'time_utc': datetime.now(timezone.utc).isoformat(), 'command': command,
    'exit_code': result.returncode, 'source_before': before, 'source_after': hashes()}
record['source_stable'] = record['source_before'] == record['source_after']
(out/'review-standards-run.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(record, ensure_ascii=True, indent=2))
print(json.dumps((out/'review-standards.log').read_text(encoding='utf-8'), ensure_ascii=True))
sys.exit(result.returncode)
