import hashlib
import json
from pathlib import Path
import time
import sys
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())))
from cn_contract.ops.workspace_backup import restore_workspace_backup
from tests.helpers.legacy_assistant_backup import PASSPHRASE

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUT=Path(__file__).resolve().parent
archive=next((ROOT/'.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx').rglob('tasks.qxbak'))
before=hashlib.sha256(archive.read_bytes()).hexdigest()
parent=ROOT/'.local/wp2-stress01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/test_restore_blocks_each_pending_execution_and_all_task_writes/restored'
assert not parent.exists()
rows=[]
for index in range(20):
    started=time.monotonic()
    try:
        value=restore_workspace_backup(archive,parent,PASSPHRASE)
        row={'index':index,'status':'PASS','published':Path(value['restored_root']).name,'seconds':round(time.monotonic()-started,3)}
    except Exception as error:
        row={'index':index,'status':'FAIL','error_type':type(error).__name__,'winerror':getattr(error,'winerror',None),
             'error':str(error),'seconds':round(time.monotonic()-started,3)}
    rows.append(row)
    (OUT/'stress.json').write_text(json.dumps({'runs':rows,'archive_unchanged':hashlib.sha256(archive.read_bytes()).hexdigest()==before},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(row,ensure_ascii=True),flush=True)
    if row['status']=='FAIL':break
