"""Single stable-input source regression on a fresh D: synthetic temp root."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

root = Path.cwd()
out = root / '.local/profile-execution-20261023'
pilot = Path('D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe')
assert pilot.is_file()
temp = root / '.local' / ('pex-' + uuid4().hex[:8])
assert not temp.exists() and temp.resolve().is_relative_to((root / '.local').resolve())
free = shutil.disk_usage(out).free
assert free > 40 * 1024**3 + 2 * 1024**3

def inputs():
    paths = set()
    for folder in ('src','config','tests','scripts'):
        paths.update(p.as_posix() for p in Path(folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.db','.sqlite'))
    paths.update(['pyproject.toml','requirements.lock','sources/upstream.lock.json'])
    return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}

before = inputs()
assert not any((out/name).exists() for name in ('target.log', 'target.xml', 'target-verification.json'))
env = {**os.environ, 'QX_PILOT_PYTHON':str(pilot), 'PYTHONPATH':str(root/'src'), 'PYTHONUTF8':'1'}
targets = (out / 'target-nodeids.txt').read_text(encoding='utf-8-sig').splitlines()
assert targets and len(targets) == len(set(targets)) and all(x.startswith('tests/') for x in targets)
commands = [('target',[sys.executable,'-X','utf8',str(out/'target_runner.py'),
    str(temp),str(out/'target.xml')])]
gates = [['-m','cn_contract.cli','schema','--check'], ['scripts/verify_defaults.py'],
    ['scripts/verify_sources.py','--mode','development'],
    ['scripts/verify_runtime_dependencies.py','--mode','development']]
commands.extend((f'gate-{i}',[sys.executable,'-X','utf8',*args]) for i,args in enumerate(gates,1))
results = []
for name, command in commands:
    started = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
    with (out/(name+'.log')).open('w',encoding='utf-8') as log:
        process = subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        (out/'active.json').write_text(json.dumps({'pid':process.pid,'command':command,'started_utc':started}),encoding='utf-8')
        code = process.wait()
    result = {'name':name,'command':command,'started_utc':started,'exit_code':code,'seconds':round(time.monotonic()-clock,3)}
    if name == 'target' and (out/'target.xml').is_file():
        suites = ET.parse(out/'target.xml').getroot()
        result['counts'] = {k:sum(int(s.get(k,0)) for s in suites.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    results.append(result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
after = inputs()
report = {'results':results,'nodeids':targets,'inputs_before':before,'inputs_after':after,'inputs_equal':before==after,
    'input_count':len(before),'environment':{'QX_PILOT_PYTHON':str(pilot),'temp_root':str(temp),'free_bytes_before':free},
    'scope':'Windows Python source, synthetic data only; not UI, Electron, frozen, installer or real model acceptance.'}
(out/'target-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'active.json').write_text(json.dumps({'completed':True,'exit_codes':[r['exit_code'] for r in results]}),encoding='utf-8')
sys.exit(0 if before==after and all(r['exit_code']==0 for r in results) else 1)

