import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())))
from cn_contract.ops.workspace_backup import restore_workspace_backup
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from scripts.restore_handles import _absolute

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
OUT=Path(__file__).resolve().parent
archive=next((ROOT/'.local/wp2-repro01xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx').rglob('tasks.qxbak'))
before=hashlib.sha256(archive.read_bytes()).hexdigest()
parent=ROOT/'.local/wp2-immediate01'/('x'*130)
assert not parent.exists()
last=ctypes.WinDLL('ntdll').RtlGetLastNtStatus;last.restype=ctypes.c_long
original=os.rename;events=[]
def rename(source,target,*args,**kwargs):
    try:return original(source,target,*args,**kwargs)
    except PermissionError as error:
        status=last()&0xffffffff;stamp=time.perf_counter_ns()
        root=_absolute(source)
        if root.name!='workspace' or root.parent.parent!=parent:raise
        event={'first_winerror':error.winerror,'last_ntstatus':hex(status),'second_attempt':'NOT_RUN'}
        try:
            # Diagnostic experiment only, not a product retry policy.
            result=original(source,target,*args,**kwargs)
            event['second_attempt']='PASS';return result
        except OSError as second:
            event.update(second_attempt='FAIL',second_winerror=second.winerror);raise
        finally:
            event['elapsed_ns']=time.perf_counter_ns()-stamp;events.append(event)
rows=[];os.rename=rename
try:
    for index in range(80):
        start=time.monotonic()
        try:
            value=restore_workspace_backup(archive,parent,PASSPHRASE)
            row={'index':index,'status':'PASS'}
        except Exception as error:row={'index':index,'status':'FAIL','error':str(error)}
        row['seconds']=round(time.monotonic()-start,3);rows.append(row)
        (OUT/'immediate-probe.json').write_text(json.dumps({'runs':rows,'events':events,'archive_unchanged':hashlib.sha256(archive.read_bytes()).hexdigest()==before},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'run':row,'events':events},ensure_ascii=True),flush=True)
        if len(events)>=3:break
finally:os.rename=original
