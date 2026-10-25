"""Synthetic reception integration; no real models, documents or client messages."""
from uuid import uuid4

from sqlalchemy import text
from tests.integration.test_assistant_routes import chat, native, sign_in


def create_intake(client, headers, **changes):
    draft = {'title':'合成咨询','consultation':'合成客户称对方未按约交货','internal_notes':'内部旧意见',
             'client_reply':'已写好的客户回复','questions':['请问约定交货日期是什么时候？']}
    result = client.post('/api/intakes', headers=headers,
        json={'request_id':str(uuid4()), 'draft':{**draft, **changes}})
    assert result.status_code == 201, result.text
    return result.json()


def test_preview_uses_saved_reception_without_writing_or_running_a_model(chat):
    client, database, _ = chat
    headers = sign_in(client)
    record = create_intake(client, headers)
    before = client.get('/api/intakes/'+record['id']).json()
    result = client.post('/api/intakes/'+record['id']+'/assistant/preview', headers=headers,
        json={'expected_revision':1, 'mode':'first_reply', 'references':[]})
    assert result.status_code == 200, result.text
    preview = result.json()
    assert preview['model_calls'] == 0 and preview['kind'] == 'template_draft'
    assert '交货日期' in preview['client_reply']
    assert '内部旧意见' not in preview['client_reply']
    assert '未经核实' in preview['prompt'] and '合成客户称' in preview['prompt']
    assert client.get('/api/intakes/'+record['id']).json() == before
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations')) == 0


def test_preview_rejects_other_owner_csrf_cross_origin_and_stale_version(chat):
    client, _, _ = chat
    headers = sign_in(client)
    record = create_intake(client, headers)
    url = '/api/intakes/'+record['id']+'/assistant/preview'
    body = {'expected_revision':1, 'mode':'follow_up', 'references':[]}
    assert client.post(url, json=body).status_code == 403
    assert client.post(url, headers={**headers,'Origin':'https://invalid.example'},json=body).status_code == 403
    assert client.post(url, headers=headers,json={**body,'expected_revision':2}).status_code == 409
    assert client.post(url, headers=headers,json={**body,'mode':'auto_sell'}).status_code == 422
    other = sign_in(client, '另一合成律师')
    assert client.post(url, headers=other,json=body).status_code == 403
    client.cookies.clear()
    assert client.post(url, headers=headers,json=body).status_code == 401


def test_assistant_chat_is_scoped_idempotent_and_never_overwrites_an_edited_draft(chat):
    client, database, _ = chat
    headers = sign_in(client)
    record = create_intake(client, headers)
    url = '/api/intakes/'+record['id']+'/assistant/conversation'
    body = {'expected_revision':1,'mode':'materials','references':[],'request_id':str(uuid4())}
    first = client.post(url,headers=headers,json=body)
    assert first.status_code == 201, first.text
    view = first.json()
    assert view['scope']['scope_kind'] == 'intake' and view['scope']['scope_ref'] == record['id']
    assert view['draft_input'] and view['composer_revision'] == 1
    repeated = client.post(url,headers=headers,json=body)
    assert repeated.status_code == 201 and repeated.json() == view
    cid = view['scope']['conversation_id']
    saved = client.put('/api/assistant/conversations/'+cid+'/draft',headers=headers,
        json={'expected_scope':view['scope'],'expected_composer_revision':1,'content':'律师手工更正，不能覆盖'})
    assert saved.status_code == 200
    assert client.post(url,headers=headers,json=body).status_code == 409
    assert client.get('/api/assistant/conversations/'+cid).json()['draft_input'] == '律师手工更正，不能覆盖'
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations')) == 1
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs')) == 0


def test_knowledge_routes_require_a_lawyer_and_page_has_real_controls(chat):
    client, _, _ = chat
    assert client.get('/api/reception/knowledge').status_code == 401
    headers = sign_in(client)
    result = client.get('/api/reception/knowledge')
    assert result.status_code == 200 and result.json()['state'] == 'not_configured'
    record = create_intake(client,headers)
    page = client.get('/intakes/'+record['id'])
    assert '法律服务接待助手' in page.text and 'reception-assistant.mjs' in page.text
    assert client.get('/static/reception-assistant.mjs').status_code == 200
    assert client.get('/api/reception/knowledge/search?q=合成').json()['items'] == []


def test_selected_knowledge_is_revalidated_and_kept_out_of_client_export(chat,tmp_path):
    from io import BytesIO
    from docx import Document
    from cn_contract.reception.knowledge import import_plugin
    from tests.unit.test_reception_knowledge import package
    client, database, _ = chat
    root = tmp_path/'references'
    import_plugin(package(tmp_path),root)
    client.app.state.reception_knowledge.root=root
    headers=sign_in(client)
    record=create_intake(client,headers)
    hit=client.get('/api/reception/knowledge/search?q=核对').json()['items'][0]
    reference={k:hit[k] for k in ('source_id','paragraph','quote_sha256')}
    url='/api/intakes/'+record['id']+'/assistant/preview'
    body={'expected_revision':1,'mode':'materials','references':[reference]}
    response=client.post(url,headers=headers,json=body)
    assert response.status_code==200,response.text
    preview=response.json()
    assert hit['text'] in preview['internal_notes'] and hit['source_id'] in preview['prompt']
    assert hit['text'] not in preview['client_reply'] and hit['source_id'] not in preview['client_reply']
    assert client.post(url,headers=headers,json={**body,'references':[reference,reference]}).status_code==422
    assert client.post(url,headers=headers,json={**body,'references':[{**reference,'quote_sha256':'0'*64}]}).status_code==409
    assert client.post(url,headers=headers,json={**body,'references':[{**reference,'source_id':'0'*64}]}).status_code==404
    original={k:record[k] for k in ('title','contact','consultation','questions','materials','follow_up_at','follow_up_note','status','client_reply','internal_notes')}
    saved=client.put('/api/intakes/'+record['id'],headers=headers,json={'expected_revision':1,'draft':{
        **original,'client_reply':record['client_reply']+'\n\n'+preview['client_reply'],
        'internal_notes':record['internal_notes']+'\n\n'+preview['internal_notes']}})
    assert saved.status_code==200 and saved.json()['revision']==2
    exported=client.post('/api/intakes/'+record['id']+'/export',headers=headers,
        json={'revision':2,'audience':'client','text_checked':True})
    assert exported.status_code==200
    text='\n'.join(p.text for p in Document(BytesIO(exported.content)).paragraphs)
    assert preview['client_reply'] in text and '内部旧意见' not in text and hit['source_id'] not in text
    assert client.post(url,headers=headers,json=body).status_code==409
    source=client.get('/api/reception/knowledge/sources/'+hit['source_id'])
    assert source.status_code==200 and 'script' in source.text
    assert client.get('/api/reception/knowledge/search',params={'q':'x'*201}).status_code==422
    assert client.get('/api/reception/knowledge/sources/'+hit['source_id']+'?start=-1').status_code==422
    (root/'originals'/(hit['source_id']+'.docx')).write_bytes(b'corrupt')
    assert client.post(url,headers=headers,json={**body,'expected_revision':2}).status_code==409


def test_role_revocation_removes_reference_access(chat):
    client,database,_=chat
    headers=sign_in(client)
    with database.session() as db:
        db.execute(text('UPDATE users SET roles=:roles WHERE username=:name'),
            {'roles':'["admin"]','name':'对话合成律师'})
    assert client.get('/api/reception/knowledge').status_code==403


def test_conversation_preserves_saved_contact_restrictions_and_follow_up_time(chat):
    client, _, _ = chat
    headers=sign_in(client)
    record=create_intake(client,headers,follow_up_note='客户明确要求本月不要再联系；仅接受邮件。',
                         follow_up_at='2026-11-05T02:00:00Z')
    result=client.post('/api/intakes/'+record['id']+'/assistant/conversation',headers=headers,
        json={'expected_revision':1,'mode':'follow_up','references':[],'request_id':str(uuid4())})
    assert result.status_code==201,result.text
    prompt=result.json()['draft_input']
    assert '客户明确要求本月不要再联系；仅接受邮件。' in prompt
    assert '2026-11-05T02:00:00+00:00' in prompt
    assert '实际联系前应再次确认' in prompt
