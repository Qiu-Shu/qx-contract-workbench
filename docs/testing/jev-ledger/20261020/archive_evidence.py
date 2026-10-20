"""Archive explicit synthetic evidence only; binaries and workspaces stay local."""
import hashlib,json,shutil
from pathlib import Path
root=Path.cwd();src=root/'.local/jev-ledger-20261020';dst=root/'docs/testing/jev-ledger/20261020'
def read(name):return json.loads((src/name).read_text('utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
verification=read('verification.json');build=read('build-report.json')
assert not verification['changed_inputs'] and all(x['exit_code']==0 for x in verification['commands'].values())
assert build['exit_code']==0 and build['inputs_unchanged']
checked={}
for name in ('verification-input-before.json','build-source-before.json'):
 expected=read(name);mismatches=[p for p,h in expected.items() if not (root/p).is_file() or sha(root/p)!=h]
 checked[name]={'files':len(expected),'mismatches':mismatches};assert not mismatches
for mode in ('source','frozen'):
 run=read(mode+'-execution.json');report=read(mode+'-backend-report.json')
 assert run['exit_code']==0 and run['unchanged'] and run['matches_final_verification']
 assert report['status']=='passed' and len(report['groups'])==5 and report['child_exits']==[0]*5
exe=src/'frozen-backend/qx-backend/qx-backend.exe'
assert sha(exe)==build['exe_sha256']==read('frozen-backend-report.json')['exe_sha256']
checked['exe_sha256']=sha(exe)
(src/'final-input-check.json').write_text(json.dumps(checked,indent=2),encoding='utf-8')
extensions={'.py','.md','.json','.xml','.log','.exit'}
files=[p for p in src.iterdir() if p.is_file() and p.suffix in extensions]
for name in ('author','review-spec-glue','review-standards'):
 # Review evidence is at the top level; nested pytest workspaces stay local.
 files.extend(p for p in (src/name).iterdir() if p.is_file() and p.suffix in extensions)
for p in files:
 target=dst/p.relative_to(src);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
manifest={p.relative_to(dst).as_posix():sha(p) for p in sorted(dst.rglob('*')) if p.is_file() and p.name!='manifest.sha256.json'}
(dst/'manifest.sha256.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(manifest),'bytes':sum(p.stat().st_size for p in dst.rglob('*') if p.is_file()),'verification':verification,'build':build},ensure_ascii=True))
