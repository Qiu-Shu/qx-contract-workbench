"""Experimental read-only native query, used only in this isolated diagnostic."""
import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
class Io(c.Structure):_fields_=[('status',c.c_void_p),('information',c.c_size_t)]
class Header(c.Structure):_fields_=[('count',w.ULONG),('first',c.c_size_t)]
k=c.WinDLL('kernel32',use_last_error=True)
k.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE];k.CreateFileW.restype=w.HANDLE
k.CloseHandle.argtypes=[w.HANDLE];k.CloseHandle.restype=w.BOOL
q=c.WinDLL('ntdll').NtQueryInformationFile
q.argtypes=[w.HANDLE,c.POINTER(Io),c.c_void_p,w.ULONG,w.ULONG];q.restype=w.LONG
def users(path):
    path=str(Path(path).absolute())
    if not path.startswith('\\\\?\\'):path='\\\\?\\'+path
    handle=k.CreateFileW(path,0,7,None,3,0x02000000,None)
    if handle==w.HANDLE(-1).value:return {'status':'OPEN_ERROR','winerror':c.get_last_error()}
    try:
        data=c.create_string_buffer(8192);io=Io()
        status=q(handle,c.byref(io),data,len(data),47)
        if status:return {'status':hex(status&0xffffffff)}
        count=w.ULONG.from_buffer(data).value;offset=Header.first.offset
        if not offset<=io.information<=len(data) or offset+count*c.sizeof(c.c_size_t)>io.information:return {'status':'INVALID_LAYOUT'}
        ids=(c.c_size_t*count).from_buffer(data,offset)
        return {'status':'OK','pids':list(ids),'own_pid':os.getpid()}
    finally:k.CloseHandle(handle)
if __name__=='__main__':
    import json,subprocess,sys
    root=Path(__file__).resolve().parent
    path=root/'native-control.txt';path.write_text('synthetic',encoding='utf-8')
    child=subprocess.Popen([sys.executable,'-u','-c',"import os,sys; f=open(sys.argv[1],'rb'); print(os.getpid(),flush=True); input(); f.close()",str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        pid=int(child.stdout.readline().strip());held=users(path)
        assert held['status']=='OK' and pid in held['pids'],held
    finally:child.communicate('\n',timeout=10)
    released=users(path);assert released['status']=='OK' and pid not in released['pids'],released
    record={'held':held,'released':released,'status':'PASS'}
    (root/'native-control.json').write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record))
