import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

here=Path(__file__).resolve().parent
root=here.parents[2]
for source,target,exports in [
    ('scripts/test_assistant_profile_generation.mjs','generation-fixture.mjs','opened,calls,mutations,failure'),
    ('scripts/test_assistant_profile_panel.mjs','panel-fixture.mjs','fixture,saved,deferred')]:
    prefix=(root/source).read_text('utf-8').split("test('",1)[0]
    prefix=prefix.replace("'../src/", "'../../../src/")
    (here/target).write_text(prefix+'\nexport {'+exports+'};\n',encoding='utf-8')
files=[
 'src/cn_contract/assistant/providers/attempts.py','src/cn_contract/assistant/providers/profile_history.py',
 'src/cn_contract/domain.py','src/cn_contract/web/app.py','src/cn_contract/web/static/assistant-api.mjs',
 'src/cn_contract/web/static/assistant-generation.mjs','src/cn_contract/web/static/assistant-profile.mjs',
 'src/cn_contract/web/static/assistant-render.mjs','src/cn_contract/web/static/assistant-state.mjs',
 'src/cn_contract/web/static/assistant.mjs','src/cn_contract/web/static/assistant.css','src/cn_contract/web/templates/assistant.html',
 'docs/plans/2026-10-23-profile-ui.md','scripts/test_assistant_profile_generation.mjs','scripts/test_assistant_profile_panel.mjs',
 'tests/integration/test_assistant_profile_history.py','tests/integration/test_assistant_profile_execution.py',
 'tests/integration/test_assistant_profile_model_integrity.py','src/cn_contract/assistant/profile_model_integrity.py',
 'src/cn_contract/assistant/model_integrity.py','src/cn_contract/assistant/profile_store.py',
 *[str(p.relative_to(root)) for p in here.iterdir() if p.suffix in ('.py','.mjs')]]
def hashes(): return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(files)}
def save(name,value): (here/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
before=hashes();save('inputs-before.json',before)
commands=[('node',['node','--test','--test-reporter=spec','--test-reporter-destination=stdout',
 '--test-reporter=junit','--test-reporter-destination='+str(here/'node.xml'),str(here/'spec-ui-probes.mjs')]),
 ('python',[sys.executable,'-m','pytest',str(here/'test_history_spec.py'),'-q','-W','error',
 '--basetemp='+str(here/'合成隔离-01'),'--junitxml='+str(here/'python.xml')])]
save('commands.json',{'cwd':str(root),'commands':commands,'fixture_reuse':'Only pre-test fixture declarations are copied from two existing Node test files; their test cases are not executed.'})
results=[]
env={**os.environ,'PYTHONPATH':str(root/'src')+os.pathsep+str(root)}
for label,command in commands:
    start=time.monotonic();r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,encoding='utf-8')
    (here/(label+'.log')).write_text(r.stdout+r.stderr,encoding='utf-8')
    (here/(label+'-exitcode.txt')).write_text(str(r.returncode),encoding='utf-8')
    cases=ET.parse(here/(label+'.xml')).findall('.//testcase')
    results.append({'name':label,'exit_code':r.returncode,'seconds':round(time.monotonic()-start,3),
       'tests':len(cases),'failures':sum(c.find('failure') is not None for c in cases),
       'errors':sum(c.find('error') is not None for c in cases)})
after=hashes();save('inputs-after.json',after)
report={'results':results,'input_count':len(before),'inputs_stable':before==after,
 'changed':[p for p in before if before[p]!=after[p]],'real_model':False,'actual_windows':False}
save('summary.json',report);print(json.dumps(report,ensure_ascii=False))
raise SystemExit(int(any(r['exit_code'] for r in results) or before!=after))
