import hashlib, json, subprocess, sys, time, uuid
from pathlib import Path
root=Path.cwd()
folder=root/'.local/library-context-20261020'
(folder/'baseline-domain.py').write_bytes(subprocess.check_output(['git','show','0d53fdf:src/cn_contract/domain.py']))
files=sorted([*root.joinpath('src').rglob('*.py'), *root.joinpath('tests').rglob('*.py'), folder/'test_spec_probes.py', folder/'baseline-domain.py'])
def snapshot():
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
before=snapshot()
base=folder/('spec-temp-'+uuid.uuid4().hex)
command=[sys.executable,'-m','pytest',str(folder/'test_spec_probes.py'),'-q','--basetemp',str(base),'--junitxml',str(folder/'spec-probes.xml')]
started=time.monotonic()
with (folder/'spec-probes.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
after=snapshot()
record={'command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-started,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after,'fixed_point':'0d53fdfdae806c6fec90c01cab1531a7cb666831'}
(folder/'spec-probes.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:record[key] for key in ('command','exit_code','elapsed_seconds','inputs_unchanged')},ensure_ascii=False))
print((folder/'spec-probes.log').read_text('utf-8'))
sys.exit(result.returncode)
