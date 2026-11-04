"""Synthetic evidence analysis roundtrips; no provider or external data."""
import copy
import importlib.util

import pytest
from business_store import CaseStore
from reader import parse


def save(*args, **kwargs):
    assert importlib.util.find_spec('evidence_analysis'), 'evidence analysis saver is missing'
    from evidence_analysis import save_evidence_analysis
    return save_evidence_analysis(*args, **kwargs)


@pytest.fixture
def evidence(tmp_path):
    cases = CaseStore(tmp_path)
    cid = cases.create('合成证据案')['id']
    source = tmp_path / '谈话.txt'
    source.write_text('甲称：已支付三万元。乙称：尚未到账。', encoding='utf-8')
    cases.store.register(source.name)
    parse(cases.store, source.name)
    cases.link_materials(cid, [source.name])
    sha = cases.read_material(cid, source.name)['sha256']
    item = {'proposition': '甲是否已付款', 'finding_kind': 'unknown',
            'assessment': '双方陈述冲突，付款情况待核。',
            'supporting': [{'statement': '甲主张付款', 'speaker': '甲', 'carrier': '谈话记录',
                            'citations': [{'path': source.name, 'sha256': sha, 'chunk': 0,
                                           'quote': '甲称：已支付三万元。'}]}],
            'opposing': [], 'unknown': ['银行流水未提交，不能认定付款不存在'],
            'admissibility': {'authenticity': ['原件及记录过程待核'], 'legality': ['取得方式待核'],
                              'relevance': ['账号与本案付款关联待核']},
            'supplement': ['核对双方银行流水与合同付款节点']}
    return cases, cid, source, item


def test_roundtrip_preserves_speaker_carrier_and_verified_citation(evidence):
    cases, cid, source, item = evidence
    note = save(cases, cid, [item], request_id='save-1')
    assert note['saved'] and note['kind'] == 'evidence_analysis'
    assert note['citations'][0]['status'] == 'matched'
    assert not note['legal_verified'] and note['review_status'] == 'unverified'
    loaded = CaseStore(cases.root).read_note(cid, note['id'])
    assert all(s in loaded['content'] for s in ('甲主张付款', '陈述主体：甲', '载体：谈话记录', '银行流水未提交'))
    assert save(cases, cid, [item], request_id='save-1')['id'] == note['id']


def test_unmatched_and_ambiguous_grounding_survive_without_promotion(evidence):
    cases, cid, source, item = evidence
    item['supporting'][0]['citations'][0].update(quote='已付四万元', status='matched')
    note = save(cases, cid, [item])
    assert note['citations'][0]['status'] != 'matched' and note['warnings']
    assert '已付四万元' in note['content']
    item['supporting'][0]['citations'][0].update(quote='甲称：已支付三万元。', status='ambiguous', start=None, end=None)
    assert save(cases, cid, [item])['citations'][0]['status'] != 'matched'


def test_other_case_reference_and_correction_rejected_without_partial_save(evidence):
    cases, cid, source, item = evidence
    other = cases.create('另一合成案')['id']
    with pytest.raises(ValueError): save(cases, other, [item])
    assert cases.get(other)['total_notes'] == 0
    first = save(cases, cid, [item])
    empty = copy.deepcopy(item); empty['supporting'] = []
    with pytest.raises(ValueError): save(cases, other, [empty], supersedes=first['id'])
    item['supporting'][0]['citations'][0]['case_id'] = other
    with pytest.raises(ValueError): save(cases, cid, [item])
    assert cases.get(cid)['total_notes'] == 1


def test_correction_keeps_history_and_export_uses_current_note(evidence, monkeypatch):
    from docx import Document
    import business_server as api
    cases, cid, source, item = evidence
    monkeypatch.setattr(api, 'cases', cases)
    monkeypatch.setattr(api.material_server, 'store', cases.store)
    first = save(cases, cid, [item])
    item['assessment'] = '补核标记：银行到账仍待确认。'
    second = save(cases, cid, [item], supersedes=first['id'])
    assert second['supersedes'] == first['id']
    assert cases.get(cid)['total_notes'] == 1
    assert cases.get(cid, include_history=True)['total_notes'] == 2
    text = '\n'.join(p.text for p in Document(api.export_case(cid)['path']).paragraphs)
    assert '补核标记' in text and '双方陈述冲突，付款情况待核。' not in text
    conflict = save(cases, cid, [item], supersedes=first['id'])
    assert not conflict['saved'] and conflict['reason'] == 'correction_conflict'


def test_stale_source_is_saved_with_warning_not_as_verified(evidence):
    cases, cid, source, item = evidence
    source.write_text('内容已修改。', encoding='utf-8')
    note = save(cases, cid, [item])
    assert note['citations'][0]['status'] != 'matched' and note['warnings']


def test_schema_rejects_silent_unknown_fields_or_missing_attribution(evidence):
    cases, cid, source, item = evidence
    for field, value in [('score', 99), ('finding_kind', 'proven'), ('proposition', ''), ('unknown', '无')]:
        bad = copy.deepcopy(item); bad[field] = value
        with pytest.raises(ValueError): save(cases, cid, [bad])
    bad = copy.deepcopy(item); del bad['supporting'][0]['speaker']
    with pytest.raises(ValueError): save(cases, cid, [bad])
    assert cases.get(cid)['total_notes'] == 0


@pytest.mark.parametrize('status', ['ambiguous', 'unmatched', 'unverified'])
def test_failed_alignment_with_valid_offsets_is_not_promoted(evidence, status):
    cases, cid, source, item = evidence
    item['supporting'][0]['citations'][0].update(status=status, start=0, end=10)
    note = save(cases, cid, [item])
    assert note['citations'][0]['status'] != 'matched'
    assert note['citations'][0]['start'] is None and note['warnings']
    assert '甲称：已支付三万元。' in note['content']


def test_body_does_not_present_unverified_input_status_as_result(evidence):
    cases, cid, source, item = evidence
    item['supporting'][0]['citations'][0].update(status='matched', quote='伪造引文四万元')
    note = save(cases, cid, [item])
    assert note['citations'][0]['status'] != 'matched'
    assert '"status": "matched"' not in note['content']
    assert '伪造引文四万元' in note['content']


@pytest.mark.parametrize('draft_path,source_kind', [
    ('drafts/work.txt', None), ('Drafts/work.txt', None),
    ('drafts/work.txt', 'original'), ('normal.txt', 'model_draft'),
    ('./drafts/work.txt', None), ('absolute', None),
])
def test_model_work_product_is_retained_but_not_matched_as_evidence(evidence, draft_path, source_kind):
    cases, cid, source, item = evidence
    if draft_path == 'absolute':
        draft_path = str(cases.root / 'drafts' / 'work.txt')
    draft = cases.root / draft_path
    draft.parent.mkdir(exist_ok=True)
    draft.write_text('甲称：已支付三万元。', encoding='utf-8')
    cases.store.register(draft_path)
    parse(cases.store, draft_path)
    cases.link_materials(cid, [draft_path])
    citation = item['supporting'][0]['citations'][0]
    citation.update(path=draft_path, sha256=cases.read_material(cid, draft_path)['sha256'],
                    status='matched', start=0, end=10)
    if source_kind:
        citation['source_kind'] = source_kind
    note = save(cases, cid, [item])
    assert note['saved'] and note['citations'][0]['status'] != 'matched'
    assert note['warnings'] and '甲称：已支付三万元。' in note['content']
    assert '工作稿' in note['content'] and '待核' in note['content']
    assert cases.read_note(cid, note['id'])['citations'][0]['status'] != 'matched'
