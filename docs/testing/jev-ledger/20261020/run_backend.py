import hashlib,json,subprocess,sys,time
from pathlib import Path
root=Path.cwd();out=root/'.local/jev-ledger-20261020';mode=sys.argv[1]
keys=json.loads((out/'verification-input-before.json').read_text('utf-8'))
def snapshot():return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in keys}
before=snapshot(); start=time.monotonic()
command=[str(root/'.venv/Scripts/python.exe'),'-X','utf8',str(out/'backend_probe.py'),mode]
with (out/(mode+'-backend.log')).open('wb') as log:
 result=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
after=snapshot(); (out/(mode+'-backend.exit')).write_text(str(result.returncode)+'\n')
report={'command':command,'exit_code':result.returncode,'seconds':round(time.monotonic()-start,3),
 'input_files':len(before),'unchanged':before==after,'matches_final_verification':before==keys,
 'changed_inputs':[p for p in before if before[p]!=after[p]]}
(out/(mode+'-execution.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report)); sys.exit(0 if result.returncode==0 and before==after==keys else 1)
