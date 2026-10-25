"""Reception worksheets on disposable synthetic native workspaces."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from test_assistant_routes import native, chat, create, sign_in

STATEMENT = '甲称借出10万元，乙称部分已还，目前没有完整还款凭证。'
NOTES = '客户诉求：先核对款项\n我方立场：尚未确认代理哪一方\n已知陈述（待核）：有人称部分已还\n待核问题：还款金额与凭证\n下一步：补充材料\n原备注：保留内部讨论。'


def start(client, headers):
    first = create(client,headers)
    return '/api/assistant/conversations/'+first['scope']['conversation_id']+'/reception-worksheet'


def basis(view):
    return {'expected_scope':view['scope'],'base_profile_revision':view['profile_revision']}


def save(client, headers, url, **edits):
    view = client.get(url).json()
    body = {'request_id':str(uuid4()),'patch':{'scope':view['scope'],
        'base_profile_revision':view['profile_revision'],'changes':[]},
        'expected_intake_id':view['expected_intake_id'],'expected_intake_revision':view['expected_intake_revision'],
        'manual_edits':[{'field':name,'value':{'kind':'text','value':value}} for name,value in edits.items()],
        'project_intake':False}
    result = client.post(url+'/commits',headers=headers,json=body)
    assert result.status_code == 200,result.text
    return result.json(),body


def test_empty_and_manual_worksheet_reopen_uses_existing_protected_profile(chat):
    client,database,_ = chat
    headers = sign_in(client);url = start(client,headers)
    view = client.get(url).json()
    assert view['profile_revision'] == 0 and view['fields'] == [] and view['writable'] is True
    receipt,body = save(client,headers,url,consultation=STATEMENT,internal_notes=NOTES,client_reply='请补充还款记录。')
    assert receipt['profile_revision'] == 1
    assert client.post(url+'/commits',headers=headers,json=body).json() == receipt
    assert client.get(url+'/receipts/'+body['request_id']).json() == receipt
    reopened = client.get(url).json()
    fields = {f['field']:f for f in reopened['fields']}
    assert fields['internal_notes']['protected_value']['value'] == NOTES
    assert fields['consultation']['protected_value']['value'] == STATEMENT
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM matters')) == 0


def test_template_questions_are_source_bound_and_do_not_run_a_model(chat):
    client,database,_ = chat
    headers = sign_in(client);url = start(client,headers)
    save(client,headers,url,consultation=STATEMENT,internal_notes=NOTES)
    view = client.get(url).json()
    response = client.post(url+'/suggestions',headers=headers,json=basis(view))
    assert response.status_code == 200,response.text
    result = response.json()
    assert result['origin'] == 'template' and result['model_called'] is False
    assert any('还款' in q['question'] and '金额' in q['question'] and '凭证' in q['question'] for q in result['items'])
    assert all(q['reason'] and q['quote'] in STATEMENT for q in result['items'])
    assert result['profile_revision'] == view['profile_revision']
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_profile_revisions')) == 1


def test_prepare_preserves_saved_additional_text_without_sending_or_changing_draft(chat):
    client,database,_ = chat
    headers = sign_in(client);url = start(client,headers)
    save(client,headers,url,consultation=STATEMENT,internal_notes=NOTES)
    conversation_url = url.removesuffix('/reception-worksheet')
    current = client.get(conversation_url).json()
    draft = client.put(conversation_url+'/draft',headers=headers,json={'expected_scope':current['scope'],
        'expected_composer_revision':current['composer_revision'],'content':'补充：乙说通过现金还过，金额还不清楚。'}).json()
    view = client.get(url).json()
    body = {**basis(view),'expected_composer_revision':view['composer_revision']}
    result = client.post(url+'/prepare',headers=headers,json=body)
    assert result.status_code == 200,result.text
    prepared = result.json()
    assert STATEMENT in prepared['content'] and NOTES in prepared['content']
    assert draft['draft_input'] in prepared['content']
    assert '不得推定欠款余额' in prepared['content'] and '追问理由' in prepared['content']
    assert prepared['model_called'] is False
    assert client.get(conversation_url).json()['draft_input'] == draft['draft_input']
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


@pytest.mark.parametrize('action',['suggestions','prepare'])
def test_stale_profile_or_scope_does_not_prepare_old_source(chat,action):
    client,_,_ = chat
    headers = sign_in(client);url = start(client,headers)
    save(client,headers,url,consultation=STATEMENT)
    old = client.get(url).json()
    save(client,headers,url,internal_notes=NOTES)
    body = basis(old)
    if action == 'prepare':body['expected_composer_revision'] = old['composer_revision']
    assert client.post(url+'/'+action,headers=headers,json=body).status_code == 409
    body = basis(client.get(url).json());body['expected_scope']['conversation_id'] = str(uuid4())
    if action == 'prepare':body['expected_composer_revision'] = old['composer_revision']
    assert client.post(url+'/'+action,headers=headers,json=body).status_code == 409


@pytest.mark.parametrize('mutation',[{'project_intake':True},{'manual_edits':[]},
    {'manual_edits':[{'field':'contact','value':{'kind':'text','value':'不可从此入口改联系方式'}}]}])
def test_worksheet_saves_only_its_explicit_manual_fields(chat,mutation):
    client,_,_ = chat
    headers = sign_in(client);url = start(client,headers)
    _,body = save(client,headers,url,consultation=STATEMENT)
    body = {**body,'request_id':str(uuid4()),**mutation}
    assert client.post(url+'/commits',headers=headers,json=body).status_code == 422


@pytest.mark.parametrize('action',['suggestions','prepare','commits'])
def test_owner_and_csrf_are_checked_before_body(chat,monkeypatch,action):
    from cn_contract.web import reception_worksheet
    client,_,_ = chat
    headers = sign_in(client);url = start(client,headers)
    assert client.post(url+'/'+action,json={}).status_code == 403
    async def unread(*args):pytest.fail('unauthorized body read')
    monkeypatch.setattr(reception_worksheet,'body_input',unread)
    other = sign_in(client,'另一合成律师')
    assert client.get(url).status_code == 403
    assert client.post(url+'/'+action,headers=other,content='invalid').status_code == 403
    client.cookies.clear()
    assert client.post(url+'/'+action,content='invalid').status_code == 401


def test_body_time_revocation_is_rechecked(chat,monkeypatch):
    from cn_contract.web import reception_worksheet
    client,database,_ = chat
    headers = sign_in(client);url = start(client,headers)
    save(client,headers,url,consultation=STATEMENT)
    view = client.get(url).json();original = reception_worksheet.body_input
    async def revoke(request,model):
        value = await original(request,model)
        with database.session() as db:db.execute(text('UPDATE sessions SET revoked=1'))
        return value
    monkeypatch.setattr(reception_worksheet,'body_input',revoke)
    assert client.post(url+'/suggestions',headers=headers,json=basis(view)).status_code == 401


def test_archived_and_fenced_worksheet_cannot_write_or_prepare(chat):
    from cn_contract.ops.storage import RestoreFenceRow
    client,database,_ = chat
    headers = sign_in(client);url = start(client,headers)
    _,body = save(client,headers,url,consultation=STATEMENT)
    with database.session() as db:db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-25T00:00:00+00:00'"))
    view = client.get(url).json();assert view['writable'] is False
    assert client.post(url+'/prepare',headers=headers,json={**basis(view),'expected_composer_revision':view['composer_revision']}).status_code == 409
    assert client.post(url+'/commits',headers=headers,json={**body,'request_id':str(uuid4())}).status_code == 409
    with database.session() as db:db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    assert client.post(url+'/suggestions',headers=headers,json=basis(view)).status_code == 409


def test_bound_intake_repeated_save_preserves_all_existing_protected_values(chat):
    from cn_contract.assistant.profile_integrity import validate_profile_records
    client,database,_ = chat;headers = sign_in(client)
    intake = client.post('/api/intakes',headers=headers,json={'request_id':str(uuid4()),
        'draft':{'title':'合成接待','consultation':'原接待陈述','internal_notes':'原接待备注'}})
    assert intake.status_code == 201,intake.text
    first = create(client,headers,scope_kind='intake',scope_ref=intake.json()['id'])
    url = '/api/assistant/conversations/'+first['scope']['conversation_id']+'/reception-worksheet'
    save(client,headers,url,consultation='律师人工更正陈述')
    receipt,body = save(client,headers,url,internal_notes='只改底稿，不修改陈述')
    assert client.post(url+'/commits',headers=headers,json=body).json() == receipt
    fields = {f['field']:f for f in client.get(url).json()['fields']}
    assert fields['consultation']['protected_value']['value'] == '律师人工更正陈述'
    assert client.get('/api/intakes/'+intake.json()['id']).json()['consultation'] == '原接待陈述'
    with database.session() as db:validate_profile_records(db)


def test_prepare_rechecks_composer_and_rejects_task_nesting_or_client_supplied_text(chat):
    from cn_contract.assistant.reception_worksheet import TASK_HEADER
    client,_,_ = chat;headers = sign_in(client);url = start(client,headers)
    save(client,headers,url,consultation=STATEMENT)
    view = client.get(url).json();body = {**basis(view),'expected_composer_revision':view['composer_revision']}
    assert client.post(url+'/prepare',headers=headers,json={**body,'content':'客户端伪造原文'}).status_code == 422
    conversation = url.removesuffix('/reception-worksheet')
    record = client.get(conversation).json()
    result = client.put(conversation+'/draft',headers=headers,json={'expected_scope':record['scope'],
        'expected_composer_revision':record['composer_revision'],'content':TASK_HEADER+'\n已经准备的任务'})
    assert result.status_code == 200
    assert client.post(url+'/prepare',headers=headers,json=body).status_code == 409
    latest = client.get(url).json()
    assert client.post(url+'/prepare',headers=headers,json={**basis(latest),
        'expected_composer_revision':latest['composer_revision']}).status_code == 409


def test_actual_backup_restores_worksheet_and_receipt_readonly(native,tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from cn_contract.ops import workspace_backup
    from cn_contract.web.local_server import build_local_app
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    app,root = native
    with TestClient(app) as client:
        headers = sign_in(client);url = start(client,headers)
        receipt,body = save(client,headers,url,consultation=STATEMENT,internal_notes=NOTES,client_reply='请补还款凭证。')
        original = client.get(url).json()
    archive = tmp_path/'合成接待底稿.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    restored_root = Path(restored['restored_root'])
    recovered = build_local_app(restored_root,data_parent=restored_root.parent.parent)
    try:
        with TestClient(recovered) as client:
            headers = sign_in(client)
            current = client.get(url).json()
            assert current['fields'] == original['fields'] and current['writable'] is False
            assert client.get(url+'/receipts/'+body['request_id']).json() == receipt
            for action in ('commits','prepare','suggestions'):
                assert client.post(url+'/'+action,headers=headers,json={}).status_code == 409
            for suffix in ('/unsafe','/receipts/not-a-uuid','/commits','/receipts/'+body['request_id']+'/unsafe'):
                assert client.get(url+suffix).status_code == 409
    finally:
        recovered.state.database.engine.dispose()
