"""Law documents are source snapshots, not automatically approved authorities."""
import hashlib
import importlib
import importlib.util
import json

import pytest


def api():
    assert importlib.util.find_spec('cn_contract.library.law_sections'), 'law importer missing'
    return importlib.import_module('cn_contract.library.law_sections')


def test_historical_versions_and_exact_aliases_are_preserved(tmp_path):
    module = api()
    incoming = tmp_path / 'laws'
    incoming.mkdir()
    first = '# 虚构条例\r\n第一条 甲版本，仅测试。\r\n'
    second = '# 虚构条例\r\n第一条 乙版本，仅测试。\r\n'
    (incoming / '吉林省虚构条例_20200101.md').write_bytes(first.encode('utf-8'))
    (incoming / '吉林省虚构条例_20250101.md').write_bytes(second.encode('utf-8'))
    (incoming / '吉林省虚构条例_20250101_转自DOC.md').write_bytes(second.encode('utf-8'))
    root = tmp_path / 'library'
    report = module.import_laws(root, incoming, 'fiction-laws')
    assert report['files'] == 3 and report['unique_records'] == 2 and report['failed'] == 0
    catalog = importlib.import_module('cn_contract.library.catalog')
    records = list(catalog.iter_records(root))
    assert len({r.version_id for r in records}) == 2
    assert len({r.fields['series_id'] for r in records}) == 1
    assert {r.fields['filename_date_candidate'] for r in records} == {'2020-01-01', '2025-01-01'}
    assert all(r.fields['effective_from'] is None and r.verification_status == 'unverified' for r in records)
    assert module.import_laws(root, incoming, 'fiction-laws')['inserted'] == 0


def test_missing_url_draft_word_and_repeal_are_not_legal_status(tmp_path):
    module = api()
    incoming = tmp_path / 'laws'
    incoming.mkdir()
    (incoming / '虚构法规草案公示规定_20250231.md').write_text('第一条 本规定提到废止，但仅为虚构测试。', encoding='utf-8')
    root = tmp_path / 'library'
    module.import_laws(root, incoming, 'fiction-laws')
    record = next(importlib.import_module('cn_contract.library.catalog').iter_records(root))
    assert record.fields['source_url'] is None
    assert record.fields['legal_status'] == 'unknown'
    assert record.fields['filename_date_candidate'] is None
    assert 'invalid_filename_date' in record.warnings


def test_toc_quotation_and_article_one_subsection(tmp_path):
    module = api()
    text = ('# 虚构条例\n目录\n第一条\n第二条\n\n第一章 总则\n'
            '第一条 这是虚构的正文内容，不是法律依据。\n'
            '第二条 这是另一个虚构条款。\n'
            '第二条之一 保留附加条文。\n引用其他虚构文件：\n> 第一条 引用文本不可混作正文。\n')
    incoming = tmp_path / 'laws'
    incoming.mkdir()
    (incoming / '虚构条例.md').write_text(text, encoding='utf-8', newline='')
    root = tmp_path / 'library'
    module.import_laws(root, incoming, 'fiction-laws')
    catalog = importlib.import_module('cn_contract.library.catalog')
    record = next(catalog.iter_records(root))
    fragments = list(module.iter_fragments(root, record.record_id))
    assert ''.join(text[f.start:f.end] for f in fragments) == text
    firsts = [f for f in fragments if f.article == '第一条']
    assert any(f.role == 'contents_candidate' for f in firsts)
    assert any(f.role == 'quoted_candidate' for f in firsts)
    assert all(f.ambiguous for f in firsts if f.role != 'contents_candidate')
    assert any(f.article == '第二条之一' for f in fragments)
    for f in fragments:
        assert hashlib.sha256(text[f.start:f.end].encode('utf-8')).hexdigest() == f.text_sha256


def test_zero_width_original_span_and_unstructured_text_survive(tmp_path):
    module = api()
    text = '\ufeff# 虚构资料\r\n第\u200b一条 文本不得覆盖。\r\n|甲|乙|\r\n|--|--|\r\n|数据|保留|\r\n附件说明\r\n'
    incoming = tmp_path / 'laws'
    incoming.mkdir()
    original = incoming / '虚构资料.md'
    raw = text.encode('utf-8')
    original.write_bytes(raw)
    root = tmp_path / 'library'
    module.import_laws(root, incoming, 'fiction-laws')
    catalog = importlib.import_module('cn_contract.library.catalog')
    record = next(catalog.iter_records(root))
    decoded = raw.decode('utf-8-sig')
    fragments = list(module.iter_fragments(root, record.record_id))
    assert any(f.article == '第一条' for f in fragments)
    assert ''.join(decoded[f.start:f.end] for f in fragments) == decoded
    assert original.read_bytes() == raw
    assert 'zero_width' in record.warnings


def test_law_import_rejects_overlapping_root(tmp_path):
    module = api()
    (tmp_path / '虚构.md').write_text('不覆盖原件', encoding='utf-8')
    with pytest.raises(ValueError, match='OVERLAP'):
        module.import_laws(tmp_path / 'generated', tmp_path, 'fiction-laws')


def test_undecodable_file_is_reported_without_stopping_good_law(tmp_path):
    module = api()
    incoming = tmp_path / 'laws'
    incoming.mkdir()
    (incoming / '甲.md').write_bytes(b'\xff\xfe\x80')
    (incoming / '乙.md').write_text('没有条号的虚构公告', encoding='utf-8')
    report = module.import_laws(tmp_path / 'library', incoming, 'fiction-laws')
    assert report['files'] == 2 and report['failed'] == 1 and report['unique_records'] == 1
    assert report['issues'][0]['reason'] == 'LAW_DECODE_FAILED'
