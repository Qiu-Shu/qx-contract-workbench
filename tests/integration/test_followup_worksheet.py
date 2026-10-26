"""Follow-up links and handling history on independent fictional native workspaces."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from test_assistant_routes import native, chat, sign_in, create
from test_evidence_worksheet import begin, statement, material, request as evidence_request


def setup(client,h):
    base,evidence_url=begin(client,h)
    fact=statement(client,h,base,evidence_url)
    assert client.post(evidence_url+'/commits',headers=h,json=evidence_request(client.get(evidence_url).json(),[fact])).status_code==200
    return base,base+'/followups',evidence_url,fact


def body(view,items):
    return {'request_id':str(uuid4()),'expected_scope':view['scope'],'expected_profile_revision':view['profile_revision'],
        'expected_evidence_revision':view['evidence_revision'],'base_revision':view['revision'],'items':items}


def item(view,fact,**updates):
    return {'id':str(uuid4()),'title':'补充逐笔还款记录及凭证','reason':'客户仅称部分已还，金额和时间不清',
        'impact':'影响还款事实与余额核对','next_action':'向客户询问每笔时间、金额、方式并收取凭证',
        'due_date':'2026-11-01','status':'open','result':'',
        'facts':[{'evidence_revision':view['evidence_revision'],'fact_id':fact['id']}],'materials':[],**updates}


def commit(client,h,url,items):
    value=body(client.get(url).json(),items);r=client.post(url+'/commits',headers=h,json=value)
    assert r.status_code==200,r.text
    return r.json(),value


def test_followup_links_status_history_retry_and_no_implicit_fact_changes(chat):
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h)
    r=client.get(url);assert r.status_code==200,r.text
    v=r.json();assert v['revision']==0 and v['facts']==[fact] and v['items']==[]
    row=item(v,fact);receipt,first=commit(client,h,url,[row])
    for status,result in [('requested','已询问客户，尚未收到'),('received','收到部分记录，待逐项核对'),('completed','已核对并记载缺口，未据此确认余额')]:
        row={**row,'status':status,'result':result};commit(client,h,url,[row])
    assert client.get(url).json()['items']==[row]
    assert client.get(ev).json()['rows']==[fact]
    assert client.get(url+'/revisions/1').json()['items'][0]['status']=='open'
    assert client.get(url+'/receipts/'+first['request_id']).json()==receipt
    assert client.post(url+'/commits',headers=h,json=first).json()==receipt
    changed=deepcopy(first);changed['items'][0]['title']='同号不同内容'
    assert client.post(url+'/commits',headers=h,json=changed).status_code==409
    assert client.get(url+'/receipts/'+str(uuid4())).json() is None
    with db.session() as session:
        assert session.scalar(text('SELECT count(*) FROM assistant_model_attempts'))==0
        assert session.scalar(text('SELECT count(*) FROM matters'))==0


def test_completed_item_needs_recheck_after_linked_fact_changes_and_explicit_relink(chat):
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h)
    assert client.get(url).status_code==200
    row=item(client.get(url).json(),fact,status='completed',result='初次核对记录')
    commit(client,h,url,[row]);old=deepcopy(fact);fact['content']='客户更正：还款金额尚未核定'
    assert client.post(ev+'/commits',headers=h,json=evidence_request(client.get(ev).json(),[fact])).status_code==200
    v=client.get(url).json();assert v['items'][0]['status']=='completed'
    assert v['attention'][0]['item_id']==row['id'] and any('事实' in x for x in v['attention'][0]['reasons'])
    # Saving unrelated notes can preserve the old completion and its warning, not erase it.
    row['next_action']='核对新说法';commit(client,h,url,[row]);assert client.get(url).json()['attention']
    row['result']='现在已经全部核定'
    assert client.post(url+'/commits',headers=h,json=body(client.get(url).json(),[row])).status_code==409
    row['facts']=[{'evidence_revision':v['evidence_revision'],'fact_id':fact['id']}];row['result']='已核对新说法，金额仍待核'
    commit(client,h,url,[row]);assert client.get(url).json()['attention']==[]
    assert client.get(url+'/revisions/1').json()['items'][0]['facts'][0]['evidence_revision']==1


def test_unrelated_fact_changes_do_not_reopen_but_removed_link_is_not_hidden(chat):
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);assert client.get(url).status_code==200
    row=item(client.get(url).json(),fact,status='completed',result='只处理对应事实');commit(client,h,url,[row])
    other=deepcopy(fact);other['id']=str(uuid4());other['content']='另一个独立陈述'
    assert client.post(ev+'/commits',headers=h,json=evidence_request(client.get(ev).json(),[fact,other])).status_code==200
    assert client.get(url).json()['attention']==[]
    assert client.post(ev+'/commits',headers=h,json=evidence_request(client.get(ev).json(),[other])).status_code==200
    assert client.get(url).json()['attention'] and client.get(url).json()['items'][0]['status']=='completed'
    # Another item cannot reuse the removed historical fact through a fresh ID.
    extra={**row,'id':str(uuid4()),'status':'open','result':''}
    assert client.post(url+'/commits',headers=h,json=body(client.get(url).json(),[row,extra])).status_code==409


def test_material_association_received_does_not_auto_complete_and_reparse_warns(chat):
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);assert client.get(url).status_code==200
    a,p,source=material(client,h,base,db);v=client.get(url).json()
    row=item(v,fact,status='received',result='收到记录，待核',materials=[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}])
    commit(client,h,url,[row]);scope=client.get(base).json()['scope']
    r=client.post(base+'/attachments/'+a['id']+'/parses',headers=h,json={'request_id':str(uuid4()),'expected_scope':scope});assert r.status_code==200,r.text
    v=client.get(url).json();assert v['items'][0]['status']=='received' and v['attention']
    row['status']='completed';row['result']='核对了旧记录'
    assert client.post(url+'/commits',headers=h,json=body(v,[row])).status_code==409
    row['materials'][0]['parse_revision']=r.json()['parse']['revision'];commit(client,h,url,[row])
    assert client.get(url).json()['attention']==[]


@pytest.mark.parametrize('damage',['no_link','result','duplicate','scope','evidence','profile','base','fact','cross_material'])
def test_invalid_or_stale_link_is_rejected_without_followup_writes(chat,damage):
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);assert client.get(url).status_code==200
    row=item(client.get(url).json(),fact);value=body(client.get(url).json(),[row])
    if damage=='no_link':row['facts']=[]
    if damage=='result':row['status']='completed'
    if damage=='duplicate':value['items'].append(row)
    if damage=='scope':value['expected_scope']['input_revision']+=1
    if damage=='evidence':value['expected_evidence_revision']+=1
    if damage=='profile':value['expected_profile_revision']+=1
    if damage=='base':value['base_revision']+=1
    if damage=='fact':row['facts'][0]['fact_id']=str(uuid4())
    if damage=='cross_material':row['materials']=[{'attachment_id':str(uuid4()),'original_sha256':'a'*64,'parse_revision':None}]
    assert client.post(url+'/commits',headers=h,json=value).status_code in (403,409,422)
    with db.session() as session:assert session.scalar(text('SELECT count(*) FROM assistant_followup_revisions'))==0


def test_owner_csrf_archive_and_body_revocation(chat,monkeypatch):
    from cn_contract.web import followup_worksheet
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);assert client.get(url).status_code==200
    value=body(client.get(url).json(),[item(client.get(url).json(),fact)])
    original=followup_worksheet.body_input
    async def reject(request,model):raise AssertionError('body read before authentication')
    monkeypatch.setattr(followup_worksheet,'body_input',reject)
    assert client.post(url+'/commits',json=value).status_code==403
    sign_in(client,'另一合成律师');assert client.get(url).status_code==403
    h=sign_in(client)
    async def revoke(request,model):
        value=await original(request,model)
        with db.session() as session:session.execute(text('UPDATE sessions SET revoked=1'))
        return value
    monkeypatch.setattr(followup_worksheet,'body_input',revoke)
    assert client.post(url+'/commits',headers=h,json=value).status_code==401


def test_actual_backup_restores_followup_links_and_fixed_receipt_readonly(native,tmp_path):
    from cn_contract.ops import workspace_backup
    from cn_contract.web.local_server import build_local_app
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    app,root=native
    with TestClient(app) as client:
        h=sign_in(client);base,url,ev,fact=setup(client,h);assert client.get(url).status_code==200
        a,p,_=material(client,h,base,app.state.database)
        row=item(client.get(url).json(),fact,materials=[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}])
        receipt,value=commit(client,h,url,[row])
    archive=tmp_path/'合成待补清单.qxbak';workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE);rr=Path(restored['restored_root']);app=build_local_app(rr,data_parent=rr.parent.parent)
    try:
        with TestClient(app) as client:
            h=sign_in(client);v=client.get(url).json();assert v['items']==[row] and v['writable'] is False
            assert client.get(url+'/receipts/'+value['request_id']).json()==receipt
            assert client.get(url+'/revisions/1').json()['items']==[row]
            assert client.get(ev+'/revisions/1').json()['rows']==[fact]
            assert client.get(base+'/attachments/'+a['id']+'/original').status_code==200
            assert client.post(url+'/commits',headers=h,json=value).status_code==409
            for suffix in ('/unsafe','/revisions/0','/receipts/not-uuid','/commits'):
                assert client.get(url+suffix).status_code==409
    finally:app.state.database.engine.dispose()


def test_archived_followups_are_readonly_and_unknown_owner_cannot_read_receipts(chat):
    from cn_contract.record_codec import now
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h)
    receipt,value=commit(client,h,url,[item(client.get(url).json(),fact)])
    sign_in(client,'另一合成律师')
    for suffix in ('','/revisions/1','/receipts/'+value['request_id']):assert client.get(url+suffix).status_code==403
    h=sign_in(client)
    with db.session() as session:session.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),{'at':now().isoformat(),'id':base.split('/')[-1]})
    assert client.get(url).json()['writable'] is False
    assert client.post(url+'/commits',headers=h,content='not json').status_code==409


def test_original_check_revocation_rejects_final_write(chat,monkeypatch):
    from cn_contract.assistant import attachment_files
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);a,p,_=material(client,h,base,db)
    row=item(client.get(url).json(),fact,materials=[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}])
    value=body(client.get(url).json(),[row]);original=attachment_files.read_checked
    def revoke(source,database):
        raw=original(source,database)
        with db.session() as session:session.execute(text('UPDATE sessions SET revoked=1'))
        return raw
    monkeypatch.setattr(attachment_files,'read_checked',revoke)
    assert client.post(url+'/commits',headers=h,json=value).status_code==401
    with db.session() as session:assert session.scalar(text('SELECT count(*) FROM assistant_followup_revisions'))==0


@pytest.mark.parametrize('fault',['fact','material','actor','scope','base'])
def test_rehashed_invalid_history_cannot_pass_backup_validation(chat,fault):
    from cn_contract.assistant.followup_records import validate_followup_records
    from cn_contract.record_codec import encode,sha
    client,db,_=chat;h=sign_in(client);base,url,ev,fact=setup(client,h);a,p,_=material(client,h,base,db)
    row=item(client.get(url).json(),fact,materials=[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}])
    commit(client,h,url,[row])
    with db.session() as session:
        validate_followup_records(session)
        session.execute(text('DROP TRIGGER immutable_assistant_followup_revisions_update'))
        saved=session.execute(text('SELECT * FROM assistant_followup_revisions')).mappings().one()
        import json
        req=json.loads(saved['request_json']);snapshot=json.loads(saved['snapshot_json'])
        if fault=='fact':req['items'][0]['facts'][0]['fact_id']=str(uuid4());snapshot['items']=req['items']
        if fault=='material':req['items'][0]['materials'][0]['original_sha256']='a'*64;snapshot['items']=req['items']
        if fault=='actor':session.execute(text('UPDATE assistant_followup_revisions SET actor_id=(SELECT id FROM users WHERE id<>:owner LIMIT 1)'),{'owner':saved['actor_id']})
        if fault=='scope':req['expected_scope']['materials_revision']=0;snapshot['scope']=req['expected_scope']
        if fault=='base':req['base_revision']=8
        session.execute(text('UPDATE assistant_followup_revisions SET request_json=:r,request_sha256=:rs,snapshot_json=:s,snapshot_sha256=:ss'),{'r':encode(req),'rs':sha(req),'s':encode(snapshot),'ss':sha(snapshot)})
        with pytest.raises((ValueError,KeyError)):validate_followup_records(session)


def test_material_only_followup_before_any_fact_and_upload_does_not_complete_existing_item(chat):
    client,db,_=chat;h=sign_in(client);base,ev=begin(client,h);url=base+'/followups'
    a,p,_=material(client,h,base,db);v=client.get(url).json()
    assert v['evidence_revision']==0 and v['profile_revision']==0 and v['facts']==[]
    row={'id':str(uuid4()),'title':'补交付记录的用途说明','reason':'材料存在但款项性质未说明','impact':'影响交付性质核对',
        'next_action':'询问原始记录提供者','due_date':None,'status':'open','result':'','facts':[],
        'materials':[{'attachment_id':a['id'],'original_sha256':a['sha256'],'parse_revision':p['revision']}]}
    commit(client,h,url,[row])
    # A different uploaded original cannot silently close or retarget this item.
    material(client,h,base,db)
    current=client.get(url).json();assert current['items']==[row] and current['attention']==[]
