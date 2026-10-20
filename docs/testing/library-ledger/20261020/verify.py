"""Run a stable-input synthetic test slice with explicit optional pilot runtime."""
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
out = root / '.local/library-ledger-20261020'
mode = sys.argv[1]
assert mode in ('target', 'full')
pilot = Path('D:/Documents/裁判文书数据库试点2025/.venv/Scripts/python.exe')
assert pilot.is_file()
patterns = ('test_assistant_library*.py','test_assistant*schema*.py','test_assistant*backup*.py',
            'test_workspace*.py','test_storage_schema*.py','test_library_records.py')
targets = sorted({p.as_posix() for folder in ('tests/unit','tests/integration')
                  for pattern in patterns for p in Path(folder).glob(pattern)} | {
    'tests/integration/test_assistant_storage.py','tests/integration/test_local_workbench.py'})

def inputs():
    paths = set()
    for folder in ('src','config','tests','scripts'):
        paths.update(p.as_posix() for p in Path(folder).rglob('*') if p.is_file()
            and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.db','.sqlite'))
    paths.update(['pyproject.toml','requirements.lock','sources/upstream.lock.json'])
    return {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sorted(paths)}

before = inputs()
env = {**os.environ, 'QX_PILOT_PYTHON':str(pilot), 'PYTHONPATH':str(root/'src'), 'PYTHONUTF8':'1'}
commands = [(mode,[sys.executable,'-X','utf8','-m','pytest',*(targets if mode=='target' else []),
                  '-q','--tb=short','--junitxml='+str(out/(mode+'.xml'))])]
if mode == 'full':
    gates = [['-m','cn_contract.cli','schema','--check'], ['scripts/verify_defaults.py'],
             ['scripts/verify_sources.py','--mode','development'],
             ['scripts/verify_runtime_dependencies.py','--mode','development']]
    commands.extend((f'gate-{i}',[sys.executable,'-X','utf8',*args]) for i,args in enumerate(gates,1))
results = []
for name, command in commands:
    started=datetime.now(timezone.utc).isoformat(); clock=time.monotonic()
    with (out/(name+'.log')).open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        (out/'active.json').write_text(json.dumps({'pid':process.pid,'command':command,'started_utc':started}),encoding='utf-8')
        code=process.wait()
    result={'name':name,'command':command,'started_utc':started,'exit_code':code,'seconds':round(time.monotonic()-clock,3)}
    if name == mode and (out/(mode+'.xml')).is_file():
        suites=ET.parse(out/(mode+'.xml')).getroot()
        result['counts']={k:sum(int(s.get(k,0)) for s in suites.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    results.append(result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
after=inputs()
report={'results':results,'inputs_before':before,'inputs_after':after,'inputs_equal':before==after,
        'input_count':len(before),'environment':{'QX_PILOT_PYTHON':str(pilot)},
        'scope':'Windows source tests; synthetic fixtures. Not frozen/GUI/installer/real-model or real-corpus acceptance.'}
(out/(mode+'-verification.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'active.json').write_text(json.dumps({'completed':True,'mode':mode,'exit_codes':[r['exit_code'] for r in results]}),encoding='utf-8')
sys.exit(0 if before==after and all(r['exit_code']==0 for r in results) else 1)
