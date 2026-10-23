"""Recheck only the legacy format assertion; keep the first full result intact."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import sys
import time
from uuid import uuid4
import xml.etree.ElementTree as ET

out=Path('.local/profile-execution-20261023')
first=json.loads((out/'target-verification.json').read_text('utf-8'))
file='tests/unit/test_assistant_profile_preparation.py'
before={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in first['inputs_after']}
assert [p for p,h in first['inputs_after'].items() if before[p] != h] == [file]
assert first['inputs_equal'] and first['results'][0]['counts']['failures'] == 1
assert all(item['exit_code']==0 for item in first['results'][1:])
failed=[x for x in ET.parse(out/'target.xml').getroot().iter('testcase') if x.find('failure') is not None]
assert len(failed)==1 and failed[0].get('name')=='test_basis_cannot_be_used_as_existing_registry_permission_or_ledger_format'
assert 'Regex pattern did not match' in failed[0].find('failure').get('message','')
command=[sys.executable,'-X','utf8','-m','pytest','-q','--tb=short',file,
         '--basetemp='+str(out/('supplement-'+uuid4().hex[:8])), '--junitxml='+str(out/'supplement.xml')]
start=datetime.now(timezone.utc).isoformat(); clock=time.monotonic()
with (out/'supplement.log').open('w',encoding='utf-8') as log:
    code=subprocess.run(command,env={**os.environ,'PYTHONPATH':str(Path.cwd()/'src'),'PYTHONUTF8':'1'},stdout=log,stderr=subprocess.STDOUT).returncode
after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
counts={k:sum(int(s.get(k,0)) for s in ET.parse(out/'supplement.xml').getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
report={'command':command,'started_utc':start,'seconds':round(time.monotonic()-clock,3),'exit_code':code,
        'counts':counts,'inputs_before':before,'inputs_after':after,'inputs_equal':before==after,
        'changed_from_initial_run':[file],'product_inputs_unchanged':True,
        'reason':'Old closed-format assertion expected a guard error; empty profile input still fails strict DTO validation. Only this test assertion changed.',
        'original_failed_test':failed[0].get('name')}
(out/'supplement-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(out/'accepted-inputs.json').write_text(json.dumps(after,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ('exit_code','counts','seconds','inputs_equal','changed_from_initial_run')}))
raise SystemExit(0 if code==0 and before==after else 1)
