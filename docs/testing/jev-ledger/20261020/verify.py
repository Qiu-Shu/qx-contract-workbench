import concurrent.futures, hashlib, json, os, re, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path.cwd(); OUT=ROOT/'.local/jev-ledger-20261020'; PY=str(ROOT/'.venv/Scripts/python.exe')

def snapshot():
    result=subprocess.run(['git','ls-files','-z','-co','--exclude-standard','--','src','desktop','tests','scripts','config','schemas','pyproject.toml','requirements.lock'],capture_output=True,check=True)
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sorted(set(result.stdout.decode('utf-8').split('\0'))-{''}) if (ROOT/n).is_file()}

tests = sorted({str(p.relative_to(ROOT)).replace('\\','/') for pattern in (
    'tests/integration/test_judge*.py', 'tests/unit/test_judge*.py',
    'tests/integration/test_assistant_judge*.py', 'tests/integration/test_assistant_model*.py'
) for p in ROOT.glob(pattern)} | set([
    'tests/integration/test_jev_provider.py', 'tests/unit/test_jev_contract_routing.py', 'tests/unit/test_jev_codec.py', 'tests/unit/test_domain.py',
    'tests/integration/test_assistant_attachment_backup.py', 'tests/integration/test_assistant_backup.py',
    'tests/integration/test_workspace_upgrade.py', 'tests/integration/test_storage_schema_versions.py',
    'tests/integration/test_assistant_storage.py', 'tests/integration/test_assistant_generation.py',
    'tests/integration/test_desktop_runtime.py', 'tests/integration/test_backup_restore.py',
    'tests/integration/test_workspace_backup.py', 'tests/integration/test_local_workbench.py',
    'tests/unit/test_model_schema.py'
]))
assert all((ROOT/p).exists() for p in tests), [p for p in tests if not (ROOT/p).exists()]
commands={
    'python-final':[PY,'-X','utf8','-m','pytest','-q',*tests,'--junitxml='+str(OUT/'python-final.xml')],
    'defaults':[PY,'-X','utf8','scripts/verify_defaults.py'],
    'sources':[PY,'-X','utf8','scripts/verify_sources.py','--mode','development'],
    'dependencies':[PY,'-X','utf8','scripts/verify_runtime_dependencies.py','--mode','development'],
    'schema':[PY,'-X','utf8','-m','cn_contract.cli','schema','--check']}

def run(item):
    name,command=item;start=time.monotonic()
    result=subprocess.run(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/(name+'.log')).write_bytes(result.stdout)
    (OUT/(name+'.exit')).write_text(str(result.returncode)+'\n')
    (OUT/(name+'-command.json')).write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
    info={'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3)}
    if name=='python-final' and (OUT/'python-final.xml').exists():
        suites=ET.parse(OUT/'python-final.xml').getroot().findall('testsuite')
        for field in ['tests','failures','errors','skipped']:info[field]=sum(int(s.attrib[field]) for s in suites)
    return name,info

before=snapshot(); (OUT/'verification-input-before.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=dict(pool.map(run,commands.items()))
after=snapshot(); (OUT/'verification-input-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
summary={'commands':results,'input_files':len(before),'changed_inputs':[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)]}
(OUT/'verification.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary));sys.exit(1 if summary['changed_inputs'] or any(v['exit_code'] for v in results.values()) else 0)


