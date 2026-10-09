"""Independent synthetic-only probes; no OCR worker calls."""
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
import json

from PIL import Image
import pypdfium2 as pdfium
from cn_contract.documents import ocr_candidates as module
from cn_contract.domain import PageOCRInput, OCRPageSource
from cn_contract.security import ServiceError

observations = []
ink = Image.new('RGB', (100, 60), (224, 224, 224))
ink.paste((208, 208, 208), (15, 9, 43, 37))
source = BytesIO()
ink.save(source, format='PDF', resolution=144)

def dark_extent(image):
    gray = image.convert('L')
    lo, hi = gray.getextrema()
    return gray.point(lambda p: 255 if p < (lo + hi) / 2 else 0).getbbox()

for rotation in (0, 90, 180, 270):
    document = pdfium.PdfDocument(source.getvalue())
    page = document[0]
    page.set_rotation(rotation)
    rotated = BytesIO()
    document.save(rotated)
    bitmap = page.render(scale=4)
    baseline = bitmap.to_pil().copy()
    bitmap.close()
    page.close()
    document.close()
    original = rotated.getvalue()
    before = sha256(original).hexdigest()
    raw, w, h, bw, bh = module.page_bitmap(original, 1)
    with Image.open(BytesIO(raw)) as enhanced:
        assert enhanced.size == baseline.size == (bw, bh)
        # Integer LUT quantization can move a threshold-selected edge by 1 px;
        # this does not move source pixels or the rendered coordinate system.
        prior_extent, new_extent = dark_extent(baseline), dark_extent(enhanced)
        assert all(abs(a-b) <= 1 for a, b in zip(prior_extent, new_extent))
        assert sha256(original).hexdigest() == before
    observations.append({'probe': 'nonuniform_rotated_ink_extent', 'rotation': rotation, 'before_extent': prior_extent, 'after_extent': new_extent, 'passed': True})

calls = []
class Bitmap:
    def to_pil(self): return Image.new('RGB', (4, 4))
    def close(self): calls.append('bitmap_closed')
class Page:
    def get_size(self): return (1, 1)
    def render(self, **kwargs): return Bitmap()
    def close(self): calls.append('page_closed')
class Document:
    def __init__(self, raw): pass
    def __len__(self): return 1
    def __getitem__(self, index): return Page()
    def close(self): calls.append('document_closed')
with patch.object(module.pdfium, 'PdfDocument', Document), patch.object(module.ImageOps, 'autocontrast', side_effect=RuntimeError('synthetic failure')):
    try:
        module.page_bitmap(b'fictional', 1)
        raise AssertionError('expected failure')
    except RuntimeError:
        assert calls == ['bitmap_closed', 'page_closed', 'document_closed']
observations.append({'probe': 'contrast_failure_closes_native_resources', 'passed': True})

for invalid in (0, 2):
    calls.clear()
    with patch.object(module.pdfium, 'PdfDocument', Document):
        try:
            module.page_bitmap(b'fictional', invalid)
            raise AssertionError('expected rejection')
        except ServiceError as error:
            assert error.code == 'VERSION_CONFLICT'
            assert calls == ['document_closed']
    observations.append({'probe': 'invalid_page_rejected', 'page': invalid, 'passed': True})

original = source.getvalue()
value = PageOCRInput(document_version_id=UUID('00000000-0000-0000-0000-000000000001'), document_sha256=sha256(original).hexdigest(), page=1)
def fake_worker(raw, metadata):
    source_metadata = OCRPageSource(**metadata)
    assert source_metadata.bitmap_sha256 == sha256(raw).hexdigest()
    assert source_metadata.document_sha256 == value.document_sha256
    assert source_metadata.page == 1
    with Image.open(BytesIO(raw)) as raster:
        assert raster.size == (source_metadata.bitmap_width, source_metadata.bitmap_height)
    return SimpleNamespace(source=source_metadata)
with patch.object(module, 'run_ocr_page', fake_worker):
    module.predict_page(original, value)
observations.append({'probe': 'enhanced_bitmap_and_original_metadata_bound', 'passed': True})
print(json.dumps({'passed': len(observations), 'failed': 0, 'real_worker_calls': 0, 'observations': observations}, ensure_ascii=False, indent=2))
