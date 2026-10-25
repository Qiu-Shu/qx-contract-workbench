import sys
sys.path.insert(0,'/Users/molin/Project/qx-contract-workbench/tests/integration')
from test_assistant_routes import native,chat,sign_in,create
from test_reception_worksheet import save
from uuid import uuid4

def test_intake_manual_profile_repeated_save(chat):
    client,_,_=chat;h=sign_in(client)
    ir=client.post('/api/intakes',headers=h,json={'request_id':str(uuid4()),'draft':{'title':'合成案件','consultation':'原接待陈述','internal_notes':'原接待备注'}})
    assert ir.status_code==201,ir.text
    first=create(client,h,scope_kind='intake',scope_ref=ir.json()['id'])
    url='/api/assistant/conversations/'+first['scope']['conversation_id']+'/reception-worksheet'
    save(client,h,url,consultation='律师人工更正陈述')
    f=lambda:{x['field']:x['protected_value'] for x in client.get(url).json()['fields']}
    assert f()['consultation']['value']=='律师人工更正陈述'
    save(client,h,url,internal_notes='只改底稿，不修改陈述')
    assert f()['consultation']['value']=='律师人工更正陈述',f()

def test_retry_after_later_save_and_explicit_null_survive(chat):
    from cn_contract.assistant.profile_integrity import validate_profile_records
    client,database,_=chat;h=sign_in(client)
    ir=client.post('/api/intakes',headers=h,json={'request_id':str(uuid4()),'draft':{'title':'合成案件','consultation':'原陈述','client_reply':'原客户回复'}}).json()
    first=create(client,h,scope_kind='intake',scope_ref=ir['id']);url='/api/assistant/conversations/'+first['scope']['conversation_id']+'/reception-worksheet'
    _,original=save(client,h,url,consultation='人工第一版')
    result,body=save(client,h,url,internal_notes='人工底稿')
    view=client.get(url).json()
    clear={**body,'request_id':str(uuid4()),'patch':{**body['patch'],'scope':view['scope'],'base_profile_revision':view['profile_revision']},'manual_edits':[{'field':'consultation','value':{'kind':'null','value':None}}]}
    assert client.post(url+'/commits',headers=h,json=clear).status_code==200
    save(client,h,url,client_reply='新的客户回复')
    assert client.post(url+'/commits',headers=h,json=body).json()==result
    now={f['field']:f['protected_value'] for f in client.get(url).json()['fields']}
    assert now['consultation']=={'kind':'null','value':None}
    assert now['client_reply']['value']=='新的客户回复'
    changed={**body,'manual_edits':[{'field':'internal_notes','value':{'kind':'text','value':'同id不同载荷'}}]}
    assert client.post(url+'/commits',headers=h,json=changed).status_code==409
    with database.session() as db:validate_profile_records(db)

def test_recovery_exact_read_and_receipts(native):
    from fastapi.testclient import TestClient
    from cn_contract.ops.storage import RestoreFenceRow
    from cn_contract.web import local_server
    app,root=native
    with TestClient(app) as client:
        h=sign_in(client);first=create(client,h);url='/api/assistant/conversations/'+first['scope']['conversation_id']+'/reception-worksheet'
        receipt,body=save(client,h,url,consultation='合成陈述',internal_notes='内部底稿')
    with app.state.database.session() as db:db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    recovery=local_server.build_local_app(root,data_parent=root.parent.parent)
    with TestClient(recovery) as client:
        h=sign_in(client)
        assert client.get(url).status_code==200
        assert client.get(url).json()['writable'] is False
        assert client.get(url+'/receipts/'+body['request_id']).json()==receipt
        for suffix in ('/commits','/prepare','/suggestions','/receipts/'+body['request_id']+'/unsafe'):
            assert client.get(url+suffix).status_code==409
        for suffix in ('/commits','/prepare','/suggestions'):
            assert client.post(url+suffix,headers=h,json=body).status_code==409
        assert client.get('/assistant/'+first['scope']['conversation_id']).status_code==200
