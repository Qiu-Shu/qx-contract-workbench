"""Persistent library records have one bounded, canonical representation."""
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.config import canonical_json


def request(**changes):
    assert hasattr(d, 'LibraryHandlerRequest'), 'persistent library request is not implemented'
    return d.LibraryHandlerRequest(**{'tool':'legal_library.search',
        'query':d.AssistantLibraryQuery(text='独立合成检索'), **changes})


def test_persistent_request_rejects_caller_authored_citation():
    request()
    with pytest.raises(ValueError):
        request(citation={'quote':'untrusted'})
    with pytest.raises(ValueError):
        request(saved_citation_id=uuid4())
    with pytest.raises(ValueError):
        request(tool='legal_library.read_original')


def test_canonical_roundtrip_rejects_duplicates_and_noncanonical_json():
    value = request()
    from cn_contract.assistant.library_records import encoded, model, sha
    raw = encoded(value)
    assert model(d.LibraryHandlerRequest, raw) == value
    assert len(sha(raw)) == 64
    for invalid in (' ' + raw, raw[:-1] + ',"tool":"legal_library.search"}', '{}', 'null'):
        with pytest.raises(ValueError, match='LIBRARY_RECORD_INVALID'):
            model(d.LibraryHandlerRequest, invalid)


def test_corrupt_deep_json_uses_fixed_record_error():
    from cn_contract.assistant.library_records import model
    with pytest.raises(ValueError, match='LIBRARY_RECORD_INVALID'):
        model(d.LibraryHandlerRequest, '[' * 20000 + '0' + ']' * 20000)


def test_result_ids_must_be_unique_and_match_citation_count():
    assert hasattr(d, 'LibraryHandlerResult'), 'persistent result is not implemented'
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=1, materials_revision=0)
    value = d.AssistantLibraryToolResult(tool='legal_library.search', scope=scope,
        page=d.LibraryCitationPage(query=d.AssistantLibraryQuery(), state='not_configured'))
    assert d.LibraryHandlerResult(result=value, citation_ids=()).result == value
    with pytest.raises(ValueError):
        d.LibraryHandlerResult(result=value, citation_ids=(uuid4(),))


def synthetic_citation():
    from cn_contract.library.catalog import canonical, digest
    value = dict(generation_id='a' * 32, record_id='b' * 64, version_id='c' * 64,
        source_id='d' * 64, registered_source_sha256='e' * 64, raw_sha256='f' * 64,
        body_sha256='c' * 64, kind='case_csv', title='独立虚构案例', metadata={},
        fragment_id=None, fragment_role=None, article=None, ambiguous=False, start=0, end=4,
        line_start=1, line_end=1, quote='合成原文', quote_sha256=digest('合成原文'.encode()),
        match_field='body', match_start=0, match_end=2, match_in_quote=True,
        source_match='record_quote_matched', support_status='unverified', applicability_status='unverified')
    value['citation_id'] = digest(canonical(['qx-library-citation-v1', value]).encode())
    return d.CitationRef.model_validate(value)


def citation_container(citation, kind):
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=1, materials_revision=0)
    if kind == 'citation':
        return citation
    if kind == 'saved':
        return d.SavedLibraryCitation(id=uuid4(), receipt_id=uuid4(), run_id=uuid4(),
            scope=scope, citation=citation, created_at='2026-10-20T00:00:00Z')
    page = d.LibraryCitationPage(query=d.AssistantLibraryQuery(), state='ready',
        generation_id=citation.generation_id, citations=(citation,))
    if kind == 'page':
        return page
    result = d.AssistantLibraryToolResult(tool='legal_library.search', scope=scope, page=page)
    return d.LibraryHandlerResult(result=result, citation_ids=(uuid4(),))


@pytest.mark.parametrize('kind', ['citation', 'page', 'handler', 'saved'])
@pytest.mark.parametrize('changes', [{'citation_id':'0' * 64}, {'title':'被替换的虚构标题'}])
def test_every_citation_container_checks_its_own_content_identity(kind, changes):
    from cn_contract.assistant.library_records import encoded, model
    original = synthetic_citation()
    good = citation_container(original, kind)
    assert model(type(good), encoded(good)) == good
    changed = citation_container(original.model_copy(update=changes), kind)
    with pytest.raises(ValueError, match='LIBRARY_RECORD_INVALID'):
        encoded(changed)
    # Recalculating an outer payload hash must not turn the nested identity valid.
    raw = canonical_json(changed.model_dump(mode='json'))
    with pytest.raises(ValueError, match='LIBRARY_RECORD_INVALID'):
        model(type(changed), raw)
