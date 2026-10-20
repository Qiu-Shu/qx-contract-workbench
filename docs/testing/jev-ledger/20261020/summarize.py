import collections,json,xml.etree.ElementTree as ET
from pathlib import Path
root=Path.cwd();out=root/'.local/jev-ledger-20261020'
def read(name):return json.loads((out/name).read_text('utf-8-sig'))
tree=ET.parse(out/'python-final.xml');cases=tree.findall('.//testcase')
nodes=[(c.attrib['classname'],c.attrib['name']) for c in cases]
assert len(nodes)==len(set(nodes))==703
summary={'phase':'CH-05B independent Jev ledger backend','baseline':'a4c3c6706caad31c2335b4d055240dbddbfbd372',
 'verification':read('verification.json'),'unique_python_tests':len(nodes),
 'python_groups':dict(sorted(collections.Counter(k[0] for k in nodes).items())),
 'warnings':['Existing test_jev_provider record_property fixture is incompatible with the selected xunit2 reporting mode; one pytest reporting warning, no test failure.',
 'Frozen build retains optional hidden-import warnings for tzdata, pysqlite2, MySQLdb, psycopg2; tested SQLite/UTC paths passed.'],
 'independent_spec':{'tests':10,'exit_code':0,'open_findings':0},
 'independent_standards':{'before_last_fix_tests':3,'targeted_after_last_fix_tests':1,'exit_code':0,'open_findings':0},
 'windows_source':read('source-backend-report.json'),'windows_frozen':read('frozen-backend-report.json'),
 'build':read('build-report.json'),
 'workbuddy':{'observation':'Summarized status tool result at beginning of this turn, not a historical receipt','connected':False,'reason':'Dedicated native chat is busy or its state is unknown: busy','delegated':False},
 'boundaries':['No second queue; referenced original assistant_runs and left main run fields unchanged.',
 'Callable trusted backend only; native Jev configuration, independent UI approval and optional main-runner phase remain pending.',
 'Only current full plain text primary_intent mapped; explicit skill skips, other purposes and attachments remain rejected.',
 'Reserved USD is policy accounting, not a vendor price or paid invoice; unknown stays occupied.',
 'No external reconciliation after restart; immutable same-call receipts and conservative recovery only.',
 'Host Python performed synthetic loopback seed; real child backends tested recovery/backup/restore, not Jev native UI execution.',
 'Installed app 0.4.1, real materials, F drive corpus, real accounts, cloud and GitHub remained unchanged.']}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'unique_tests':len(nodes),'test_files':len(summary['python_groups'])}))
