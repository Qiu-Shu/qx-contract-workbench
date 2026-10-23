"""Run only independent synthetic probes against hashed frozen product files."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path.cwd()
evidence = root / '.local/profile-application-20261023/standards-review'
baseline = '3d0e1859041572ed9c574e7a917afd044aedc6bf'
products = [
    'src/cn_contract/domain.py', 'src/cn_contract/assistant/native_profile_control.py',
    'src/cn_contract/assistant/native_model_control.py', 'src/cn_contract/desktop_control.py',
    'src/cn_contract/assistant/task_manager.py', 'src/cn_contract/web/assistant_profile_generation.py',
    'src/cn_contract/web/assistant_generation.py',
]


def snapshot():
    paths = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard']).decode().split('\0')
    wanted = {p for p in paths if p and p.startswith(('src/','config/','scripts/'))}
    wanted.update(products)
    wanted.update(('CONTRIBUTING.md','AGENTS.md','docs/plans/2026-10-23-profile-application.md',
        'tests/integration/test_assistant_generation.py',
        'tests/integration/test_assistant_profile_execution.py',
        'tests/integration/test_assistant_generation_routes.py',
        'tests/integration/test_assistant_main_provider.py',
        '.local/profile-application-20261023/standards-review/test_application_standards.py'))
    return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(wanted) if (root/p).is_file()}


started = datetime.now(timezone.utc).isoformat()
before = snapshot()
(evidence/'inputs-before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2),encoding='utf-8')
command = [sys.executable,'-X','utf8','-m','pytest',
    '.local/profile-application-20261023/standards-review/test_application_standards.py',
    '-q','--tb=short','--basetemp='+str(evidence/'temp-final-v2'),
    '--junitxml='+str(evidence/'final.xml')]
environment = dict(os.environ)
environment['PYTHONPATH'] = str(root/'tests/integration')+os.pathsep+environment.get('PYTHONPATH','')
with (evidence/'final.log').open('w',encoding='utf-8') as stream:
    completed = subprocess.run(command,cwd=root,env=environment,stdout=stream,stderr=subprocess.STDOUT)
after = snapshot()
(evidence/'inputs-after.json').write_text(json.dumps(after,ensure_ascii=False,indent=2),encoding='utf-8')
suites = ET.parse(evidence/'final.xml').getroot()
counts = {name:sum(int(suite.get(name,0)) for suite in suites.iter('testsuite'))
          for name in ('tests','failures','errors','skipped')}
result = dict(baseline=baseline,started_at=started,completed_at=datetime.now(timezone.utc).isoformat(),
    command=command,cwd=str(root),exit_code=completed.returncode,counts=counts,
    input_count=len(before),inputs_stable=before==after,
    product_hashes={p:before[p] for p in products},
    changed_inputs=sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)))
(evidence/'run-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(completed.returncode or (0 if before==after else 3))

