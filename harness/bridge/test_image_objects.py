"""Regression: Harness uploads images as extensionless objects, not named files."""
import hashlib
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from store import MaterialStore
from reader import parse
from business_store import CaseStore


def uploaded_image(root, fmt='JPEG', text=None):
    image = Image.new('RGB', (1400, 300), 'white')
    if text:
        ImageDraw.Draw(image).text((40, 80), text,
            font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 48), fill='black')
    from io import BytesIO
    data = BytesIO(); image.save(data, format=fmt); raw = data.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    path = root / 'inbox/.harness/attachments/v1/objects' / digest[:2] / digest
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    return path.relative_to(root).as_posix(), raw


@pytest.mark.parametrize('fmt', ['JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'])
def test_extensionless_uploaded_images_are_listed_and_registered_without_copy(tmp_path, fmt):
    name, raw = uploaded_image(tmp_path, fmt)
    store = MaterialStore(tmp_path)
    assert name in [item['path'] for item in store.list()['materials']]
    record = store.register(name)
    assert record['path'] == name
    assert record['sha256'] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / name).read_bytes() == raw
    assert [p for p in (tmp_path / 'inbox').rglob('*') if p.is_file()] == [tmp_path / name]


def test_extensionless_jpeg_ocr_and_case_readback_keep_original_identity(tmp_path):
    clause = '验收合格后十日内付款'
    name, raw = uploaded_image(tmp_path, text=clause)
    store = MaterialStore(tmp_path)
    store.register(name)
    result = parse(store, name)
    assert result['status'] == 'ready'
    assert store.search(clause, path=name)['matches']
    cases = CaseStore(store); cid = cases.create('图片附件回归测试')['id']
    cases.link_materials(cid, [name])
    readback = cases.read_material(cid, name)
    assert clause in ''.join(chunk['text'] for chunk in readback['chunks'])
    assert cases.materials(cid)[0]['sha256'] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / name).read_bytes() == raw


def test_unknown_extensionless_files_stay_unsupported(tmp_path):
    (tmp_path / 'unknown').write_bytes(b'not an image')
    store = MaterialStore(tmp_path)
    with pytest.raises(ValueError, match='不支持'):
        store.register('unknown')
    assert store.list()['materials'] == []


def test_extensionless_images_do_not_escape_workspace(tmp_path):
    name, _ = uploaded_image(tmp_path)
    store = MaterialStore(tmp_path / 'restricted')
    with pytest.raises(ValueError, match='工作区'):
        store.register(tmp_path / name)
