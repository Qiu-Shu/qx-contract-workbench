"""Asset boundary tests use small independent fake assets, never upstream code."""
import hashlib
import importlib
import importlib.util
import json

import pytest

from cn_contract.security import ServiceError


def module():
    assert importlib.util.find_spec('cn_contract.documents.pdfjs_assets') is not None, 'PDF.js needs a locked local asset gate'
    return importlib.import_module('cn_contract.documents.pdfjs_assets')


def assets(tmp_path, monkeypatch):
    m = module()
    root = tmp_path / 'assets'
    rows = []
    for name, raw in [('build/pdf.mjs', b'// independent test api'), ('build/pdf.worker.mjs', b'// independent test worker'), ('LICENSE', b'Independent test license')]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        rows.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    value = {'format_version': 1, 'package': 'pdfjs-dist', 'version': '6.4.299', 'files': rows,
             'development_scope': 'independent_synthetic_pdf_only', 'production_approved': False}
    raw = json.dumps(value).encode()
    manifest = tmp_path / 'lock.json'
    manifest.write_bytes(raw)
    monkeypatch.setattr(m, 'ASSET_ROOT', root)
    monkeypatch.setattr(m, 'MANIFEST_PATH', manifest)
    monkeypatch.setattr(m, 'MANIFEST_SHA256', hashlib.sha256(raw).hexdigest())
    return m, root, manifest


def test_exact_locked_asset_and_mime(tmp_path, monkeypatch):
    m, _, _ = assets(tmp_path, monkeypatch)
    raw, mime = m.read_pdfjs_asset('build/pdf.mjs')
    assert raw == b'// independent test api' and mime == 'text/javascript'


@pytest.mark.parametrize('change', ['missing', 'corrupt', 'extra', 'lock_corrupt', 'directory_instead', 'hardlink'])
def test_assets_fail_closed_for_incomplete_or_changed_set(tmp_path, monkeypatch, change):
    m, root, manifest = assets(tmp_path, monkeypatch)
    target = root / 'build/pdf.worker.mjs'
    if change == 'missing': target.unlink()
    elif change == 'corrupt': target.write_bytes(b'// changed')
    elif change == 'extra': (root / 'unexpected.mjs').write_text('canary')
    elif change == 'lock_corrupt': manifest.write_bytes(manifest.read_bytes() + b' ')
    elif change == 'directory_instead': target.unlink(); target.mkdir()
    else: (tmp_path / 'linked.mjs').hardlink_to(target)
    with pytest.raises(ServiceError) as caught:
        m.read_pdfjs_asset('build/pdf.mjs')
    assert caught.value.code == 'PDF_VIEWER_UNAVAILABLE'


@pytest.mark.parametrize('name', ['../lock.json', '/build/pdf.mjs', 'build\\pdf.mjs', 'https://example.invalid/a', 'package.json', 'build/pdf.mjs:other', 'BUILD/pdf.mjs'])
def test_no_arbitrary_path_or_unlisted_asset(tmp_path, monkeypatch, name):
    m, _, _ = assets(tmp_path, monkeypatch)
    with pytest.raises(ServiceError) as caught:
        m.read_pdfjs_asset(name)
    assert caught.value.status_code == 404
