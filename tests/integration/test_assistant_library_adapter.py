"""Source-bound citations from a real, independently invented local library."""
import csv
import hashlib
import json

import pytest

from cn_contract import domain as d
from cn_contract.library import service as library_service
from cn_contract.library.catalog import canonical, connection
from cn_contract.library.csv_source import import_case_file
from cn_contract.library.index import activate_generation, build_generation
from cn_contract.library.law_sections import import_laws


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


@pytest.fixture
def library(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    text = ('# 完全虚构资料\n目录\n第一条 租赁\n第二条 保管\n'
            '第一条 这是完全虚构的租赁正文，不能作为正式法律依据。\n'
            '> 第二条 虚构引述租赁规则。\n'
            '第三条 另一个租赁正文。\n第三条 重复租赁条号待核。\n'
            '第四条 仅有相邻禁入标记。')
    (laws / '吉林虚构规则_20250101.md').write_text(text, encoding='utf-8', newline='')
    (laws / '只在标题命中.md').write_text('第一条 这是另一个独立资料。', encoding='utf-8')
    cases = tmp_path / 'cases.csv'
    with cases.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '文书内容', '判决时间', '原始链接'])
        writer.writerow(['纯虚构租赁案', '(2025)虚001号', '虚构法院',
                         '重复内容。' * 260 + '目标租赁正文。' + '重复内容。' * 300,
                         '2025-04-05', 'https://fiction.invalid/case'])
        writer.writerow(['空正文租赁目录', '(2025)虚002号', '虚构法院', '', 'not-a-date', ''])
        writer.writerow(['隔壁资料', '(2025)虚003号', '虚构法院', '只有相邻文书禁入标记。', '', ''])
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    import_case_file(root, cases, 'synthetic')
    activate_generation(root, build_generation(root))
    return root, text


def adapter(root):
    from cn_contract.assistant.tools.library import LegalLibraryAdapter
    return LegalLibraryAdapter(root)


def query(**kwargs):
    return d.AssistantLibraryQuery(**kwargs)


def first_case(root):
    return adapter(root).search(query(text='目标租赁', kind='case_csv')).citations[0]


def test_real_search_produces_exact_citations_without_private_paths(library):
    root, text = library
    page = adapter(root).search(query(text='租赁', kind='law_markdown', limit=8))
    assert page.state == 'ready' and page.generation_id
    assert page.query.limit == 8 and page.coverage['law_markdown'] == 2
    assert 1 <= len(page.citations) <= 8
    for ref in page.citations:
        assert ref.quote == text[ref.start:ref.end]
        assert ref.quote_sha256 == digest(ref.quote)
        assert ref.end - ref.start == len(ref.quote) <= 1200
        assert ref.source_match == 'record_quote_matched'
        assert ref.support_status == ref.applicability_status == 'unverified'
        assert adapter(root).read_original(ref) == ref
    payload = page.model_dump_json()
    assert str(root) not in payload and 'aliases' not in payload and 'raw_fields' not in payload
    assert 'source_url' not in payload


def test_fragment_roles_ambiguity_and_scope_are_preserved(library):
    root, _ = library
    refs = adapter(root).search(query(text='租赁', kind='law_markdown', limit=8)).citations
    assert {'contents_candidate', 'quoted_candidate', 'article_candidate'} <= {r.fragment_role for r in refs}
    assert any(r.article == '第三条' and r.ambiguous for r in refs)
    for ref in refs:
        assert '相邻禁入标记' not in ref.quote
        assert ref.fragment_id is not None


def test_title_only_is_a_candidate_and_not_body_support(library):
    root, _ = library
    ref = adapter(root).search(query(text='只在标题', kind='law_markdown')).citations[0]
    assert ref.match_field == 'title'
    assert ref.match_start is ref.match_end is None and ref.match_in_quote is False
    assert ref.quote == '第一条 这是另一个独立资料。'
    assert ref.support_status == 'unverified'


def test_long_case_quote_has_exact_duplicate_text_position_and_bound(library):
    root, _ = library
    ref = first_case(root)
    text = '重复内容。' * 260 + '目标租赁正文。' + '重复内容。' * 300
    assert ref.quote == text[ref.start:ref.end]
    assert ref.match_start == 1300 and ref.match_end == 1304
    assert ref.match_in_quote is True and len(ref.quote) <= 1200
    assert '相邻文书禁入标记' not in ref.quote
    assert ref.metadata['decision_date'] == '2025-04-05'
    assert ref.title == '纯虚构租赁案'
    assert adapter(root).read_original(ref) == ref


@pytest.mark.parametrize('payload', [
    {'limit': 9}, {'limit': True}, {'text': '字' * 201}, {'court': '字' * 201},
    {'cause': '字' * 201}, {'province': '字' * 201}, {'case_no': '字' * 201},
    {'document_type': '字' * 201}, {'text': 3}, {'cursor': 'x' * 2049},
])
def test_queries_are_bounded(payload):
    with pytest.raises(ValueError):
        query(**payload)


def test_unconfigured_not_ready_empty_and_catalog_only_are_distinct(library, tmp_path):
    root, _ = library
    assert adapter(None).search(query(text='租赁')).state == 'not_configured'
    (root / 'current.json').unlink()
    assert adapter(root).search(query(text='租赁')).state == 'not_ready'
    activate_generation(root, build_generation(root))
    assert adapter(root).search(query(text='绝无命中')).state == 'ready'
    assert adapter(root).search(query(text='绝无命中')).citations == ()
    page = adapter(root).search(query(text='空正文', kind='case_csv'))
    assert page.citations == () and page.omitted_hits == 1


@pytest.mark.parametrize('field,value', [
    ('generation_id', '0' * 31), ('start', True), ('start', -1), ('end', 0),
    ('quote', '伪造原文'), ('quote_sha256', '0' * 64), ('line_start', 0),
    ('support_status', 'verified'), ('applicability_status', 'verified'),
])
def test_malformed_citation_is_not_accepted(library, field, value):
    root, _ = library
    ref = first_case(root).model_copy(update={field: value})
    with pytest.raises(ValueError, match='LIBRARY_CITATION_'):
        adapter(root).read_original(ref)


@pytest.mark.parametrize('field,value', [
    ('record_id', 'f' * 64), ('version_id', 'f' * 64), ('source_id', 'f' * 64),
    ('registered_source_sha256', 'f' * 64), ('raw_sha256', 'f' * 64), ('body_sha256', 'f' * 64),
    ('title', '伪造标题'), ('line_start', 10), ('kind', 'law_markdown'),
    ('citation_id', 'f' * 64), ('match_in_quote', False),
])
def test_changed_citation_identity_or_display_is_rejected(library, field, value):
    root, _ = library
    ref = first_case(root).model_copy(update={field: value})
    with pytest.raises(ValueError, match='LIBRARY_'):
        adapter(root).read_original(ref)


def test_changed_record_metadata_is_derived_again_from_csv(library):
    root, _ = library
    before = first_case(root)
    with connection(root, writable=True) as db:
        row = json.loads(db.execute('SELECT record_json FROM records WHERE record_id=?', (before.record_id,)).fetchone()[0])
        row['fields']['title'] = '篡改标题'
        row['fields']['decision_date'] = '1900-01-01'
        db.execute('UPDATE records SET record_json=? WHERE record_id=?', (canonical(row), before.record_id))
    assert adapter(root).read_original(before) == before
    again = first_case(root)
    assert again.title == '纯虚构租赁案' and again.metadata['decision_date'] == '2025-04-05'


def test_tampered_fragment_semantics_fail_even_with_same_text_hash(library):
    root, _ = library
    ref = next(r for r in adapter(root).search(query(text='租赁', kind='law_markdown', limit=8)).citations
               if r.fragment_role == 'quoted_candidate')
    with connection(root, writable=True) as db:
        row = json.loads(db.execute('SELECT fragment_json FROM fragments WHERE fragment_id=?', (ref.fragment_id,)).fetchone()[0])
        row['role'] = 'article_candidate'
        db.execute('UPDATE fragments SET fragment_json=? WHERE fragment_id=?', (canonical(row), ref.fragment_id))
    with pytest.raises(ValueError, match='LIBRARY_SOURCE_UNAVAILABLE'):
        adapter(root).read_original(ref)


def test_source_corruption_is_never_returned(library):
    root, _ = library
    ref = first_case(root)
    source = root / 'assets' / ref.registered_source_sha256 / 'original'
    raw = source.read_bytes()
    source.write_bytes(raw.replace('目标'.encode(), '坏坏'.encode()))
    with pytest.raises(ValueError, match='LIBRARY_SOURCE_UNAVAILABLE'):
        adapter(root).read_original(ref)


def test_old_generation_is_rejected_even_if_identical_text(library):
    root, _ = library
    ref = first_case(root)
    activate_generation(root, build_generation(root))
    with pytest.raises(ValueError, match='LIBRARY_GENERATION_STALE'):
        adapter(root).read_original(ref)


def test_generation_switch_during_read_discards_result(library, monkeypatch):
    root, _ = library
    new = build_generation(root)
    real = library_service.read_original
    def switch(*args):
        result = real(*args)
        activate_generation(root, new)
        return result
    monkeypatch.setattr(library_service, 'read_original', switch)
    with pytest.raises(ValueError, match='LIBRARY_GENERATION_STALE'):
        adapter(root).search(query(text='目标租赁', kind='case_csv'))


def test_partial_timeout_preserves_state_and_cursor(library, monkeypatch):
    root, _ = library
    real = library_service.search
    def partial(*args):
        return real(*args).model_copy(update={'state': 'timeout', 'next_cursor': 'partial-cursor'})
    monkeypatch.setattr(library_service, 'search', partial)
    page = adapter(root).search(query(text='目标租赁', kind='case_csv'))
    assert page.state == 'timeout' and page.citations and page.next_cursor == 'partial-cursor'


def test_same_citation_has_stable_id_without_writing_catalog(library):
    root, _ = library
    with connection(root) as db:
        before = tuple(db.iterdump())
    first = first_case(root)
    assert first_case(root).citation_id == first.citation_id
    assert adapter(root).read_original(first).citation_id == first.citation_id
    with connection(root) as db:
        assert tuple(db.iterdump()) == before


def test_cross_fragment_phrase_is_not_quoted_as_single_rule(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    (laws / '虚构分界.md').write_text('第一条 前段末尾甲\n第二条 后段开头乙。', encoding='utf-8', newline='')
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    activate_generation(root, build_generation(root))
    page = adapter(root).search(query(text='尾甲 第二条', mode='phrase', kind='law_markdown'))
    assert page.citations == ()
    assert page.omitted_hits == 1


def test_index_hit_metadata_cannot_supply_quote_or_fragment_semantics(library, monkeypatch):
    root, text = library
    real = library_service.search
    def changed(*args):
        page = real(*args)
        hits = tuple(hit.model_copy(update={'snippet': '伪造正文', 'title': '伪造标题',
                    'fragment_role': 'paragraph', 'article': '伪造条号', 'ambiguous': False})
                     for hit in page.hits)
        return page.model_copy(update={'hits': hits})
    monkeypatch.setattr(library_service, 'search', changed)
    page = adapter(root).search(query(text='租赁', kind='law_markdown', limit=8))
    assert any(ref.ambiguous for ref in page.citations)
    assert any(ref.fragment_role == 'quoted_candidate' for ref in page.citations)
    for ref in page.citations:
        assert ref.quote == text[ref.start:ref.end]
        assert ref.title == '吉林虚构规则' and ref.article != '伪造条号'


def test_metadata_filters_are_rechecked_from_original_csv(library, monkeypatch):
    root, _ = library
    real = library_service.search
    def wrong_filter(path, requested):
        # Simulates a damaged derived index accepting a different court.
        return real(path, requested.model_copy(update={'court': None}))
    monkeypatch.setattr(library_service, 'search', wrong_filter)
    page = adapter(root).search(query(text='目标租赁', court='另一个虚构法院', kind='case_csv'))
    assert page.citations == () and page.omitted_hits == 1


def test_normalized_match_keeps_unicode_and_crlf_source_coordinates(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    original = '# 合成\r\n第一条 ＡＢＣ租\u200b赁\r\n第二条 禁止进入。'
    (laws / '虚构全角.md').write_text(original, encoding='utf-8', newline='')
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    activate_generation(root, build_generation(root))
    ref = adapter(root).search(query(text='abc租赁')).citations[0]
    assert ref.match_start == 10 and ref.match_end == 16
    assert ref.start == 6 and ref.end == 18
    assert ref.quote == '第一条 ＡＢＣ租\u200b赁\r\n'
    assert ref.line_start == ref.line_end == 2
    assert adapter(root).read_original(ref) == ref


def test_result_limit_and_cursor_remain_bounded(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    for index in range(10):
        (laws / f'虚构规则{index}.md').write_text(f'第一条 统一租赁规则{index}。', encoding='utf-8')
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    activate_generation(root, build_generation(root))
    first = adapter(root).search(query(text='统一租赁', limit=8))
    assert len(first.citations) == 8 and first.next_cursor
    second = adapter(root).search(query(text='统一租赁', limit=8, cursor=first.next_cursor))
    assert len(second.citations) == 2 and second.next_cursor is None
    assert not {r.citation_id for r in first.citations} & {r.citation_id for r in second.citations}
    activate_generation(root, build_generation(root))
    with pytest.raises(ValueError, match='LIBRARY_QUERY_INVALID'):
        adapter(root).search(query(text='统一租赁', limit=8, cursor=first.next_cursor))


def test_invisible_expansion_never_exceeds_quote_limit_or_claims_full_match(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    original = '第一条 目' + '\u200b' * 1500 + '标。'
    (laws / '虚构隐形字符.md').write_text(original, encoding='utf-8')
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    activate_generation(root, build_generation(root))
    ref = adapter(root).search(query(text='目标')).citations[0]
    assert len(ref.quote) == 1200 and ref.match_in_quote is False
    assert ref.quote == original[:1200]
    assert ref.match_start == 4 and ref.match_end == 1506
    assert adapter(root).read_original(ref) == ref


@pytest.mark.parametrize('field', ['citation_id', 'record_id', 'version_id', 'source_id',
                                  'registered_source_sha256', 'raw_sha256', 'body_sha256', 'quote_sha256'])
def test_citation_hashes_do_not_coerce_bytes(library, field):
    root, _ = library
    ref = first_case(root)
    bad = ref.model_dump(mode='python')
    bad[field] = bad[field].encode('ascii')
    with pytest.raises(ValueError):
        d.CitationRef.model_validate(bad)


def test_unavailable_errors_are_fixed_without_exposing_local_paths(library, monkeypatch):
    root, _ = library
    ref = first_case(root)
    def missing(*args):
        raise OSError(f'cannot read private location {root}/asset')
    monkeypatch.setattr(library_service, 'read_original', missing)
    with pytest.raises(ValueError) as error:
        adapter(root).read_original(ref)
    assert str(error.value) == 'LIBRARY_SOURCE_UNAVAILABLE'
    with pytest.raises(ValueError, match='LIBRARY_NOT_CONFIGURED'):
        adapter(None).read_original(ref)


def test_title_index_false_positive_is_not_a_verified_candidate(library, monkeypatch):
    root, _ = library
    real = library_service.search
    def wrong_title(path, requested):
        return real(path, requested.model_copy(update={'text': '只在标题'}))
    monkeypatch.setattr(library_service, 'search', wrong_title)
    page = adapter(root).search(query(text='伪造标题', kind='law_markdown'))
    assert page.citations == () and page.omitted_hits == 1


def test_model_copy_cannot_bypass_strict_input_types(library):
    root, _ = library
    ref = first_case(root)
    with pytest.raises(ValueError, match='LIBRARY_CITATION_INVALID'):
        adapter(root).read_original(ref.model_copy(update={'source_id': ref.source_id.encode('ascii')}))
    with pytest.raises(ValueError, match='LIBRARY_QUERY_INVALID'):
        adapter(root).search(query(text='租赁').model_copy(update={'text': '租赁'.encode('utf-8')}))


def test_kind_filter_is_rechecked_from_source(library, monkeypatch):
    root, _ = library
    real = library_service.search
    def wrong_kind(path, requested):
        return real(path, requested.model_copy(update={'kind': 'all'}))
    monkeypatch.setattr(library_service, 'search', wrong_kind)
    page = adapter(root).search(query(text='只在标题', kind='case_csv'))
    assert page.citations == () and page.omitted_hits == 1


def test_body_hit_cannot_be_relabelled_as_title(library, monkeypatch):
    root, _ = library
    real = library_service.search
    def changed(path, requested):
        page = real(path, requested)
        assert page.hits[0].match_field == 'body'
        return page.model_copy(update={'hits': tuple(hit.model_copy(update={
            'match_field': 'title', 'match_start': None, 'match_end': None,
            'title': '目标租赁伪造标题'}) for hit in page.hits)})
    monkeypatch.setattr(library_service, 'search', changed)
    page = adapter(root).search(query(text='目标租赁', kind='case_csv'))
    assert page.citations == () and page.omitted_hits == 1


def test_query_can_start_inside_normalized_compatibility_character(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    original = '第一条 ㍻年标记。'
    (laws / '虚构兼容字符.md').write_text(original, encoding='utf-8')
    root = tmp_path / 'library'
    import_laws(root, laws, 'synthetic')
    activate_generation(root, build_generation(root))
    requested = query(text='成年', kind='law_markdown')
    assert len(library_service.search(root, requested).hits) == 1
    page = adapter(root).search(requested)
    assert len(page.citations) == 1 and page.omitted_hits == 0
    ref = page.citations[0]
    assert ref.match_start == 4 and ref.match_end == 6
    assert original[ref.match_start:ref.match_end] == '㍻年'
    assert ref.quote == original and adapter(root).read_original(ref) == ref


def test_nonreferenced_csv_row_change_does_not_imply_whole_file_rehash(library):
    root, _ = library
    ref = first_case(root)
    source = root / 'assets' / ref.registered_source_sha256 / 'original'
    raw = source.read_bytes()
    changed = raw.replace('只有相邻文书禁入标记'.encode(), '另一相邻文书禁入标记'.encode())
    assert len(raw) == len(changed) and raw != changed
    source.write_bytes(changed)
    assert hashlib.sha256(source.read_bytes()).hexdigest() != ref.registered_source_sha256
    assert adapter(root).read_original(ref) == ref
    assert ref.source_match == 'record_quote_matched'
