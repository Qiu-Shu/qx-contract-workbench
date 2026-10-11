"""Synthetic temporary jobs; ordinary CI substitutes the native predictor only."""
from hashlib import sha256
from io import BytesIO
from uuid import uuid4
import pytest
from PIL import Image
from cn_contract.documents import ocr_process,_windows_ocr
from cn_contract.security import ServiceError


@pytest.fixture
def workspace(monkeypatch,tmp_path):
    monkeypatch.setattr(ocr_process,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',lambda:None)
    stream=BytesIO();Image.new('RGB',(1,1),'white').save(stream,format='PNG');raw=stream.getvalue()
    source=dict(document_version_id=uuid4(),document_sha256='0'*64,page=1,page_width_points=1,
        page_height_points=1,bitmap_width=1,bitmap_height=1,bitmap_sha256=sha256(raw).hexdigest(),
        coordinate_space='rendered_page_top_left')
    jobs=[]
    def stage(work):
        jobs.append(work);(work/'models').mkdir();(work/'models/model.bin').write_bytes(b'synthetic model')
    def launch(work,*args):
        (work/'output.json').write_bytes(b'{"status":"ok","blocks":[]}')
        return dict(timed_out=False,exit_code=0)
    monkeypatch.setattr(ocr_process,'stage_models',stage)
    monkeypatch.setattr(_windows_ocr,'run_sandboxed',launch)
    return raw,source,jobs,tmp_path


def test_success_removes_its_temporary_job_but_keeps_history_and_original(workspace):
    raw,source,jobs,root=workspace
    parent=root/'.local/ocr-jobs';history=parent/('a'*32);history.mkdir(parents=True)
    (history/'output.json').write_bytes(b'historical evidence')
    original=root/'original.docx';original.write_bytes(b'fictional immutable original')
    result=ocr_process.run_ocr_page(raw,source)
    assert result.source.bitmap_sha256==sha256(raw).hexdigest()
    assert len(jobs)==1 and not jobs[0].exists()
    assert (history/'output.json').read_bytes()==b'historical evidence'
    assert original.read_bytes()==b'fictional immutable original'


def test_residue_rejects_before_expensive_verification(workspace,monkeypatch):
    raw,source,_,root=workspace
    residue=root/'.local/ocr-jobs'/('managed-'+'b'*32);residue.mkdir(parents=True)
    def forbidden():pytest.fail('residue must block before runtime verification')
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',forbidden)
    with pytest.raises(ServiceError) as error:ocr_process.run_ocr_page(raw,source)
    assert error.value.code=='OCR_CLEANUP_REQUIRED'
    assert residue.exists()


@pytest.mark.parametrize('fault',['stage','launch','timeout','output'])
def test_failure_removes_new_job_and_allows_retry(workspace,monkeypatch,fault):
    raw,source,jobs,_=workspace
    if fault=='stage':
        stage=ocr_process.stage_models
        def broken(work):stage(work);raise OSError('synthetic disk failure')
        monkeypatch.setattr(ocr_process,'stage_models',broken)
    else:
        def broken(work,*args):
            if fault=='launch':raise OSError('synthetic launch failure')
            (work/'output.json').write_bytes(b'{}')
            return dict(timed_out=fault=='timeout',exit_code=0)
        monkeypatch.setattr(_windows_ocr,'run_sandboxed',broken)
    with pytest.raises((OSError,ServiceError)):ocr_process.run_ocr_page(raw,source)
    assert len(jobs)==1 and not jobs[0].exists()
    def unavailable():raise ServiceError('OCR_ASSETS_INVALID',503)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',unavailable)
    with pytest.raises(ServiceError) as retry:ocr_process.run_ocr_page(raw,source)
    assert retry.value.code=='OCR_ASSETS_INVALID'


@pytest.mark.parametrize('fault',['unlink','sandbox_cleanup','hardlink','junction'])
def test_unconfirmed_cleanup_preserves_residue_and_blocks_retry(workspace,monkeypatch,fault):
    import os,subprocess
    from pathlib import Path
    raw,source,jobs,root=workspace
    external=root/'outside';external.mkdir();sentinel=external/'keep.txt';sentinel.write_bytes(b'keep')
    original_unlink=Path.unlink
    def launch(work,*args):
        if fault=='sandbox_cleanup':raise _windows_ocr.SandboxCleanupError('synthetic cleanup failure')
        if fault=='hardlink':os.link(sentinel,work/'linked.txt')
        if fault=='junction':
            # Native junction inside a synthetic job; never delete its target.
            command=['powershell','-NoProfile','-Command',
                "New-Item -ItemType Junction -Path '"+str(work/'linked').replace("'","''")+"' -Target '"+str(external).replace("'","''")+"' | Out-Null"]
            result=subprocess.run(command,capture_output=True,creationflags=0x8000000)
            assert result.returncode==0,result.stderr
        (work/'output.json').write_bytes(b'{"status":"ok","blocks":[]}')
        return dict(timed_out=False,exit_code=0)
    def locked(path,*args,**kwargs):
        if path.name=='input.png':raise PermissionError('synthetic locked file')
        return original_unlink(path,*args,**kwargs)
    monkeypatch.setattr(_windows_ocr,'run_sandboxed',launch)
    if fault=='unlink':monkeypatch.setattr(Path,'unlink',locked)
    with pytest.raises(ServiceError) as error:ocr_process.run_ocr_page(raw,source)
    assert error.value.code=='OCR_CLEANUP_REQUIRED'
    assert jobs[0].exists() and sentinel.read_bytes()==b'keep'
    def forbidden():pytest.fail('unclean job allowed another runtime verification')
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',forbidden)
    with pytest.raises(ServiceError) as retry:ocr_process.run_ocr_page(raw,source)
    assert retry.value.code=='OCR_CLEANUP_REQUIRED'
    # Remove only the test-created link; pytest must never traverse its target.
    if fault=='junction':(jobs[0]/'linked').rmdir()


@pytest.mark.parametrize('kind',['bytes','entries'])
def test_oversized_job_is_rejected_before_launch_and_cleaned(workspace,monkeypatch,kind):
    raw,source,jobs,_=workspace;stage=ocr_process.stage_models
    def oversized(work):
        stage(work)
        if kind=='bytes':
            with (work/'oversized.bin').open('wb') as stream:stream.truncate(129*1024**2)
        else:
            for number in range(257):(work/str(number)).touch()
    def forbidden(*args):pytest.fail('oversized job launched native OCR')
    monkeypatch.setattr(ocr_process,'stage_models',oversized)
    monkeypatch.setattr(_windows_ocr,'run_sandboxed',forbidden)
    with pytest.raises(ServiceError) as error:ocr_process.run_ocr_page(raw,source)
    assert error.value.code=='OCR_STORAGE_LIMIT'
    assert not jobs[0].exists()


def test_low_free_space_fails_before_verification(workspace,monkeypatch):
    from types import SimpleNamespace
    from cn_contract.documents import ocr_workspace
    raw,source,jobs,_=workspace
    monkeypatch.setattr(ocr_workspace.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
    def forbidden():pytest.fail('low disk space allowed runtime verification')
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',forbidden)
    with pytest.raises(ServiceError) as error:ocr_process.run_ocr_page(raw,source)
    assert error.value.code=='OCR_STORAGE_LIMIT' and jobs==[]


def test_cleanup_rejects_a_directory_outside_job_parent(tmp_path):
    from cn_contract.documents.ocr_workspace import cleanup
    parent=tmp_path/'jobs';parent.mkdir()
    outside=tmp_path/('managed-'+'c'*32);outside.mkdir();(outside/'keep').write_bytes(b'keep')
    with pytest.raises(ServiceError) as error:cleanup(outside,parent)
    assert error.value.code=='OCR_CLEANUP_REQUIRED' and (outside/'keep').read_bytes()==b'keep'
