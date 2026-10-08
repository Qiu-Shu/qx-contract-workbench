"""Presentation only: fictional parse inventories and actual protected exports."""
from io import BytesIO
import importlib
from docx import Document
import pytest
from tests.helpers.synthetic_exports import setup, package, api


@pytest.mark.parametrize('pages,expected', [
    ([], ''), ([1], '1'), ([3, 1, 2, 2, 5, 7, 8], '1–3、5、7–8'),
    (list(range(1, 49)), '1–48'),
])
def test_page_ranges_preserve_gaps(pages, expected):
    assert api()._page_ranges(pages) == expected


def test_client_labels_preserve_unknown_diagnostics():
    values = ['page:1:unsupported', 'page:3:unsupported', 'page:4:unsupported',
              'page:2:images', 'page:01:unsupported', 'page:0:unsupported',
              'OCR_NOT_DEPLOYED:page:1', 'OCR_NOT_DEPLOYED:page:3',
              'PDF_COORDINATES_UNRELIABLE:page:2', 'unknown:page:5']
    text = api()._client_scope_labels(values)
    assert '自动解析未取得可用文字：第1、3–4页' in text
    assert '自动解析未取得文字：第1、3页（按页识别和人工来源核对另行记录）' in text
    for unknown in (values[3], values[4], values[5], values[8], values[9]):
        assert unknown in text


@pytest.mark.parametrize('audience', ['client', 'internal', 'counterparty'])
def test_scope_presentation_keeps_audience_and_source_boundaries(tmp_path, monkeypatch, audience):
    world = setup(tmp_path)
    database, actor, _, _, _, parsed, run = world
    # Simulates the automatic parser's inventory, not an OCR or legal quality test.
    inventory = parsed.model_copy(update={
        'parts': tuple(f'page:{p}:unsupported' for p in range(1, 49)),
        'pages': tuple(range(1, 49)),
        'unsupported_parts': tuple(f'page:{p}' for p in range(1, 49)),
        'quality_issues': tuple(f'OCR_NOT_DEPLOYED:page:{p}' for p in range(1, 49)) + ('UNKNOWN_DIAGNOSTIC',),
    })
    original_scope = api()._scope
    def synthetic_scope(*args, **kwargs):
        with monkeypatch.context() as local:
            local.setattr(importlib.import_module('cn_contract.documents.ingest'), '_parse', lambda *args: inventory)
            return original_scope(*args, **kwargs)
    monkeypatch.setattr(api(), '_scope', synthetic_scope)
    bundle = package(world, audience)
    with database.session() as db:
        raw = api().download_artifact(bundle.artifacts[0].id, actor, db=db).getvalue()
    document = Document(BytesIO(raw))
    text = '\n'.join(p.text for p in document.paragraphs)
    if audience == 'counterparty':
        assert '读取材料范围' not in text
        assert 'UNKNOWN_DIAGNOSTIC' not in text
    else:
        assert str(run.id) in text
        assert next(iter(run.manifest.document_hashes.values())) in text
        assert 'UNKNOWN_DIAGNOSTIC' in text
        assert '未查询不能解释为无风险' in text
        if audience == 'client':
            assert '页码范围：1–48' in text
            assert '未支持或未读项：第1–48页' in text
            assert '按页识别和人工来源核对另行记录' in text
            assert 'OCR_NOT_DEPLOYED' not in text
            assert '事实快照：' not in text
        else:
            assert 'OCR_NOT_DEPLOYED:page:48' in text
            assert '页码范围：1、2、3、' in text
            assert '事实快照：' + run.manifest.fact_snapshot_sha256 in text
