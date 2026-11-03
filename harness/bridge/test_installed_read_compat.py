"""Synthetic regression for packaged methods and imported DOCX style gaps."""
from hashlib import sha256
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

from docx import Document
from lxml import etree as ET
import pytest

import workflows
from reader import parse, docx_style_fallback
from store import MaterialStore

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def test_installed_methods_use_seed_without_active_workspace(tmp_path, monkeypatch):
    seed = tmp_path / 'workspace-seed/.dsh/skills'
    shutil.copytree(workflows.SKILLS, seed)
    monkeypatch.setattr(workflows, 'SKILLS', tmp_path / 'config/skills')
    monkeypatch.setattr(workflows, 'PACKAGED_SKILLS', seed, raising=False)
    for name in ('contract', 'reception', 'case', 'hearing'):
        result = workflows.workflow(name)
        assert result['method'] and result['sources']
        assert result['name'] == name


def make_style_gap_docx(path):
    doc = Document()
    paragraph = doc.add_paragraph('普通正文')
    paragraph.add_run('明确隐藏').font.hidden = True
    doc.add_table(rows=1, cols=1).cell(0, 0).text = '表格约定'
    doc.save(path)
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(parts['word/document.xml'])
    ns = {'w': W}
    for paragraph in root.xpath('./w:body//w:p', namespaces=ns):
        props = paragraph.find(f'{{{W}}}pPr')
        if props is None:
            props = ET.Element(f'{{{W}}}pPr'); paragraph.insert(0, props)
        ET.SubElement(props, f'{{{W}}}pStyle', {f'{{{W}}}val': 'MissingImportedStyle'})
    p = root.xpath('./w:body/w:p', namespaces=ns)[0]
    hyperlink = ET.SubElement(p, f'{{{W}}}hyperlink')
    ET.SubElement(ET.SubElement(hyperlink, f'{{{W}}}r'), f'{{{W}}}t').text = '链接文字'
    for kind, text, leaf in [('ins', '新增文字', 't'), ('del', '删除文字', 'delText'),
                             ('moveTo', '移入文字', 't'), ('moveFrom', '移出文字', 't')]:
        revision = ET.SubElement(p, f'{{{W}}}{kind}', {f'{{{W}}}id': str(len(p))})
        ET.SubElement(ET.SubElement(revision, f'{{{W}}}r'), f'{{{W}}}{leaf}').text = text
    parts['word/document.xml'] = ET.tostring(root)
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, data in parts.items(): archive.writestr(name, data)


@pytest.mark.parametrize('mode,included,excluded', [
    ('original', ('删除文字', '移出文字'), ('新增文字', '移入文字')),
    ('accepted_view', ('新增文字', '移入文字'), ('删除文字', '移出文字')),
])
def test_missing_style_preserves_structure_and_revision_view(tmp_path, mode, included, excluded):
    path = tmp_path / 'style-gap.docx'
    make_style_gap_docx(path)
    before = sha256(path.read_bytes()).hexdigest()
    store = MaterialStore(tmp_path)
    store.register(path.name)
    result = parse(store, path.name, revision_mode=mode)
    assert result['status'] == 'ready'
    assert any('样式' in warning for warning in result['warnings'])
    chunks = store.read(path.name)['chunks']
    text = '\n'.join(chunk['text'] for chunk in chunks)
    for expected in ('普通正文', '表格约定', '链接文字', *included): assert expected in text
    for absent in ('明确隐藏', *excluded): assert absent not in text
    assert len(chunks) == 2
    assert any('/w:tbl/' in chunk['location'] for chunk in chunks)
    assert sha256(path.read_bytes()).hexdigest() == before


def test_fallback_uses_validated_bytes_without_filename_gate(tmp_path):
    # The fallback must not import the Word editing API's filename restriction.
    path = tmp_path / 'extensionless-object'
    make_style_gap_docx(path)
    from cn_contract.config import load_settings
    from cn_contract.domain import BaselineView, DocumentParseInput
    from cn_contract.documents.docx_adapter import parse_docx
    from uuid import uuid4
    raw = path.read_bytes()
    parsed = parse_docx(raw, DocumentParseInput(id=uuid4(), baseline_view=BaselineView.ORIGINAL), load_settings())
    assert any('STYLE_DEPENDENCY' in issue for issue in parsed.quality_issues)
    result = list(docx_style_fallback(raw, 'original'))
    assert len(result) == 2
    assert '表格约定' in result[1][0]
    assert path.read_bytes() == raw
