"""Small real-file regression for the expanded local attachment readers."""
from io import BytesIO
from uuid import uuid4

import pytest

from cn_contract.config import load_settings
from cn_contract.documents.material_adapter import material_type, parse_material
from cn_contract.security import ServiceError


@pytest.mark.parametrize('factory,extension,mime', [
    ('OpenDocumentText', 'odt', 'application/vnd.oasis.opendocument.text'),
    ('OpenDocumentPresentation', 'odp', 'application/vnd.oasis.opendocument.presentation'),
])
def test_opendocument_headings_and_paragraphs_keep_reading_order(factory,extension,mime):
    from odf import opendocument, text, draw
    document = getattr(opendocument, factory)()
    container = document.text if extension == 'odt' else draw.TextBox()
    container.addElement(text.H(outlinelevel=1, text='合同条款'))
    container.addElement(text.P(text='验收合格后十日内付款'))
    if extension == 'odp':
        frame=draw.Frame();frame.addElement(container)
        page=draw.Page(name='Slide1',masterpagename='Default');page.addElement(frame)
        document.presentation.addElement(page)
    output=BytesIO();document.save(output);raw=output.getvalue()
    assert material_type(raw,'source.'+extension,mime)==extension
    result=parse_material(raw,'source.'+extension,uuid4(),load_settings())
    assert [a.quote for a in result.anchors]==['合同条款','验收合格后十日内付款']


def test_text_encodings_and_inert_html():
    for encoding in ('utf-8-sig','utf-16','gb18030'):
        result=parse_material('验收合格后十日内付款'.encode(encoding),'source.txt',uuid4(),load_settings())
        assert result.anchors[0].quote=='验收合格后十日内付款'
    result=parse_material(b'<p>Actual clause</p><script>secret-script</script>','source.html',uuid4(),load_settings())
    assert [a.quote for a in result.anchors]==['Actual clause']


def test_wrong_binary_type_is_not_a_readable_attachment():
    for name,mime in [('wrong.xls','application/vnd.ms-excel'),('wrong.png','image/png')]:
        with pytest.raises(ServiceError):material_type(b'not a document',name,mime)
