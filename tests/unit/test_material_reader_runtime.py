"""Real synthetic files for the readers used by the Harness bridge; no model/API."""
from io import BytesIO
from uuid import uuid4

import pytest
from cn_contract.config import load_settings
from cn_contract.documents.material_adapter import material_type, parse_material


@pytest.mark.parametrize('kind', ['xlsx', 'pptx'])
def test_office_readers_extract_actual_file_values(kind):
    buffer = BytesIO()
    if kind == 'xlsx':
        from xlsxwriter import Workbook
        with Workbook(buffer, {'in_memory': True}) as book:
            book.add_worksheet('虚构材料').write('A1', '验收合格后十日内付款35000元')
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        from pptx import Presentation
        from pptx.util import Inches
        book = Presentation()
        slide = book.slides.add_slide(book.slide_layouts[6])
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1)).text = '验收合格后十日内付款35000元'
        book.save(buffer)
        mime = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    raw = buffer.getvalue()
    assert material_type(raw, 'synthetic.' + kind, mime) == kind
    result = parse_material(raw, 'synthetic.' + kind, uuid4(), load_settings())
    assert any('验收合格后十日内付款35000元' in anchor.quote for anchor in result.anchors)


@pytest.mark.parametrize('kind', ['png', 'pdf'])
def test_local_ocr_reads_actual_image_and_scanned_pdf(kind):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1200, 220), 'white')
    ImageDraw.Draw(image).text((50, 70), 'PAYMENT 35000', font=ImageFont.load_default(size=64), fill='black')
    buffer = BytesIO()
    image.save(buffer, format=kind.upper())
    raw = buffer.getvalue()
    assert material_type(raw, 'synthetic.' + kind, 'image/png' if kind == 'png' else 'application/pdf') == kind
    result = parse_material(raw, 'synthetic.' + kind, uuid4(), load_settings())
    assert any('35000' in anchor.quote for anchor in result.anchors)
    assert any('OCR_IS_UNVERIFIED' in item for item in result.quality_issues)
