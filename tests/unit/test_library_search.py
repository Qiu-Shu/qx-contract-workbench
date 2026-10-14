"""Chinese retrieval must resolve to the original version and character span."""
import csv
import importlib
import importlib.util
from pathlib import Path

import pytest


def api(name):
    assert importlib.util.find_spec('cn_contract.library.' + name), name + ' missing'
    return importlib.import_module('cn_contract.library.' + name)


def world(tmp_path):
    index = api('index')
    incoming = tmp_path / 'cases.csv'
    bodies = ['这是虚构资料，离\u200b婚后处理租赁。', '虚构离婚租赁连续短语。', '只有虚构租赁，不含别的词。']
    with incoming.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['标题', '案号', '法院', '省', '判决时间', '文书内容', '文书类型', '案由'])
        for i, body in enumerate(bodies, 1):
            writer.writerow(['租赁标题' if i == 3 else '虚构案' + str(i), f'（２０２５）吉虚{i}号',
                             '虚构法院', '吉林省', '2025-01-02', body, '判决书', '租赁合同纠纷'])
    root = tmp_path / 'library'
    api('csv_source').import_case_file(root, incoming, 'fiction')
    generation = index.build_generation(root)
    index.activate_generation(root, generation)
    return root, generation


def query(**values):
    return importlib.import_module('cn_contract.domain').LibraryQuery(**values)


def test_two_character_words_original_offsets_and_phrase_all(tmp_path):
    root, _ = world(tmp_path)
    service = api('service')
    page = service.search(root, query(text='离婚', kind='case_csv'))
    assert len(page.hits) == 2
    for hit in page.hits:
        original = service.read_original(root, hit.record_id, hit.version_id)
        assert '离婚' == original.text[hit.match_start:hit.match_end].replace('\u200b', '')
        assert hit.verification_status == 'unverified'
    phrase = service.search(root, query(text='离婚租赁', mode='phrase'))
    assert len(phrase.hits) == 1
    all_words = service.search(root, query(text='离婚 租赁', mode='all'))
    assert len(all_words.hits) == 2


def test_case_number_filters_and_title_ranking(tmp_path):
    root, _ = world(tmp_path)
    service = api('service')
    exact = service.search(root, query(case_no='(2025)吉虚1号', kind='case_csv'))
    assert len(exact.hits) == 1
    ranked = service.search(root, query(text='租赁', kind='case_csv', province='吉林省'))
    assert ranked.hits[0].title == '租赁标题'
    assert not service.search(root, query(text='租赁', province='不存在的省')).hits


def test_control_characters_do_not_inject_queries_and_single_han_is_explicit(tmp_path):
    root, _ = world(tmp_path)
    service = api('service')
    assert not service.search(root, query(text='"OR秘密"')).hits
    assert not service.search(root, query(text='b')).hits
    for text in ('法', '!!!', '" OR 秘密'):
        with pytest.raises(ValueError, match='QUERY_'):
            service.search(root, query(text=text))


def test_cursor_is_bound_to_query_and_generation(tmp_path):
    root, generation = world(tmp_path)
    service = api('service')
    first = service.search(root, query(text='租赁', limit=1))
    assert first.next_cursor
    second = service.search(root, query(text='租赁', limit=1, cursor=first.next_cursor))
    assert second.hits[0].record_id != first.hits[0].record_id
    with pytest.raises(ValueError, match='CURSOR_'):
        service.search(root, query(text='离婚', limit=1, cursor=first.next_cursor))
    new_generation = api('index').build_generation(root)
    api('index').activate_generation(root, new_generation)
    with pytest.raises(ValueError, match='CURSOR_'):
        service.search(root, query(text='租赁', limit=1, cursor=first.next_cursor))


def test_source_hash_and_version_must_match(tmp_path):
    root, _ = world(tmp_path)
    service = api('service')
    hit = service.search(root, query(text='离婚')).hits[0]
    with pytest.raises(ValueError, match='VERSION_'):
        service.read_original(root, hit.record_id, 'f' * 64)
    original = service.read_original(root, hit.record_id, hit.version_id)
    path = root / 'assets' / original.source.asset_key
    path.write_bytes(b'x' * path.stat().st_size)
    with pytest.raises(ValueError, match='HASH_MISMATCH|HEADER_INVALID|SOURCE_CHANGED'):
        service.read_original(root, hit.record_id, hit.version_id)


def test_law_fragments_remain_in_one_version(tmp_path):
    index = api('index')
    laws = tmp_path / 'laws'
    laws.mkdir()
    (laws / '吉林省虚构规定_20200101.md').write_text('第一条 虚构租赁规则甲。\n第二条 旧文本。', encoding='utf-8')
    (laws / '吉林省虚构规定_20250101.md').write_text('第一条 虚构租赁规则乙。\n第二条 新文本。', encoding='utf-8')
    root = tmp_path / 'library'
    api('law_sections').import_laws(root, laws, 'fiction-laws')
    index.activate_generation(root, index.build_generation(root))
    service = api('service')
    page = service.search(root, query(text='租赁', kind='law_markdown'))
    assert len(page.hits) == 2 and len({hit.version_id for hit in page.hits}) == 2
    for hit in page.hits:
        original = service.read_fragment(root, hit.fragment_id)
        assert original.record.record_id == hit.record_id
        assert original.fragment.version_id == hit.version_id
        assert original.text[original.fragment.start:original.fragment.end].startswith('第一条')


def test_unbuilt_index_is_not_reported_as_no_matches(tmp_path):
    service = api('service')
    page = service.search(tmp_path / 'unbuilt', query(text='离婚'))
    assert page.state == 'not_ready' and not page.hits


def test_cli_uses_same_search_and_original_service(tmp_path, capsys):
    root, _ = world(tmp_path)
    cli = api('__main__')
    assert cli.main(['build-index', '--library-root', str(root), '--activate']) == 0
    capsys.readouterr()
    assert cli.main(['search', '--library-root', str(root), '--query', '离婚']) == 0
    import json
    page = json.loads(capsys.readouterr().out)
    assert len(page['hits']) == 2
    hit = page['hits'][0]
    assert cli.main(['show', '--library-root', str(root), '--record-id', hit['record_id'], '--version-id', hit['version_id']]) == 0
    original = json.loads(capsys.readouterr().out)
    assert original['record']['version_id'] == hit['version_id']
    assert '虚构' in original['text']


def test_timeout_is_explicit_not_empty_success(tmp_path, monkeypatch):
    root, _ = world(tmp_path)
    service = api('service')
    from types import SimpleNamespace
    from itertools import chain, repeat
    clock = chain([0.0], repeat(3.0))
    monkeypatch.setattr(service, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    result = service.search(root, query(text='离婚'))
    assert result.state == 'timeout' and result.total_matches is None


def test_structured_filters_use_indexes_and_document_type(tmp_path):
    import sqlite3
    root, generation = world(tmp_path)
    assert len(api('service').search(root, query(document_type='判决书')).hits) == 3
    assert not api('service').search(root, query(document_type='裁定书')).hits
    with sqlite3.connect(root / 'generations' / generation / 'search.sqlite') as db:
        for field, value in [('court', '虚构法院'), ('cause', '租赁合同纠纷'), ('province', '吉林省'), ('document_type', '判决书'), ('decision_date', '2025-01-02')]:
            plan = db.execute(f'EXPLAIN QUERY PLAN SELECT unit_id FROM units WHERE {field}=? ORDER BY unit_id', (value,)).fetchall()
            assert 'SEARCH' in str(plan) and 'INDEX' in str(plan), plan


def test_identical_law_alias_title_is_searchable(tmp_path):
    laws = tmp_path / 'laws'
    laws.mkdir()
    for title in ['甲地出租规定', '乙地商业租赁细则']:
        (laws / (title + '.md')).write_text('第一条 完全虚构的相同正文。', encoding='utf-8')
    root = tmp_path / 'library'
    api('law_sections').import_laws(root, laws, 'fiction')
    api('index').activate_generation(root, api('index').build_generation(root))
    assert api('service').search(root, query(text='出租')).hits
    assert api('service').search(root, query(text='商业租赁')).hits


def test_deep_cursor_rejected_with_narrow_query_hint(tmp_path):
    root, generation = world(tmp_path)
    service = api('service')
    q = query(text='租赁')
    from cn_contract.library.catalog import canonical, digest
    fingerprint = digest(canonical(q.model_dump(mode='json', exclude={'cursor'})).encode('utf-8'))
    deep = service._cursor_encode(generation, fingerprint, 2000)
    with pytest.raises(ValueError, match='CURSOR_TOO_DEEP'):
        service.search(root, q.model_copy(update={'cursor': deep}))


def law_world(tmp_path, files):
    laws = tmp_path / 'laws'
    laws.mkdir()
    for filename, body in files.items():
        (laws / filename).write_text(body, encoding='utf-8')
    root = tmp_path / 'library'
    api('law_sections').import_laws(root, laws, 'fiction')
    api('index').activate_generation(root, api('index').build_generation(root))
    return root


@pytest.mark.parametrize('invisible', ['', '\u200b' * 300])
def test_phrase_crossing_fragment_boundary_is_found_once(tmp_path, invisible):
    body = '第一条 ' + '甲' * 3995 + '租' + invisible + '赁乙乙乙乙'
    root = law_world(tmp_path, {'虚构边界规定.md': body})
    page = api('service').search(root, query(text='租赁'))
    assert len(page.hits) == 1
    hit = page.hits[0]
    assert body[hit.match_start:hit.match_end] == '租' + invisible + '赁'
    original = api('service').read_fragment(root, hit.fragment_id)
    assert original.fragment.start <= hit.match_start < original.fragment.end
    assert hit.match_end > original.fragment.end


def test_fragment_role_survives_search_and_original_export(tmp_path):
    root = law_world(tmp_path, {'虚构角色.md': '目录\n第一条 租赁\n\n第一章 总则\n第一条 租赁正文。\n> 第二条 租赁引述。'})
    hits = api('service').search(root, query(text='租赁')).hits
    assert {hit.fragment_role for hit in hits} >= {'contents_candidate', 'article_candidate', 'quoted_candidate'}
    for hit in hits:
        original = api('service').read_fragment(root, hit.fragment_id)
        assert hit.model_dump()['fragment_role'] == original.fragment.role


def test_title_results_are_one_per_version_before_body_locations(tmp_path):
    root = law_world(tmp_path, {
        '虚构租赁办法_20250101.md': '\n'.join(f'第{i}条 虚构短文。' for i in range(1, 2002)),
        '虚构租赁办法_20200101.md': '第一条 ' + '虚构旧文。' * 100,
    })
    page = api('service').search(root, query(text='虚构租赁办法', limit=2))
    assert len({hit.version_id for hit in page.hits}) == 2
    assert all(hit.match_field == 'title' and hit.fragment_id is None for hit in page.hits)
    following = api('service').search(root, query(text='虚构租赁办法', limit=2, cursor=page.next_cursor))
    assert not following.hits
    metadata = api('service').search(root, query(kind='law_markdown', limit=100))
    assert len(metadata.hits) == 2
    # Multiword title + body searches still retain the matching body location.
    mixed = api('service').search(root, query(text='租赁 旧文'))
    assert len(mixed.hits) == 1 and mixed.hits[0].fragment_id
