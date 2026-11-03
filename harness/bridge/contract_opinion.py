"""Contract opinions as safe HTML and Word documents with the same supplied content."""
from hashlib import sha256
from html import escape
from io import BytesIO
from math import ceil
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4
from zipfile import ZipFile

from docx_delivery import _filename, _publish, _store, _string, _w, _xml


# Derived only from the user's supplied reference layout; no client facts or injected browser CSS.
CSS = '''body{font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#253142;background:#f4f6f8;margin:0;font-size:16px;line-height:1.85}
main{max-width:1050px;margin:32px auto;padding:42px;background:#fff}
h1{font-size:29px;color:#142c46;line-height:1.5;margin:0 0 12px}h2{font-size:22px;line-height:1.6;margin:36px 0 12px;color:#253142}h3,h4,h5,h6{font-size:18px;line-height:1.6;margin:26px 0 10px;color:#253142}
p{margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}h1,h2,h3,h4,h5,h6{white-space:pre-wrap;overflow-wrap:anywhere}.subtitle{color:#58677a;font-size:15px;margin-top:0}
table{width:100%;border-collapse:collapse;font-size:14px;table-layout:fixed}td,th{border:1px solid #cbd4df;padding:12px;vertical-align:top;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere}th{background:#ecf2f8;font-weight:600}thead{display:table-header-group}.table{overflow-x:auto;margin:18px 0}
a{color:#14528a;text-underline-offset:3px;overflow-wrap:anywhere}.references{color:#58677a;font-size:14px;margin-top:20px}.references p{margin:6px 0}.references-label{font-weight:600}
@media(max-width:1134px){main{margin:24px;padding:32px}}@media(max-width:650px){main{margin:0;padding:22px}h1{font-size:24px}h2{font-size:20px}.table table{min-width:620px}}
@media print{@page{size:A4;margin:20mm}body{background:#fff;font-size:11pt;line-height:1.65}main{max-width:none;margin:0;padding:0}h1{font-size:21pt}h2{font-size:16pt}h3,h4,h5,h6{font-size:13pt}h1,h2,h3,h4,h5,h6{break-after:avoid}p{orphans:2;widows:2}.short-row{break-inside:avoid}a{color:inherit}.table{overflow:visible}table{font-size:9.5pt;min-width:0!important}td,th{padding:7px}}
'''


def _base(filename):
    _string(filename, 'filename', empty=False)
    base = str(Path(filename).with_suffix('')) if Path(filename).suffix.lower() in {'.html', '.docx'} else filename
    if not base.strip() or base in {'.', '..'}: raise ValueError('filename 需要普通文件名。')
    _filename(base+'.docx')
    return base


def _list(value, label):
    if not isinstance(value, list): raise ValueError(f'{label} 必须为列表。')
    return value


def _url(value):
    _string(value, '来源链接', empty=False)
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {'http', 'https'} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or re.search(r'[\x00-\x20\x7f<>"\\]', value)):
            raise ValueError()
        parsed.port
    except ValueError as error:
        raise ValueError('来源链接仅接受不含控制字符或账号密码的完整 http(s) URL。') from error
    return value


def _sections(sections, counts):
    result = []
    for section in _list(sections, 'sections/subsections'):
        if not isinstance(section, dict): raise ValueError('每个章节必须为对象。')
        unknown = set(section)-{'heading', 'paragraphs', 'table', 'references', 'subsections'}
        if unknown: raise ValueError('章节含未支持的字段：'+', '.join(sorted(unknown))+'，请放入正文而非丢弃。')
        heading = _string(section.get('heading', ''), 'heading')
        paragraphs = [_string(p, 'paragraphs中的正文') for p in _list(section.get('paragraphs', []), 'paragraphs')]
        table = section.get('table')
        if table is not None:
            if not isinstance(table, dict) or set(table)-{'headers', 'rows'}: raise ValueError('table 只接受 headers 和 rows。')
            headers = [_string(v, '表头') for v in _list(table.get('headers'), 'table.headers')]
            if not headers: raise ValueError('表格需要至少一个表头。')
            rows = []
            for row in _list(table.get('rows', []), 'table.rows'):
                _list(row, '表格行')
                if len(row) != len(headers): raise ValueError('表格每行单元格数必须与表头一致，不会截断多余内容。')
                rows.append([_string(v, '表格单元格') for v in row])
            table = {'headers': headers, 'rows': rows}; counts['tables'] += 1; counts['rows'] += len(rows)
        references = []
        for reference in _list(section.get('references', []), 'references'):
            if not isinstance(reference, dict) or set(reference)-{'label', 'url'}: raise ValueError('references 每项只接受 label 和 url。')
            url = _url(reference.get('url'))
            references.append({'label': _string(reference.get('label', url), '来源名称'), 'url': url})
        counts['sections'] += 1; counts['paragraphs'] += len(paragraphs); counts['references'] += len(references)
        result.append({'heading': heading, 'paragraphs': paragraphs, 'table': table,
                       'references': references, 'subsections': _sections(section.get('subsections', []), counts)})
    return result


def _widths(columns, total):
    shares = [0.12, 0.20, 0.34, 0.34] if columns == 4 else [1/columns]*columns
    widths = [int(total*share) for share in shares]
    widths[-1] += total-sum(widths)
    return widths


def _short_row(row, widths):
    # Layout estimate only: preserve short rows together while letting long opinions flow across pages.
    for value, width in zip(row, widths):
        columns = max(1, width/20/10-1.5)
        lines = sum(max(1, ceil(sum(1 if unicodedata.east_asian_width(c) in 'WF' else 0.5 for c in line)/columns))
                    for line in value.split('\n'))
        if lines > 10: return False
    return True


def _html(title, subtitle, sections):
    out = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
           '<title>'+escape(title)+'</title><style>'+CSS+'</style></head><body><main>',
           '<header><h1>'+escape(title)+'</h1>']
    if subtitle: out.append('<p class="subtitle">'+escape(subtitle)+'</p>')
    out.append('</header>')

    def section_html(section, depth=2):
        out.append('<section>')
        if section['heading']: out.append(f'<h{min(depth, 6)}>'+escape(section['heading'])+f'</h{min(depth, 6)}>')
        out.extend('<p>'+escape(p)+'</p>' for p in section['paragraphs'])
        table = section['table']
        if table:
            widths = _widths(len(table['headers']), 9400)
            out.append('<div class="table" role="region" aria-label="'+escape(section['heading'] or '意见表', quote=True)+'" tabindex="0"><table><colgroup>')
            out.extend(f'<col style="width:{width/94:.4f}%">' for width in widths)
            out.append('</colgroup><thead><tr>')
            out.extend('<th scope="col">'+escape(h)+'</th>' for h in table['headers'])
            out.append('</tr></thead><tbody>')
            for row in table['rows']:
                out.append('<tr'+(' class="short-row"' if _short_row(row, widths) else '')+'>')
                out.extend('<td>'+escape(v)+'</td>' for v in row); out.append('</tr>')
            out.append('</tbody></table></div>')
        for child in section['subsections']: section_html(child, depth+1)
        if section['references']:
            out.append('<div class="references"><p class="references-label">参考来源</p>')
            for reference in section['references']:
                out.append('<p><a href="'+escape(reference['url'], quote=True)+'" target="_blank" rel="noopener noreferrer">'+escape(reference['label'])+'</a></p>')
            out.append('</div>')
        out.append('</section>')

    for section in sections: section_html(section)
    out.append('</main></body></html>')
    return '\n'.join(out).encode('utf-8')


def _word(title, subtitle, sections):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.shared import Cm, Pt, RGBColor, Twips
    doc = Document(); page = doc.sections[0]
    page.page_width = Cm(21); page.page_height = Cm(29.7)
    page.top_margin = page.bottom_margin = Cm(2.1)
    page.left_margin = page.right_margin = Cm(2.2)
    for name in ('Normal', 'Title', 'Subtitle', *[f'Heading {i}' for i in range(1, 10)]):
        style = doc.styles[name]; style.font.name = 'Microsoft YaHei'; style.font.size = Pt(12)
        style.font.color.rgb = RGBColor.from_string('253142')
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'): fonts.attrib.pop(_w(attribute), None)
        fonts.set(_w('eastAsia'), 'Microsoft YaHei')
        for border in style.element.findall('./'+_w('pPr')+'/'+_w('pBdr')): border.getparent().remove(border)
        paragraph = style.paragraph_format
        paragraph.line_spacing = 1.65; paragraph.space_after = Pt(8)
        paragraph.keep_together = False; paragraph.keep_with_next = name.startswith('Heading') or name in {'Title', 'Subtitle'}
        paragraph.page_break_before = False; paragraph.widow_control = True
        if name.startswith('Heading'):
            style.font.bold = True; style.font.size = Pt(16 if name == 'Heading 1' else 13)
            paragraph.space_before = Pt(16); paragraph.space_after = Pt(8)
    doc.styles['Title'].font.size = Pt(21); doc.styles['Title'].font.bold = True
    doc.styles['Title'].font.color.rgb = RGBColor.from_string('142C46')
    doc.styles['Subtitle'].font.size = Pt(11); doc.styles['Subtitle'].font.color.rgb = RGBColor.from_string('58677A')
    doc.core_properties.title = title; doc.core_properties.subject = subtitle
    doc.core_properties.author = ''; doc.core_properties.last_modified_by = ''; doc.core_properties.comments = ''
    doc.add_paragraph(title, 'Title')
    if subtitle: doc.add_paragraph(subtitle, 'Subtitle')
    total = page.page_width.twips-page.left_margin.twips-page.right_margin.twips

    def section_word(section, depth=1):
        if section['heading']: doc.add_paragraph(section['heading'], f'Heading {min(depth, 9)}')
        for text in section['paragraphs']: doc.add_paragraph(text)
        value = section['table']
        if value:
            table = doc.add_table(rows=1, cols=len(value['headers'])); table.style = 'Table Grid'; table.autofit = False
            widths = _widths(len(value['headers']), total)
            for column, width in zip(table.columns, widths): column.width = Twips(width)
            for index, contents in enumerate([value['headers'], *value['rows']]):
                row = table.rows[0] if index == 0 else table.add_row()
                if index == 0: row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
                if index == 0 or _short_row(contents, widths): row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                for cell, text, width in zip(row.cells, contents, widths):
                    cell.width = Twips(width); cell.text = text
                    if index == 0:
                        shading = OxmlElement('w:shd'); shading.set(_w('fill'), 'ECF2F8'); cell._tc.get_or_add_tcPr().append(shading)
                    for p in cell.paragraphs:
                        p.paragraph_format.line_spacing = 1.35; p.paragraph_format.space_after = Pt(4)
                        p.paragraph_format.keep_with_next = False; p.paragraph_format.keep_together = False
                        for run in p.runs: run.font.size = Pt(10); run.bold = index == 0
        for child in section['subsections']: section_word(child, depth+1)
        if section['references']:
            label = doc.add_paragraph('参考来源'); label.paragraph_format.keep_with_next = True
            for reference in section['references']:
                p = doc.add_paragraph()
                hyperlink = OxmlElement('w:hyperlink')
                rid = p.part.relate_to(reference['url'], RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
                hyperlink.set('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id', rid)
                run = OxmlElement('w:r'); properties = OxmlElement('w:rPr')
                color = OxmlElement('w:color'); color.set(_w('val'), '14528A'); properties.append(color)
                underline = OxmlElement('w:u'); underline.set(_w('val'), 'single'); properties.append(underline)
                run.append(properties); text = OxmlElement('w:t'); text.text = reference['label']; run.append(text)
                hyperlink.append(run); p._p.append(hyperlink)
                p.add_run('（'+reference['url']+'）').font.size = Pt(9)

    for section in sections: section_word(section)
    output = BytesIO(); doc.save(output)
    with ZipFile(BytesIO(output.getvalue())) as archive:
        for name in archive.namelist():
            if name.endswith(('.xml', '.rels')): _xml(archive.read(name))
    return output.getvalue()


def _publish_html(store, base, data):
    directory = store.root/'drafts'; directory.mkdir(exist_ok=True); store.safe(directory, internal=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=directory, prefix='.qx-opinion-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        filename = base+'.html'
        while True:
            target = store.safe(directory/filename, must_exist=False)
            try:
                os.link(temporary, target)
                return {'path': str(target), 'relative_path': target.relative_to(store.root).as_posix(),
                        'bytes': len(data), 'sha256': sha256(data).hexdigest()}
            except FileExistsError: filename = base+'-'+uuid4().hex[:8]+'.html'
    finally:
        if temporary is not None and temporary.exists(): store.safe(temporary).unlink()


def write_contract_opinion(workspace, filename, title, subtitle='', sections=None):
    """Write the supplied opinion as escaped responsive HTML and a matching editable DOCX.

    Sections use heading, paragraphs, optional table {headers, rows}, references
    [{label, url}], and recursive subsections. No legal conclusions are generated.
    """
    base = _base(filename); _string(title, 'title', empty=False); _string(subtitle, 'subtitle')
    counts = {'sections': 0, 'paragraphs': 0, 'tables': 0, 'rows': 0, 'references': 0}
    normalized = _sections([] if sections is None else sections, counts)
    html_data = _html(title, subtitle, normalized); word_data = _word(title, subtitle, normalized)
    store = _store(workspace)
    word = _publish(store, base+'.docx', word_data)
    try:
        html = _publish_html(store, Path(word['path']).stem, html_data)
    except Exception:
        # This is the new file from this call, never a source or an existing user's document.
        written = store.safe(word['path'])
        if sha256(written.read_bytes()).hexdigest() == word['sha256']: written.unlink()
        raise
    return {'status': 'draft', 'html': html, 'word': word, 'html_path': html['path'], 'word_path': word['path'],
            'counts': counts, 'notice': 'HTML 与 Word 使用同一份传入正文。请核对事实、条款对应和法律来源；未自动补写结论或日期。'}
