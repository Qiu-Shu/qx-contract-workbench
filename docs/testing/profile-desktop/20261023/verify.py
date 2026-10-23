from pathlib import Path
import subprocess, json, os, hashlib, time, sys
from datetime import datetime, timezone
root=Path.cwd(); out=root/'.local/profile-desktop-20261023'
def inputs():
    names=subprocess.check_output(['git','ls-files','-z','-co','--exclude-standard','--','src','desktop','tests','scripts','config','schemas','pyproject.toml','requirements.lock'],cwd=root).decode().split('\0')
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(set(names)-{''}) if (root/p).is_file()}
before=inputs()
env={**os.environ,'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}
commands=[('desktop',['node','--test','--test-reporter=tap',*[str(p) for p in sorted(Path('desktop/tests').glob('*.test.cjs'))]]),
          ('frontend',['node','--test','--test-reporter=tap',*[str(p) for p in sorted(Path('scripts').glob('test_assistant*.mjs'))]])]
gates=[['-m','cn_contract.cli','schema','--check'],['scripts/verify_defaults.py'],['scripts/verify_sources.py','--mode','development'],['scripts/verify_runtime_dependencies.py','--mode','development']]
commands += [(f'gate-{i}',[sys.executable,'-X','utf8',*args]) for i,args in enumerate(gates,1)]
results=[]
for name,command in commands:
    started=time.monotonic()
    with (out/(name+'.log')).open('w',encoding='utf-8') as log:
        child=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
        (out/'active.json').write_text(json.dumps({'pid':child.pid,'name':name,'command':command}),encoding='utf-8')
        code=child.wait()
    result={'name':name,'command':command,'exit_code':code,'seconds':round(time.monotonic()-started,3)}
    results.append(result);print(json.dumps(result),flush=True)
after=inputs()
(out/'verification.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'results':results,'before':before,'after':after,'stable':before==after},ensure_ascii=False,indent=2),encoding='utf-8')
(out/'active.json').write_text(json.dumps({'completed':True,'exit_codes':[r['exit_code'] for r in results]}),encoding='utf-8')
sys.exit(0 if before==after and all(r['exit_code']==0 for r in results) else 1)
