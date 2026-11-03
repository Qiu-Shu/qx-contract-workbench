"""保存的引用有两种契约，完整性校验必须按各自的契约解析，而不是拿旧模型套新引用。"""
from hashlib import sha256

import pytest

from cn_contract import domain as d
from cn_contract.assistant.library_integrity import _citation
from cn_contract.assistant.library_records import citation_body, encoded, model, result_citations

TEXT = '唯一条文正文'
UNIT = 'law_unit:unit_0123456789abcdef01234567'
CASE = 'case_book:2026年度案例【虚构买卖合同】#001'


def knowledge(source_id=UNIT, text=TEXT):
    digest = sha256(text.encode('utf-8')).hexdigest()
    return d.KnowledgeCitation(
        source_id=source_id, kind='law' if source_id.startswith('law_unit:') else 'case',
        title='虚构条文', heading_path='',
        source_version={'sha256': 'a' * 64, 'basis': 'documents.sha256+raw_text_recomputed',
                        'verified': 'recomputed'},
        location=d.KnowledgeLocation(line_start=2, line_end=2, char_start=0, char_end=len(text),
                                     basis='text_search'),
        snippet=d.KnowledgeSnippet(text=text, start=0, end=len(text), sha256=digest,
                                   match_field='body', match_start=0, match_end=2),
        verification=d.KnowledgeVerification(support='unverified', applicability='unverified'),
        score=1.0, score_basis='bm25_char_bigram_v1')


def row(raw):
    return {'citation_json': raw}


def test_saved_knowledge_citation_uses_its_own_contract():
    value = knowledge()
    parsed = _citation(row(encoded(value)))
    assert parsed == value
    assert isinstance(parsed, d.KnowledgeCitation)


def legacy():
    from cn_contract.assistant.citation_identity import citation_identity
    quote = '虚构片段'
    draft = d.CitationRef(citation_id='0' * 64, generation_id='ab' * 16, record_id='cd' * 32,
        version_id='ef' * 32, source_id='12' * 32, registered_source_sha256='34' * 32,
        raw_sha256='56' * 32, body_sha256='78' * 32, kind='law_markdown', title='虚构条文',
        metadata={}, fragment_id=None, fragment_role=None, article=None, ambiguous=False,
        start=0, end=len(quote), line_start=1, line_end=1, quote=quote,
        quote_sha256=sha256(quote.encode('utf-8')).hexdigest(), match_field='body',
        match_start=0, match_end=2, match_in_quote=True)
    return draft.model_copy(update={'citation_id': citation_identity(draft.model_dump(mode='json'))})


def test_legacy_citation_ref_rows_still_validate():
    # 旧记录不能被新契约顺手判死：本地资料库保存的 CitationRef 必须照旧解析
    reference = legacy()
    parsed = _citation(row(encoded(reference)))
    assert parsed == reference
    assert isinstance(parsed, d.CitationRef)


def test_unknown_citation_shape_is_refused():
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        _citation(row('{"quote":"untrusted"}'))


def test_tampered_snippet_text_is_refused():
    value = knowledge()
    raw = encoded(value)
    # 把片段文本换掉、哈希留在原处：这正是"内容被替换但记录没变"的形态
    broken = raw.replace(TEXT, '替换后正文')
    assert broken != raw
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        _citation(row(broken))


def test_version_must_be_a_full_sha256():
    value = knowledge()
    raw = encoded(value).replace('a' * 64, 'abc')
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        _citation(row(raw))


def test_snippet_window_must_sit_inside_the_located_block():
    # 直接改库里的 JSON（不走模型）：写入路径会先拦一次，历史记录只能靠读取校验
    raw = encoded(knowledge())
    broken = raw.replace('"char_start":0', '"char_start":5')
    assert broken != raw
    with pytest.raises(ValueError, match='ASSISTANT_LIBRARY_INTEGRITY'):
        _citation(row(broken))


def test_result_citations_keep_law_then_case_order():
    # 回执里的引用顺序必须与 citation_ids 的顺序一致，否则前端会配错引用
    page = d.KnowledgeSearchPage(state='ready', query='虚构检索', groups={
        'law': (knowledge(),), 'case': (knowledge(CASE),)})
    result = d.AssistantLibraryToolResult(tool='legal_knowledge.search',
        scope=_scope(), knowledge_page=page)
    assert [item.source_id for item in result_citations(result)] == [UNIT, CASE]
    # 检索结果模型没有 knowledge_citation 字段：单条引用体只属于回执层
    assert citation_body(result) is None


def _scope():
    from uuid import uuid4
    return d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), scope_kind='conversation',
                           scope_ref=None, input_revision=1, materials_revision=0, binding_revision=1)


def test_knowledge_result_roundtrip_is_canonical():
    result = d.AssistantLibraryToolResult(tool='legal_knowledge.search', scope=_scope(),
        knowledge_page=d.KnowledgeSearchPage(state='ready', query='虚构检索',
                                             groups={'law': (knowledge(),), 'case': ()}))
    raw = encoded(result)
    assert model(d.AssistantLibraryToolResult, raw) == result
