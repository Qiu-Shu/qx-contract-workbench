import hashlib,json,os,subprocess,sys,time
from pathlib import Path
root=Path.cwd();out=root/'.local/jev-ledger-20261020';py=root/'.venv/Scripts/python.exe'
keys=sorted(set(json.loads((root/'.local/native-model-control-20261019/build-source-before.json').read_text('utf-8'))) | {p.as_posix() for p in Path('src/cn_contract').rglob('*.py')})
def snapshot():return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in keys}
before=snapshot();(out/'build-source-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
command=[str(py),'-X','utf8','-m','PyInstaller','--noconfirm','--distpath',str(out/'frozen-backend'),'--workpath',str(out/'build-backend'),str(root/'desktop/backend.spec')]
(out/'frozen-build-command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
start=time.monotonic()
with (out/'frozen-build.log').open('wb') as log:
 result=subprocess.run(command,cwd=root,env={**os.environ,'PYTHONPATH':str(root/'.local/desktop-tools/python-build')},stdout=log,stderr=subprocess.STDOUT)
after=snapshot();(out/'build-source-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8');(out/'frozen-build.exit').write_text(str(result.returncode)+'\n')
exe=out/'frozen-backend/qx-backend/qx-backend.exe'
summary={'exit_code':result.returncode,'seconds':round(time.monotonic()-start,2),'input_files':len(before),'inputs_unchanged':before==after,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest() if exe.exists() else None}
(out/'build-report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary));sys.exit(0 if result.returncode==0 and before==after else 1)
