import hashlib
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())))
from cn_contract.ops.workspace_backup import restore_workspace_backup
from tests.helpers.legacy_assistant_backup import PASSPHRASE

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUT=Path(__file__).resolve().parent
archive=next((ROOT/'.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx').rglob('tasks.qxbak'))
before=hashlib.sha256(archive.read_bytes()).hexdigest()
base=ROOT/'.local/wp2-matrix01'
assert not base.exists()
rows=[]
for length in (10,50,100,130,160):
    parent=base/('x'*length)
    for attempt in range(3):
        started=time.monotonic()
        try:
            value=restore_workspace_backup(archive,parent,PASSPHRASE)
            row={'status':'PASS','published':Path(value['restored_root']).name}
        except Exception as error:
            row={'status':'FAIL','error_type':type(error).__name__,'winerror':getattr(error,'winerror',None),'error':str(error)}
        row.update(parent_length=len(str(parent)),component_length=length,attempt=attempt,seconds=round(time.monotonic()-started,3))
        rows.append(row)
        print(json.dumps(row,ensure_ascii=True),flush=True)
        (OUT/'path-matrix.json').write_text(json.dumps({'runs':rows,'archive_unchanged':hashlib.sha256(archive.read_bytes()).hexdigest()==before},ensure_ascii=False,indent=2),encoding='utf-8')
