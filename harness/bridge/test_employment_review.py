"""Synthetic employment reviews: append-only provenance and exact scenario arithmetic."""
import importlib.util
from pathlib import Path

import pytest
from business_store import CaseStore


def api():
    path = Path(__file__).with_name('employment_review.py')
    assert path.exists(), 'employment review implementation is missing'
    spec = importlib.util.spec_from_file_location('employment_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finding(**changes):
    return dict(fact='员工保护状态未知', basis='劳动合同法第42条，适用待核',
                source='合成客户陈述', risk='不能按无保护状态处理',
                action='核对医疗期等材料', **changes)


def test_review_roundtrip_retry_and_append_only_correction(tmp_path):
    s = CaseStore(tmp_path); cid = s.create('合成劳动案')['id']; a = api()
    first = a.save_employment_review(s, cid, 'termination', [finding()], request_id='r1')
    assert first['kind'] == 'employment_review' and first['review_status'] == 'unverified'
    assert '待核' in first['content'] and '员工保护状态未知' in first['content']
    assert a.save_employment_review(s, cid, 'termination', [finding()], request_id='r1')['id'] == first['id']
    later = a.save_employment_review(s, cid, 'termination', [finding(pending='待核：医疗期')], supersedes=first['id'])
    assert later['id'] != first['id'] and s.read_note(cid, first['id'])['content'] == first['content']
    other = s.create('另一合成案')['id']
    with pytest.raises(ValueError):
        a.save_employment_review(s, other, 'termination', [finding()], supersedes=first['id'])
    conflict = a.save_employment_review(s, cid, 'termination', [finding()], supersedes=first['id'])
    assert conflict['recorded'] is False


@pytest.mark.parametrize('stage,items', [('unknown', [finding()]), ('hiring', []),
    ('hiring', [{'fact': 'only fact'}]), ('hiring', [finding(unrecognized='discard?')]),
    ('hiring', [finding(citations='wrong')])])
def test_invalid_review_leaves_no_note(tmp_path, stage, items):
    s = CaseStore(tmp_path); cid = s.create('合成案')['id']
    with pytest.raises(ValueError): api().save_employment_review(s, cid, stage, items)
    assert s.get(cid)['notes'] == []


def test_material_source_validation_is_reused(tmp_path):
    from reader import parse
    s = CaseStore(tmp_path); cid = s.create('合成引用案')['id']
    (tmp_path/'source.txt').write_text('合成材料：入职日待核。', encoding='utf8')
    s.store.register('source.txt'); parse(s.store, 'source.txt'); s.link_materials(cid, ['source.txt'])
    note = api().save_employment_review(s, cid, 'hiring', [finding(citations=[{'path':'source.txt','quote':'不存在的原文'}])])
    assert note['warnings'] and note['review_status'] == 'unverified'


def test_explicit_arithmetic_is_exact_and_not_legal_entitlement():
    result = api().calculate_employment_amount('10000.01', '2.5', '2', '纯情景：基数及年限由用户明确给定，法律资格另核')
    assert result['amount'] == '50000.05' and result['legal_entitlement_verified'] is False
    assert result['rounding'] == 'ROUND_HALF_UP to 0.01' and result['assumptions']
    assert api().calculate_employment_amount('0.01', '0.5', '1', '显式算术情景')['amount'] == '0.01'


@pytest.mark.parametrize('base,years,multiplier,assumptions', [
    ('NaN','1','1','已确认'), ('Infinity','1','1','已确认'), ('-1','1','1','已确认'),
    ('1','-1','1','已确认'), ('1','1','1',''), (0.1,'1','1','已确认'),
    ('1e99999','1','1','已确认'), ('1','1','0','已确认'), ('1.001','1','1','已确认')])
def test_invalid_or_implicit_amount_inputs_are_rejected(base, years, multiplier, assumptions):
    with pytest.raises(ValueError): api().calculate_employment_amount(base, years, multiplier, assumptions)


def linked_source(tmp_path, name):
    from reader import parse
    s = CaseStore(tmp_path); cid = s.create('合成劳动引文案')['id']
    path = tmp_path/name; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('员工拒绝签收。', encoding='utf8')
    s.store.register(name); parse(s.store, name); s.link_materials(cid, [name])
    return s, cid


@pytest.mark.parametrize('status', ['unmatched', 'ambiguous', 'unverified'])
def test_failed_alignment_cannot_be_promoted_by_correct_offsets(tmp_path, status):
    import json
    s, cid = linked_source(tmp_path, 'source.txt')
    ref = {'path':'source.txt', 'quote':'员工拒绝签收。', 'start':0, 'end':7, 'status':status}
    note = api().save_employment_review(s, cid, 'termination', [finding(citations=[ref])])
    saved = s.read_note(cid, note['id'])
    assert saved['citations'][0]['status'] == 'unverified' and saved['warnings']
    assert saved['citations'][0]['provided_status'] == status
    assert json.dumps(ref, ensure_ascii=False, sort_keys=True) in saved['content']
    assert ref['start'] == 0 and ref['end'] == 7


@pytest.mark.parametrize('name,extra', [('drafts/opinion.txt', {}),
    ('DrAfTs/opinion.txt', {}), ('source.txt', {'source_kind':'model_draft'})])
def test_draft_quote_is_retained_but_not_original_evidence(tmp_path, name, extra):
    import json
    s, cid = linked_source(tmp_path, name)
    ref = {'path':name, 'quote':'员工拒绝签收。', 'start':0, 'end':7, **extra}
    note = api().save_employment_review(s, cid, 'termination', [finding(citations=[ref])])
    saved = s.read_note(cid, note['id'])
    assert saved['citations'][0]['status'] == 'unverified' and saved['warnings']
    assert json.dumps(ref, ensure_ascii=False, sort_keys=True) in saved['content']
    assert '原始证据' in saved['content']


@pytest.mark.parametrize('items', [
    [dict(finding(), fact='字'*20001)],
    [finding(citations=[{}]*21)],
    [finding(citations=[{}]*20)]*11,
    [dict(finding(), fact='字'*20000)]*11,
])
def test_oversized_review_is_rejected_atomically_not_truncated(tmp_path, items):
    s = CaseStore(tmp_path); cid = s.create('合成限额案')['id']
    with pytest.raises(ValueError, match='分批|上限|至多'):
        api().save_employment_review(s, cid, 'termination', items)
    assert s.get(cid)['notes'] == []


def test_allowed_long_review_preserves_all_user_text(tmp_path):
    s = CaseStore(tmp_path); cid = s.create('合成长正文案')['id']
    text = '  原文含前后空格及换行\n' * 600
    item = dict(finding(), fact=text)
    note = api().save_employment_review(s, cid, 'termination', [item])
    restored = ''; start = 0
    while True:
        page = s.read_note(cid, note['id'], start=start)
        restored += page['content']
        if page['next_start'] is None: break
        start = page['next_start']
    assert text in restored


@pytest.mark.parametrize('style', ['relative', 'dot', 'absolute', 'windows'])
def test_draft_paths_keep_case_binding_and_normalize_for_source_check(tmp_path, style):
    name = 'drafts/opinion.txt'
    s, cid = linked_source(tmp_path, name)
    paths = {'relative':name, 'dot':'./'+name, 'absolute':str(tmp_path/name),
             'windows':name.replace('/', '\\')}
    ref = {'path':paths[style], 'quote':'员工拒绝签收。', 'start':0, 'end':7}
    note = api().save_employment_review(s, cid, 'termination', [finding(citations=[ref])])
    assert note['citations'][0]['path'] == name
    assert note['citations'][0]['status'] == 'unverified'
    other = s.create('无该材料的另一案')['id']
    with pytest.raises(ValueError, match='尚未关联'):
        api().save_employment_review(s, other, 'termination', [finding(citations=[ref])])
    assert s.get(other)['notes'] == []


@pytest.mark.parametrize('source_kind', ['model_draft', 'inference', 'draft'])
def test_non_original_source_kinds_still_require_case_link(tmp_path, source_kind):
    s, cid = linked_source(tmp_path, 'source.txt')
    ref = {'path':'source.txt', 'quote':'员工拒绝签收。', 'start':0, 'end':7, 'source_kind':source_kind}
    note = api().save_employment_review(s, cid, 'termination', [finding(citations=[ref])])
    assert note['citations'][0]['path'] == 'source.txt'
    assert note['citations'][0]['status'] == 'unverified'
    other = s.create('无来源的另一案')['id']
    with pytest.raises(ValueError, match='尚未关联'):
        api().save_employment_review(s, other, 'termination', [finding(citations=[ref])])


def test_ordinary_linked_original_still_matches(tmp_path):
    s, cid = linked_source(tmp_path, 'source.txt')
    note = api().save_employment_review(s, cid, 'termination', [finding(citations=[
        {'path':'source.txt', 'quote':'员工拒绝签收。', 'start':0, 'end':7}])])
    assert note['citations'][0]['status'] == 'matched'
    assert note['review_status'] == 'unverified'
