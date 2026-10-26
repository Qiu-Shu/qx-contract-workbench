import gc
from file_processes import users
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())))
from cn_contract.ops.workspace_backup import restore_workspace_backup
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from scripts.restore_handles import _absolute,own_process_handles

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUT=Path(__file__).resolve().parent
archive=next((ROOT/'.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx').rglob('tasks.qxbak'))
before=hashlib.sha256(archive.read_bytes()).hexdigest()
parent=ROOT/'.local/wp2-native01'/('x'*130)
assert not parent.exists()
original=os.rename
observations=[]
def rename(source,target,*args,**kwargs):
    try:return original(source,target,*args,**kwargs)
    except PermissionError as error:
        root=_absolute(source)
        if root.name=='workspace' and root.parent.parent==parent:
            value={'winerror':error.winerror,'path_length':len(str(root)),'handles':None}
            try:value['handles']=own_process_handles(root)
            except Exception as scan_error:value['scan_error']=type(scan_error).__name__
            value['sqlite_cursors']=[]
            for item in gc.get_objects():
                if isinstance(item,sqlite3.Cursor):
                    try:state={'connection_open':True,'in_transaction':item.connection.in_transaction}
                    except sqlite3.ProgrammingError:state={'connection_open':False}
                    value['sqlite_cursors'].append(state)
            value['file_processes']={str(p.relative_to(root)):users(p) for p in [root,*root.rglob('*')]}
            observations.append(value)
        raise
rows=[]
os.rename=rename
try:
    for index in range(60):
        started=time.monotonic()
        try:
            value=restore_workspace_backup(archive,parent,PASSPHRASE)
            row={'status':'PASS','published':Path(value['restored_root']).name}
        except Exception as error:
            row={'status':'FAIL','error_type':type(error).__name__,'winerror':getattr(error,'winerror',None),'error':str(error)}
        row.update(index=index,seconds=round(time.monotonic()-started,3))
        rows.append(row)
        (OUT/'native-probe.json').write_text(json.dumps({'runs':rows,'observations':observations,'archive_unchanged':hashlib.sha256(archive.read_bytes()).hexdigest()==before},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(row,ensure_ascii=True),flush=True)
        if row['status']=='FAIL':
            print(json.dumps(observations,ensure_ascii=True),flush=True);break
finally:os.rename=original
