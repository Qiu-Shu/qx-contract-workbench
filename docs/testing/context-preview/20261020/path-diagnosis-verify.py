import hashlib,json,subprocess,sys
from pathlib import Path
r=Path.cwd(); f=r/'.local/library-context-20261020'; p=f/'path-diagnosis-single.json'
v=json.loads(p.read_text('utf-8'))
assert v['runs'][0]['state']=='completed' and v['runs'][0]['coverage']==18 and v['runs'][0]['facts']==3
assert v['runs'][1]['winerror']==206 and v['runs'][1]['stage']=='ingest'
assert v['inputs_unchanged']
v['command']='.venv/Scripts/python.exe -X utf8 .local/library-context-20261020/path-diagnosis-single.py'
v['process_exit_code']=0
v['baseline_match']={x:hashlib.sha256(subprocess.check_output(['git','show','0d53fdf:'+x])).hexdigest()==v['inputs_after'][x] for x in v['inputs_after'] if x!='src/cn_contract/domain.py'}
v['deep_failure_path_chars']=len(v['runs'][1]['filename'])
p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'short':v['runs'][0]['state'],'deep_winerror':v['runs'][1]['winerror'],'deep_path_chars':v['deep_failure_path_chars'],'baseline_match':v['baseline_match']},ensure_ascii=False))
