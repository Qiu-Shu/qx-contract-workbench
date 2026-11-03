"""只读知识服务接入显式检索路径的契约测试。

这几条盯的都是"会不会悄悄退化"：
- 知识服务的引用是 `KnowledgeCitation`，不能被硬塞进 `CitationRef`（那需要伪造文件类型）；
- 两种来源的结果各自带自己的字段，互不冒充；
- 保存引用的顺序必须与展示顺序一致，否则前端按 index 取 id 会配错引用；
- 服务故障、未配置、关键词非法要映射成既有错误码，不能被当成"没命中"。
"""
from __future__ import annotations

import hashlib

import pytest

from cn_contract import domain as d
from cn_contract.assistant.tools.knowledge_source import KnowledgeLibraryAdapter
from cn_contract.assistant.tools.kb_readonly import KnowledgeServiceError
from cn_contract.assistant.tools.service import ResearchSources
from cn_contract.assistant.library_records import result_citations


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _citation(source_id: str, kind: str, title: str, quote: str) -> dict:
    start = 0
    return {
        'source_id': source_id,
        'kind': kind,
        'title': title,
        'heading_path': '',
        'source_version': {'sha256': _sha('原文'), 'basis': 'documents.sha256+raw_text_recomputed',
                           'verified': 'recomputed'},
        'location': {'line_start': 1, 'line_end': 2, 'char_start': start, 'char_end': start + len(quote),
                     'basis': 'line_map'},
        'snippet': {'text': quote, 'start': start, 'end': start + len(quote), 'sha256': _sha(quote),
                    'match_field': 'block', 'match_start': None, 'match_end': None},
        'verification': {'support': 'unverified', 'applicability': 'unverified'},
        'score': 1.0,
        'score_basis': 'like_bounded',
    }


def _page(law=(), case=()) -> d.KnowledgeSearchPage:
    law, case = tuple(law), tuple(case)
    return d.KnowledgeSearchPage.model_validate({
        'state': 'ready' if (law or case) else 'empty',
        'query': '违约金',
        'groups': {'law': list(law), 'case': list(case)},
        'notes': [],
        'degraded': [],
        'elapsed_ms': 1.0,
    })


class _Client:
    def __init__(self, page=None, error=None, captured=None):
        self.page = page
        self.error = error
        self.captured = captured if captured is not None else []

    def search(self, request):
        self.captured.append(request)
        if self.error is not None:
            raise self.error
        return self.page


def test_adapter_maps_query_and_returns_own_page():
    captured = []
    page = _page(law=[_citation('law_unit:unit_' + 'a' * 24, 'law', '第三条', '违约金过高可以请求减少')])
    adapter = KnowledgeLibraryAdapter(_Client(page=page, captured=captured))
    result = adapter.search(d.AssistantLibraryQuery(text='违约金 过高', limit=5))
    assert result is page
    assert captured[0].query == '违约金 过高'
    assert captured[0].kinds == ('law', 'case')
    assert captured[0].limit == 5


@pytest.mark.parametrize('code,expected', [
    ('KB_SERVICE_NOT_CONFIGURED', 'LIBRARY_NOT_CONFIGURED'),
    ('KB_SERVICE_UNAVAILABLE', 'LIBRARY_SOURCE_UNAVAILABLE'),
    ('KB_SERVICE_DEGRADED', 'LIBRARY_SOURCE_UNAVAILABLE'),
    ('KNOWLEDGE_QUERY_INVALID', 'LIBRARY_QUERY_INVALID'),
    ('KNOWLEDGE_SOURCE_STALE', 'LIBRARY_GENERATION_STALE'),
])
def test_adapter_maps_service_errors_to_existing_codes(code, expected):
    adapter = KnowledgeLibraryAdapter(_Client(error=KnowledgeServiceError(code)))
    with pytest.raises(ValueError) as caught:
        adapter.search(d.AssistantLibraryQuery(text='违约金', limit=3))
    assert str(caught.value) == expected


def test_adapter_rejects_filter_only_query():
    # 只给法院/案号这类条件时知识服务没有对应检索面，必须明确拒绝
    adapter = KnowledgeLibraryAdapter(_Client(page=_page()))
    with pytest.raises(ValueError) as caught:
        adapter.search(d.AssistantLibraryQuery(text='', court='虚构中院', limit=3))
    assert str(caught.value) == 'LIBRARY_QUERY_INVALID'


def test_sources_without_knowledge_report_not_configured():
    class _Library:
        def search(self, query):
            raise AssertionError('不该走本地资料库')

    sources = ResearchSources(_Library(), None)
    with pytest.raises(ValueError) as caught:
        sources.knowledge_search(d.AssistantLibraryQuery(text='违约金', limit=3))
    assert str(caught.value) == 'LIBRARY_NOT_CONFIGURED'


def test_knowledge_result_keeps_its_own_shape():
    quote = '违约金过分高于造成的损失的，可以请求适当减少。'
    page = _page(law=[_citation('law_unit:unit_' + 'b' * 24, 'law', '第四条', quote)])
    result = d.AssistantLibraryToolResult(tool='legal_knowledge.search', scope=_scope(), knowledge_page=page)
    assert result.page is None and result.citation is None
    assert result.knowledge_page.groups['law'][0].source_id.startswith('law_unit:')
    # 不允许把知识服务的结果塞进本地资料库的页，反之亦然
    with pytest.raises(ValueError):
        d.AssistantLibraryToolResult(tool='legal_knowledge.search', scope=_scope(), page=d.LibraryCitationPage(
            query=d.AssistantLibraryQuery(text='违约金', limit=3), state='not_configured'))


def test_saved_citation_order_follows_display_order():
    law = _citation('law_unit:unit_' + 'c' * 24, 'law', '第三条', '法条摘录')
    case = _citation('case_book:2026年度案例【虚构】#001', 'case', '虚构案例', '裁判要旨摘录')
    result = d.AssistantLibraryToolResult(tool='legal_knowledge.search', scope=_scope(),
                                          knowledge_page=_page(law=[law], case=[case]))
    saved = result_citations(result)
    assert [item.source_id for item in saved] == [law['source_id'], case['source_id']]
    handler_result = d.LibraryHandlerResult(result=result, citation_ids=_ids(2))
    assert len(handler_result.citation_ids) == 2


def test_saved_citation_carries_exactly_one_body():
    citation = d.KnowledgeCitation.model_validate(
        _citation('law_unit:unit_' + 'd' * 24, 'law', '第三条', '法条摘录'))
    saved = d.SavedLibraryCitation(id=_uuid(1), receipt_id=_uuid(2), run_id=_uuid(3), scope=_scope(),
                                   knowledge_citation=citation, created_at='2026-11-01T00:00:00Z')
    assert saved.citation is None
    with pytest.raises(ValueError):
        d.SavedLibraryCitation(id=_uuid(1), receipt_id=_uuid(2), run_id=_uuid(3), scope=_scope(),
                               created_at='2026-11-01T00:00:00Z')


def _uuid(value: int) -> str:
    return f'00000000-0000-4000-8000-{value:012d}'


def _ids(count: int):
    from uuid import UUID
    return tuple(UUID(_uuid(index + 1)) for index in range(count))


def _scope() -> d.ScopeSnapshot:
    return d.ScopeSnapshot.model_validate({
        'workspace_id': _uuid(9), 'conversation_id': _uuid(8), 'scope_kind': 'matter',
        'scope_ref': _uuid(7), 'binding_revision': 1, 'input_revision': 0, 'materials_revision': 0,
    })
