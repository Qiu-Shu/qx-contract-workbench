import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT=Path.cwd()
OUT=ROOT/'.local/native-model-settings-20261019'
PY=str(ROOT/'.venv/Scripts/python.exe')

def snapshot():
    result=subprocess.run(['git','ls-files','-z','-co','--exclude-standard','--','src','desktop','tests','scripts','config','schemas','pyproject.toml','requirements.lock'],capture_output=True,check=True)
    names=set(result.stdout.decode('utf-8').split('\0'))-{''}
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(names) if (ROOT/name).is_file()}

commands={
 'node-final':['node','--test','--test-reporter=tap',*[str(p) for p in sorted((ROOT/'desktop/tests').glob('*.test.cjs'))]],
 'defaults':[PY,'-X','utf8','scripts/verify_defaults.py'],
 'sources':[PY,'-X','utf8','scripts/verify_sources.py','--mode','development'],
 'dependencies':[PY,'-X','utf8','scripts/verify_runtime_dependencies.py','--mode','development'],
 'schema':[PY,'-X','utf8','-m','cn_contract.cli','schema','--check'],
}
before=snapshot();(OUT/'verification-input-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
def run(item):
    name,command=item;start=time.monotonic()
    result=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/(name+'.log')).write_bytes(result.stdout)
    (OUT/(name+'.exit')).write_text(str(result.returncode)+'\n')
    (OUT/(name+'-command.json')).write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
    info={'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)}
    if name=='node-final':
        for field in ['tests','pass','fail','skipped']:
            found=re.search(r'^# '+field+r' (\d+)$',result.stdout.decode('utf-8','replace'),re.M)
            if found:info[field]=int(found[1])
    return name,info
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results=dict(pool.map(run,commands.items()))
after=snapshot();(OUT/'verification-input-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
summary={'commands':results,'input_files':len(before),'changed_inputs':[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]}
(OUT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
sys.exit(1 if summary['changed_inputs'] or any(v['exit_code'] for v in results.values()) else 0)
