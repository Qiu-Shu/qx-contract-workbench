from pathlib import Path
import sys,subprocess,time,hashlib,json
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[2];out=Path(__file__).resolve().parent
stage=sys.argv[1];argv=sys.argv[2:];start=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
with (out/(stage+'.txt')).open('wb') as stream:
 p=subprocess.Popen(argv,cwd=root,stdout=stream,stderr=subprocess.STDOUT);code=p.wait()
raw=(out/(stage+'.txt')).read_bytes()
record={'stage':stage,'argv':argv,'started_utc':start,'finished_utc':datetime.now(timezone.utc).isoformat(),'seconds':round(time.monotonic()-clock,3),'exit_code':code,'output_sha256':hashlib.sha256(raw).hexdigest()}
(out/(stage+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(record,ensure_ascii=False));print(raw[-4500:].decode('utf8',errors='replace'));raise SystemExit(code)
