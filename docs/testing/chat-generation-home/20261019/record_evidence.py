import hashlib,json,shutil,subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

raw=Path(__file__).resolve().parent
root=raw.parents[1]
dest=root/'docs/testing/chat-generation-home/20261019'
dest.mkdir(parents=True,exist_ok=True)
def load(path):return json.loads(path.read_text('utf-8-sig'))
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

checks=load(raw/'verified-checks/final-checks.json')
assert checks['source_unchanged'] and all(v['exit']==0 for v in checks['results'].values())
source=load(raw/'verified-checks/final-source-after.json')
assert all(sha(root/name)==digest for name,digest in source.items())
xml=ET.parse(raw/'verified-checks/final-targeted.xml').getroot()
cases=xml.findall('.//testcase')
identities={(v.attrib['classname'],v.attrib['name']) for v in cases}
assert len(cases)==len(identities)==223
assert not xml.findall('.//failure') and not xml.findall('.//error') and not xml.findall('.//skipped')
suite=xml.find('testsuite')
browser=load(raw/'browser-verified/browser-report.json')
assert browser['exit_code']==0 and len(browser['checks'])==11 and browser['upstream_posts']==6 and browser['source_unchanged']
assert all(sha(root/name)==digest for name,digest in browser['source_after'].items())
desktop=load(raw/'desktop-final-summary.json')
assert desktop['status']=='passed' and desktop['build_inputs_unchanged'] and not desktop['desktop_source_mismatch']
for folder in ('electron-default-verified','electron-synthetic-verified'):
    report=load(raw/folder/'report.json')
    assert report['exit_code']==0 and report['source_unchanged']
    assert all(sha(root/name)==digest for name,digest in report['source_after'].items())
recovery=load(raw/'review-read-recovery/report.json')
assert recovery['exit_code']==0 and len(recovery['checks'])==3
wb=load(raw/'workbuddy-review-completed.json')
receipt=json.loads(wb['content'][0]['text'])
assert receipt['state']=='completed' and receipt['stop_reason']=='end_turn'
assert len(receipt['tool_events'])==3 and all(v['tool']=='Read' and v['status']=='completed' for v in receipt['tool_events'])

# No databases, credentials, raw workspaces, dependency caches or binary builds.
extensions={'.json','.xml','.log','.exit','.txt','.md','.py','.mjs','.cjs','.ps1'}
for path in sorted(raw.iterdir()):
    if path.is_file() and path.suffix in extensions:
        shutil.copyfile(path,dest/path.name)
folders={
    'verified-checks':None,
    'browser-first':{'browser-report.json'},'browser-final':{'browser-report.json'},'browser-verified':{'browser-report.json'},
    'read-recovery-red':{'report.json'},'read-recovery-green':{'report.json'},'read-recovery-final':{'report.json'},
    'review-read-recovery':{'report.json'},
    'visual-first':{'report.json','desktop-empty.png','desktop-result.png','desktop-long.png','narrow-top.png','narrow-bottom.png','large-font-bottom.png'},
    'visual-confirm':{'report.json','retry-visible.png'},
    'electron-default-initial':{'report.json'},'electron-synthetic-initial':{'report.json'},
    'electron-default-second':{'report.json'},'electron-synthetic-second':{'report.json'},
    'electron-default-verified':{'report.json','electron-home.png','electron-stderr.txt','electron-stdout.txt'},
    'electron-synthetic-verified':{'report.json','electron-home.png','electron-candidate-visible.png','electron-stderr.txt','electron-stdout.txt'},
}
for folder,names in folders.items():
    for path in (raw/folder).iterdir():
        if path.is_file() and (names is None or path.name in names):
            (dest/folder).mkdir(exist_ok=True)
            shutil.copyfile(path,dest/folder/path.name)

tracked=['src/cn_contract/web/app.py','src/cn_contract/web/assistant_generation.py',
    'src/cn_contract/web/static/assistant.mjs','src/cn_contract/web/static/assistant-state.mjs',
    'src/cn_contract/web/static/assistant-generation.mjs','src/cn_contract/assistant/providers/history.py']
metrics={}
for name in tracked:
    prior=subprocess.run(['git','show','f218f44:'+name],cwd=root,capture_output=True)
    metrics[name]={'baseline_lines':len(prior.stdout.splitlines()) if prior.returncode==0 else 0,
        'current_lines':len((root/name).read_bytes().splitlines()),'current_bytes':(root/name).stat().st_size}
save(dest/'module-metrics.json',metrics)
save(dest/'summary.json',{
    'baseline':'f218f44','slice':'CH-04C','status':'engineering_slice_verified_not_production',
    'targeted_pytest':{'distinct_tests':223,'passed':223,'failed':0,'errors':0,'skipped':0,'exit_code':0,
        'junit_seconds':float(suite.attrib['time']),'source_files':len(source),'sources_unchanged':True,
        'includes_frontend_wrappers':7,'includes_new_history_tests':25},
    'new_frontend_groups':{'generation_state':27,'render':12,'independent_entry':7,'transport_total':5,
        'counting':'These run inside frontend wrappers; do not add to the 223 pytest count.'},
    'browser':{'final_groups':11,'loopback_posts':6,'external_requests':0,'page_errors':0,'csp_violations':0,
        'independent_first_read_recovery_checks':3,'visual_keyboard_groups':4,'screens_initial':6,'screens_confirmation':1},
    'desktop':desktop,'development_gates':checks['results'],
    'review':{'closed_p2_issues':2,'closed_regression_extra_read':1,'unresolved_in_review_scope':0,
        'workbuddy_task':receipt['task_id'],'workbuddy_reads':3,'workbuddy_runtime_testing':False},
    'limits':['No full Python suite this slice','No real provider calls','No installer or installed app changes',
        'Synthetic composition events are not physical IME acceptance','No physical Windows DPI validation',
        'Model settings, skills, attachments in generation, Jev and automatic profiles remain follow-up work',
        'No Git push or cloud deployment'],
})
print(json.dumps({'archived_to':str(dest),'pytest':223,'junit_seconds':suite.attrib['time'],'source_files':len(source)},ensure_ascii=False))
