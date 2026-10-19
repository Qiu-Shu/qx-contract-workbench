from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[3]
out=Path(__file__).resolve().parent
products=['src/cn_contract/domain.py','src/cn_contract/assistant/routing.py',
          'src/cn_contract/assistant/providers/main.py','src/cn_contract/assistant/providers/jev.py',
          'src/cn_contract/assistant/providers/jev_codec.py']
def snapshot():return {p:sha256((root/p).read_bytes()).hexdigest() for p in products}
before=snapshot()
args=[sys.executable,'-m','pytest',*[str(out/name) for name in
      ['probe_contract.py','probe_codec.py','probe_transport.py','probe_logging.py']],'-q',
      '--junitxml='+str(out/'final.xml')]
environment={**os.environ,'PYTHONPATH':'src;.'}
result=subprocess.run(args,cwd=root,env=environment,capture_output=True,text=True,encoding='utf-8')
(out/'final.log').write_text(result.stdout+result.stderr,encoding='utf-8')
after=snapshot()
document=ET.parse(out/'final.xml')
cases=document.findall('.//testcase')
failures=[c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
report={'baseline':'7dd5abb','review_axis':'Spec','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
        'command':args,'environment':{'PYTHONPATH':'src;.'},'exit_code':result.returncode,
        'passed':len(cases)-len(failures),'failed':len(failures),'failure_names':failures,
        'product_sha256_before':before,'product_sha256_after':after,'product_unchanged':before==after,
        'cases':[c.attrib['name'] for c in cases],
        'closed_findings':['fixed question/result deadline invariants','RouteDecision source/workflow/reason invariants',
                           'JSON response media type','alternating main/auxiliary logging wrapper growth'],
        'clarifications':['model means verified received supplier model, not requested config model'],
        'remaining_findings':[],
        'limitations':['Synthetic local-loopback/offline only; no TypeSafe connection, actual credential, legal-quality or persistent integration claim.',
                       'Synchronous Python work can exceed wall-clock deadline; overdue answer is rejected, not hard real-time scheduling.',
                       'Caller must retain full request and validate current scope, distinct egress permission, budget and durable claim before allowing preflight.']}
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(result.stdout+result.stderr)
print(json.dumps({'passed':report['passed'],'failed':report['failed'],'exit_code':result.returncode,
                  'product_unchanged':before==after}))
sys.exit(result.returncode if result.returncode else 0 if before==after else 2)
