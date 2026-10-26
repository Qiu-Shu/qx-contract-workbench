"""Diagnostic query only: never shut down or restart an application."""
import ctypes as c
from ctypes import wintypes as w

class Process(c.Structure):
    _fields_=[('pid',w.DWORD),('start',w.FILETIME)]
class Info(c.Structure):
    _fields_=[('process',Process),('name',w.WCHAR*256),('service',w.WCHAR*64),
              ('kind',c.c_int),('status',w.ULONG),('session',w.DWORD),('restartable',w.BOOL)]
api=c.WinDLL('rstrtmgr')
api.RmStartSession.argtypes=[c.POINTER(w.DWORD),w.DWORD,w.LPWSTR]
api.RmStartSession.restype=w.DWORD
api.RmRegisterResources.argtypes=[w.DWORD,w.UINT,c.POINTER(w.LPCWSTR),w.UINT,c.POINTER(Process),w.UINT,c.POINTER(w.LPCWSTR)]
api.RmRegisterResources.restype=w.DWORD
api.RmGetList.argtypes=[w.DWORD,c.POINTER(w.UINT),c.POINTER(w.UINT),c.POINTER(Info),c.POINTER(w.DWORD)]
api.RmGetList.restype=w.DWORD
api.RmEndSession.argtypes=[w.DWORD]
api.RmEndSession.restype=w.DWORD

def users(paths):
    paths=[str(p.absolute()) for p in paths]
    session=w.DWORD();key=c.create_unicode_buffer(33)
    status=api.RmStartSession(c.byref(session),0,key)
    if status:return {'status':status,'phase':'start'}
    try:
        names=(w.LPCWSTR*len(paths))(*paths)
        status=api.RmRegisterResources(session,len(paths),names,0,None,0,None)
        if status:return {'status':status,'phase':'register'}
        needed=w.UINT();count=w.UINT();reasons=w.DWORD()
        status=api.RmGetList(session,c.byref(needed),c.byref(count),None,c.byref(reasons))
        if status==0:return {'status':0,'processes':[],'file_count':len(paths)}
        if status!=234 or needed.value>256:return {'status':status,'phase':'size','needed':needed.value}
        values=(Info*needed.value)();count.value=needed.value
        status=api.RmGetList(session,c.byref(needed),c.byref(count),values,c.byref(reasons))
        return {'status':status,'file_count':len(paths),'processes':[
            {'pid':value.process.pid,'name':value.name,'service':value.service,'kind':value.kind}
            for value in values[:count.value]] if status==0 else None}
    finally:api.RmEndSession(session)

if __name__=='__main__':
    import json
    import subprocess
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parent
    path=root/'rm-control.txt';path.write_text('independent synthetic calibration',encoding='utf-8')
    child=subprocess.Popen([sys.executable,'-u','-c',"import os,sys; f=open(sys.argv[1],'rb'); print(os.getpid(),flush=True); input(); f.close()",str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        actual_pid=int(child.stdout.readline().strip())
        held=users([path]);assert held['status']==0 and any(p['pid']==actual_pid for p in held['processes']),held
    finally:child.communicate('\n',timeout=10)
    released=users([path]);assert released['status']==0 and not released['processes'],released
    report={'held':held,'released':released,'status':'PASS'}
    (root/'rm-control.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
