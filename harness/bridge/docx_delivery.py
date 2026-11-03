"""Non-destructive DOCX review and clean litigation document generation."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import posixpath
import re
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from lxml import etree as ET
from store import MaterialStore

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
OFFICE_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
NS = {'w': W}
MANIFEST = Path(__file__).resolve().parents[1] / 'config/templates/catalog.json'


def _w(name):
    return f'{{{W}}}{name}'


def _xml(data):
    parser = ET.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    root = ET.fromstring(data, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('不处理含外部实体或 DTD 的 Word XML。')
    return root


def _bytes(root):
    return ET.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)


def _store(workspace):
    return workspace if isinstance(workspace, MaterialStore) else MaterialStore(workspace)


def _load(workspace, source):
    from reader import available_memory
    store = _store(workspace)
    path = store.safe(source)
    if path.suffix.lower() != '.docx':
        raise ValueError('本工具只处理 .docx；请先另存 Word 文档。')
    budget = max(1, available_memory() // 8)
    memory_notice = '原件已保留，但本机当前可用内存不足以整体处理此 DOCX；请释放内存后重试。'
    if path.stat().st_size > budget: raise ValueError(memory_notice)
    data = path.read_bytes()
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) != len({i.filename for i in infos}): raise ValueError('DOCX 含重复部件，无法安全定位。')
            if sum(i.file_size for i in infos) + len(data) > budget: raise ValueError(memory_notice)
            parts = {i.filename: archive.read(i) for i in infos}
        for name, content in parts.items():
            if name.endswith(('.xml', '.rels')): _xml(content)
        root = _xml(parts['word/document.xml'])
    except (BadZipFile, KeyError, ET.XMLSyntaxError) as error:
        raise ValueError('DOCX 包或 XML 损坏，未修改原件。') from error
    if root.tag != _w('document'):
        raise ValueError('当前仅支持常见 WordprocessingML DOCX，未修改原件。')
    return store, path, parts, root, sha256(data).hexdigest()


def _text(paragraph):
    values = []
    for node in paragraph.iter():
        if node.tag not in {_w('t'), _w('tab'), _w('br'), _w('cr')}: continue
        ancestors = list(node.iterancestors())
        if next((a for a in ancestors if a.tag == _w('p')), None) is not paragraph: continue
        if any(a.tag in {_w('del'), _w('moveFrom')} for a in ancestors): continue
        values.append(node.text or '' if node.tag == _w('t') else '\t' if node.tag == _w('tab') else '\n')
    return ''.join(values)


def _unsupported(paragraph):
    reasons = set()
    if any(a.tag not in {_w(n) for n in ('document', 'body', 'tbl', 'tr', 'tc')} for a in paragraph.iterancestors()):
        reasons.add('内容控件、文本框或其他复杂容器')
    allowed_children = {_w(n) for n in ('pPr', 'r', 'commentRangeStart', 'commentRangeEnd', 'bookmarkStart', 'bookmarkEnd', 'proofErr')}
    if any(c.tag not in allowed_children for c in paragraph): reasons.add('既有修订、超链接、域或复杂段落对象')
    if paragraph.xpath('.//w:pPrChange | .//w:rPrChange | .//w:ins | .//w:del', namespaces=NS):
        reasons.add('既有修订')
    for run in paragraph.findall(_w('r')):
        if any(c.tag not in {_w(n) for n in ('rPr', 't', 'tab', 'br', 'cr', 'commentReference')} for c in run):
            reasons.add('图片、域或其他非普通文字对象')
    return sorted(reasons)


def _paragraphs(root):
    result = []
    for index, paragraph in enumerate(root.xpath('./w:body//w:p', namespaces=NS), 1):
        identifier = f'p{index:06d}-' + sha256(ET.tostring(paragraph)).hexdigest()[:16]
        result.append((identifier, paragraph))
    return result


def inspect_docx(workspace, source, offset=0, limit=100):
    """Read main-body/table paragraphs; IDs are tied to exact paragraph XML and order."""
    store, path, parts, root, digest = _load(workspace, source)
    paragraphs = _paragraphs(root)
    offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
    rows = []
    for identifier, p in paragraphs[offset:offset+limit]:
        unsupported = _unsupported(p)
        rows.append({'paragraph_id': identifier, 'text': _text(p),
                     'location': root.getroottree().getpath(p), 'editable': not unsupported,
                     'unsupported': unsupported})
    other_parts = sorted(n for n in parts if re.match(r'word/(header\d*|footer\d*|footnotes|endnotes)\.xml$', n))
    return {'source': path.relative_to(store.root).as_posix(), 'source_sha256': digest,
            'paragraphs': rows, 'total': len(paragraphs),
            'next_offset': offset+limit if offset+limit < len(paragraphs) else None,
            'uneditable_parts': other_parts,
            'notice': '正文为可见文字视图；既有修订保留，未执行接受修订。页眉页脚及脚注尾注只保留不修改。'}


def _string(value, label, empty=True):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f'{label} 必须为'+('非空' if not empty else '')+'文字。')
    try:
        element = ET.Element('text'); element.text = value
    except (ValueError, TypeError, UnicodeError) as error:
        raise ValueError(f'{label} 含 XML 不支持的控制字符。') from error
    return value


def _filename(filename):
    if not isinstance(filename, str) or Path(filename).name != filename or re.search(r'[<>:"/\\|?*\x00-\x1f]', filename) or not filename.lower().endswith('.docx'):
        raise ValueError('filename 必须为简单的 .docx 文件名。')
    if filename.rstrip(' .') != filename or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', filename, re.I):
        raise ValueError('filename 不能使用系统保留名称。')


def _publish(store, filename, data):
    _filename(filename)
    directory = store.root / 'drafts'
    if directory.exists(): store.safe(directory, internal=True)
    directory.mkdir(exist_ok=True)
    store.safe(directory, internal=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=directory, prefix='.qx-docx-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
        for _ in range(20):
            target = store.safe(directory / filename, must_exist=False)
            try:
                # Linking a completed temp file publishes atomically and never overwrites, on Windows and POSIX.
                os.link(temporary, target)
                return {'path': str(target), 'relative_path': target.relative_to(store.root).as_posix(),
                        'bytes': len(data), 'sha256': sha256(data).hexdigest()}
            except FileExistsError:
                filename = Path(filename).stem + '-' + uuid4().hex[:8] + '.docx'
        raise ValueError('同名输出冲突，请换一个文件名。')
    finally:
        if temporary is not None and temporary.exists(): store.safe(temporary).unlink()


def _run_text(run):
    return ''.join(c.text or '' if c.tag == _w('t') else '\t' if c.tag == _w('tab') else '\n'
                   for c in run if c.tag in {_w('t'), _w('tab'), _w('br'), _w('cr')})


def _span(paragraph, start, end):
    runs, position = [], 0
    for child in paragraph:
        value = _text(child) if child.tag != _w('r') else _run_text(child)
        stop = position + len(value)
        if start < stop and end > position:
            if child.tag != _w('r') or any(c.tag not in {_w(n) for n in ('rPr', 't', 'tab', 'br', 'cr')} for c in child):
                raise ValueError('目标包含既有修订或非普通文字对象，已保留建议，未自动修改。')
            runs.append((child, max(0, start-position), min(len(value), end-position)))
        position = stop
    if not runs: raise ValueError('目标范围未找到。')
    first, last = paragraph.index(runs[0][0]), paragraph.index(runs[-1][0])
    if any(c.tag != _w('r') or c.find(_w('commentReference')) is not None for c in list(paragraph)[first:last+1]):
        raise ValueError('目标跨越批注、书签或其他范围边界，未自动修改。')
    return runs


def _slice_run(run, start, end, deleted=False):
    if start == end: return None
    clone = ET.Element(run.tag, dict(run.attrib), nsmap=run.nsmap)
    properties = run.find(_w('rPr'))
    if properties is not None: clone.append(deepcopy(properties))
    position = 0
    for child in run:
        if child.tag == _w('rPr'): continue
        length = len(child.text or '') if child.tag == _w('t') else 1
        a, b = max(start, position), min(end, position+length)
        if a < b:
            piece = deepcopy(child)
            if child.tag == _w('t'):
                piece.text = (child.text or '')[a-position:b-position]
                piece.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                if deleted: piece.tag = _w('delText')
            clone.append(piece)
        position += length
    return clone


def _new_run(text, reference=None):
    run = ET.Element(_w('r'))
    if reference is not None:
        properties = reference.find(_w('rPr'))
        if properties is not None: run.append(deepcopy(properties))
    for token in re.split(r'(\n|\t)', text):
        if not token: continue
        if token in ('\n', '\t'): ET.SubElement(run, _w('br' if token == '\n' else 'tab'))
        else:
            node = ET.SubElement(run, _w('t')); node.text = token
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    return run


def _comments(parts):
    rel_name = 'word/_rels/document.xml.rels'
    rels = _xml(parts[rel_name]) if rel_name in parts else ET.Element(f'{{{R}}}Relationships', nsmap={None: R})
    links = [r for r in rels if r.get('Type') == OFFICE_REL+'comments']
    if len(links) > 1: raise ValueError('原件有多个批注部件关系，不能安全追加批注。')
    if links:
        rel = links[0]
        if rel.get('TargetMode') == 'External': raise ValueError('不向外部批注部件写入。')
        name = posixpath.normpath(posixpath.join('word', rel.get('Target', ''))).lstrip('/')
        if name not in parts: raise ValueError('原件批注部件缺失，不能安全追加。')
        comments = _xml(parts[name])
    else:
        name = 'word/comments.xml'
        comments = _xml(parts[name]) if name in parts else ET.Element(_w('comments'), nsmap={'w': W})
        used = {r.get('Id') for r in rels}; rid = 'rIdQxComments'
        while rid in used: rid += '1'
        ET.SubElement(rels, f'{{{R}}}Relationship', Id=rid, Type=OFFICE_REL+'comments', Target='comments.xml')
    if comments.tag != _w('comments'): raise ValueError('原件批注 XML 类型不受支持。')
    parts[rel_name] = _bytes(rels)
    types = _xml(parts['[Content_Types].xml'])
    if not any(c.get('PartName') == '/'+name for c in types):
        ET.SubElement(types, f'{{{CT}}}Override', PartName='/'+name,
                      ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
    parts['[Content_Types].xml'] = _bytes(types)
    return name, comments


def write_review_docx(workspace, source, filename, edits, author='律师', source_sha256='', mode='comments'):
    """Annotate exact paragraph spans by default; tracked body changes are explicit."""
    _filename(filename); _string(author, 'author', empty=False)
    if mode not in {'comments', 'tracked_changes'}: raise ValueError('mode 只能为 comments（默认批注）或 tracked_changes（修订正文）。')
    if not isinstance(edits, list) or not edits: raise ValueError('edits 必须为非空列表。')
    store, path, parts, root, digest = _load(workspace, source)
    if source_sha256 and source_sha256 != digest: raise ValueError('原件版本已变化，请重新 inspect_docx 后定位。')
    if any(n.startswith('_xmlsignatures/') for n in parts): raise ValueError('原件有数字签名，不能在保留签名有效性的前提下修订。')
    paragraphs = dict(_paragraphs(root)); plans = []; results = []
    for index, edit in enumerate(edits):
        result = {'index': index, 'edit': edit, 'status': 'not_applied'}; results.append(result)
        try:
            if not isinstance(edit, dict): raise ValueError('每项修改必须为对象。')
            paragraph = paragraphs.get(edit.get('paragraph_id'))
            if paragraph is None: raise ValueError('段落编号不存在或原段落已变化，请重新定位。')
            issues = _unsupported(paragraph)
            if issues: raise ValueError('目标段落暂不支持：'+'、'.join(issues)+'。')
            old = _string(edit.get('old'), 'old', empty=False)
            new = _string(edit.get('new', old), 'new')
            comment = _string(edit.get('comment', ''), 'comment')
            if old == new and not comment: raise ValueError('该项没有文字变化或批注内容。')
            if mode == 'comments' and new != old:
                suggestion = '建议替换为：\n'+new if new else '建议删除该处原文：\n'+old
                comment = (comment+'\n\n' if comment else '') + suggestion
                new = old
            value = _text(paragraph)
            matches = [m.start() for m in re.finditer('(?='+re.escape(old)+')', value)]
            if len(matches) != 1: raise ValueError('原文在指定段落中未找到或不唯一，请提供包含上下文的完整原文。')
            start = matches[0]; end = start+len(old)
            _span(paragraph, start, end)
            plans.append({'p': paragraph, 'start': start, 'end': end, 'new': new, 'old': old, 'comment': comment, 'result': result})
        except (ValueError, TypeError) as error: result['reason'] = str(error)
    for plan in plans:
        if any(other is not plan and other['p'] is plan['p'] and plan['start'] < other['end'] and plan['end'] > other['start'] for other in plans):
            plan['result']['reason'] = '本批修改范围相互重叠，请合并为一条修改。'
    plans = [p for p in plans if 'reason' not in p['result']]
    comments_name, comments = None, None
    if any(p['comment'] for p in plans):
        try: comments_name, comments = _comments(parts)
        except ValueError as error:
            for plan in plans:
                if plan['comment']: plan['result']['reason'] = str(error)
            plans = [p for p in plans if 'reason' not in p['result']]
    identifiers = [int(x) for name, data in parts.items() if name.startswith('word/') and name.endswith('.xml')
                   for x in _xml(data).xpath('//@w:id', namespaces=NS) if re.fullmatch(r'\d+', x)]
    next_id = max(identifiers, default=-1)+1
    date = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    for plan in sorted(plans, key=lambda p: p['start'], reverse=True):
        p = plan['p']; runs = _span(p, plan['start'], plan['end'])
        first, last = runs[0], runs[-1]; at = p.index(first[0]); nodes = []
        before = _slice_run(first[0], 0, first[1])
        after = _slice_run(last[0], last[2], len(_run_text(last[0])))
        if before is not None: nodes.append(before)
        comment_id = None
        if plan['comment']:
            comment_id = str(next_id); next_id += 1
            nodes.append(ET.Element(_w('commentRangeStart'), {_w('id'): comment_id}))
        if plan['new'] != plan['old']:
            deletion = ET.Element(_w('del'), {_w('id'): str(next_id), _w('author'): author, _w('date'): date}); next_id += 1
            for run, start, end in runs: deletion.append(_slice_run(run, start, end, deleted=True))
            nodes.append(deletion)
            if plan['new']:
                insertion = ET.Element(_w('ins'), {_w('id'): str(next_id), _w('author'): author, _w('date'): date}); next_id += 1
                insertion.append(_new_run(plan['new'], first[0])); nodes.append(insertion)
        else:
            nodes.extend(_slice_run(run, start, end) for run, start, end in runs)
        if comment_id is not None:
            nodes.append(ET.Element(_w('commentRangeEnd'), {_w('id'): comment_id}))
            ref = ET.Element(_w('r')); ET.SubElement(ref, _w('commentReference'), {_w('id'): comment_id}); nodes.append(ref)
            comment = ET.SubElement(comments, _w('comment'), {_w('id'): comment_id, _w('author'): author, _w('date'): date})
            ET.SubElement(comment, _w('p')).append(_new_run(plan['comment']))
        if after is not None: nodes.append(after)
        for run, _, _ in runs: p.remove(run)
        for position, node in enumerate(nodes): p.insert(at+position, node)
        plan['result'].update(status='applied', reason='')
    applied = len(plans)
    result = {'status': 'not_written' if not applied else 'partial' if applied < len(edits) else 'draft',
              'mode': mode, 'source_sha256': digest, 'applied': applied, 'failed': len(edits)-applied, 'results': results,
              'notice': '仅落入已明确定位的正文及表格普通文字；原件和已有修订批注保留。请逐条查看未应用项，并在 Word/WPS 核对版式。'}
    if not applied: return result
    parts['word/document.xml'] = _bytes(root)
    if comments is not None: parts[comments_name] = _bytes(comments)
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            if name.endswith(('.xml', '.rels')): _xml(data)
            archive.writestr(name, data)
    if sha256(path.read_bytes()).hexdigest() != digest: raise ValueError('原件在生成期间变化，未发布副本，请重新读取。')
    result.update(_publish(store, filename, output.getvalue()))
    return result


def list_templates():
    return json.loads(MANIFEST.read_text(encoding='utf-8'))


def _items(value, label):
    if not isinstance(value, list) or not value: raise ValueError(f'{label} 必须为非空列表；不会以模板示例补足。')
    return [_string(item, f'{label}[{i}]', empty=False) for i, item in enumerate(value)]


def generate_template_document(workspace, template_id, filename, data, author=''):
    """Build a clean document with the supplied template's layout, never its example facts."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.oxml import OxmlElement
    from docx.shared import Pt, Twips, RGBColor
    _filename(filename); _string(author, 'author')
    template = next((t for t in list_templates()['templates'] if t['id'] == template_id), None)
    if template is None: raise ValueError('模板编号不存在，请先 list_templates。')
    if not isinstance(data, dict): raise ValueError('data 必须为对象。')
    if template['kind'] == 'complaint':
        parties = _items(data.get('parties'), 'parties'); claims = _items(data.get('claims'), 'claims'); facts = _items(data.get('facts'), 'facts')
    else:
        evidence = data.get('evidence')
        if not isinstance(evidence, list) or not evidence: raise ValueError('evidence 必须为非空列表。')
        for i, item in enumerate(evidence):
            if not isinstance(item, dict): raise ValueError(f'evidence[{i}] 必须为对象。')
            _string(item.get('name'), f'evidence[{i}].name', empty=False)
            for key in ('content', 'purpose', 'page_range', 'source'): _string(item.get(key, ''), f'evidence[{i}].{key}')
    for key in ('title', 'court', 'signature', 'date', 'submitter'): _string(data.get(key, ''), key)
    doc = Document(); layout = template['layout']; section = doc.sections[0]
    for key in ('page_width', 'page_height', 'top_margin', 'bottom_margin', 'left_margin', 'right_margin'):
        setattr(section, key, Twips(layout[key]))
    for name in ('Normal', 'Title', 'Heading 1'):
        style = doc.styles[name]; style.font.name = '仿宋'; style.font.color.rgb = RGBColor(0, 0, 0)
        fonts = style.element.get_or_add_rPr().get_or_add_rFonts()
        for attribute in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'): fonts.attrib.pop(_w(attribute), None)
        fonts.set(_w('eastAsia'), '仿宋')
        for border in style.element.findall('./'+_w('pPr')+'/'+_w('pBdr')): border.getparent().remove(border)
        style.font.size = Pt(layout['body_pt']); style.paragraph_format.space_after = Pt(0)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        style.paragraph_format.line_spacing = Pt(layout['line_pt'])
    doc.styles['Title'].font.size = Pt(layout['title_pt']); doc.styles['Title'].font.bold = True
    doc.styles['Title'].paragraph_format.space_after = Pt(12)
    doc.core_properties.author = author; doc.core_properties.last_modified_by = author
    doc.core_properties.comments = ''; doc.core_properties.title = data.get('title') or ('民事起诉状' if template['kind'] == 'complaint' else '证据目录')
    p = doc.add_paragraph(doc.core_properties.title, 'Title'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    warnings = []; counts = {}

    def paragraph(value, *, indent=False, bold=False):
        p = doc.add_paragraph(value)
        p.paragraph_format.widow_control = True
        if indent: p.paragraph_format.first_line_indent = Pt(layout['body_pt']*2)
        if bold:
            for run in p.runs: run.bold = True
            p.paragraph_format.keep_with_next = True
        return p

    def supplied(key, fallback):
        if data.get(key): return data[key]
        warnings.append(f'{key} 未提供，已标注待补。')
        return fallback

    if template['kind'] == 'complaint':
        for item in parties: paragraph(item, indent=True)
        paragraph('诉讼请求', bold=True)
        for i, item in enumerate(claims, 1): paragraph(f'{i}. {item}', indent=True)
        paragraph('事实与理由', bold=True)
        for item in facts: paragraph(item, indent=True)
        paragraph('此致'); paragraph(supplied('court', '【受理法院待补】'))
        paragraph(supplied('signature', '【具状人待补】')).alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph(supplied('date', '【日期待补】')).alignment = WD_ALIGN_PARAGRAPH.RIGHT
        counts = {'parties': len(parties), 'claims': len(claims), 'facts': len(facts)}
    else:
        paragraph('提交人：'+supplied('submitter', '【提交人待补】')).alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph('提交日期：'+supplied('date', '【日期待补】')).alignment = WD_ALIGN_PARAGRAPH.RIGHT
        table = None
        if template['format'] == 'table':
            table = doc.add_table(rows=1, cols=4); table.style = 'Table Grid'; table.autofit = False
            widths = [800, 2000, section.page_width.twips-section.left_margin.twips-section.right_margin.twips-3700, 900]
            for column, width in zip(table.columns, widths): column.width = Twips(width)
            for c, width, text in zip(table.rows[0].cells, widths, ['序号', '名称', '证明内容及目的', '页码']):
                c.width = Twips(width); c.text = text
                for run in c.paragraphs[0].runs: run.bold = True
            table.rows[0]._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        for i, item in enumerate(evidence, 1):
            content = item.get('content') or '【证据内容待补】'; purpose = item.get('purpose') or '【证明目的待补】'
            pages = item.get('page_range') or '待编页'
            if not item.get('page_range'): warnings.append(f'证据{i}未提供页码，未自动计算。')
            for key in ('content', 'purpose'):
                if not item.get(key): warnings.append(f'证据{i}的{key}待补。')
            source = '\n来源：'+item['source'] if item.get('source') else ''
            if table is not None:
                row = table.add_row()
                row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
                for c, width, text in zip(row.cells, widths, [str(i), item['name'], '证据内容：'+content+'\n证明目的：'+purpose+source, pages]):
                    c.width = Twips(width); c.text = text
                    for p in c.paragraphs:
                        p.paragraph_format.line_spacing = 1.2
                        for run in p.runs: run.font.size = Pt(11)
            else:
                paragraph(f'证据{i}：{item["name"]}', bold=True)
                paragraph('证据内容：'+content, indent=True); paragraph('证明目的：'+purpose, indent=True)
                if item.get('source'): paragraph('来源：'+item['source'], indent=True)
                paragraph('页码：'+pages, indent=True)
        counts = {'evidence': len(evidence)}
    output = BytesIO(); doc.save(output)
    # Validate all written XML before publishing a downloadable file.
    with ZipFile(BytesIO(output.getvalue())) as archive:
        for name in archive.namelist():
            if name.endswith(('.xml', '.rels')): _xml(archive.read(name))
    result = _publish(_store(workspace), filename, output.getvalue())
    result.update(status='draft', template_id=template_id, template_source=template['source'],
                  counts=counts, warnings=warnings,
                  notice='按所选模板版式生成干净草稿，仅使用传入内容；请核对事实、诉请、证据和实际分页。')
    return result
