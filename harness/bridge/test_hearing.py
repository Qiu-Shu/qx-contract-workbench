"""Synthetic temporary workspaces only; no model or user database access."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from business_store import CaseStore
from hearing import HearingStore, ROLES, STAGES


@pytest.fixture
def world(tmp_path):
    cases = CaseStore(tmp_path)
    case = cases.create('虚构庭审案', our_role='plaintiff', request_id='case-1')
    source = tmp_path / 'fiction.txt'
    source.write_text('虚构材料：约定价款三万元，交付情况待核。', encoding='utf-8')
    cases.link_materials(case['id'], [str(source)])
    return cases, HearingStore(cases), case['id'], source


def test_five_stages_survive_reopen_and_complete_only_after_recording(world):
    cases, hearings, cid, _ = world
    started = hearings.start(cid, 'plaintiff', '交付与付款', request_id='start')
    hid = started['id']
    assert (started['next_stage'], started['next_role']) == ('issues', 'moderator')
    for stage in STAGES:
        for role in ROLES[stage]:
            saved = hearings.append_turn(hid, stage, role, f'虚构{stage}/{role}发言', request_id=f'{stage}-{role}')
            assert saved['recorded'] is True
    recovered = HearingStore(CaseStore(cases.store.root)).get(hid, limit=3)
    assert recovered['status'] == 'completed'
    assert recovered['turn_count'] == 11
    assert recovered['next_stage'] is None and recovered['next_role'] is None
    assert len(recovered['turns']) == 3 and recovered['next_offset'] == 3
    assert hearings.get(hid, offset=9)['turns'][-1]['role'] == 'reviewer'
    with pytest.raises(ValueError, match='结束'):
        hearings.append_turn(hid, 'review', 'reviewer', '不能误添尾轮', request_id='extra')


def test_requests_are_idempotent_and_conflicting_reuse_is_rejected(world):
    _, hearings, cid, _ = world
    first = hearings.start(cid, 'defendant', request_id='start')
    assert hearings.start(cid, 'defendant', request_id='start')['id'] == first['id']
    with pytest.raises(ValueError, match='request_id'):
        hearings.start(cid, 'plaintiff', request_id='start')
    args = (first['id'], 'issues', 'moderator', '先核清争点')
    one = hearings.append_turn(*args, request_id='turn')
    two = hearings.append_turn(*args, request_id='turn')
    assert one['turn'] == two['turn'] and two['idempotent'] is True
    assert hearings.get(first['id'])['turn_count'] == 1
    with pytest.raises(ValueError, match='request_id'):
        hearings.append_turn(first['id'], 'issues', 'moderator', '变更正文', request_id='turn')


def test_wrong_stage_or_role_never_advances_and_concurrent_retry_adds_once(world):
    _, hearings, cid, _ = world
    hid = hearings.start(cid, 'plaintiff')['id']
    with pytest.raises(ValueError, match='顺序'):
        hearings.append_turn(hid, 'debate', 'plaintiff', '错误次序')
    assert hearings.get(hid)['turn_count'] == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: hearings.append_turn(hid, 'issues', 'moderator', '并发重试', request_id='same'), range(2)))
    assert all(item['recorded'] for item in results)
    assert hearings.get(hid)['turn_count'] == 1


def test_material_change_preserves_unsaved_text_and_explicit_restart_links_history(world):
    cases, hearings, cid, source = world
    hid = hearings.start(cid, 'plaintiff', request_id='start')['id']
    hearings.append_turn(hid, 'issues', 'moderator', '旧材料下争点', request_id='old-turn')
    source.write_text('虚构材料新版本：价款变更为四万元，是否交付仍待核。', encoding='utf-8')
    assert hearings.get(hid)['materials_changed'] is True
    blocked = hearings.append_turn(hid, 'issues', 'plaintiff', '已生成的可用自然语言', request_id='after-change')
    assert blocked['recorded'] is False and blocked['reason'] == 'materials_changed'
    assert blocked['unsaved_turn']['text'] == '已生成的可用自然语言'
    assert hearings.get(hid)['turn_count'] == 1
    cases.link_materials(cid, [str(source)])
    fresh = hearings.start(cid, 'plaintiff', request_id='restart', previous_id=hid)
    assert fresh['id'] != hid and fresh['previous_id'] == hid
    assert fresh['turn_count'] == 0 and fresh['materials_changed'] is False
    assert hearings.get(hid)['turns'][0]['text'] == '旧材料下争点'


def test_added_material_and_cross_case_restart_cannot_silently_change_basis(world):
    cases, hearings, cid, source = world
    hid = hearings.start(cid, 'plaintiff')['id']
    extra = source.parent / 'extra.txt'
    extra.write_text('虚构补件', encoding='utf-8')
    cases.link_materials(cid, [str(extra)])
    assert hearings.get(hid)['materials_changed'] is True
    other = cases.create('另一虚构案件')['id']
    with pytest.raises(ValueError, match='案件'):
        hearings.start(other, 'plaintiff', previous_id=hid)


def test_unverified_citations_do_not_discard_long_natural_language(world):
    _, hearings, cid, _ = world
    hid = hearings.start(cid, 'plaintiff')['id']
    text = '这是完整的虚构庭审说明。' * 2500
    value = hearings.append_turn(hid, 'issues', 'moderator', text,
        citations=[{'path': 'fiction.txt', 'quote': '此引文不存在'}], unresolved='原文待核', request_id='long')
    assert value['recorded'] is True and value['turn']['text'] == text
    assert value['turn']['warnings']
    assert value['turn']['citations'][0]['status'] == 'unverified'


def test_role_context_separates_frozen_evidence_and_simulated_statements(world):
    _, hearings, cid, _ = world
    hid = hearings.start(cid, 'defendant', '交付事实')['id']
    hearings.append_turn(hid, 'issues', 'moderator', '这只是模拟追问')
    context = hearings.role_context(hid, 'defendant')
    assert context['role'] == 'defendant' and context['our_role'] == 'defendant'
    assert context['evidence_materials'][0]['path'] == 'fiction.txt'
    assert context['simulation_turns'][0]['text'] == '这只是模拟追问'
    assert '模拟' in context['notice'] and '独立' in context['notice']
    with pytest.raises(ValueError, match='角色'):
        hearings.role_context(hid, 'customer')


def test_verified_quote_and_foreign_reference_keep_distinct_statuses(world):
    cases, hearings, cid, _ = world
    with cases.store.db() as db:
        db.execute("UPDATE materials SET status='ready' WHERE path='fiction.txt'")
        db.execute('INSERT INTO chunks VALUES(?,?,?,?,?)', ('fiction.txt', 0, None, '段1', '约定价款三万元'))
    other = cases.create('另一虚构案')['id']
    hid = hearings.start(cid, 'plaintiff')['id']
    saved = hearings.append_turn(hid, 'issues', 'moderator', '两条来源均不影响保留正文', citations=[
        {'path': 'fiction.txt', 'chunk': 0, 'quote': '价款三万元'},
        {'case_id': other, 'path': 'fiction.txt', 'quote': '价款三万元'},
    ])
    assert [row['status'] for row in saved['turn']['citations']] == ['matched', 'unverified']
    assert saved['turn']['review_status'] == 'unverified'
    assert saved['turn']['warnings']


def test_fact_correction_changes_context_but_output_notes_do_not(world):
    cases, hearings, cid, _ = world
    original = cases.add_note(cid, 'consultation', '客户原话仍待核。' * 800, source='user')
    hid = hearings.start(cid, 'plaintiff')['id']
    context = hearings.role_context(hid, 'moderator')
    frozen = context['source_notes'][0]
    assert frozen['id'] == original['id'] and frozen['review_status'] == 'unverified'
    assert frozen['content_complete'] is False and frozen['next_start'] == 4000
    assert frozen['total_chars'] > len(frozen['content_preview'])
    cases.add_note(cid, 'internal_note', '模拟复盘不能变成事实输入')
    cases.add_note(cid, 'client_reply', '客户回复输出')
    assert hearings.get(hid)['context_changed'] is False
    correction = cases.add_note(cid, 'consultation', '客户明确更正原话：未完成交付。', source='user', supersedes=original['id'])
    view = hearings.get(hid)
    assert view['context_changed'] is True and view['source_notes_changed'] is True
    assert view['materials_changed'] is False
    blocked = hearings.append_turn(hid, 'issues', 'moderator', '已生成但未写入旧事实基础')
    assert blocked['recorded'] is False and blocked['reason'] == 'context_changed'
    assert blocked['unsaved_turn']['text'] == '已生成但未写入旧事实基础'
    newer = hearings.start(cid, 'plaintiff', previous_id=hid)
    assert newer['context_changed'] is False
    assert newer['source_notes'][0]['id'] == correction['id']
    assert hearings.get(hid)['source_notes'][0]['id'] == original['id']


def test_resume_by_case_and_read_long_turn_in_full_without_cross_hearing_access(world):
    cases, hearings, cid, _ = world
    hid = hearings.start(cid, 'plaintiff')['id']
    text = '长篇发言需要保留完整上下文。' * 3000
    saved = hearings.append_turn(hid, 'issues', 'moderator', text)
    reopened = HearingStore(CaseStore(cases.root))
    page = reopened.list(cid, limit=1)
    assert page['hearings'][0]['id'] == hid
    assert page['hearings'][0]['next_role'] == 'plaintiff'
    view = reopened.get(hid)
    preview = view['turns'][0]
    assert len(preview['text']) < len(text) and preview['next_start'] == len(preview['text'])
    restored = ''; start = 0
    while True:
        part = reopened.read_turn(hid, saved['turn']['id'], start=start, limit=3000)
        restored += part['text']
        if part['next_start'] is None: break
        start = part['next_start']
    assert restored == text
    other = hearings.start(cid, 'plaintiff')['id']
    with pytest.raises(ValueError, match='本次演练'):
        reopened.read_turn(other, saved['turn']['id'])
    another_case = cases.create('另一案件')['id']
    assert reopened.list(another_case)['hearings'] == []
