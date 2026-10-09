"""OCR raster quality and allocation budget; no model imports or predictions."""
from io import BytesIO
import math

from PIL import Image, ImageOps
import pypdfium2 as pdfium
import pytest

from cn_contract.documents import ocr_candidates as module
from cn_contract.security import ServiceError


def fake_page(monkeypatch, width, height):
    calls = []

    class Raster:
        def __init__(self, scale):
            self.width = math.ceil(width * scale)
            self.height = math.ceil(height * scale)

        def save(self, stream, format):
            stream.write(b'fictional raster')

    class Bitmap:
        def __init__(self, scale): self.scale = scale
        def to_pil(self): return Raster(self.scale)
        def close(self): calls.append('bitmap_closed')

    class Page:
        def get_size(self): return width, height
        def render(self, scale):
            calls.append(scale)
            return Bitmap(scale)
        def close(self): calls.append('page_closed')

    class Document:
        def __init__(self, raw): pass
        def __len__(self): return 1
        def __getitem__(self, index): return Page()
        def close(self): calls.append('document_closed')

    monkeypatch.setattr(module.pdfium, 'PdfDocument', Document)
    # Allocation tests use a fake raster; real pixel behavior is checked below.
    monkeypatch.setattr(ImageOps, 'autocontrast', lambda image: image)
    return calls


@pytest.mark.parametrize('width,height,scale', [
    (600, 200, 4), (595, 842, 4), (842, 595, 4),
    (1000, 1000, 4), (1000.01, 1000, 2),
    (2000, 2000, 2), (4096, 1, 2), (2048, 1, 4),
])
def test_render_uses_higher_resolution_within_existing_budget(monkeypatch, width, height, scale):
    calls = fake_page(monkeypatch, width, height)
    raw, w, h, bw, bh = module.page_bitmap(b'fixture', 1)
    assert calls == [scale, 'bitmap_closed', 'page_closed', 'document_closed']
    assert (w, h, bw, bh) == (width, height, math.ceil(width*scale), math.ceil(height*scale))
    assert max(bw, bh) <= 8192 and bw*bh <= 16_000_000


@pytest.mark.parametrize('width,height', [
    (4096.01, 1), (2000.01, 2000), (float('inf'), 200),
    (600, float('nan')), (0, 200), (600, -1), (1e308, 200),
])
def test_invalid_or_oversized_page_is_rejected_before_allocation(monkeypatch, width, height):
    calls = fake_page(monkeypatch, width, height)
    with pytest.raises(ServiceError) as error:
        module.page_bitmap(b'fixture', 1)
    assert error.value.code == 'FILE_LIMIT'
    assert calls == ['page_closed', 'document_closed']


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_actual_pdf_raster_preserves_rotated_fractional_page_mapping(rotation):
    doc = pdfium.PdfDocument.new()
    page = doc.new_page(120.25, 80.5)
    page.set_rotation(rotation)
    page.close()
    stream = BytesIO()
    doc.save(stream)
    doc.close()
    raw, w, h, bw, bh = module.page_bitmap(stream.getvalue(), 1)
    with Image.open(BytesIO(raw)) as image:
        assert image.size == (bw, bh) == (math.ceil(w*4), math.ceil(h*4))
    # Source mapping uses actual dimensions, including the raster edge rounding.
    assert bw*(w/bw) == pytest.approx(w)
    assert bh*(h/bh) == pytest.approx(h)


@pytest.mark.parametrize('ink,paper', [(208, 224), (24, 40)])
def test_faint_ink_is_enhanced_without_moving_its_page_position(ink, paper):
    image = Image.new('RGB', (100, 60), (paper,)*3)
    image.paste((ink,)*3, (20, 10, 60, 40))
    original = BytesIO()
    image.save(original, format='PDF', resolution=144)
    before = original.getvalue()
    raw, w, h, bw, bh = module.page_bitmap(before, 1)
    with Image.open(BytesIO(raw)) as raster:
        assert (w, h, bw, bh) == (50, 30, 200, 120)
        # PDF image encoding introduces edge ringing; require useful separation,
        # not artificial pure-black/pure-white interior pixels.
        assert min(raster.getpixel((180, 100))) - max(raster.getpixel((80, 40))) >= 160
        # Contrast changes values, never the location or extent of the ink.
        assert raster.getpixel((80, 40)) < raster.getpixel((10, 40))
    assert original.getvalue() == before


@pytest.mark.parametrize('value', [0, 220, 255])
def test_uniform_page_remains_uniform_and_has_no_invented_ink(value):
    original = BytesIO()
    Image.new('RGB', (100, 60), (value,)*3).save(original, format='PDF')
    raw, *_ = module.page_bitmap(original.getvalue(), 1)
    with Image.open(BytesIO(raw)) as raster:
        assert raster.getextrema() == ((value, value),)*3


def test_full_range_color_raster_keeps_exact_pixels():
    original = BytesIO()
    image = Image.new('RGB', (100, 60), 'white')
    image.paste('black', (10, 10, 30, 40))
    image.paste('red', (60, 10, 90, 40))
    image.save(original, format='PDF')
    raw, *_ = module.page_bitmap(original.getvalue(), 1)
    document = pdfium.PdfDocument(original.getvalue())
    page = document[0]
    bitmap = page.render(scale=4)
    try:
        with Image.open(BytesIO(raw)) as raster:
            assert raster.tobytes() == bitmap.to_pil().tobytes()
    finally:
        bitmap.close()
        page.close()
        document.close()
