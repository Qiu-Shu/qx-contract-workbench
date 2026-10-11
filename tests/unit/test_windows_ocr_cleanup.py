"""Fault-injected native launch checks; these are not actual OS isolation evidence."""
import ctypes
from pathlib import Path
import pytest
from cn_contract.documents import _windows_ocr as native
from cn_contract.config import PROJECT_ROOT


@pytest.mark.parametrize('fault',['assign','wait','cleanup','acl_timeout','accounting','active','resource','grant_timeout','grant_failed','grant_and_revoke_failed'])
def test_launch_failure_kills_child_and_attempts_all_cleanup(monkeypatch,fault):
    events=[]
    monkeypatch.setattr('cn_contract.documents.pdfjs_assets._regular',lambda *a,**k:None)
    monkeypatch.setattr(native,'createprofile',lambda *a:0)
    monkeypatch.setattr(native,'deleteprofile',lambda *a:events.append('profile') or 0)
    monkeypatch.setattr(native,'createjob',lambda *a:42)
    monkeypatch.setattr(native,'setjob',lambda *a:True)
    def accounting(*args):
        events.append('accounting')
        if fault=='active':ctypes.cast(args[2],ctypes.POINTER(native.ACCOUNTING)).contents.active=1
        return fault!='accounting'
    monkeypatch.setattr(native,'queryjob',accounting)
    from cn_contract.security import ServiceError
    def budget(*args):
        if fault=='resource':raise ServiceError('OCR_STORAGE_LIMIT',503)
    monkeypatch.setattr('cn_contract.documents.ocr_workspace.require_budget',budget)
    monkeypatch.setattr(native,'init',lambda *a:True)
    monkeypatch.setattr(native,'update',lambda *a:True)
    monkeypatch.setattr(native,'deleteattrs',lambda *a:events.append('attrs'))
    def create(*args):
        pi=ctypes.cast(args[-1],ctypes.POINTER(native.PI)).contents
        pi.process=81;pi.thread=82
        return True
    monkeypatch.setattr(native,'createprocess',create)
    monkeypatch.setattr(native,'assign',lambda *a:fault!='assign')
    monkeypatch.setattr(native,'opentoken',lambda *a:True)
    def token(*args):
        ctypes.cast(args[2],ctypes.POINTER(native.D)).contents.value=1
        return True
    monkeypatch.setattr(native,'tokeninfo',token)
    monkeypatch.setattr(native,'resume',lambda *a:0)
    monkeypatch.setattr(native,'wait',lambda *a:0xffffffff if fault=='wait' else 0)
    monkeypatch.setattr(native,'exitcode',lambda *a:True)
    monkeypatch.setattr(native,'terminate',lambda *a:events.append('child') or True)
    monkeypatch.setattr(native,'close',lambda *a:True)
    original=native.api
    def api(lib,name,*args):
        if name=='ConvertSidToStringSidW':
            def sid(*args):
                ctypes.cast(args[1],ctypes.POINTER(native.w.LPWSTR))[0]='S-1-15-2-test'
                return True
            return sid
        if name=='TerminateJobObject':return lambda *a:events.append('job') or True
        if name=='LocalFree':return lambda *a:None
        return original(lib,name,*args)
    monkeypatch.setattr(native,'api',api)
    import subprocess
    def acl(args,**kwargs):
        from types import SimpleNamespace
        if '/grant' in args:
            if fault=='grant_timeout':raise subprocess.TimeoutExpired(args,30)
            if fault in ('grant_failed','grant_and_revoke_failed'):return SimpleNamespace(returncode=1)
        if '/remove:g' in args:
            events.append('acl')
            if fault=='acl_timeout':raise subprocess.TimeoutExpired(args,30)
            if fault in ('cleanup','grant_and_revoke_failed'):return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subprocess,'run',acl)
    with pytest.raises(ServiceError if fault=='resource' else OSError) as caught:
        native.run_sandboxed(PROJECT_ROOT/'.local/ocr-jobs/fake',PROJECT_ROOT/'.local/ocr-worker/python',PROJECT_ROOT/'.local/ocr-assets/models')
    if fault=='resource':assert caught.value.code=='OCR_STORAGE_LIMIT'
    if fault in ('accounting','active','cleanup','acl_timeout','grant_and_revoke_failed'):
        assert isinstance(caught.value,native.SandboxCleanupError)
    assert events.count('acl')==(1 if fault.startswith('grant_') else 3)
    if not fault.startswith('grant_'):
        assert 'child' in events
        assert events.index('child')<events.index('accounting')<events.index('acl')
    assert 'profile' in events
