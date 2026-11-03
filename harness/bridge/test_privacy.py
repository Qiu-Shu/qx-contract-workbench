"""Synthetic upload privacy checks. No user materials or model requests."""
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

import privacy


def prepare(tmp_path, text, **options):
    source = tmp_path / '张三-13800138000.txt'
    source.write_text(text, encoding='utf-8')
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'), **options)
    return result, Path(result['safe_path']).read_text(encoding='utf-8') if result['status'] == 'ready' else ''


def test_redacts_identifiers_names_organizations_addresses_without_changing_dates_money(tmp_path):
    original = ('姓名：张三，联系人：李四。张三与李四签约。\n'
                '甲方：上海星河科技有限公司，上海星河科技有限公司付款。\n'
                '电话：13800138000；座机：021-55667788；邮箱：zhang@example.com\n'
                '身份证号：110101199003071234；银行卡：6222021234567890123\n'
                '住址：上海市浦东新区测试路88号3室。\n'
                '2026年11月3日支付人民币12,500.50元。')
    result, safe = prepare(tmp_path, original)
    assert result['status'] == 'ready'
    for value in ('张三', '李四', '上海星河科技有限公司', '13800138000', '021-55667788',
                  'zhang@example.com', '110101199003071234', '6222021234567890123', '上海市浦东新区测试路88号3室'):
        assert value not in safe
        assert value not in json.dumps(result, ensure_ascii=False)
    assert '2026年11月3日支付人民币12,500.50元' in safe
    assert result['replacement_count'] >= 12
    assert (tmp_path / '张三-13800138000.txt').read_text(encoding='utf-8') == original
    assert list((tmp_path / 'vault').rglob('original.txt'))
    assert list((tmp_path / 'vault').rglob('mapping.sqlite'))
    manifest = json.loads(next((tmp_path / 'vault').rglob('manifest.json')).read_text(encoding='utf-8'))
    assert (tmp_path / 'vault' / manifest['safe_file']).resolve() == Path(result['safe_path']).resolve()
    assert (tmp_path / 'vault' / manifest['mapping_file']).is_file()


def test_longest_custom_phrase_wins_and_replacements_never_cascade(tmp_path):
    result, safe = prepare(tmp_path, '甲公司与甲公司法务👩‍⚖️；甲公司法务👩‍⚖️审查。',
                           custom_terms=['甲公司', '甲公司法务👩‍⚖️'])
    assert result['status'] == 'ready'
    assert result['replacement_count'] == 3
    assert '甲公司' not in safe and '法务' not in safe and '👩' not in safe
    tokens = re.findall(r'【[^】]+】', safe)
    assert len(tokens) == 3 and tokens[1] == tokens[2] and tokens[0] != tokens[1]


def test_context_is_opt_in_and_reuses_only_that_context(tmp_path):
    _, first = prepare(tmp_path, '电话13800138000', context_id='case-A')
    _, second = prepare(tmp_path, '电话13800138000', context_id='case-A')
    _, separate = prepare(tmp_path, '电话13800138000', context_id='case-B')
    _, isolated = prepare(tmp_path, '电话13800138000')
    assert first == second
    assert separate != first and isolated != first


@pytest.mark.parametrize('value', ['', ' \n\t', '\x00\x00'])
def test_unreadable_text_fails_without_a_safe_file(tmp_path, value):
    result, safe = prepare(tmp_path, value)
    assert result['status'] == 'failed' and not safe
    assert 'safe_path' not in result
    assert not list((tmp_path / 'vault').rglob('safe/*.txt'))


def test_parse_exception_is_generic_and_does_not_expose_original(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('秘密姓名张三在C:/private/原件.docx')
    monkeypatch.setattr(privacy.reader, 'parse', fail)
    result, _ = prepare(tmp_path, '电话13800138000')
    assert result['status'] == 'failed'
    assert '张三' not in json.dumps(result, ensure_ascii=False)
    assert 'private' not in json.dumps(result)
    assert not list((tmp_path / 'vault').rglob('safe/*.txt'))


def test_vault_inside_model_workspace_is_rejected(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    source = tmp_path / 'sample.txt'
    source.write_text('13800138000')
    result = privacy.prepare_upload(str(source), str(workspace / 'private'), workspace_dir=str(workspace))
    assert result['status'] == 'failed'
    assert result['error_code'] == 'VAULT_BOUNDARY'
    assert not (workspace / 'private').exists()


@pytest.mark.parametrize('kind', ['txt', 'md', 'csv', 'tsv', 'json', 'html', 'htm', 'rtf'])
def test_text_formats_are_safe_text_only(tmp_path, kind):
    value = {'html': '<p>13800138000</p>', 'htm': '<p>13800138000</p>',
             'rtf': r'{\rtf1\ansi 13800138000}', 'json': '{"phone":"13800138000"}'}
    source = tmp_path / ('sample.' + kind)
    source.write_text(value.get(kind, '13800138000'), encoding='utf-8')
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    assert Path(result['safe_path']).suffix == '.txt'
    assert '13800138000' not in Path(result['safe_path']).read_text(encoding='utf-8')


def test_docx_runs_and_metadata_do_not_bypass_redaction(tmp_path):
    from docx import Document
    source = tmp_path / '张三.docx'
    document = Document()
    paragraph = document.add_paragraph('姓名：')
    paragraph.add_run('张')
    paragraph.add_run('三')
    document.add_paragraph('电话13800138000')
    document.core_properties.author = '隐藏秘密作者'
    document.save(source)
    original = source.read_bytes()
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    safe = Path(result['safe_path']).read_text(encoding='utf-8')
    assert '张三' not in safe and '13800138000' not in safe and '隐藏秘密作者' not in safe
    assert source.read_bytes() == original


def test_cli_only_emits_safe_metadata(tmp_path):
    source = tmp_path / '秘密张三.txt'
    source.write_text('姓名：张三；电话13800138000', encoding='utf-8')
    command = subprocess.run([sys.executable, str(Path(privacy.__file__))],
                             input=json.dumps({'source_path': str(source), 'vault_dir': str(tmp_path / 'vault')}),
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    result = json.loads(command.stdout)
    assert command.returncode == 0 and result['status'] == 'ready'
    assert '张三' not in command.stdout + command.stderr
    assert '13800138000' not in command.stdout + command.stderr


def test_number_shaped_amounts_are_preserved_and_custom_terms_can_override(tmp_path):
    _, safe = prepare(tmp_path, '人民币13800138000元，金额110101199003071234元；电话：13900139000。另一个电话13800138000。')
    assert '13800138000元' in safe and '110101199003071234元' in safe
    assert '13900139000' not in safe
    assert safe.count('13800138000') == 1
    _, overridden = prepare(tmp_path, '金额13800138000元', custom_terms=['13800138000'])
    assert '13800138000' not in overridden


def test_phone_split_at_reader_chunk_boundary_still_redacts(tmp_path):
    _, safe = prepare(tmp_path, '测试。' * 1332 + '13800138000')
    assert '13800138000' not in safe and '1380' not in safe


def test_unicode_equivalent_custom_terms_match_without_splitting_emoji(tmp_path):
    _, safe = prepare(tmp_path, 'Jose\u0301 👩‍⚖️ Jose\u0301', custom_terms=['José', '👩‍⚖️'])
    assert 'José' not in safe and 'Jose' not in safe and '👩' not in safe


def test_context_mapping_is_consistent_under_concurrent_uploads(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    sources = []
    for number in range(6):
        source = tmp_path / f'synthetic-{number}.txt'
        source.write_text('电话13800138000', encoding='utf-8')
        sources.append(source)
    def upload(source):
        return privacy.prepare_upload(str(source), str(tmp_path / 'vault'), context_id='one-batch')
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(upload, sources))
    assert all(result['status'] == 'ready' for result in results), results
    assert len({Path(result['safe_path']).read_text(encoding='utf-8') for result in results}) == 1


@pytest.mark.parametrize('kind', ['xlsx', 'xls', 'pptx', 'odt', 'ods', 'odp'])
def test_office_formats_use_existing_reader_and_emit_only_redacted_text(tmp_path, kind):
    source = tmp_path / ('synthetic.' + kind)
    if kind == 'xlsx':
        import xlsxwriter
        with xlsxwriter.Workbook(source) as book:
            book.add_worksheet('Sheet').write(0, 0, '13800138000')
    elif kind == 'xls':
        import xlwt
        book = xlwt.Workbook()
        book.add_sheet('Sheet').write(0, 0, '13800138000')
        book.save(str(source))
    elif kind == 'pptx':
        from pptx import Presentation
        from pptx.util import Inches
        book = Presentation()
        slide = book.slides.add_slide(book.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, Inches(5), Inches(1)).text = '13800138000'
        book.save(source)
    else:
        from odf import opendocument, text, draw, table
        factory = {'odt': 'OpenDocumentText', 'ods': 'OpenDocumentSpreadsheet', 'odp': 'OpenDocumentPresentation'}[kind]
        book = getattr(opendocument, factory)()
        paragraph = text.P(text='13800138000')
        if kind == 'odt':
            book.text.addElement(paragraph)
        elif kind == 'ods':
            sheet = table.Table(name='Sheet')
            row = table.TableRow()
            cell = table.TableCell(valuetype='string')
            cell.addElement(paragraph)
            row.addElement(cell)
            sheet.addElement(row)
            book.spreadsheet.addElement(sheet)
        else:
            box = draw.TextBox()
            box.addElement(paragraph)
            frame = draw.Frame()
            frame.addElement(box)
            page = draw.Page(name='Slide1', masterpagename='Default')
            page.addElement(frame)
            book.presentation.addElement(page)
        book.save(str(source))
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    assert '13800138000' not in Path(result['safe_path']).read_text(encoding='utf-8')
    assert result['replacement_count'] > 0


def synthetic_image(phone='13800138000'):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1100, 180), 'white')
    ImageDraw.Draw(image).text((25, 50), '电话：' + phone,
                              font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 48), fill='black')
    return image


@pytest.mark.parametrize('kind', ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tif', 'tiff'])
def test_image_formats_ocr_before_emitting_text(tmp_path, kind):
    source = tmp_path / ('synthetic.' + kind)
    synthetic_image().save(source)
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    safe = Path(result['safe_path']).read_text(encoding='utf-8')
    assert '13800138000' not in safe and result['replacement_count'] >= 1


def test_all_tiff_frames_are_ocr_redacted(tmp_path):
    source = tmp_path / 'multi.tiff'
    synthetic_image().save(source, save_all=True, append_images=[synthetic_image('13900139000')])
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    safe = Path(result['safe_path']).read_text(encoding='utf-8')
    assert '13800138000' not in safe and '13900139000' not in safe
    assert result['replacement_count'] == 2


def native_pdf():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 300] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               b'<< /Length 45 >>\nstream\nBT /F1 18 Tf 30 240 Td (13700137000) Tj ET\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    raw = bytearray(b'%PDF-1.4\n')
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(f'{number} 0 obj\n'.encode() + body + b'\nendobj\n')
    start = len(raw)
    raw.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets:
        raw.extend(f'{offset:010d} 00000 n \n'.encode())
    raw.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF'.encode())
    return bytes(raw)


def test_mixed_pdf_native_image_and_later_scanned_pages_are_all_redacted(tmp_path):
    from io import BytesIO
    import pypdfium2 as pdfium
    source = tmp_path / 'mixed.pdf'
    scanned = BytesIO()
    synthetic_image('13900139000').save(scanned, format='PDF')
    jpeg = BytesIO()
    synthetic_image('13800138000').save(jpeg, format='JPEG')
    with pdfium.PdfDocument(native_pdf()) as document, pdfium.PdfDocument(scanned.getvalue()) as scan:
        page = document[0]
        image = pdfium.PdfImage.new(document)
        image.load_jpeg(BytesIO(jpeg.getvalue()))
        image.set_matrix(pdfium.PdfMatrix(550, 0, 0, 90, 20, 50))
        page.insert_obj(image)
        page.gen_content()
        page.close()
        document.import_pages(scan)
        document.save(source)
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'ready', result
    safe = Path(result['safe_path']).read_text(encoding='utf-8')
    for phone in ['13700137000', '13800138000', '13900139000']:
        assert phone not in safe
    assert result['replacement_count'] >= 3


def test_ocr_failure_cannot_fall_back_to_original_image(tmp_path, monkeypatch):
    from cn_contract.documents import material_ocr
    source = tmp_path / 'synthetic.png'
    synthetic_image().save(source)
    def fail(_):
        raise RuntimeError('sensitive runtime diagnostics')
    monkeypatch.setattr(material_ocr, 'recognize', fail)
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'failed' and 'safe_path' not in result
    assert 'sensitive' not in json.dumps(result)


@pytest.mark.parametrize('kind', ['pdf', 'png', 'doc', 'ppt'])
def test_corrupt_files_are_rejected_without_original_fallback(tmp_path, kind):
    source = tmp_path / ('synthetic.' + kind)
    source.write_bytes(b'corrupt 13800138000 bytes')
    result = privacy.prepare_upload(str(source), str(tmp_path / 'vault'))
    assert result['status'] == 'failed' and 'safe_path' not in result


def test_buffered_library_diagnostics_stay_private_even_when_it_raises():
    script = '''import privacy
try:
    with privacy._quiet_libraries():
        print('sensitive diagnostic with raw source text', end='')
        raise ValueError('failure')
except ValueError:
    print('safe failure result')
'''
    command = subprocess.run([sys.executable, '-c', script], cwd=Path(privacy.__file__).parent,
                             capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert command.returncode == 0
    assert command.stdout.strip() == 'safe failure result'
    assert command.stderr == ''
