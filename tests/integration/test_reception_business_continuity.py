"""Continuous reception uses fictional local statements and existing profile history."""
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import business, profile_integrity
from test_assistant_routes import chat, native, create, sign_in
from test_assistant_business import submit


FIRST = '客户咨询：虚构甲称2025年1月借给朋友三万元，尚未收到还款，想问要准备什么材料。'
MORE = '补充：客户说明2025年2月收到五千元，银行转账记录尚待提供。'
CORRECTION = '更正：刚才说错了，原始出借金额是四万元，不是三万元。'


def start(chat, content=FIRST):
    client, database, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    response, url, body = submit(client, headers, view, content, workflow='sales')
    assert response.status_code == 200, response.text
    return client, database, headers, url.removesuffix('/business'), response.json()


def send(state, content):
    client, _, headers, base, first = state
    response, url, body = submit(client, headers, client.get(base).json(), content, task_id=first['task_id'])
    assert response.status_code == 200, response.text
    assert response.json()['task_id'] == first['task_id']
    assert client.post(url, headers=headers, json=body).json() == response.json()
    return response.json()


def consultation(state):
    client, _, _, base, _ = state
    profile = client.get(base+'/profile').json()
    return profile, next(field for field in profile['fields'] if field['field']=='consultation')


def validate(state):
    with state[1].session() as db:
        business.validate_business_records(db, allowed=True)
        profile_integrity.validate_profile_records(db)


def manual(state, content, *, legacy=False, request_id=None):
    client, _, headers, base, first = state
    if legacy:
        url = '/api/intakes/'+first['intake_id']
        previous = client.get(url).json()
        draft = {key:previous[key] for key in d.IntakeDraft.model_fields}
        draft['consultation'] = content
        response = client.put(url, headers=headers, json={'expected_revision':previous['revision'], 'draft':draft})
    else:
        view = client.get(base+'/reception-worksheet').json()
        response = client.post(base+'/reception-worksheet/commits', headers=headers, json={
            'request_id':str(request_id or uuid4()), 'patch':{'scope':view['scope'],
                'base_profile_revision':view['profile_revision'], 'changes':[]},
            'expected_intake_id':view['expected_intake_id'], 'expected_intake_revision':view['expected_intake_revision'],
            'manual_edits':[{'field':'consultation','value':{'kind':'text','value':content}}], 'project_intake':False})
    assert response.status_code == 200, response.text


def test_continuous_statements_and_correction_keep_one_intake_and_readable_sources(chat):
    state = start(chat)
    client, _, headers, base, first = state
    before = client.get(base+'/profile/revisions/1').json()
    for content in (MORE, CORRECTION):
        assert send(state, content)['intake_id'] == first['intake_id']
    profile, field = consultation(state)
    selected = field['protected_value']['value'] if field['protected_value'] else ''
    assert all(content in selected for content in (FIRST, MORE, CORRECTION))
    assert '明确更正' in selected and '待核' in selected
    assert client.get('/api/intakes/'+first['intake_id']).json()['consultation'] == selected
    view = client.get(base+'/reception-worksheet').json()
    suggestions = client.post(base+'/reception-worksheet/suggestions', headers=headers, json={
        'expected_scope':view['scope'], 'base_profile_revision':view['profile_revision']})
    assert suggestions.status_code == 200, suggestions.text
    messages = {item['id']:item for item in client.get(base).json()['messages'] if item['role']=='user'}
    assert {candidate['value']['value'] for candidate in field['candidates']} == {FIRST, MORE, CORRECTION}
    assert all(messages[ref['message_id']]['content'][ref['start']:ref['end']] == ref['quote']
               for candidate in field['candidates'] for ref in candidate['source_refs'])
    assert client.get(base+'/profile/revisions/1').json() == before
    assert len(client.get('/api/intakes').json()['items']) == 1
    validate(state)


@pytest.mark.parametrize('instruction', [
    '请把回复缩短两句', '请把回复改得更委婉一点', '请用两句话回复', '请润色一下刚才的回复',
    '请把给客户的回复缩短到两句话。', '请把回复改成更委婉的语气。',
    '麻烦将给客户的答复精简成两句。', '请将发给客户的回复压缩为三句话。',
    '把上面的回复改成更礼貌的语气。', '请把回复调整为更温和的语气。',
])
def test_output_only_instruction_does_not_change_fact_candidates_or_projection(chat, instruction):
    state = start(chat)
    client, database, _, base, first = state
    before = client.get(base+'/profile').json()
    intake = client.get('/api/intakes/'+first['intake_id']).json()
    result = send(state, instruction)
    assert result['intake_id'] == first['intake_id']
    assert client.get(base+'/profile').json() == before
    assert client.get('/api/intakes/'+first['intake_id']).json() == intake
    receipt_id = str(uuid5(NAMESPACE_URL, 'qx-business-profile:'+result['run_id']))
    receipt = client.get(base+'/profile/receipts/'+receipt_id).json()
    assert receipt['profile_changed'] is False and receipt['projection_changed'] is False
    assert instruction in [m['content'] for m in client.get(base).json()['messages']]
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
    validate(state)


@pytest.mark.parametrize('legacy', [False, True], ids=['worksheet', 'intake-page'])
@pytest.mark.parametrize('change', ['different', 'empty', 'same'])
def test_manual_consultation_even_same_value_or_clear_is_never_auto_replaced(chat, legacy, change):
    state = start(chat)
    _, field = consultation(state)
    initial = field['protected_value']['value'] if field['protected_value'] else FIRST
    chosen = {'different':'律师手工保留的陈述，内容仍待核。', 'empty':'', 'same':initial}[change]
    manual(state, chosen, legacy=legacy)
    for content in (MORE, CORRECTION):
        send(state, content)
        _, field = consultation(state)
        assert field['protected_value'] is not None
        assert field['protected_value']['value'] == chosen
    assert {candidate['value']['value'] for candidate in field['candidates']} == {FIRST, MORE, CORRECTION}
    validate(state)


def test_unrelated_business_run_uuid5_cannot_relabel_manual_edit_as_automatic(chat):
    state = start(chat)
    client, _, headers, base, _ = state
    case, _, _ = submit(client, headers, client.get(base).json(), '整理这个案件', workflow='case')
    assert case.status_code == 200
    _, field = consultation(state)
    initial = field['protected_value']['value'] if field['protected_value'] else FIRST
    manual(state, initial, request_id=uuid5(NAMESPACE_URL, 'qx-business-profile:'+case.json()['run_id']))
    send(state, MORE)
    _, field = consultation(state)
    assert field['protected_value']['value'] == initial
    validate(state)


def test_exceeding_archive_limit_retains_old_statement_and_full_new_source(chat):
    original = '客户咨询：'+'虚构原始陈述。'*1500
    state = start(chat, original)
    before, old = consultation(state)
    content = '补充：'+'虚构补充材料尚待核对。'*200
    result = send(state, content)
    _, field = consultation(state)
    previous = old['protected_value']['value'] if old['protected_value'] else original
    assert field['protected_value'] is not None and field['protected_value']['value'] == previous
    assert '超限' in result['text'] and '未并入' in result['text']
    assert any(ref['quote']==content for candidate in field['candidates'] for ref in candidate['source_refs'])
    assert state[0].get(state[3]+'/profile/revisions/'+str(before['revision'])).json() == before
    assert content in [m['content'] for m in state[0].get(state[3]).json()['messages']]
    validate(state)


@pytest.mark.parametrize('content', [
    '请把回复缩短两句；补充：客户今天收到五千元。',
    '请把给客户的回复缩短到两句话。补充：客户今天收到五千元。',
    '更正：客户收到的是六千元。请把回复改成更委婉的语气。',
])
def test_output_instruction_with_new_facts_is_not_discarded(chat, content):
    state = start(chat)
    send(state, content)
    _, field = consultation(state)
    assert any(candidate['value']['value']==content for candidate in field['candidates'])
    assert content in field['protected_value']['value']
    validate(state)


def test_identical_client_names_in_separate_chats_never_merge(chat):
    first = start(chat)
    second = start(chat)
    assert first[4]['intake_id'] != second[4]['intake_id']
    assert first[4]['task_id'] != second[4]['task_id']
    validate(first)
