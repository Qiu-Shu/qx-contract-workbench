import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())))
from cn_contract.ops.workspace_backup import restore_workspace_backup
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from scripts.restore_publish_diagnostics import observe_restore

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUT=Path(__file__).resolve().parent
archive=next((ROOT/'.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx').rglob('tasks.qxbak'))
before=hashlib.sha256(archive.read_bytes()).hexdigest()
parent=ROOT/'.local/wp2-observe01'/('x'*130)
assert not parent.exists()
rows=[]
for index in range(40):
    started=time.monotonic();events=[]
    try:
        with observe_restore(parent,events):
            value=restore_workspace_backup(archive,parent,PASSPHRASE)
        row={'status':'PASS','published':Path(value['restored_root']).name}
    except Exception as error:
        row={'status':'FAIL','error_type':type(error).__name__,'winerror':getattr(error,'winerror',None),'error':str(error)}
    row.update(index=index,seconds=round(time.monotonic()-started,3),events=events)
    rows.append(row)
    (OUT/'observed.json').write_text(json.dumps({'runs':rows,'archive_unchanged':hashlib.sha256(archive.read_bytes()).hexdigest()==before},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in row.items() if k!='events'},ensure_ascii=True),flush=True)
    if row['status']=='FAIL':
        print(json.dumps(events,ensure_ascii=True),flush=True);break
