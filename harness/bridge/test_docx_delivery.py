"""Synthetic OOXML tests: originals, history, precise edits and complete templates."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from lxml import etree as ET
import pytest

import docx_delivery as api

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}


def package(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def xml(parts, name='word/document.xml'):
    return ET.fromstring(parts[name])


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.docx'
    doc = Document()
    p = doc.add_paragraph()
    p.add_run('支付A&').bold = True
    p.add_run('B款项').italic = True
    doc.add_paragraph('支付A&B款项')
    doc.add_paragraph('重复重复')
    doc.add_table(rows=1, cols=1).cell(0, 0).text = '表格金额待核'
    doc.add_paragraph('历史文字')
    doc.add_paragraph('既有批注段落')
    doc.save(path)
    parts = package(path)
    root = xml(parts)
    paragraphs = root.xpath('.//w:body//w:p', namespaces=NS)
    history = paragraphs[-2]
    run = history[0]
    revision = ET.Element(f'{{{W}}}ins', {f'{{{W}}}id': '98', f'{{{W}}}author': '前审阅人'})
    history.remove(run)
    revision.append(run)
    history.append(revision)
    p = paragraphs[-1]
    p.insert(0, ET.Element(f'{{{W}}}commentRangeStart', {f'{{{W}}}id': '42'}))
    p.append(ET.Element(f'{{{W}}}commentRangeEnd', {f'{{{W}}}id': '42'}))
    ref = ET.SubElement(p, f'{{{W}}}r')
    ET.SubElement(ref, f'{{{W}}}commentReference', {f'{{{W}}}id': '42'})
    comments = ET.Element(f'{{{W}}}comments', nsmap={'w': W})
    comment = ET.SubElement(comments, f'{{{W}}}comment', {f'{{{W}}}id': '42', f'{{{W}}}author': '前审阅人'})
    ET.SubElement(ET.SubElement(ET.SubElement(comment, f'{{{W}}}p'), f'{{{W}}}r'), f'{{{W}}}t').text = '原有批注&原样保留'
    parts['word/comments.xml'] = ET.tostring(comments)
    parts['word/document.xml'] = ET.tostring(root)
    rels = xml(parts, 'word/_rels/document.xml.rels')
    ET.SubElement(rels, '{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                  Id='rIdComments', Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments', Target='comments.xml')
    parts['word/_rels/document.xml.rels'] = ET.tostring(rels)
    types = xml(parts, '[Content_Types].xml')
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override',
                  PartName='/word/comments.xml', ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
    parts['[Content_Types].xml'] = ET.tostring(types)
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items(): archive.writestr(name, data)
    return path


def test_cross_run_exact_paragraph_keeps_original_history_and_xml(source):
    before = source.read_bytes()
    inspected = api.inspect_docx(source.parent, source.name)
    assert inspected == api.inspect_docx(source.parent, source.name)
    ps = inspected['paragraphs']
    result = api.write_review_docx(source.parent, source.name, 'review.docx', [
        {'paragraph_id': ps[0]['paragraph_id'], 'old': 'A&B', 'new': '<新金额>&待核', 'comment': '核对<原件>&金额'},
        {'paragraph_id': ps[3]['paragraph_id'], 'old': '待核', 'new': '已核'},
    ], author='测试律师', source_sha256=inspected['source_sha256'], mode='tracked_changes')
    assert result['status'] == 'draft' and result['applied'] == 2 and result['failed'] == 0
    assert source.read_bytes() == before
    parts = package(result['path'])
    for name, data in parts.items():
        if name.endswith(('.xml', '.rels')): ET.fromstring(data)
    root = xml(parts)
    paragraphs = root.xpath('.//w:body//w:p', namespaces=NS)
    assert ''.join(paragraphs[1].xpath('.//w:t/text()', namespaces=NS)) == '支付A&B款项'
    assert paragraphs[0].xpath('.//w:delText/text()', namespaces=NS) == ['A&', 'B']
    assert '<新金额>&待核' in paragraphs[0].xpath('.//w:ins//w:t/text()', namespaces=NS)
    assert root.xpath('.//w:ins[@w:id="98"]', namespaces=NS)
    comments = xml(parts, 'word/comments.xml')
    assert comments.xpath('.//w:comment[@w:id="42"]//w:t/text()', namespaces=NS) == ['原有批注&原样保留']
    ids = comments.xpath('./w:comment/@w:id', namespaces=NS)
    assert len(ids) == len(set(ids)) == 2 and int(ids[-1]) > 98
    original = package(source)
    changed = {'word/document.xml', 'word/comments.xml', 'word/settings.xml', 'word/_rels/document.xml.rels', '[Content_Types].xml'}
    assert all(data == parts[name] for name, data in original.items() if name not in changed)


def test_rejected_edits_are_reported_with_suggestions_and_no_false_success(source):
    ps = api.inspect_docx(source.parent, source.name)['paragraphs']
    result = api.write_review_docx(source.parent, source.name, 'review.docx', [
        {'paragraph_id': ps[2]['paragraph_id'], 'old': '重复', 'new': '唯一'},
        {'paragraph_id': ps[4]['paragraph_id'], 'old': '历史', 'new': '更新'},
        {'paragraph_id': 'missing', 'old': '支付', 'new': '不应写入'},
    ])
    assert result['status'] == 'not_written' and result['applied'] == 0 and result['failed'] == 3
    assert 'path' not in result and all(x['reason'] and x['edit']['new'] for x in result['results'])
    assert not (source.parent / 'drafts' / 'review.docx').exists()


def test_comment_only_multiple_edits_and_nonoverwrite(source):
    p = api.inspect_docx(source.parent, source.name)['paragraphs'][0]
    edits = [{'paragraph_id': p['paragraph_id'], 'old': '支付', 'new': '应付'},
             {'paragraph_id': p['paragraph_id'], 'old': '款项', 'comment': '请核实。'}]
    one = api.write_review_docx(source.parent, source.name, 'review.docx', edits)
    saved = Path(one['path']).read_bytes()
    two = api.write_review_docx(source.parent, source.name, 'review.docx', edits)
    assert one['applied'] == two['applied'] == 2 and one['path'] != two['path']
    assert Path(one['path']).read_bytes() == saved
    with pytest.raises(ValueError): api.write_review_docx(source.parent, source.name, '../bad.docx', edits)
    with pytest.raises(ValueError): api.write_review_docx(source.parent, source.name, 'x.docx', edits, source_sha256='0'*64)


def test_existing_comment_anchor_survives_edit_inside_it_and_partial_status(source):
    p = api.inspect_docx(source.parent, source.name)['paragraphs'][-1]
    result = api.write_review_docx(source.parent, source.name, 'inside.docx', [
        {'paragraph_id': p['paragraph_id'], 'old': '批注', 'new': '审阅', 'comment': '新注释'},
        {'paragraph_id': p['paragraph_id'], 'old': '不存在', 'new': '不会出现'},
    ], mode='tracked_changes')
    root = xml(package(result['path']))
    assert result['status'] == 'partial' and result['applied'] == result['failed'] == 1
    for marker in ('commentRangeStart', 'commentRangeEnd', 'commentReference'):
        assert len(root.xpath(f'.//w:{marker}[@w:id="42"]', namespaces=NS)) == 1
    assert root.xpath('.//w:ins//w:t[text()="审阅"]', namespaces=NS)


def test_overlap_and_crossing_old_comment_boundary_are_explicit_failures(source):
    ps = api.inspect_docx(source.parent, source.name)['paragraphs']
    result = api.write_review_docx(source.parent, source.name, 'overlap.docx', [
        {'paragraph_id': ps[0]['paragraph_id'], 'old': '支付A', 'new': '甲'},
        {'paragraph_id': ps[0]['paragraph_id'], 'old': 'A&B', 'new': '乙'},
    ])
    assert result['applied'] == 0 and result['failed'] == 2
    parts = package(source); root = xml(parts); p = root.xpath('.//w:body//w:p', namespaces=NS)[0]
    p.insert(1, ET.Element(f'{{{W}}}commentRangeStart', {f'{{{W}}}id': '42'}))
    parts['word/document.xml'] = ET.tostring(root)
    with ZipFile(source, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items(): archive.writestr(name, data)
    before = source.read_bytes()
    p = api.inspect_docx(source.parent, source.name)['paragraphs'][0]
    result = api.write_review_docx(source.parent, source.name, 'boundary.docx', [
        {'paragraph_id': p['paragraph_id'], 'old': 'A&B', 'new': '丙'},
    ])
    assert result['failed'] == 1 and result['status'] == 'not_written' and source.read_bytes() == before


def test_multiple_text_nodes_preserve_tabs_linebreaks_and_format(tmp_path):
    source = tmp_path / 'tokens.docx'; doc = Document()
    p = doc.add_paragraph(); run = p.add_run('前缀'); run.bold = True
    run.add_tab(); run.add_text('跨节点'); run.add_break(); run.add_text('尾部')
    doc.save(source)
    paragraph = api.inspect_docx(tmp_path, source.name)['paragraphs'][0]
    assert paragraph['text'] == '前缀\t跨节点\n尾部'
    result = api.write_review_docx(tmp_path, source.name, 'tokens-review.docx', [
        {'paragraph_id': paragraph['paragraph_id'], 'old': '节点', 'new': '替换&<值>'},
    ], mode='tracked_changes')
    root = xml(package(result['path']))
    assert root.xpath('.//w:tab', namespaces=NS) and root.xpath('.//w:br', namespaces=NS)
    assert root.xpath('.//w:ins/w:r/w:rPr/w:b', namespaces=NS)
    assert root.xpath('.//w:delText/text()', namespaces=NS) == ['节点']
    assert '尾部' in root.xpath('.//w:t/text()', namespaces=NS)


def test_three_disjoint_replacements_in_same_run_keep_all_new_text(tmp_path):
    source = tmp_path / 'same-run.docx'; doc = Document(); doc.add_paragraph('左侧 中间 右侧'); doc.save(source)
    p = api.inspect_docx(tmp_path, source.name)['paragraphs'][0]
    result = api.write_review_docx(tmp_path, source.name, 'same-run-review.docx', [
        {'paragraph_id': p['paragraph_id'], 'old': '左侧', 'new': '左侧增加很多字'},
        {'paragraph_id': p['paragraph_id'], 'old': '中间', 'new': '中'},
        {'paragraph_id': p['paragraph_id'], 'old': '右侧', 'new': '右侧替换', 'comment': '保留批注'},
    ], mode='tracked_changes')
    root = xml(package(result['path']))
    assert result['applied'] == 3 and result['failed'] == 0
    assert ''.join(root.xpath('.//w:body//w:t/text()', namespaces=NS)) == '左侧增加很多字 中 右侧替换'


def test_memory_admission_is_dynamic_and_original_stays_available(source, monkeypatch):
    import reader
    before = source.read_bytes()
    monkeypatch.setattr(reader, 'available_memory', lambda: 1024)
    with pytest.raises(ValueError, match='内存'):
        api.inspect_docx(source.parent, source.name)
    assert source.read_bytes() == before
    monkeypatch.setattr(reader, 'available_memory', lambda: 4 * 1024**3)
    assert api.inspect_docx(source.parent, source.name)['paragraphs']


def test_default_review_adds_comments_without_changing_contract_text(source):
    original = source.read_bytes()
    before = xml(package(source))
    paragraphs = api.inspect_docx(source.parent, source.name)['paragraphs']
    result = api.write_review_docx(source.parent, source.name, '批注合同.docx', [
        {'paragraph_id': paragraphs[0]['paragraph_id'], 'old': 'A&B', 'new': '双方确认的款项', 'comment': '原文缺少付款条件。'},
        {'paragraph_id': paragraphs[3]['paragraph_id'], 'old': '待核', 'new': '', 'comment': '需确认是否删除占位文字。'},
    ])
    after = xml(package(result['path']))
    assert result['mode'] == 'comments' and result['applied'] == 2
    assert source.read_bytes() == original
    assert before.xpath('.//w:t/text()', namespaces=NS) != []
    assert ''.join(before.xpath('.//w:t/text()', namespaces=NS)) == ''.join(after.xpath('.//w:t/text()', namespaces=NS))
    assert len(before.xpath('.//w:ins|.//w:del', namespaces=NS)) == len(after.xpath('.//w:ins|.//w:del', namespaces=NS))
    comments = xml(package(result['path']), 'word/comments.xml')
    text = ''.join(comments.xpath('.//w:t/text()', namespaces=NS))
    assert all(t in text for t in ('原有批注&原样保留', '原文缺少付款条件', '双方确认的款项', '建议删除', '待核'))


def test_comment_only_and_unknown_mode(source):
    p = api.inspect_docx(source.parent, source.name)['paragraphs'][0]
    edit = {'paragraph_id': p['paragraph_id'], 'old': 'A&B', 'comment': '请核对具体计价范围。'}
    result = api.write_review_docx(source.parent, source.name, '备注.docx', [edit])
    assert result['applied'] == 1 and result['mode'] == 'comments'
    with pytest.raises(ValueError, match='mode'):
        api.write_review_docx(source.parent, source.name, '错误.docx', [edit], mode='overwrite')


def all_text(path):
    parts = package(path)
    return '\n'.join(''.join(ET.fromstring(data).itertext()) for name, data in parts.items() if name.endswith('.xml'))


def test_every_template_keeps_all_long_items_without_source_examples(tmp_path):
    templates = api.list_templates()['templates']
    assert len(templates) == 7
    claims = [f'第{i}项诉请：' + '长项仍应完整保留。'*40 for i in range(1, 9)]
    facts = [f'事实第{i}项：' + '根据测试材料记录事实。'*30 for i in range(1, 9)]
    evidence = [{'name': f'合成证据{i}', 'content': '逐项证据内容。'*35,
                 'purpose': f'证明目的{i}', 'source': f'合成来源{i}'} for i in range(1, 13)]
    for template in templates:
        data = {'parties': ['原告：合成甲。', '被告：合成乙。'], 'claims': claims, 'facts': facts,
                'court': '测试法院', 'signature': '合成甲', 'date': '2026年11月3日'} if template['kind'] == 'complaint' else {'evidence': evidence, 'submitter': '合成甲'}
        result = api.generate_template_document(tmp_path, template['id'], template['id']+'.docx', data)
        text = all_text(result['path'])
        assert all(item in text for item in (claims+facts if template['kind'] == 'complaint' else [e['name'] for e in evidence]))
        assert all(marker not in text for marker in ['张某某', '李某某', '××', '1-18', '2 / 2', '加计50%', 'lexie', 'DoubleOX'])
        assert result['template_source']['sha256'] and result['status'] == 'draft'
        styles = xml(package(result['path']), 'word/styles.xml')
        assert not styles.xpath('./w:style[@w:styleId="Title"]/w:pPr/w:pBdr', namespaces=NS)
        if template['id'] == 'evidence-table':
            doc = Document(result['path'])
            assert len(doc.tables[0].rows) == 13
            assert doc.tables[0].rows[-1].cells[3].text == '待编页'
            assert all(row._tr.find(f'{{{W}}}trPr/{{{W}}}cantSplit') is not None for row in doc.tables[0].rows[1:])
    with pytest.raises(ValueError): api.generate_template_document(tmp_path, 'complaint-sales', 'missing.docx', {'claims': []})
    with pytest.raises(ValueError): api.generate_template_document(tmp_path, 'evidence-table', 'bad.docx', {'evidence': [{'name': '甲'}, None]})
