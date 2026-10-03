"""T03 independent synthetic document parsing behavior."""
from io import BytesIO
from pathlib import Path
import sys
from uuid import uuid4
import pytest
from cn_contract.config import load_settings
from cn_contract.security import ServiceError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helpers'))
from synthetic_documents import api, docx, pdf, parsed, upload_meta, world


def test_body_table_repeated_quote_exact_paths(tmp_path):
    body = '<w:p><w:r><w:t>付款</w:t></w:r><w:r><w:t>100元</w:t></w:r></w:p><w:p><w:r><w:t>付款100元</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>付款100元</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
    documents, p, database, actor, matter, version, result = parsed(tmp_path, docx(body))
    assert [anchor.quote for anchor in result.anchors] == ['付款100元'] * 3
    assert len({anchor.element_id for anchor in result.anchors}) == 3
    assert [anchor.kind for anchor in result.anchors] == ['body_paragraph', 'body_paragraph', 'table_cell']
    assert result.anchors[-1].table == result.anchors[-1].row == result.anchors[-1].cell == 0
    with database.session() as db:
        for anchor in result.anchors:
            assert documents.resolve_anchor(anchor, version, actor=actor, db=db).quote == '付款100元'
        assert p.read_version(matter.id, version.id, actor, db).parse_status == 'pending'
        assert p.get_parse_result(matter.id, version.id, actor, db) == result


@pytest.mark.parametrize('fragment,part', [
    ('<w:r><w:rPr><w:vanish/></w:rPr><w:t>隐藏</w:t></w:r>', 'hidden'),
    ('<w:r><w:drawing><w:txbxContent><w:p><w:r><w:t>框内100元</w:t></w:r></w:p></w:txbxContent></w:drawing></w:r>', 'textboxes'),
    ('<w:r><w:object/></w:r>', 'embedded_objects'),
    ('<w:sdt><w:sdtContent><w:r><w:t>控件</w:t></w:r></w:sdtContent></w:sdt>', 'unknown_objects'),
])
def test_unsupported_objects_not_claimed_fully_read(tmp_path, fragment, part):
    *_, result = parsed(tmp_path, docx(f'<w:p><w:r><w:t>已读</w:t></w:r>{fragment}</w:p>'))
    assert any(part in unsupported for unsupported in result.unsupported_parts)
    assert result.anchors[0].quote == '已读'


@pytest.mark.parametrize('part', ['word/header1.xml', 'word/footer1.xml', 'word/footnotes.xml', 'word/endnotes.xml', 'word/comments.xml', 'customXml/item1.xml', 'word/media/image1.png'])
def test_inventory_reports_unread_parts(tmp_path, part):
    *_, result = parsed(tmp_path, docx(extras={part: '<unread>独立虚构附件</unread>'}))
    assert part in result.unsupported_parts
    assert any(part in item for item in result.parts)


def test_docprops_binary_is_unread_not_metadata(tmp_path):
    *_, result = parsed(tmp_path, docx(extras={'docProps/thumbnail.jpeg': b'SYNTHETIC unread image'}))
    assert 'docProps/thumbnail.jpeg' in result.unsupported_parts
    assert 'docProps/thumbnail.jpeg:unsupported' in result.parts


@pytest.mark.parametrize('view,quote', [('original', '旧100元'), ('accepted_view', '新200元'), ('rejected_view', '旧100元')])
def test_revision_selected_view_exact(tmp_path, view, quote):
    body = '<w:p><w:del><w:r><w:delText>旧100元</w:delText></w:r></w:del><w:ins><w:r><w:t>新200元</w:t></w:r></w:ins></w:p>'
    *_, result = parsed(tmp_path, docx(body), {'baseline_view': view})
    assert result.anchors[0].quote == quote
    assert any('revisions' in item for item in result.unsupported_parts)


def test_revision_needs_explicit_selection(tmp_path):
    documents = api()
    *_, database, actor, matter = world(tmp_path)
    body = '<w:p><w:ins><w:r><w:t>新增</w:t></w:r></w:ins></w:p>'
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(docx(body)), upload_meta(matter.id), actor, db=db)
        assert error.value.code == 'BASELINE_REQUIRED'


def test_custom_baseline_without_artifact_is_manual(tmp_path):
    *_, result = parsed(tmp_path, docx(), {'baseline_view': 'confirmed_custom'})
    assert result.anchors == ()
    assert 'CUSTOM_BASELINE_ARTIFACT_REQUIRED' in result.quality_issues


def test_external_relationship_is_never_loaded(tmp_path):
    rel = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="e" TargetMode="External" Target="http://127.0.0.1/private" Type="hyperlink"/></Relationships>'
    *_, result = parsed(tmp_path, docx(extras={'word/_rels/document.xml.rels': rel}))
    assert any('external_relationship' in item for item in result.unsupported_parts)


def test_pdf_every_page_scan_gap_and_tail(tmp_path):
    *_, result = parsed(tmp_path, pdf(['SYNTHETIC pay 100', None, 'TAIL guarantee 200']), {'original_name': 'synthetic.pdf', 'mime': 'application/pdf'})
    assert result.pages == (1, 2, 3)
    assert 'page:2:unsupported' in result.parts
    assert 'OCR_NOT_DEPLOYED:page:2' in result.quality_issues
    assert any(anchor.page == 3 and 'TAIL guarantee 200' == anchor.quote for anchor in result.anchors)
    assert all(anchor.bbox is not None for anchor in result.anchors)


def test_pdf_page_limit_rejects_whole_file(tmp_path):
    documents = api()
    settings = load_settings().model_copy(update={'parse_max_pages_per_file': 2})
    *_, database, actor, matter = world(tmp_path, settings)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(pdf(['one', 'two', 'three'])), upload_meta(matter.id, original_name='x.pdf', mime='application/pdf'), actor, db=db)
        assert error.value.code == 'FILE_LIMIT'


def test_over_limit_pdf_does_not_construct_unbounded_pages(tmp_path, monkeypatch):
    documents = api()
    import pdfplumber.pdf as pdf_module
    constructed = []
    original = pdf_module.Page
    def counted(*args, **kwargs):
        constructed.append(kwargs['page_number'])
        return original(*args, **kwargs)
    monkeypatch.setattr(pdf_module, 'Page', counted)
    settings = load_settings().model_copy(update={'parse_max_pages_per_file': 2})
    *_, database, actor, matter = world(tmp_path, settings)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.ingest(BytesIO(pdf(['one', 'two', 'three', 'four'])), upload_meta(matter.id, original_name='x.pdf', mime='application/pdf'), actor, db=db)
        assert error.value.code == 'FILE_LIMIT'
    assert len(constructed) <= 2


def test_unknown_table_row_objects_are_in_inventory(tmp_path):
    body = '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>已读100元</w:t></w:r></w:p></w:tc><w:customContractObject>未读款项</w:customContractObject></w:tr></w:tbl>'
    *_, result = parsed(tmp_path, docx(body))
    assert any('customContractObject' in part for part in result.unsupported_parts)


@pytest.mark.parametrize('wrapper', ['sdt', 'customXml'])
def test_wrapped_table_cells_are_never_silently_lost(tmp_path, wrapper):
    body = f'<w:tbl><w:tr><w:{wrapper}><w:tc><w:p><w:r><w:t>未读担保900元</w:t></w:r></w:p></w:tc></w:{wrapper}></w:tr></w:tbl>'
    *_, result = parsed(tmp_path, docx(body))
    assert any('900元' in anchor.quote for anchor in result.anchors) or any(wrapper in part for part in result.unsupported_parts)


@pytest.mark.parametrize('subtype', ['FreeText', 'FileAttachment', 'Link'])
def test_pdf_annotations_report_unread_obligations(tmp_path, subtype):
    annotation = f'<< /Type /Annot /Subtype /{subtype} /Rect [72 600 300 650] /Contents (SYNTHETIC added pay 900) /A << /S /URI /URI (http://127.0.0.1/private) >> >>'.encode()
    *_, result = parsed(tmp_path, pdf(['SYNTHETIC original 100'], annotation), {'original_name': 'synthetic.pdf', 'mime': 'application/pdf'})
    assert 'page:1:annotations' in result.unsupported_parts
    assert 'page:1:manual' in result.parts


@pytest.mark.parametrize('mode', [3, 7])
def test_pdf_invisible_text_is_manual(tmp_path, mode):
    stream = f'BT /F1 12 Tf {mode} Tr 72 720 Td (SYNTHETIC hidden pay 900) Tj ET'.encode()
    *_, result = parsed(tmp_path, pdf([stream]), {'original_name': 'synthetic.pdf', 'mime': 'application/pdf'})
    assert 'page:1:manual' in result.parts
    assert 'page:1:text_rendering' in result.unsupported_parts
    assert 'TEXT_RENDERING_REQUIRES_CONFIRMATION:page:1' in result.quality_issues


@pytest.mark.parametrize('change', ['quote', 'element_id', 'offset', 'id', 'version'])
def test_resolve_rejects_tampered_or_old_anchor(tmp_path, change):
    documents, p, database, actor, matter, version, result = parsed(tmp_path)
    original = result.anchors[0]
    values = original.model_dump(mode='python')
    if change == 'quote':
        import hashlib
        values.update(quote='伪造付款金额', quote_sha256=hashlib.sha256('伪造付款金额'.encode()).hexdigest(), end=len('伪造付款金额'))
    elif change == 'element_id':
        values['element_id'] = 'body/p[999]'
    elif change == 'offset':
        values.update(start=1, end=original.end + 1)
    elif change == 'id':
        values['id'] = uuid4()
    else:
        values['document_version_id'] = uuid4()
    anchor = type(original)(**values)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            documents.resolve_anchor(anchor, version, actor=actor, db=db)
        assert error.value.code == 'VERSION_CONFLICT'
