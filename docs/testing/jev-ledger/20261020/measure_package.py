"""Measure existing frozen backend bytes only; not Electron/installer/RSS."""
import hashlib,json
from pathlib import Path
root=Path.cwd();out=root/'.local/jev-ledger-20261020'
def measure(folder):
 report=json.loads((folder/'build-report.json').read_text('utf-8'))
 package=folder/'frozen-backend/qx-backend';exe=package/'qx-backend.exe'
 digest=hashlib.sha256(exe.read_bytes()).hexdigest();assert digest==report['exe_sha256']
 sizes={p.relative_to(package).as_posix():p.stat().st_size for p in sorted(package.rglob('*')) if p.is_file()}
 return {'directory':str(package),'exe_sha256':digest,'files':len(sizes),'bytes':sum(sizes.values()),'sizes':sizes}
before=measure(root/'.local/model-intent-lifetime-20261020');after=measure(out)
report={'comparison':'CH-04I frozen backend to CH-05B frozen backend, includes CH-05A and CH-05B',
 'scope':'existing backend directory bytes; not full Electron application, installer, RAM, or comparable cold-start benchmark',
 'before':before,'after':after,'delta_bytes':after['bytes']-before['bytes'],
 'changes':{p:{'before':before['sizes'].get(p),'after':after['sizes'].get(p)} for p in sorted(before['sizes'].keys()|after['sizes'].keys()) if before['sizes'].get(p)!=after['sizes'].get(p)}}
(out/'backend-size-observation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('comparison','scope','delta_bytes')}|{'before_bytes':before['bytes'],'after_bytes':after['bytes'],'before_files':before['files'],'after_files':after['files']}))
