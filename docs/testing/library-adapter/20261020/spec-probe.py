"""Independent CH-06A probes; temporary invented data only."""
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.library import service
from cn_contract.library.catalog import canonical, connection
from cn_contract.library.csv_source import import_case_file
from cn_contract.library.index import activate_generation, build_generation
from cn_contract.library.law_sections import import_laws


def rejects(code, action):
    try:
        action()
    except ValueError as error:
        assert str(error) == code, (code, str(error))
    else:
        raise AssertionError('expected ' + code)


def run():
    checks = []
    with TemporaryDirectory(prefix='spec-review-', dir=Path(__file__).parent) as temporary:
        base = Path(temporary)
        laws = base / 'laws'
        laws.mkdir()
        law = '第一条 独立租赁目标。' + '甲' * 1300 + '\n第二条 相邻禁入。'
        (laws / '纯虚构法规.md').write_text(law, encoding='utf-8')
        (laws / '纯虚构兼容字符.md').write_text('第一条 ㍻年标记。', encoding='utf-8')
        case_file = base / 'cases.csv'
        with case_file.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['标题', '案号', '法院', '文书内容', '判决时间'])
            writer.writerow(['虚构租赁案', '(2024)虚A号', '合成法院', '独立租赁目标。', '2024-01-01'])
            writer.writerow(['另一个虚构案', '(2024)虚B号', '合成法院', '非引用记录甲。', '2024-02-01'])
        root = base / 'library'
        import_laws(root, laws, 'spec-independent')
        import_case_file(root, case_file, 'spec-independent')
        activate_generation(root, build_generation(root))
        adapter = LegalLibraryAdapter(root)
        page = adapter.search(d.AssistantLibraryQuery(text='独立租赁', kind='law_markdown'))
        ref = page.citations[0]
        assert ref.quote == law[ref.start:ref.end] and len(ref.quote) == 1200
        assert '相邻禁入' not in ref.quote
        assert ref.support_status == ref.applicability_status == 'unverified'
        assert adapter.read_original(ref) == ref
        checks.append('bounded exact source snapshot and unverified semantics')
        generation = build_generation(root)
        real_search = service.search
        def rotate(*args):
            result = real_search(*args)
            activate_generation(root, generation)
            return result
        with patch.object(service, 'search', rotate):
            rejects('LIBRARY_GENERATION_STALE', lambda: adapter.search(page.query))
        checks.append('generation replacement before citation reads rejected')
        rejects('LIBRARY_GENERATION_STALE', lambda: adapter.read_original(ref))
        checks.append('previous citation generation rejected')
        current = adapter.search(page.query).citations[0]
        with connection(root, writable=True) as db:
            fragment = json.loads(db.execute('SELECT fragment_json FROM fragments WHERE fragment_id=?', (current.fragment_id,)).fetchone()[0])
            fragment['role'] = 'quoted_candidate'
            db.execute('UPDATE fragments SET fragment_json=? WHERE fragment_id=?', (canonical(fragment), current.fragment_id))
        rejects('LIBRARY_SOURCE_UNAVAILABLE', lambda: adapter.read_original(current))
        checks.append('catalog fragment semantic corruption rejected')
        case_query = d.AssistantLibraryQuery(text='独立租赁', kind='case_csv')
        case = adapter.search(case_query).citations[0]
        raw_path = root / 'assets' / case.registered_source_sha256 / 'original'
        original_bytes = raw_path.read_bytes()
        raw_path.write_bytes(original_bytes.replace('非引用记录甲'.encode(), '非引用记录乙'.encode()))
        changed_whole_source = hashlib.sha256(raw_path.read_bytes()).hexdigest() != case.registered_source_sha256
        unchanged_quote_accepted = adapter.read_original(case) == case
        assert changed_whole_source and unchanged_quote_accepted
        assert 'source_sha256' not in case.model_dump() and case.source_match == 'record_quote_matched'
        print(json.dumps({'observation': 'same CSV other row changed', 'whole_source_hash_changed': changed_whole_source,
                          'unchanged_quote_accepted': unchanged_quote_accepted}, ensure_ascii=False))
        checks.append('registered full-source identity is distinct from cited-row verification')
        raw_path.write_bytes(original_bytes.replace('独立租赁目标'.encode(), '损坏租赁目标'.encode()))
        rejects('LIBRARY_SOURCE_UNAVAILABLE', lambda: adapter.read_original(case))
        checks.append('cited CSV row corruption rejected')
        normalized_query = d.AssistantLibraryQuery(text='成年', kind='law_markdown')
        upstream = service.search(root, normalized_query)
        adapted = adapter.search(normalized_query)
        assert len(upstream.hits) == len(adapted.citations) == 1
        normalized_ref = adapted.citations[0]
        assert normalized_ref.match_start == 4 and normalized_ref.match_end == 6
        assert adapter.read_original(normalized_ref) == normalized_ref
        checks.append('normalization expansion has exact original-character match coordinates')
        print(json.dumps({'observation': 'normalized expansion boundary', 'upstream_hits':len(upstream.hits),
                          'adapter_citations':len(adapted.citations), 'omitted':adapted.omitted_hits}, ensure_ascii=False))
    print(json.dumps({'passed':len(checks), 'checks':checks}, ensure_ascii=False))


if __name__ == '__main__':
    run()
