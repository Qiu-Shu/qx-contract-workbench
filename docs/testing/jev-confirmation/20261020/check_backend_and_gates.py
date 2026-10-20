import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

root = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
old = root/'.local/jev-request-20261020/parent'
build = json.loads((old/'build.json').read_text('utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def selected(name):
    return name.startswith(('src/', 'config/', 'prompts/', 'rules/', 'tests/fixtures/assisted-v1/', 'tests/fixtures/synthetic/')) or name in ('desktop/backend.spec','desktop/requirements-build.lock','scripts/desktop_backend_entry.py','pyproject.toml','requirements.lock')
baseline = {p:h for p,h in build['inputs_after'].items() if selected(p)}
assert baseline and all(sha(root/p)==h for p,h in baseline.items())
exe = root/'.local/jev-request-20261020/frozen-backend/qx-backend/qx-backend.exe'
assert sha(exe)=='564a347488b4930f5928851c44571e2e8ecaa5f1ebefdbe2b195654a07271f07'
reuse = {'status':'passed','exe_sha256':sha(exe),'verified_repository_inputs':baseline,
    'count':len(baseline),'scope':'D1 recorded Python and packaged asset/build inputs unchanged; not a third-party closure attestation; current Electron source is tested separately'}
(out/'backend-reuse.json').write_text(json.dumps(reuse,ensure_ascii=False,indent=2),encoding='utf-8')
print('backend reuse:',len(baseline),'unchanged repository inputs',flush=True)
for i in range(1,5):
    cmd = json.loads((old/f'gate-{i}.json').read_text('utf-8'))['command']
    start=time.monotonic()
    p=subprocess.run(cmd,cwd=root,env={**os.environ,'PYTHONPATH':str(root/'src')},capture_output=True,text=True,encoding='utf-8')
    (out/f'gate-{i}.log').write_text(p.stdout+p.stderr,encoding='utf-8')
    (out/f'gate-{i}.json').write_text(json.dumps({'command':cmd,'exit_code':p.returncode,'elapsed_seconds':round(time.monotonic()-start,3)},ensure_ascii=False,indent=2),encoding='utf-8')
    print('gate',i,'exit',p.returncode,flush=True)
    assert p.returncode==0
