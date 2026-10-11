"""Admission through service entry points; no real OCR model calls."""
from concurrent.futures import ThreadPoolExecutor
import threading
import pytest
from cn_contract.documents import ocr_process
from cn_contract.security import ServiceError


@pytest.mark.parametrize('entry',['bitmap','pdf'])
def test_busy_request_does_not_verify_runtime(monkeypatch,tmp_path,entry):
    monkeypatch.setattr(ocr_process,'PROJECT_ROOT',tmp_path)
    entered=threading.Event();release=threading.Event();calls=[]
    def runtime():
        calls.append(threading.get_ident())
        if len(calls)==1:
            entered.set();assert release.wait(10)
        raise ServiceError('OCR_ASSETS_INVALID',503)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(ocr_process.run_ocr_page,b'fictional',{})
        try:
            assert entered.wait(5)
            from cn_contract.documents import ocr_candidates
            def forbidden_render(*args):pytest.fail('busy request rendered a PDF')
            monkeypatch.setattr(ocr_candidates,'page_bitmap',forbidden_render)
            with pytest.raises(ServiceError) as busy:
                if entry=='bitmap':ocr_process.run_ocr_page(b'fictional',{})
                else:ocr_candidates.predict_page(b'fictional PDF',object())
            assert busy.value.code=='OCR_BUSY'
            assert len(calls)==1
        finally:release.set()
        with pytest.raises(ServiceError) as failed:first.result(timeout=5)
        assert failed.value.code=='OCR_ASSETS_INVALID'
    with pytest.raises(ServiceError) as retry:ocr_process.run_ocr_page(b'fictional',{})
    assert retry.value.code=='OCR_ASSETS_INVALID'
    assert len(calls)==2


def test_separate_process_is_rejected_before_runtime_and_render(monkeypatch,tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    from cn_contract.documents import ocr_candidates
    monkeypatch.setattr(ocr_process,'PROJECT_ROOT',tmp_path)
    child='''
import sys
from pathlib import Path
from cn_contract.documents import ocr_process as m
from cn_contract.security import ServiceError
m.PROJECT_ROOT=Path(sys.argv[1])
def runtime():
    print('admitted',flush=True)
    sys.stdin.readline()
    raise ServiceError('OCR_ASSETS_INVALID',503)
m.require_ocr_runtime=runtime
try:m.run_ocr_page(b'fictional',{})
except ServiceError as e:
    assert e.code=='OCR_ASSETS_INVALID'
'''
    env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[2]/'src')}
    process=subprocess.Popen([sys.executable,'-X','utf8','-c',child,str(tmp_path)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    def forbidden(*args):pytest.fail('cross-process busy request did expensive work')
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',forbidden)
    monkeypatch.setattr(ocr_candidates,'page_bitmap',forbidden)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            ready=pool.submit(process.stdout.readline)
            try:assert ready.result(timeout=10).strip()=='admitted'
            except BaseException:process.kill();raise
        with pytest.raises(ServiceError) as busy:ocr_candidates.predict_page(b'fictional PDF',object())
        assert busy.value.code=='OCR_BUSY'
        _,stderr=process.communicate('\n',timeout=10)
        assert process.returncode==0,stderr
    finally:
        if process.poll() is None:process.kill();process.communicate()
    def unavailable():raise ServiceError('OCR_ASSETS_INVALID',503)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',unavailable)
    with pytest.raises(ServiceError) as retry:ocr_process.run_ocr_page(b'fictional',{})
    assert retry.value.code=='OCR_ASSETS_INVALID'


@pytest.mark.parametrize('failure',['prepare','staging','launch','timeout','output','none'])
def test_admission_released_after_worker_and_preparation_outcomes(monkeypatch,tmp_path,failure):
    from io import BytesIO
    from hashlib import sha256
    from uuid import uuid4
    from PIL import Image
    from cn_contract.documents import _windows_ocr
    monkeypatch.setattr(ocr_process,'PROJECT_ROOT',tmp_path)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',lambda:None)
    stream=BytesIO();Image.new('RGB',(1,1),'white').save(stream,format='PNG');raw=stream.getvalue()
    source=dict(document_version_id=uuid4(),document_sha256='0'*64,page=1,
        page_width_points=1,page_height_points=1,bitmap_width=1,bitmap_height=1,
        bitmap_sha256=sha256(raw).hexdigest(),coordinate_space='rendered_page_top_left')
    def prepare():
        if failure=='prepare':raise ValueError('synthetic preparation failure')
        return raw,source
    def stage(work):
        if failure=='staging':raise OSError('synthetic disk failure')
    def launch(work,*args):
        if failure=='launch':raise OSError('synthetic launch failure')
        (work/'output.json').write_bytes(b'{}' if failure=='output' else b'{"status":"ok","blocks":[]}')
        return {'timed_out':failure=='timeout','exit_code':0}
    monkeypatch.setattr(ocr_process,'stage_models',stage)
    monkeypatch.setattr(_windows_ocr,'run_sandboxed',launch)
    if failure=='none':assert ocr_process.run_prepared_ocr_page(prepare).blocks==()
    else:
        with pytest.raises((ValueError,OSError,ServiceError)) as caught:ocr_process.run_prepared_ocr_page(prepare)
        expected={'launch':'OCR_ISOLATION_UNAVAILABLE','timeout':'OCR_TIMEOUT','output':'OCR_OUTPUT_INVALID'}
        if failure in expected:assert caught.value.code==expected[failure]
    # A second public request must reach runtime verification, rather than stay busy.
    def unavailable():raise ServiceError('OCR_ASSETS_INVALID',503)
    monkeypatch.setattr(ocr_process,'require_ocr_runtime',unavailable)
    with pytest.raises(ServiceError) as retry:ocr_process.run_ocr_page(raw,source)
    assert retry.value.code=='OCR_ASSETS_INVALID'
