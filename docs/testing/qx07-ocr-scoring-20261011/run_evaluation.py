from pathlib import Path
from datetime import datetime,timezone
import subprocess,sys,time,json,hashlib
out=Path('docs/testing/qx07-ocr-scoring-20261011')
(out/'.gitattributes').write_bytes(b'* -text\n')
command=[sys.executable,'-X','utf8','-u','.audit-local/qx07_evaluate.py']
start=time.monotonic();started=datetime.now(timezone.utc).isoformat()
with (out/'evaluation.log').open('wb') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
receipt=dict(command=command,cwd=str(Path.cwd()),started_utc=started,exit_code=result.returncode,elapsed_seconds=round(time.monotonic()-start,3),log_sha256=hashlib.sha256((out/'evaluation.log').read_bytes()).hexdigest())
(out/'evaluation-execution.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
sys.exit(result.returncode)
