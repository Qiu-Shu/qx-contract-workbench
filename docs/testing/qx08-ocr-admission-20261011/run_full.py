from pathlib import Path
from datetime import datetime,timezone
import sys,json,subprocess,hashlib,time,xml.etree.ElementTree as ET
ROOT=Path.cwd();sys.path.insert(0,str(ROOT/'src'))
from cn_contract.mcp.bound_entry import build_binding_snapshot
binding=build_binding_snapshot(ROOT)
(ROOT/'plugins/qx-contract-offline-codex/runtime-binding.json').write_text(json.dumps(binding,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
local=ROOT/'plugins/qx-contract-offline-local/runtime-binding.json'
data=json.loads(local.read_text(encoding='utf-8'));data['repository_file_hashes']=binding['repository_file_hashes'];data['utc_generated']=datetime.now(timezone.utc).isoformat()
local.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
out=ROOT/'docs/testing/qx08-ocr-admission-20261011';out.mkdir(parents=True,exist_ok=True)
(out/'.gitattributes').write_bytes(b'* -text\n')
def snapshot():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for top in ['src','tests','plugins','schemas','scripts'] for p in (ROOT/top).rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    for p in [ROOT/'pytest.ini', ROOT/'pyproject.toml', *ROOT.glob('requirements*.lock'),
              * (ROOT/'sources').glob('*.lock.json')]:
        if p.is_file():files[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    return files
before=snapshot()
collect=[sys.executable,'-X','utf8','-m','pytest','--collect-only','-q']
collection=subprocess.run(collect,capture_output=True,text=True,encoding='utf-8')
assert collection.returncode==0,collection.stderr
nodes=[line for line in collection.stdout.splitlines() if line.startswith('tests/') and '::' in line]
assert len(nodes)==len(set(nodes))
(out/'collection.json').write_text(json.dumps(nodes,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
command=[sys.executable,'-X','utf8','-u','-m','pytest','-q','--tb=short','--junitxml='+str(out/'full.xml')]
started=datetime.now(timezone.utc).isoformat();start=time.monotonic()
print(json.dumps(dict(collected=len(nodes),build_id=binding['build_id'],files=len(binding['repository_file_hashes'])),ensure_ascii=False),flush=True)
with (out/'full.log').open('wb') as log:result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
after=snapshot()
receipt=dict(command=command,started_utc=started,exit_code=result.returncode,elapsed_seconds=round(time.monotonic()-start,3),before=before,
    changed_during_run=[p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)],
    log_sha256=hashlib.sha256((out/'full.log').read_bytes()).hexdigest())
if (out/'full.xml').exists():
    tree=ET.parse(out/'full.xml');receipt['junit']=[s.attrib for s in tree.getroot().iter('testsuite')]
    def key(n):
        parts=n.split('::');return (parts[0][:-3].replace('/','.')+''.join('.'+p for p in parts[1:-1]),parts[-1])
    actual=[(r.attrib.get('classname'),r.attrib.get('name')) for r in tree.findall('.//testcase')]
    receipt['collection_matches_junit']=sorted(actual)==sorted(key(n) for n in nodes)
(out/'full-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='before'},ensure_ascii=False),flush=True)
sys.exit(result.returncode)
