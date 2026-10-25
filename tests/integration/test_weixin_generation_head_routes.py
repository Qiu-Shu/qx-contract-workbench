"""Real HTTP callers obtain full CAS heads without reading internal account tables."""
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.record_codec import sha
from cn_contract.weixin_inbox import accounts
from test_api import create_case
from test_assistant_routes import chat,native,create,sign_in
from test_weixin_authorization_routes import bind,endpoint,module
from test_weixin_generation_routes import setup,target
from tests.helpers.synthetic_weixin_generations import state


def snapshot(database):
    value=state(database)
    with database.session() as db:
        for table in ('audit_events','assistant_conversations','assistant_messages','assistant_material_snapshots','assistant_model_attempts'):
            value[table]=[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))]
    return value


def read(client,base):
    response=client.get(base+'/head')
    assert response.status_code==200,response.text
    value=response.json()
    assert set(value)=={'mode','state','generation','generation_sha256','scope','scope_sha256','checkpoint_revision'}
    assert value['mode']=='synthetic' and value['state']=='history_only'
    assert value['scope_sha256']==sha(value['scope'])
    return value


def input_from_head(head,view,binding):
    return dict(request_id=str(uuid4()),expected_generation=head['generation'],
        expected_previous_generation_sha256=head['generation_sha256'],
        expected_previous_scope_sha256=head['scope_sha256'],expected_checkpoint_revision=head['checkpoint_revision'],
        task_binding_id=binding['id'],expected_scope=view['scope'],reason='独立合成HTTP head明确追加')


def test_head_to_two_explicit_posts_uses_only_http_metadata_and_stale_head_conflicts(chat):
    client,database,headers,view,actor,account,mapping,dest,binding=setup(chat)
    base=endpoint(view['scope']['conversation_id'])+'/generations'
    before=snapshot(database);zero=read(client,base)
    assert zero['generation']==0 and zero['generation_sha256'] is None and zero['checkpoint_revision']==0
    assert zero['scope']==view['scope'] and snapshot(database)==before
    first=client.post(base,headers=headers,json=input_from_head(zero,dest,binding))
    assert first.status_code==200,first.text
    second_view,second_binding=target(client,headers)
    stale=input_from_head(zero,second_view,second_binding);before=snapshot(database)
    assert client.post(base,headers=headers,json=stale).status_code==409
    assert snapshot(database)==before
    one=read(client,base)
    assert one['generation']==1 and one['generation_sha256']==first.json()['generation_sha256']
    second=client.post(base,headers=headers,json=input_from_head(one,second_view,second_binding))
    assert second.status_code==200,second.text
    before=snapshot(database);two=read(client,base)
    assert two['generation']==2 and two['scope']==second_view['scope']
    assert two['generation_sha256']==second.json()['generation_sha256'] and snapshot(database)==before
    for secret in (str(actor.user_id),str(account.id),str(mapping.id),account.bot_account_id,mapping.sender_peer_id,binding['id']):
        assert secret not in str(two)
    assert client.get(endpoint(dest['scope']['conversation_id'])+'/generations/head').json() is None


def test_unbound_head_is_null_and_creates_nothing(chat):
    client,database,_=chat;headers=sign_in(client);view=create(client,headers)
    before=snapshot(database);response=client.get(endpoint(view['scope']['conversation_id'])+'/generations/head')
    assert response.status_code==200 and response.json() is None
    assert snapshot(database)==before


def test_head_authentication_and_exact_read_predicate(chat):
    client,_,_=chat;base=endpoint(uuid4())+'/generations'
    assert client.get(base+'/head').status_code==401
    predicate=module().is_weixin_authorization_read_path
    assert predicate(base+'/head')
    for suffix in ('/head/','/head/x','/heads','/head/polls','/Head','/head/by-request/'+str(uuid4())):
        assert not predicate(base+suffix)


@pytest.mark.parametrize('damage',['origin','fetch_site','owner','unknown','workspace'])
def test_head_rechecks_same_origin_and_current_root_authority(chat,damage):
    client,database,headers,view,_,_,_,_,_=setup(chat);cid=view['scope']['conversation_id'];extra={}
    if damage=='origin':extra={'Origin':'https://evil.invalid'}
    elif damage=='fetch_site':extra={'Sec-Fetch-Site':'same-site'}
    elif damage=='owner':sign_in(client,'另一合成律师')
    elif damage=='unknown':cid=str(uuid4())
    else:
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET workspace_id=:new WHERE id=:id'),{'new':str(uuid4()),'id':cid})
    response=client.get(endpoint(cid)+'/generations/head',headers=extra)
    assert response.status_code==403,response.text


@pytest.mark.parametrize('damage,expected',[('membership',403),('matter_archive',403),('owner',409),('workspace',409)])
def test_latest_target_current_acl_is_required_before_head_disclosure(chat,damage,expected):
    client,database,headers,view,actor,_,_,_,_=setup(chat)
    matter=create_case(client,headers);destination,binding=target(client,headers,scope_kind='matter',scope_ref=matter)
    base=endpoint(view['scope']['conversation_id'])+'/generations';value=read(client,base)
    response=client.post(base,headers=headers,json=input_from_head(value,destination,binding))
    assert response.status_code==200,response.text
    with database.session() as db:
        if damage=='membership':
            db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id AND user_id=:user'),{'id':matter,'user':str(actor.user_id)})
        elif damage=='matter_archive':db.execute(text("UPDATE matters SET status='archived' WHERE id=:id"),{'id':matter})
        elif damage=='owner':
            db.execute(text('''UPDATE assistant_conversations SET owner_id=(SELECT id FROM users
                WHERE username='另一合成律师') WHERE id=:id'''),{'id':destination['scope']['conversation_id']})
        else:
            db.execute(text('UPDATE assistant_conversations SET workspace_id=:new WHERE id=:id'),{'new':str(uuid4()),'id':destination['scope']['conversation_id']})
    before=snapshot(database);found=client.get(base+'/head')
    # Identity mutation also corrupts immutable provenance; its history check precedes target ACL.
    assert found.status_code==expected,found.text
    assert found.json()['code']==('VERSION_CONFLICT' if expected==409 else 'CROSS_MATTER_DENIED')
    after=snapshot(database)
    assert {k:v for k,v in after.items() if k!='audit_events'}=={k:v for k,v in before.items() if k!='audit_events'}


def test_old_nonlatest_target_acl_does_not_grant_access_or_block_latest_head(chat):
    client,database,headers,view,actor,_,_,_,_=setup(chat)
    matter=create_case(client,headers);first,binding=target(client,headers,scope_kind='matter',scope_ref=matter)
    base=endpoint(view['scope']['conversation_id'])+'/generations'
    assert client.post(base,headers=headers,json=input_from_head(read(client,base),first,binding)).status_code==200
    second,binding2=target(client,headers)
    assert client.post(base,headers=headers,json=input_from_head(read(client,base),second,binding2)).status_code==200
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id AND user_id=:user'),{'id':matter,'user':str(actor.user_id)})
    before=snapshot(database);head=read(client,base)
    assert head['generation']==2 and head['scope']==second['scope'] and snapshot(database)==before


def test_fenced_app_allows_exact_head_and_keeps_writes_and_nearby_paths_blocked(native):
    from cn_contract.web import local_server
    original,root=native
    with TestClient(original) as client:
        client,database,headers,view,_,_,_,dest,binding=setup((client,original.state.database,root))
        base=endpoint(view['scope']['conversation_id'])+'/generations';value=input_from_head(read(client,base),dest,binding)
        assert client.post(base,headers=headers,json=value).status_code==200
        expected=read(client,base)
        with database.session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    app=local_server.build_local_app(root,data_parent=root.parent.parent)
    try:
        with TestClient(app) as restored:
            headers=sign_in(restored);before=snapshot(app.state.database)
            assert read(restored,base)==expected
            assert restored.post(base,headers=headers,json=value).status_code==409
            for suffix in ('/head/','/head/x','/head/polls','/heads','/Head'):
                assert restored.get(base+suffix).status_code==409
            assert snapshot(app.state.database)==before
    finally:app.state.database.engine.dispose()
