from pathlib import Path
import pytest
from title_excerpt import excerpts


def test_extracts_body_from_generic_filename_and_limits_text(tmp_path):
    source = tmp_path / '材料.txt'
    source.write_text('虚构采购合同\n' + '付款条件。' * 10000, encoding='utf-8')
    result = excerpts(tmp_path, [str(source)])
    assert result[0]['text'].startswith('虚构采购合同')
    assert len(result[0]['text']) <= 6000


def test_rejects_outside_workspace_without_reading_it(tmp_path):
    workspace = tmp_path / 'workspace'
    outside = tmp_path / 'outside.txt'
    outside.write_text('不得出现在摘要里', encoding='utf-8')
    result = excerpts(workspace, [str(outside)])
    assert result[0]['text'] == ''


def test_docx_body_not_just_filename(tmp_path):
    from docx import Document
    source = tmp_path / '材料.docx'
    doc = Document()
    doc.add_paragraph('虚构劳动争议：申请人请求支付拖欠工资。')
    doc.save(source)
    assert '拖欠工资' in excerpts(tmp_path, [str(source)])[0]['text']


def test_image_object_without_extension_is_read_with_attachment_type(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    source = tmp_path / ('a' * 64)
    image = Image.new('RGB', (600, 120), 'white')
    ImageDraw.Draw(image).text((20, 20), '虚构租赁合同 1234', fill='black', font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 44))
    image.save(source, format='PNG')
    assert '租赁合同' in excerpts(tmp_path, [str(source)], image_paths=[str(source)])[0]['text']
