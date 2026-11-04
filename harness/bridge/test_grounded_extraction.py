"""Synthetic case-scoped grounding; no model or network."""
import pytest
from business_store import CaseStore
from reader import parse
from grounded_extraction import ground_case_extractions


@pytest.fixture
def evidence(tmp_path):
    cases = CaseStore(tmp_path)
    cid = cases.create('虚构甲案')['id']
    path = tmp_path / '合同.txt'
    path.write_text('虚构合同：价款35000元。交货后付款。重复。重复。ABC。', encoding='utf-8')
    cases.store.register(path.name)
    parse(cases.store, path.name)
    cases.link_materials(cid, [path.name])
    sha = cases.read_material(cid, path.name)['sha256']
    return cases, cid, path, sha


def test_exact_chinese_quote_retains_source_and_does_not_create_fact(evidence):
    cases, cid, path, sha = evidence
    result = ground_case_extractions(cases, cid, path.name, sha, 0,
                                    [{'label': '价款', 'quote': '价款35000元'}])
    row = result['extractions'][0]
    assert row['status'] == 'matched' and row['quote'] == '价款35000元'
    assert row['sha256'] == sha and row['chunk'] == 0
    text = cases.read_material(cid, path.name)['chunks'][0]['text']
    assert text[row['start']:row['end']] == row['quote']
    assert result['case_id'] == cid and not result['legal_verified']
    assert not cases.get(cid)['notes']


def test_missing_ambiguous_and_case_changed_quotes_not_accepted(evidence):
    cases, cid, path, sha = evidence
    result = ground_case_extractions(cases, cid, path.name, sha, 0, [
        {'label': '金额', 'quote': '价款36000元'},
        {'label': '重复', 'quote': '重复'},
        {'label': '大小写', 'quote': 'abc'}])
    assert [r['status'] for r in result['extractions']] == ['unmatched', 'ambiguous', 'unmatched']
    assert all(r['start'] is None and r['end'] is None for r in result['extractions'])
    note = cases.add_note(cid, 'inference', '摘录定位待核，不能作为已核实事实。',
                          citations=result['extractions'])
    assert all(c['status'] != 'matched' for c in note['citations'])


def test_other_case_stale_hash_and_missing_chunk_rejected(evidence):
    cases, cid, path, sha = evidence
    items = [{'label': '价款', 'quote': '价款35000元'}]
    other = cases.create('虚构乙案')['id']
    with pytest.raises(ValueError): ground_case_extractions(cases, other, path.name, sha, 0, items)
    with pytest.raises(ValueError): ground_case_extractions(cases, cid, path.name, '0'*64, 0, items)
    with pytest.raises(ValueError): ground_case_extractions(cases, cid, path.name, sha, 999, items)
    path.write_text('修改后的材料', encoding='utf-8')
    with pytest.raises(ValueError): ground_case_extractions(cases, cid, path.name, sha, 0, items)


def test_invalid_input_is_bounded(evidence):
    cases, cid, path, sha = evidence
    for items in ([], [{'label': 'x', 'quote': ''}], [{'label': 'x', 'quote': 'x'}]*31,
                  [{'label': 'x', 'quote': 'x', 'attributes': {'已证实': True}}]):
        with pytest.raises(ValueError): ground_case_extractions(cases, cid, path.name, sha, 0, items)


def test_sparse_pdf_style_ordinals_are_not_treated_as_page_offsets(evidence):
    cases, cid, path, sha = evidence
    # PDF reader uses page*1000000+local ordinal, not contiguous row numbers.
    with cases.store.db() as db:
        db.execute('UPDATE chunks SET ordinal=1000000,page=1,location=? WHERE path=?',
                   ('第1页', path.name))
    result = ground_case_extractions(cases, cid, path.name, sha, 1000000,
                                    [{'label': '金额', 'quote': '价款35000元'}])
    assert result['extractions'][0]['status'] == 'matched'
    assert result['extractions'][0]['page'] == 1
    assert result['extractions'][0]['chunk'] == 1000000


def test_real_pdf_reader_roundtrip_retains_page(tmp_path):
    from test_privacy import native_pdf
    cases = CaseStore(tmp_path)
    cid = cases.create('合成PDF案')['id']
    source = tmp_path / '合成.pdf'
    source.write_bytes(native_pdf())
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    view = cases.read_material(cid, source.name)
    chunk = view['chunks'][0]
    assert chunk['ordinal'] == 1000000
    result = ground_case_extractions(cases, cid, source.name, view['sha256'], chunk['ordinal'],
                                    [{'label': '合成号码', 'quote': '13700137000'}])
    row = result['extractions'][0]
    assert row['status'] == 'matched' and row['page'] == 1
    saved = cases.add_note(cid, 'inference', '材料载有合成号码，归属待核。', citations=[row])
    assert saved['citations'][0]['status'] == 'matched' and saved['review_status'] == 'unverified'
