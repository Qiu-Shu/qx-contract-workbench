"""CSV byte boundaries and conservative field normalization, synthetic only."""
import csv
import hashlib
import importlib
import importlib.util
import io

import pytest


def api(name):
    module = 'cn_contract.library.' + name
    assert importlib.util.find_spec(module), name + ' implementation missing'
    return importlib.import_module(module)


def make_csv(tmp_path, rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(['标题', '案号', '法院', '文书类型', '判决时间', '发布时间', '判决年份', '文书内容'])
    writer.writerows(rows)
    path = tmp_path / '虚构 多行.csv'
    path.write_bytes(b'\xef\xbb\xbf' + stream.getvalue().encode('utf-8'))
    return path


def test_multiline_offsets_and_bom(tmp_path):
    module = api('csv_source')
    assets = api('assets')
    original = make_csv(tmp_path, [
        ['虚构甲', '（２０２５）虚字１号', '虚构法院', 'None', '2025-01-02', '2025-02-03', '2025', '虚构第一行\n第二行,"None"原文保留'],
        ['虚构乙', '(2025)虚字1号', '虚构法院', '判决书', '2025-01-02', '', '2025', '另一个正文'],
    ])
    root = tmp_path / 'library'
    src = assets.register_source(root, original, 'fiction', 'case_csv')
    records = list(module.iter_case_records(root, src, 1, 0))
    assert len(records) == 2
    assert records[0].ordinal == 1 and records[1].ordinal == 2
    assert records[0].byte_end == records[1].byte_start
    assert records[0].fields['case_no'] == '(2025)虚字1号'
    assert records[0].fields['document_type'] is None
    for record, expected in zip(records, ['虚构第一行\n第二行,"None"原文保留', '另一个正文']):
        raw = original.read_bytes()[record.byte_start:record.byte_end]
        assert hashlib.sha256(raw).hexdigest() == record.raw_sha256
        assert hashlib.sha256(expected.encode('utf-8')).hexdigest() == record.body_sha256
        assert list(csv.reader(io.StringIO(raw.decode('utf-8'), newline='')))[0][-1] == expected
    assert records[0].record_id != records[1].record_id
    assert records[0].version_id != records[1].version_id
    resumed = list(module.iter_case_records(root, src, 2, records[1].byte_start))
    assert resumed == records[1:]


def test_null_metadata_preserves_literal_body():
    result = api('cleaning').clean_case({'标题': '虚构', '文书类型': ' NaN ', '法院': 'None',
        '文书内容': 'None、null、NaN是本段原文', '案号': '（２０２５） 虚字 ３ 号'})
    assert result['fields']['document_type'] is None
    assert result['fields']['court'] is None
    assert result['fields']['case_no'] == '(2025)虚字3号'
    assert 'missing:document_type' in result['warnings']


def test_date_conflict_keeps_raw():
    result = api('cleaning').clean_case({'判决时间': '2025-02-31', '发布时间': '20250101'})
    assert result['fields']['decision_date'] is None
    assert result['fields']['publication_date'] is None
    assert 'invalid_date:decision_date' in result['warnings']
    result = api('cleaning').clean_case({'判决时间': '2025-03-10', '发布时间': '2025-03-01', '判决年份': '2024'})
    assert result['fields']['publication_date'] == '2025-03-01'
    assert 'publication_before_decision' in result['warnings']
    assert 'decision_year_conflict' in result['warnings']


def test_same_case_different_body_survives_and_replay_is_idempotent(tmp_path):
    module = api('csv_source')
    path = make_csv(tmp_path, [['虚构', '同案号', '甲法院', '', '', '', '', '甲正文'],
                               ['虚构', '同案号', '甲法院', '', '', '', '', '乙正文']])
    root = tmp_path / 'library'
    first = module.import_case_file(root, path, 'fiction', limit=2, batch_size=1)
    second = module.import_case_file(root, path, 'fiction', limit=2, batch_size=1)
    assert first['stored'] == second['stored'] == 2
    assert second['inserted'] == 0
    records = list(api('catalog').iter_records(root))
    assert len({r.version_id for r in records}) == 2
    assert len({r.fields['case_no'] for r in records}) == 1


def test_broken_quote_stops_file_and_retains_committed_rows(tmp_path):
    module = api('csv_source')
    path = make_csv(tmp_path, [['虚构', '1', '甲法院', '', '', '', '', '正常虚构正文']])
    with path.open('ab') as stream:
        stream.write(b'"never closed\r\nmore text')
    root = tmp_path / 'library'
    result = module.import_case_file(root, path, 'fiction', batch_size=1)
    assert result['stored'] == 1
    assert result['state'] == 'parse_aborted'
    assert result['next_ordinal'] == 2
    assert result['failed'] == 1
    assert not result['complete']


def test_column_mismatch_retained_and_next_record_survives(tmp_path):
    module = api('csv_source')
    path = make_csv(tmp_path, [['缺列'], ['虚构', '2', '', '', '', '', '', '正文']])
    root = tmp_path / 'library'
    result = module.import_case_file(root, path, 'fiction', batch_size=2)
    assert result['stored'] == 2 and result['failed'] == 1
    records = list(api('catalog').iter_records(root))
    assert records[0].body_status == 'damaged_record'
    assert records[1].body_status == 'body_present_unverified'


def test_source_changed_reject_resume(tmp_path):
    module = api('csv_source')
    path = make_csv(tmp_path, [['虚构', str(i), '', '', '', '', '', '正文'] for i in range(4)])
    root = tmp_path / 'library'
    module.import_case_file(root, path, 'fiction', limit=2, batch_size=1)
    with path.open('ab') as stream:
        stream.write('新增,不是原版本\n'.encode('utf-8'))
    with pytest.raises(ValueError, match='SOURCE_CHANGED'):
        module.import_case_file(root, path, 'fiction', limit=4, batch_size=1)
    assert len(list(api('catalog').iter_records(root))) == 2


def test_duplicate_header_is_rejected_without_records(tmp_path):
    module = api('csv_source')
    path = tmp_path / '坏表头.csv'
    path.write_text('案号,案号,文书内容\n1,2,正文\n', encoding='utf-8')
    with pytest.raises(ValueError, match='HEADER_INVALID'):
        module.import_case_file(tmp_path / 'library', path, 'fiction')


def test_limit_does_not_parse_broken_next_record(tmp_path):
    module = api('csv_source')
    path = make_csv(tmp_path, [['虚构', '1', '', '', '', '', '', '正文']])
    with path.open('ab') as stream:
        stream.write(b'"broken next record')
    result = module.import_case_file(tmp_path / 'library', path, 'fiction', limit=1)
    assert result['state'] == 'partial'
    assert result['failed'] == 0
    assert result['stored'] == 1
