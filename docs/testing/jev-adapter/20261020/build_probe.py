import hashlib,json,os,subprocess,sys,time
from pathlib import Path
root=Path.cwd();out=root/'.local/jev-adapter-20261020';py=root/'.venv/Scripts/python.exe'
keys=['src/cn_contract/__init__.py','src/cn_contract/domain.py','src/cn_contract/config.py','src/cn_contract/assistant/__init__.py','src/cn_contract/assistant/providers/__init__.py','src/cn_contract/assistant/providers/jev.py','src/cn_contract/assistant/providers/jev_codec.py','src/cn_contract/assistant/routing.py','tests/helpers/synthetic_jev_entry.py','pyproject.toml','requirements.lock']
def snapshot():return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in keys}
before=snapshot();(out/'probe-build-input-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
command=[str(py),'-X','utf8','-m','PyInstaller','--noconfirm','--onedir','--name','jev-probe','--distpath',str(out/'frozen-probe'),'--workpath',str(out/'build-probe'),'--specpath',str(out),'--paths',str(root/'src'),'--exclude-module','pytest',str(root/'tests/helpers/synthetic_jev_entry.py')]
(out/'probe-build-command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
start=time.monotonic()
with (out/'probe-build.log').open('wb') as log:
    result=subprocess.run(command,cwd=root,env={**os.environ,'PYTHONPATH':str(root/'.local/desktop-tools/python-build')},stdout=log,stderr=subprocess.STDOUT)
after=snapshot();(out/'probe-build-input-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8');(out/'probe-build.exit').write_text(str(result.returncode)+'\n')
exe=out/'frozen-probe/jev-probe/jev-probe.exe'
summary={'exit_code':result.returncode,'seconds':round(time.monotonic()-start,2),'input_files':len(before),'inputs_unchanged':before==after,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest() if exe.exists() else None,'kind':'standalone_synthetic_jev_probe','not_production_installer':True}
(out/'probe-build-report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary));sys.exit(0 if result.returncode==0 and before==after else 1)
