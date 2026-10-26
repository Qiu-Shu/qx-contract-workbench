from copy import deepcopy
from uuid import uuid4
from sqlalchemy import text
from test_assistant_routes import native, chat, sign_in
from test_evidence_worksheet import begin, request, statement, material
from test_reception_worksheet import save

def test_old_statement_exact_retention_new_id_cannot_mint(chat):
    client,db,_=chat;h=sign_in(client);base,url=begin(client,h)
    fact=statement(client,h,base,url)
    assert client.post(url+'/commits',headers=h,json=request(client.get(url).json(),[fact])).status_code==200
    save(client,h,base+'/reception-worksheet',consultation='客户更正：原陈述有误，需要逐笔核对。')
    view=client.get(url).json();assert view['historical_ids']==[fact['id']]
    fact['note']='保留旧陈述，记载新更正';fact['review_state']='disputed'
    assert client.post(url+'/commits',headers=h,json=request(view,[fact])).status_code==200
    extra=deepcopy(fact);extra['id']=str(uuid4())
    assert client.post(url+'/commits',headers=h,json=request(client.get(url).json(),[fact,extra])).status_code==409
    with db.session() as s:assert s.scalar(text('SELECT count(*) FROM assistant_evidence_revisions'))==2

def test_current_owner_required_for_history_and_receipt(chat):
    client,db,_=chat;h=sign_in(client);base,url=begin(client,h)
    fact=statement(client,h,base,url);body=request(client.get(url).json(),[fact])
    assert client.post(url+'/commits',headers=h,json=body).status_code==200
    sign_in(client,'另一合成律师')
    assert client.get(url).status_code==403
    assert client.get(url+'/revisions/1').status_code==403
    assert client.get(url+'/receipts/'+body['request_id']).status_code==403

def test_revocation_between_original_check_and_final_write(chat,monkeypatch):
    from cn_contract.assistant import attachment_files
    client,db,_=chat;h=sign_in(client);base,url=begin(client,h)
    a,p,source=material(client,h,base,db)
    fact={'id':str(uuid4()),'category':'other','content':'合成事实，待核','source':source}
    body=request(client.get(url).json(),[fact]);original=attachment_files.read_checked
    def revoke(row,database):
        result=original(row,database)
        with database.session() as s:s.execute(text('UPDATE sessions SET revoked=1'))
        return result
    monkeypatch.setattr(attachment_files,'read_checked',revoke)
    assert client.post(url+'/commits',headers=h,json=body).status_code==401
    with db.session() as s:assert s.scalar(text('SELECT count(*) FROM assistant_evidence_revisions'))==0
