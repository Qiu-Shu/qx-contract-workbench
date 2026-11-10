"""Byte verification is separate from adoption and execution approval."""
import hashlib,json,stat
from pathlib import PurePosixPath
from ..config import PROJECT_ROOT
from ..security import ServiceError
from .pdfjs_assets import _regular

ASSET_ROOT=PROJECT_ROOT/'.local/ocr-assets'
MANIFEST_PATH=PROJECT_ROOT/'sources/ocr-assets.lock.json'
MANIFEST_SHA256='f64178ccbd67fc75c6757ff0185fb6d672b97c17028fb26218a049a73105a73b'


def verify_ocr_assets():
    try:
        _regular(MANIFEST_PATH)
        if MANIFEST_PATH.stat().st_size>2_000_000:raise ValueError('large manifest')
        raw=MANIFEST_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA256:raise ValueError('manifest changed')
        manifest=json.loads(raw)
        if manifest['format_version']!=1 or manifest['production_approved'] is not False:raise ValueError('scope')
        _regular(ASSET_ROOT,directory=True)
        rows=manifest['files']
        if not 1<=len(rows)<=256:raise ValueError('inventory limit')
        expected={r['path']:r for r in rows}
        if len(expected)!=len(rows):raise ValueError('duplicate')
        actual=set()
        for count,path in enumerate(ASSET_ROOT.rglob('*')):
            if count>1024:raise ValueError('inventory limit')
            info=path.lstat();_regular(path,directory=stat.S_ISDIR(info.st_mode))
            if stat.S_ISREG(info.st_mode):actual.add(path.relative_to(ASSET_ROOT).as_posix())
        if actual!=expected.keys():raise ValueError('incomplete inventory')
        total=0
        for name,row in expected.items():
            p=PurePosixPath(name)
            if p.is_absolute() or p.as_posix()!=name or '..' in p.parts or ':' in name or '\\' in name:raise ValueError('path')
            if type(row['bytes']) is not int or not 0<=row['bytes']<=200_000_000:raise ValueError('size')
            path=ASSET_ROOT/name;total+=row['bytes']
            if total>1_000_000_000 or path.stat().st_size!=row['bytes']:raise ValueError('size')
            with path.open('rb') as stream:actual_hash=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual_hash!=row['sha256']:raise ValueError('digest')
        return {'files':len(rows),'bytes':total,'runtime_approved':manifest['runtime_approved']}
    except (OSError,ValueError,KeyError,TypeError):
        raise ServiceError('OCR_ASSETS_INVALID',503) from None


def require_ocr_runtime():
    result=verify_ocr_assets()
    if result['runtime_approved'] is not True:raise ServiceError('OCR_LICENSE_APPROVAL_REQUIRED',409)
    verify_environment()
    return result


def verify_environment():
    try:
        lock=json.loads(MANIFEST_PATH.read_bytes())
        manifest=PROJECT_ROOT/'sources/ocr-environment.lock.json';_regular(manifest)
        if manifest.stat().st_size>8_000_000:raise ValueError('environment lock limit')
        raw=manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=lock['environment_lock_sha256']:raise ValueError('environment lock changed')
        payload=json.loads(raw);rows=payload['files'];root=PROJECT_ROOT/'.local/ocr-worker/python'
        _regular(root,directory=True)
        if not 1<=len(rows)<=40000:raise ValueError('environment limit')
        actual=set()
        for count,path in enumerate(root.rglob('*')):
            if count>60000:raise ValueError('environment limit')
            info=path.lstat();_regular(path,directory=stat.S_ISDIR(info.st_mode))
            if stat.S_ISREG(info.st_mode):actual.add(path.relative_to(root).as_posix())
        if actual!={row['path'] for row in rows}:raise ValueError('environment inventory')
        for row in rows:
            name=row['path'];p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or p.as_posix()!=name:raise ValueError('environment path')
            path=root/name
            if path.stat().st_size!=row['bytes']:raise ValueError('environment size')
            with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            if digest!=row['sha256']:raise ValueError('environment changed')
    except (OSError,ValueError,KeyError,TypeError):raise ServiceError('OCR_ENVIRONMENT_INVALID',503) from None
