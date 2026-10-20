import hashlib,json,subprocess,sys,time,uuid
from pathlib import Path
root=Path.cwd(); out=root/'.local/long-path-20261020'
inputs=['src/cn_contract/persistence.py','src/cn_contract/ops/file_paths.py','tests/unit/test_contract_long_paths.py','tests/integration/test_contract_long_path_backup.py','tests/unit/test_versions.py','docs/plans/2026-10-20-contract-long-path.md','.local/long-path-20261020/spec-path-probes.py']
def hashes():return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in inputs}
before=hashes(); temporary=root/'.local'/('lps-'+uuid.uuid4().hex[:8])
command=[sys.executable,'-m','pytest',str(out/'spec-path-probes.py'),'-q','--basetemp',str(temporary),'--junitxml',str(out/'spec-path-probes.xml')]
started=time.monotonic()
with (out/'spec-path-probes.log').open('w',encoding='utf-8') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,cwd=root)
after=hashes()
record={'fixed_point':'7446a9ce47d9452568f7d2ea1cf53c92167d53f4','command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-started,'inputs_before':before,'inputs_after':after,'inputs_unchanged':before==after}
(out/'spec-path-probes.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:record[k] for k in ('command','exit_code','elapsed_seconds','inputs_unchanged')},ensure_ascii=False))
print((out/'spec-path-probes.log').read_text('utf-8'))
sys.exit(result.returncode)
