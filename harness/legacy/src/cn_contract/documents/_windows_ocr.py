"""Private Windows AppContainer and Job Object launcher; never used as a fallback."""
import ctypes as c
from ctypes import wintypes as w
import json, os, uuid

k=c.WinDLL('kernel32',use_last_error=True); u=c.WinDLL('userenv',use_last_error=True); a=c.WinDLL('advapi32',use_last_error=True)
P=c.c_void_p; Z=c.c_size_t; D=w.DWORD
class SI(c.Structure):
    _fields_=[('cb',D),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),*[(n,D) for n in ('x','y','xs','ys','xc','yc','fill','flags')],('show',w.WORD),('reserved2size',w.WORD),('reserved2',P),('stdin',P),('stdout',P),('stderr',P)]
class SX(c.Structure): _fields_=[('si',SI),('attrs',P)]
class PI(c.Structure): _fields_=[('process',P),('thread',P),('pid',D),('tid',D)]
class CAP(c.Structure): _fields_=[('sid',P),('caps',P),('count',D),('reserved',D)]
class BASIC(c.Structure): _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',D),('minws',Z),('maxws',Z),('active',D),('affinity',Z),('priority',D),('scheduling',D)]
class IO(c.Structure): _fields_=[(n,c.c_uint64) for n in ('readops','writeops','otherops','readbytes','writebytes','otherbytes')]
class LIMIT(c.Structure): _fields_=[('basic',BASIC),('io',IO),('processmem',Z),('jobmem',Z),('peakprocess',Z),('peakjob',Z)]
class ACCOUNTING(c.Structure):
    _fields_=[(n,c.c_int64) for n in ('user','kernel','period_user','period_kernel')]+[(n,D) for n in ('faults','total','active','terminated')]
class SandboxCleanupError(OSError):
    """Do not delete the job directory when isolation cleanup is unconfirmed."""
def api(lib,name,args,result=w.BOOL):
    f=getattr(lib,name); f.argtypes=args; f.restype=result; return f
createprofile=api(u,'CreateAppContainerProfile',[w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,P,D,c.POINTER(P)],c.c_long)
deleteprofile=api(u,'DeleteAppContainerProfile',[w.LPCWSTR],c.c_long)
freesid=api(a,'FreeSid',[P],P)
init=api(k,'InitializeProcThreadAttributeList',[P,D,D,c.POINTER(Z)])
update=api(k,'UpdateProcThreadAttribute',[P,D,Z,P,Z,P,P])
deleteattrs=api(k,'DeleteProcThreadAttributeList',[P],None)
createjob=api(k,'CreateJobObjectW',[P,w.LPCWSTR],P)
setjob=api(k,'SetInformationJobObject',[P,c.c_int,P,D])
queryjob=api(k,'QueryInformationJobObject',[P,c.c_int,P,D,P])
assign=api(k,'AssignProcessToJobObject',[P,P])
createprocess=api(k,'CreateProcessW',[w.LPCWSTR,w.LPWSTR,P,P,w.BOOL,D,P,w.LPCWSTR,P,c.POINTER(PI)])
resume=api(k,'ResumeThread',[P],D)
wait=api(k,'WaitForSingleObject',[P,D],D)
exitcode=api(k,'GetExitCodeProcess',[P,c.POINTER(D)])
close=api(k,'CloseHandle',[P])
terminate=api(k,'TerminateProcess',[P,w.UINT])
opentoken=api(a,'OpenProcessToken',[P,D,c.POINTER(P)])
tokeninfo=api(a,'GetTokenInformation',[P,c.c_int,P,D,c.POINTER(D)])
def check(ok,stage):
    if not ok: raise OSError(c.get_last_error(),stage)


def run_sandboxed(workdir, runtime, models, *, timeout=60, memory=2*1024**3):
    """Server-owned paths only. No credentials or handles inherited; fresh SID."""
    import subprocess,time
    from pathlib import Path
    from ..config import PROJECT_ROOT
    from .pdfjs_assets import _regular
    from .ocr_workspace import require_budget
    expected=PROJECT_ROOT/'.local'
    for path in (workdir,runtime,models):_regular(path,directory=True)
    if (runtime!=expected/'ocr-worker/python' or models!=expected/'ocr-assets/models'
        or workdir.parent!=expected/'ocr-jobs' or not 0<timeout<=60 or not 0<memory<=2*1024**3):
        raise ValueError('sandbox paths or limits invalid')
    name='QX.Synthetic.OCR.'+uuid.uuid4().hex
    sid=P();job=None;pi=PI();attrs=None;initialized=False;created=False;token=P();granted=[]
    sid_text=w.LPWSTR(); text_sid=api(a,'ConvertSidToStringSidW',[P,c.POINTER(w.LPWSTR)])
    localfree=api(k,'LocalFree',[P],P);terminatejob=api(k,'TerminateJobObject',[P,w.UINT])
    def acl(path,*arguments):
        try:
            result=subprocess.run([os.path.join(os.environ['SystemRoot'],'System32','icacls.exe'),str(path),*arguments],
                capture_output=True,creationflags=0x8000000,timeout=30)
        except subprocess.TimeoutExpired:raise OSError('private sandbox ACL timeout') from None
        if result.returncode:raise OSError(result.returncode,'private sandbox ACL')
    try:
        hr=createprofile(name,name,'Local synthetic OCR only',None,0,c.byref(sid))
        if hr<0:raise OSError(hr,'CreateAppContainerProfile')
        created=True;check(text_sid(sid,c.byref(sid_text)),'ConvertSidToStringSid')
        principal='*'+sid_text.value
        for path,rights in ((runtime,'RX'),(models,'RX'),(workdir,'M')):
            granted.append(path)
            acl(path,'/grant',principal+':(OI)(CI)('+rights+')')
        acl(workdir,'/setintegritylevel','(OI)(CI)L')
        size=Z();init(None,1,0,c.byref(size));attrs=c.create_string_buffer(size.value)
        check(init(attrs,1,0,c.byref(size)),'InitializeProcThreadAttributeList');initialized=True
        caps=CAP(sid,None,0,0);check(update(attrs,0,0x20009,c.byref(caps),c.sizeof(caps),None,None),'UpdateProcThreadAttribute')
        job=createjob(None,None);check(job,'CreateJobObject')
        limits=LIMIT();limits.basic.flags=0x2000|0x200|0x8;limits.basic.active=8;limits.jobmem=memory
        check(setjob(job,9,c.byref(limits),c.sizeof(limits)),'SetInformationJobObject')
        startup=SX();startup.si.cb=c.sizeof(startup);startup.attrs=c.cast(attrs,P)
        exe=str(runtime/'python.exe')
        command=c.create_unicode_buffer(subprocess.list2cmdline([exe,'-I','-B',str(workdir/'worker.py')]))
        values={key:os.environ[key] for key in ('SystemRoot','SystemDrive','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA','TEMP','TMP') if key in os.environ}
        values.update(PATH=str(runtime)+';'+os.path.join(os.environ['SystemRoot'],'System32'),
            HOME=str(workdir),USERPROFILE=str(workdir),TEMP=str(workdir),TMP=str(workdir),
            PADDLE_PDX_CACHE_HOME=str(workdir/'cache'),PADDLE_HOME=str(workdir/'cache'),
            PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',HF_HUB_OFFLINE='1',HF_HOME=str(workdir/'cache'),
            OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='2',CUDA_VISIBLE_DEVICES='',
            PYTHONIOENCODING='utf-8',QX_MODELS=str(models))
        env=c.create_unicode_buffer('\0'.join(key+'='+value for key,value in sorted(values.items()))+'\0\0')
        check(createprocess(exe,command,None,None,False,0x80000|4|0x400|0x8000000,env,str(workdir),c.byref(startup),c.byref(pi)),'CreateProcessW')
        check(assign(job,pi.process),'AssignProcessToJobObject')
        check(opentoken(pi.process,8,c.byref(token)),'OpenProcessToken')
        value=D();used=D();check(tokeninfo(token,29,c.byref(value),c.sizeof(value),c.byref(used)),'TokenIsAppContainer')
        if value.value!=1:raise ValueError('container missing')
        check(resume(pi.thread)!=0xffffffff,'ResumeThread')
        started=time.monotonic()
        while True:
            state=wait(pi.process,50)
            require_budget(workdir,workdir.parent)
            if state==0:break
            check(state==258,'WaitForSingleObject')
            if time.monotonic()-started>timeout:
                check(terminatejob(job,124),'TerminateJobObject');wait(pi.process,5000)
                return {'exit_code':124,'timed_out':True,'appcontainer':True,'memory_limit':memory}
        code=D();check(exitcode(pi.process,c.byref(code)),'GetExitCodeProcess')
        return {'exit_code':code.value,'timed_out':False,'appcontainer':True,'memory_limit':memory}
    finally:
        cleanup_error=None
        if job and not terminatejob(job,125):cleanup_error=SandboxCleanupError('job termination unconfirmed')
        # A failed assignment leaves a suspended child outside the job.
        if pi.process:
            terminate(pi.process,125)
            if wait(pi.process,5000)!=0:cleanup_error=SandboxCleanupError('child termination unconfirmed')
        for handle in (token,pi.thread,pi.process):
            if handle:close(handle)
        if job:
            deadline=time.monotonic()+5
            while True:
                accounting=ACCOUNTING()
                if not queryjob(job,1,c.byref(accounting),c.sizeof(accounting),None):
                    cleanup_error=SandboxCleanupError('job accounting unavailable');break
                if accounting.active==0:break
                if time.monotonic()>=deadline:
                    cleanup_error=SandboxCleanupError('job processes still active');break
                time.sleep(.05)
            close(job)
        if initialized:deleteattrs(attrs)
        for path in reversed(granted):
            try:acl(path,'/remove:g','*'+sid_text.value)
            except OSError as error:cleanup_error=error
        if sid_text:localfree(c.cast(sid_text,P))
        if sid:freesid(sid)
        if created:
            hr=deleteprofile(name)
            if hr<0:cleanup_error=OSError(hr,'DeleteAppContainerProfile')
        if cleanup_error:raise SandboxCleanupError('sandbox cleanup unconfirmed') from None
