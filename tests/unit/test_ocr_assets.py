"""No OCR code may execute merely because public artifacts were downloaded."""
import importlib, importlib.util
import hashlib,json
import pytest
from cn_contract.security import ServiceError


def module():
    assert importlib.util.find_spec('cn_contract.documents.ocr_assets'), 'locked OCR preflight missing'
    return importlib.import_module('cn_contract.documents.ocr_assets')


def assets(tmp_path,monkeypatch):
    m=module();root=tmp_path/'assets';root.mkdir();(root/'model.bin').write_bytes(b'fictional model')
    row={'path':'model.bin','bytes':15,'sha256':hashlib.sha256(b'fictional model').hexdigest()}
    raw=json.dumps({'format_version':1,'runtime_approved':False,'production_approved':False,'files':[row]}).encode()
    manifest=tmp_path/'lock.json';manifest.write_bytes(raw)
    monkeypatch.setattr(m,'ASSET_ROOT',root);monkeypatch.setattr(m,'MANIFEST_PATH',manifest)
    monkeypatch.setattr(m,'MANIFEST_SHA256',hashlib.sha256(raw).hexdigest())
    return m,root,manifest


def test_verified_download_does_not_authorize_runtime(tmp_path,monkeypatch):
    m,_,_=assets(tmp_path,monkeypatch)
    assert m.verify_ocr_assets()['files']==1
    with pytest.raises(ServiceError) as caught:m.require_ocr_runtime()
    assert caught.value.code=='OCR_LICENSE_APPROVAL_REQUIRED'


@pytest.mark.parametrize('change',['missing','corrupt','extra','hardlink','lock'])
def test_changed_ocr_assets_fail_before_runtime(tmp_path,monkeypatch,change):
    m,root,manifest=assets(tmp_path,monkeypatch);file=root/'model.bin'
    if change=='missing':file.unlink()
    elif change=='corrupt':file.write_bytes(b'wrong')
    elif change=='extra':(root/'unknown.bin').write_bytes(b'wrong')
    elif change=='hardlink':(tmp_path/'alias.bin').hardlink_to(file)
    else:manifest.write_bytes(b'{}')
    with pytest.raises(ServiceError) as caught:m.require_ocr_runtime()
    assert caught.value.code=='OCR_ASSETS_INVALID'


@pytest.mark.parametrize('change',['none','missing','corrupt','extra','environment_lock'])
def test_dedicated_environment_is_exact_inventory(tmp_path,monkeypatch,change):
    m,_,manifest=assets(tmp_path,monkeypatch)
    root=tmp_path/'.local/ocr-worker/python';root.mkdir(parents=True)
    file=root/'python.exe';file.write_bytes(b'fictional interpreter')
    payload={'files':[{'path':'python.exe','bytes':file.stat().st_size,'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}]}
    env=tmp_path/'sources/ocr-environment.lock.json';env.parent.mkdir();env.write_text(json.dumps(payload),encoding='utf8')
    lock=json.loads(manifest.read_bytes());lock['environment_lock_sha256']=hashlib.sha256(env.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(lock),encoding='utf8');monkeypatch.setattr(m,'PROJECT_ROOT',tmp_path)
    if change=='none':m.verify_environment();return
    if change=='missing':file.unlink()
    elif change=='corrupt':file.write_bytes(b'changed interpreter')
    elif change=='extra':(root/'unknown.dll').write_bytes(b'unknown')
    else:env.write_bytes(b'{}')
    with pytest.raises(ServiceError) as caught:m.verify_environment()
    assert caught.value.code=='OCR_ENVIRONMENT_INVALID'
