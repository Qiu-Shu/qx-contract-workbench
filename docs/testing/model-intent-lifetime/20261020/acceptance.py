from pathlib import Path
import json, subprocess, sys, time
root=Path.cwd();out=root/'.local/model-intent-lifetime-20261020';mode=sys.argv[1]
command=[str(root/'.venv/Scripts/python.exe'),'-X','utf8','desktop/tests/model-approval-acceptance.py',str(out/('native-'+mode))]
if mode=='frozen':command.append(str(out/'frozen-backend/qx-backend/qx-backend.exe'))
(out/(mode+'-command.json')).write_text(json.dumps(command,ensure_ascii=False,indent=2),encoding='utf-8')
start=time.monotonic()
with (out/(mode+'-acceptance.log')).open('wb') as log:r=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
(out/(mode+'-acceptance.exit')).write_text(str(r.returncode)+'\n')
print(json.dumps({'mode':mode,'exit_code':r.returncode,'seconds':round(time.monotonic()-start,2)}));sys.exit(r.returncode)
