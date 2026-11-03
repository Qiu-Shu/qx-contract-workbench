"""Synthetic contract opinion output: safety, completeness and original protection."""
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from lxml import etree as ET
import pytest

import contract_opinion as api


class Markup(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []; self.links = []; self.text = []
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        self.tags.append(tag)
        if tag == 'a': self.links.append(dict(attributes))

    def handle_data(self, data):
        self.text.append(data)


def test_all_user_text_is_escaped_but_explicit_https_link_is_clickable(tmp_path):
    attack = '<script>alert("甲&乙")</script><img src=x onerror=alert(1)>'
    result = api.write_contract_opinion(tmp_path, '合成意见.html', attack, attack, [{
        'heading': attack, 'paragraphs': [attack],
        'table': {'headers': [attack, '原条款', '风险', '建议'], 'rows': [[attack, '甲', '乙', '丙']]},
        'references': [{'label': attack, 'url': 'https://example.org/law?x=1&y=2'}],
        'subsections': [{'heading': '替换条款🙂', 'paragraphs': [attack]}],
    }])
    content = Path(result['html_path']).read_text(encoding='utf-8'); parsed = Markup(content)
    assert result['status'] == 'draft' and 'script' not in parsed.tags and 'img' not in parsed.tags
    assert parsed.links[0]['href'] == 'https://example.org/law?x=1&y=2'
    assert '&lt;script&gt;' in content and 'Content-Security-Policy' in content
    assert ''.join(parsed.text).count(attack) >= 7
    doc = Document(result['word_path'])
    assert doc.paragraphs[0].text == attack
    with ZipFile(result['word_path']) as archive:
        for name in archive.namelist():
            if name.endswith(('.xml', '.rels')): ET.fromstring(archive.read(name))
        rels = ET.fromstring(archive.read('word/_rels/document.xml.rels'))
        assert any(rel.get('Target') == 'https://example.org/law?x=1&y=2' for rel in rels)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'data:text/html,<script>1</script>',
                                  'file:///C:/private.txt', '//example.org', 'https://example.org/\nattack',
                                  'https://example.org/"onmouseover="alert(1)', 'https://user:secret@example.org'])
def test_unsafe_references_fail_before_any_files_are_written(tmp_path, url):
    with pytest.raises(ValueError):
        api.write_contract_opinion(tmp_path, 'bad', '合成审查意见', '', [{
            'heading': '依据', 'references': [{'label': '来源', 'url': url}],
        }])
    assert not list(tmp_path.rglob('*.html')) and not list(tmp_path.rglob('*.docx'))


def test_all_long_unicode_sections_rows_and_subsections_survive(tmp_path):
    long = '第α项🧾意见：应核对原件，不加入未经证实的结论。\n'*300
    rows = [[f'风险{i}', f'第{i}条', '合成风险说明', long if i == 19 else f'第{i}项建议'] for i in range(20)]
    sections = [{'heading': f'章节{i}', 'paragraphs': [f'自由章节{i}，事实仅供测试。']} for i in range(25)]
    sections.append({'heading': '风险表', 'paragraphs': [long],
                     'table': {'headers': ['级别', '条款', '意见', '建议'], 'rows': rows},
                     'subsections': [{'heading': '替换条款A', 'paragraphs': [long]},
                                     {'heading': '替换条款B', 'paragraphs': ['最后一项不会遗漏。']}],
                     'references': [{'label': '合成来源α', 'url': 'http://example.org/reference'}]})
    result = api.write_contract_opinion(tmp_path, '完整意见.docx', '合成合同审查意见', 'Unicode与长文本排版测试', sections)
    html = Markup(Path(result['html_path']).read_text(encoding='utf-8'))
    assert ''.join(html.text).count(long) == 3 and '最后一项不会遗漏。' in ''.join(html.text)
    doc = Document(result['word_path']); body = '\n'.join(p.text for p in doc.paragraphs)
    assert body.count(long) == 2 and all(f'自由章节{i}，事实仅供测试。' in body for i in range(25))
    assert len(doc.tables[0].rows) == 21 and doc.tables[0].rows[-1].cells[3].text == long
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    assert doc.tables[0].rows[0]._tr.xpath('./w:trPr/w:tblHeader')
    assert doc.tables[0].rows[1]._tr.xpath('./w:trPr/w:cantSplit')
    assert not doc.tables[0].rows[-1]._tr.xpath('./w:trPr/w:cantSplit')
    assert result['counts'] == {'sections': 28, 'paragraphs': 28, 'tables': 1, 'rows': 20, 'references': 1}


def test_existing_files_and_same_name_outputs_are_never_overwritten(tmp_path):
    drafts = tmp_path / 'drafts'; drafts.mkdir()
    originals = {drafts/'意见.docx': b'original Word', drafts/'意见.html': b'original HTML'}
    for path, data in originals.items(): path.write_bytes(data)
    one = api.write_contract_opinion(tmp_path, '意见', '合成', '', [])
    saved = {Path(one[key]): Path(one[key]).read_bytes() for key in ('html_path', 'word_path')}
    two = api.write_contract_opinion(tmp_path, '意见.html', '另一次合成', '', [])
    assert one['html_path'] != two['html_path'] and one['word_path'] != two['word_path']
    assert all(path.read_bytes() == data for path, data in (originals | saved).items())
    for name in ('../escape', 'folder/name', 'CON', ''):
        with pytest.raises(ValueError): api.write_contract_opinion(tmp_path, name, '标题', '', [])


def test_mismatched_table_cells_and_invalid_xml_text_are_not_silently_dropped(tmp_path):
    with pytest.raises(ValueError):
        api.write_contract_opinion(tmp_path, 'bad', '标题', '', [{'table': {'headers': ['甲', '乙'], 'rows': [['一格']]}}])
    with pytest.raises(ValueError):
        api.write_contract_opinion(tmp_path, 'bad', '标题', '', [{'paragraphs': ['控制字符\x00不得丢失']}])
    assert not list(tmp_path.rglob('*.docx'))
