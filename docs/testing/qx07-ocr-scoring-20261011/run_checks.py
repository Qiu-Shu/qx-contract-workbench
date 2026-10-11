from pathlib import Path
import subprocess,sys,json,time,hashlib,xml.etree.ElementTree as ET
out=Path('docs/testing/qx07-ocr-scoring-20261011')
commands=[['scripts/verify_sources.py'],['scripts/verify_defaults.py'],['src/cn_contract/mcp/bound_entry.py','--check'],['-m','compileall','-q','src/cn_contract/acceptance/ocr_scoring.py','scripts/ocr_synthetic_acceptance.py']]
rows=[]
for n,args in enumerate(commands,1):
 command=[sys.executable,'-X','utf8',*args]; start=time.monotonic();result=subprocess.run(command,capture_output=True)
 log=out/f'check-{n}.log';log.write_bytes(result.stdout+result.stderr)
 rows.append(dict(command=command,exit_code=result.returncode,seconds=round(time.monotonic()-start,3),log=log.name,sha256=hashlib.sha256(log.read_bytes()).hexdigest()))
 print(json.dumps(rows[-1],ensure_ascii=False))
(out/'checks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert all(r['exit_code']==0 for r in rows)
stages=[]
for p in sorted(out.glob('*.xml')):
 if p.name=='full.xml':continue
 suites=[n.attrib for n in ET.parse(p).getroot().iter('testsuite')]
 stages.append(dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),junit=suites))
(out/'stage-evidence.json').write_text(json.dumps(stages,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
