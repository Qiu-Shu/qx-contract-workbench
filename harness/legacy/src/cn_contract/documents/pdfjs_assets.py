"""Serve only measured, local browser assets; never fetch at runtime."""
import hashlib
import json
from pathlib import PurePosixPath
import stat

from ..config import PROJECT_ROOT
from ..security import ServiceError

ASSET_ROOT = PROJECT_ROOT / '.local/pdfjs-assets/6.4.299'
MANIFEST_PATH = PROJECT_ROOT / 'sources/pdfjs-assets.lock.json'
MANIFEST_SHA256 = '7f6249702ac3b21327e66b090dfc3acc7e33db555dc37c049405d742a84df4d2'
MIME = {'.mjs':'text/javascript', '.js':'text/javascript', '.bcmap':'application/octet-stream',
        '.pfb':'application/octet-stream', '.ttf':'font/ttf', '.wasm':'application/wasm', '.icc':'application/octet-stream'}


def _regular(path, *, directory=False):
    for ancestor in (*reversed(path.parents), path):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('linked path')
        if ancestor != path or directory:
            if not stat.S_ISDIR(info.st_mode): raise ValueError('directory required')
        elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('regular independent file required')


def _inventory():
    _regular(MANIFEST_PATH)
    if MANIFEST_PATH.stat().st_size > 256 * 1024: raise ValueError('manifest limit')
    raw = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256: raise ValueError('manifest changed')
    manifest = json.loads(raw)
    if (manifest['format_version'] != 1 or manifest['package'] != 'pdfjs-dist'
            or manifest['version'] != '6.4.299' or manifest['production_approved'] is not False
            or manifest['development_scope'] != 'independent_synthetic_pdf_only'):
        raise ValueError('manifest scope')
    rows = manifest['files']
    if not 3 <= len(rows) <= 512: raise ValueError('file count')
    expected = {row['path']:row for row in rows}
    if len(expected) != len(rows): raise ValueError('duplicate asset')
    if not {'build/pdf.mjs','build/pdf.worker.mjs','LICENSE'} <= expected.keys(): raise ValueError('incomplete set')
    _regular(ASSET_ROOT, directory=True)
    actual = set()
    count = 0
    for path in ASSET_ROOT.rglob('*'):
        count += 1
        if count > 1024: raise ValueError('entry limit')
        info = path.lstat()
        _regular(path, directory=stat.S_ISDIR(info.st_mode))
        if stat.S_ISREG(info.st_mode): actual.add(path.relative_to(ASSET_ROOT).as_posix())
    if actual != expected.keys(): raise ValueError('asset inventory changed')
    total = 0
    for name, row in expected.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or relative.as_posix() != name or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('asset path')
        path = ASSET_ROOT / name
        if type(row['bytes']) is not int or not 0 <= row['bytes'] <= 16 * 1024 * 1024: raise ValueError('asset size')
        total += row['bytes']
        if total > 64 * 1024 * 1024 or path.stat().st_size != row['bytes']: raise ValueError('asset size')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']: raise ValueError('asset changed')
    return expected


def read_pdfjs_asset(name):
    relative = PurePosixPath(name)
    if (not isinstance(name, str) or relative.is_absolute() or relative.as_posix() != name
            or '..' in relative.parts or '\\' in name or ':' in name or relative.suffix not in MIME
            or relative.parts[0] not in {'build','cmaps','standard_fonts','wasm','iccs'}):
        raise ServiceError('NOT_SUPPORTED', 404)
    try:
        expected = _inventory()
        if name not in expected: raise ServiceError('NOT_SUPPORTED', 404)
        path = ASSET_ROOT / name
        _regular(path)
        data = path.read_bytes()
        if len(data) != expected[name]['bytes'] or hashlib.sha256(data).hexdigest() != expected[name]['sha256']:
            raise ValueError('asset changed during read')
        return data, MIME[relative.suffix]
    except ServiceError:
        raise
    except (OSError, ValueError, KeyError, TypeError):
        raise ServiceError('PDF_VIEWER_UNAVAILABLE', 503) from None
