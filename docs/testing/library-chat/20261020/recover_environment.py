"""Rerun only failed full-run nodes on a fresh, ample-space synthetic temp drive."""
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

root=Path.cwd(); out=root/'.local/library-chat-20261020'
full=json.loads((out/'full-verification.json').read_text(encoding='utf-8'))
assert full['inputs_equal'] and full['results'][0]['exit_code']==1
def same():
    return all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in full['inputs_after'].items())
assert same()
nodes=[]
for case in ET.parse(out/'full.xml').getroot().iter('testcase'):
    failure=case.find('failure')
    if failure is None: continue
    assert 'LIBRARY_DISK_BUDGET' in (failure.text or '') or case.get('name') == 'test_bulk_laws_committed_batch_survives_resource_stop'
    node=case.get('classname').replace('.','/')+'.py::'+case.get('name')
    assert node.startswith('tests/unit/test_library_')
    nodes.append(node)
assert len(nodes)==38 and len(set(nodes))==38
temp=(out/('pytest-recovery-'+uuid4().hex)).resolve()
assert not temp.exists() and temp.is_relative_to(root.resolve())
command=[sys.executable,'-X','utf8','-m','pytest',*nodes,'--basetemp='+str(temp),'-q','--tb=short','--junitxml='+str(out/'environment-recovery.xml')]
env={**os.environ,'QX_PILOT_PYTHON':full['environment']['QX_PILOT_PYTHON'],'PYTHONPATH':str(root/'src'),'PYTHONUTF8':'1'}
started=datetime.now(timezone.utc).isoformat(); clock=time.monotonic()
with (out/'environment-recovery.log').open('w',encoding='utf-8') as log:
    p=subprocess.Popen(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
    (out/'active.json').write_text(json.dumps({'pid':p.pid,'mode':'environment_recovery','started_utc':started,'log':str(out/'environment-recovery.log')}),encoding='utf-8')
    code=p.wait()
counts={k:sum(int(s.get(k,0)) for s in ET.parse(out/'environment-recovery.xml').getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
result={'started_utc':started,'command':command,'exit_code':code,'seconds':round(time.monotonic()-clock,3),'counts':counts,'failed_full_nodes':nodes,'inputs_equal_to_full':same(),'input_count':full['input_count'],'full_passed':3233,'distinct_cases_covered':3271,'scope':'Same source/test/script bytes, original 38 disk-budget failures only; D: unique temp directory. Two batches, not a single green full run.'}
(out/'recovery-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'active.json').write_text(json.dumps({'completed':True,'mode':'environment_recovery','exit_code':code}),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('command','failed_full_nodes')},ensure_ascii=False))
sys.exit(0 if code==0 and result['inputs_equal_to_full'] and counts=={'tests':38,'failures':0,'errors':0,'skipped':0} else 1)
