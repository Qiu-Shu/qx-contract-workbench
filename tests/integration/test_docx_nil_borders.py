"""Fictional OOXML: explicit no-border metadata must not hide ordinary text."""
from xml.etree import ElementTree as ET

import pytest

from tests.integration.test_docx_office_parts import W, edited, office_document, parse, saved


def border_document(name, value='nil', defect=None):
    def insert(root):
        normal = next(node for node in root if node.get(f'{{{W}}}styleId') == 'Normal')
        props = normal.find(f'{{{W}}}pPr')
        if props is None:
            props = ET.SubElement(normal, f'{{{W}}}pPr')
        parent = props if defect == 'parent' else ET.SubElement(props, f'{{{W}}}pBdr')
        node = ET.SubElement(parent, f'{{{W}}}{name}', {f'{{{W}}}val': value})
        if defect == 'child':
            ET.SubElement(node, f'{{{W}}}vanish')
        elif defect == 'attribute':
            node.set('unrecognized', 'true')
        elif defect == 'text':
            node.text = 'SYNTHETIC must remain unread'
        elif defect == 'tail':
            node.tail = 'SYNTHETIC must remain unread'
    return edited(saved(office_document()), {'word/styles.xml': insert})


@pytest.mark.parametrize('name', ['between', 'bar'])
@pytest.mark.parametrize('value', ['nil', 'none'])
def test_explicit_no_border_does_not_block_plain_contract(name, value):
    result = parse(border_document(name, value))
    assert len(result.anchors) == 3
    assert result.unsupported_parts == result.quality_issues == ()
    assert 'word/styles.xml:metadata_read' in result.parts


@pytest.mark.parametrize('name', ['between', 'bar'])
@pytest.mark.parametrize('defect', ['parent', 'child', 'attribute', 'text', 'tail'])
def test_malformed_no_border_still_requires_manual_reading(name, defect):
    result = parse(border_document(name, defect=defect))
    assert result.anchors == ()
    assert 'word/styles.xml:unsupported' in result.parts


@pytest.mark.parametrize('name', ['between', 'bar'])
def test_drawn_border_not_implicitly_claimed_supported(name):
    result = parse(border_document(name, 'single'))
    assert result.anchors == ()
    assert 'word/styles.xml:unsupported' in result.parts
