import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
paths = ['src/cn_contract/domain.py', 'src/cn_contract/assistant/profiles.py',
         'tests/unit/test_assistant_profiles.py', 'src/cn_contract/record_codec.py']
def hashes():
    return {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in paths}
command = [str(root/'.venv/Scripts/python.exe'), '-X', 'utf8', '-m', 'pytest', '-q',
           str(out/'spec-probes.py'), '--tb=short', '-o', 'junit_family=xunit1',
           '--junitxml='+str(out/'spec-probes.xml'),
           '--basetemp='+str(root/'.local/spec-profile-a-20261023')]
before = hashes()
started = datetime.now(timezone.utc).isoformat()
with (out/'spec-probes.log').open('wb') as handle:
    result = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT)
after = hashes()
record = {'baseline': 'a6d20edf8663222ce6469bae80edfc92c02627b2', 'command': command,
          'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
          'exit_code': result.returncode, 'inputs_before': before, 'inputs_after': after,
          'inputs_unchanged': before == after, 'data': 'independent synthetic pure DTO inputs only'}
(out/'spec-command.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print((out/'spec-probes.log').read_text('utf-8'))
raise SystemExit(result.returncode)
