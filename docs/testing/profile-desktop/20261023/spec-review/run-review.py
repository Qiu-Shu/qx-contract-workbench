import hashlib
import json
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

here = Path(__file__).resolve().parent
root = here.parents[2]
files = [
    'desktop/backend.cjs', 'desktop/model-control.cjs', 'desktop/model-session.cjs',
    'desktop/profile-basis.cjs', 'desktop/profile-approval.cjs', 'desktop/model-approval.cjs',
    'desktop/preload.cjs', 'desktop/model-approval-window.cjs', 'desktop/model-approval.html',
    'desktop/model-approval.js', 'desktop/model-approval.css', 'desktop/package.json',
    'src/cn_contract/web/app.py', 'src/cn_contract/domain.py',
    'src/cn_contract/assistant/native_profile_control.py',
    'docs/plans/2026-10-23-profile-desktop.md',
    'tests/integration/test_assistant_frontend.py',
    'desktop/tests/profile-native.test.cjs', 'desktop/tests/profile-approval.test.cjs',
    'desktop/tests/model-approval-window.test.cjs',
    str(here.relative_to(root) / 'spec-probes.cjs'),
]
def hashes():
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}
def save(name, value):
    (here/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
before = hashes()
save('inputs-before.json', before)
command = ['node', '--test', '--test-reporter=spec', '--test-reporter-destination=stdout',
           '--test-reporter=junit', '--test-reporter-destination='+str(here/'results.xml'),
           str(here/'spec-probes.cjs')]
save('command.json', {'cwd': str(root), 'argv': command})
started = time.monotonic()
result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding='utf-8')
(here/'output.log').write_text(result.stdout+result.stderr, encoding='utf-8')
(here/'exitcode.txt').write_text(str(result.returncode)+'\n', encoding='utf-8')
after = hashes()
save('inputs-after.json', after)
tree = ET.parse(here/'results.xml')
cases = tree.findall('.//testcase')
summary = {'exit_code': result.returncode, 'seconds': round(time.monotonic()-started,3),
           'tests':len(cases), 'failures':sum(c.find('failure') is not None for c in cases),
           'errors':sum(c.find('error') is not None for c in cases),
           'input_count':len(before), 'inputs_stable':before == after,
           'changed':[p for p in before if before[p] != after[p]],
           'network':'No network calls: in-process synthetic native session, snapshot dependencies, and VM DOM only.',
           'actual_electron_or_python_db':False}
save('summary.json', summary)
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(result.returncode or (0 if before == after else 1))
