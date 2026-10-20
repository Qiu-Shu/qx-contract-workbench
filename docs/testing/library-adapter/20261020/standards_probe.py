"""Independent synthetic standards probe; never touches configured libraries."""
import csv
import warnings

import pytest

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.library import service
from cn_contract.library.csv_source import import_case_file
from cn_contract.library.index import activate_generation, build_generation
from cn_contract.assistant.tools.service import execute_tool
from cn_contract.security import ServiceError
from tests.integration.test_assistant_storage import workspace, conversation


def test_title_classification_is_rechecked_against_original_title(tmp_path, monkeypatch):
    source = tmp_path / 'independent.csv'
    with source.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '文书内容'])
        writer.writerow(['独立合成空白标题', '(2026)虚901号', '完全虚构法院',
                         '这是独立合成前言。' * 200 + '探针标的只存在正文。'])
    root = tmp_path / 'standards-library'
    import_case_file(root, source, 'independent-standards')
    activate_generation(root, build_generation(root))
    original_search = service.search

    def damaged_title_hit(path, query):
        page = original_search(path, query)
        assert page.hits and page.hits[0].match_field == 'body'
        return page.model_copy(update={'hits': tuple(hit.model_copy(update={
            'match_field': 'title', 'match_start': None, 'match_end': None,
            'title': '探针标的伪造索引标题',
        }) for hit in page.hits)})

    monkeypatch.setattr(service, 'search', damaged_title_hit)
    page = LegalLibraryAdapter(root).search(d.AssistantLibraryQuery(text='探针标的', kind='case_csv'))
    assert page.citations == (), 'Original title does not contain the query; index title label must be rejected'


def test_rejected_copied_input_does_not_log_query_content(workspace):
    database, actors, _, _ = workspace
    view = conversation(workspace)
    query = d.AssistantLibraryQuery(text='synthetic').model_copy(update={'text': b'PRIVATE_QUERY_MARKER'})
    call = d.AssistantLibraryToolCall(tool='legal_library.search', expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, query=d.AssistantLibraryQuery(text='synthetic'))
    call = call.model_copy(update={'query': query})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        with pytest.raises(ServiceError) as rejected:
            execute_tool(actors['lawyer'], call, database, LegalLibraryAdapter(None))
    assert rejected.value.code == 'LIBRARY_TOOL_INPUT_INVALID'
    assert all('PRIVATE_QUERY_MARKER' not in str(warning.message) for warning in caught)

