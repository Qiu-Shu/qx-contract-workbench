"""Synthetic native-workspace HTTP, body boundaries and actual TCP event reads."""
from contextlib import contextmanager
import json
import socket
from threading import Event, Thread
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import text
import uvicorn

from cn_contract.domain import Role
from cn_contract.security import provision_user
from cn_contract.web import local_server

PASSWORD = 'fiction123'
USERNAME = '对话合成律师'


@pytest.fixture
def native(tmp_path):
    root = tmp_path/'workspaces/main'
    local_server.initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    app = local_server.build_local_app(root, data_parent=tmp_path)
    with app.state.database.session() as db:
        provision_user('另一合成律师', PASSWORD, {Role.HANDLING_LAWYER}, db, local_workbench_password=True)
    return app, root


@pytest.fixture
def chat(native):
    app, root = native
    with TestClient(app) as client:
        yield client, app.state.database, root


def sign_in(client, username=USERNAME):
    response = client.post('/api/login',json={'username':username,'password':PASSWORD})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token':response.json()['csrf_token']}


def create(client, headers, **fields):
    response = client.post('/api/assistant/conversations',headers=headers,
        json={'request_id':str(uuid4()),**fields})
    assert response.status_code == 201, response.text
    return response.json()


def sent(client, headers, conversation):
    request = {'request_id':str(uuid4()),'expected_scope':conversation['scope'],
        'expected_composer_revision':conversation['composer_revision'], 'content':'原话：独立合成客户称尚未收款。'}
    response = client.post('/api/assistant/conversations/'+conversation['scope']['conversation_id']+'/messages',
                           headers=headers,json=request)
    assert response.status_code == 202, response.text
    return response.json(), request


def test_roundtrip_preserves_input_idempotency_and_legacy_pages(chat):
    client, database, _ = chat
    headers = sign_in(client)
    first = create(client,headers,display_title='合成聊天')
    url = '/api/assistant/conversations/'+first['scope']['conversation_id']
    draft = client.put(url+'/draft',headers=headers,json={'expected_scope':first['scope'],
        'expected_composer_revision':0,'content':'下一句未发送'})
    assert draft.status_code == 200
    run, request = sent(client,headers,draft.json())
    assert run['state']=='queued' and run['selected_provider'] is run['selected_model'] is None
    assert client.post(url+'/messages',headers=headers,json=request).json()['id']==run['id']
    assert client.post(url+'/messages',headers=headers,json={**request,'content':'变了'}).status_code==409
    view=client.get(url).json()
    assert view['messages'][0]['content']==request['content']
    assert view['scope']['input_revision']==1 and view['draft_input']==''
    assert client.get('/api/assistant/runs/'+run['id']).json()['id']==run['id']
    page=client.get('/api/assistant/conversations',params={'limit':1}).json()
    assert len(page['items'])==1 and 'messages' not in page['items'][0]
    assert client.get('/').status_code==client.get('/workspace').status_code==200
    assert client.get('/api/intakes').status_code==200
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs'))==1


def test_authentication_and_ownership_precede_body_read(chat, monkeypatch):
    from cn_contract.web import assistant
    client, _, _ = chat
    async def unread(*args):
        raise AssertionError('request body must not be read')
    headers=sign_in(client); first=create(client,headers)
    run,_=sent(client,headers,first)
    other=sign_in(client,'另一合成律师')
    monkeypatch.setattr(assistant,'body_input',unread)
    base='/api/assistant/conversations/'+first['scope']['conversation_id']
    assert client.put(base+'/draft',headers=other,content='not-json').status_code==403
    assert client.post(base+'/messages',headers=other,content='not-json').status_code==403
    assert client.post('/api/assistant/runs/'+run['id']+'/cancel',headers=other,content='not-json').status_code==403
    client.cookies.clear()
    assert client.post('/api/assistant/conversations',content='not-json').status_code==401


def test_session_revocation_while_reading_body_is_rechecked(chat, monkeypatch):
    from cn_contract.web import assistant
    client,database,_=chat; headers=sign_in(client)
    original=assistant.body_input
    async def revoke(request,model):
        value=await original(request,model)
        with database.session() as db: db.execute(text('UPDATE sessions SET revoked=1'))
        return value
    monkeypatch.setattr(assistant,'body_input',revoke)
    assert client.post('/api/assistant/conversations',headers=headers,json={'request_id':str(uuid4())}).status_code==401
    with database.session() as db: assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations'))==0


def test_csrf_origin_strict_body_and_bounded_queries(chat):
    client,_,_=chat; headers=sign_in(client)
    url='/api/assistant/conversations'; data={'request_id':str(uuid4())}
    assert client.post(url,json=data).status_code==403
    assert client.post(url,json=data,headers={**headers,'Origin':'https://evil.invalid'}).status_code==403
    assert client.post(url,json={**data,'workspace_id':str(uuid4())},headers=headers).status_code==422
    assert client.post(url,content='{"request_id":"x","request_id":"y"}',headers=headers).status_code==422
    assert client.post(url,content='x'*(256*1024+1),headers=headers).status_code==413
    assert client.get(url,params={'limit':51}).status_code==422
    assert client.get(url,params={'cursor':'bad'}).status_code==422
    skills=client.get('/api/assistant/skills')
    assert skills.status_code==200 and skills.json()['generation_enabled'] is False
    assert [s['id'] for s in skills.json()['items']][:4]==['client_reply','material_organize','contract_review','content_draft']
    assert all(s['state']==('local_only' if s['id']=='legal_research' else 'not_connected')
               for s in skills.json()['items'])


def test_cancel_and_resume_committed_events(chat):
    client,database,_=chat; headers=sign_in(client); first=create(client,headers); run,_=sent(client,headers,first)
    url='/api/assistant/runs/'+run['id']; key=str(uuid4())
    result=client.post(url+'/cancel',headers=headers,json={'request_id':key})
    assert result.status_code==200 and result.json()['state']=='cancelled'
    assert client.post(url+'/cancel',headers=headers,json={'request_id':key}).json()==result.json()
    response=client.get(url+'/events',params={'after_seq':1})
    assert response.status_code==200 and response.headers['content-type'].startswith('text/event-stream')
    assert 'id: 2\n' in response.text and 'run.cancelled' in response.text and 'message.accepted' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert client.get(url+'/events',headers={'Last-Event-ID':'2'},params={'after_seq':0}).text==''
    for headers_extra in ({'Last-Event-ID':'-1'},{'Last-Event-ID':'NaN'},{'Last-Event-ID':'9'*100}):
        assert client.get(url+'/events',headers=headers_extra).status_code==422
    assert client.get(url+'/events',params={'after_seq':3}).status_code==409
    assert client.get(url+'/events',headers={'Origin':'https://evil.invalid'}).status_code==403
    assert client.get(url+'/events',headers={'Sec-Fetch-Site':'same-site'}).status_code==403
    sign_in(client,'另一合成律师')
    assert client.get(url+'/events').status_code==403
    with database.session() as db: assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs'))==1


def test_recovery_allows_exact_assistant_reads_and_rejects_all_writes(native):
    from cn_contract.ops import storage
    original,root=native; database=original.state.database
    with TestClient(original) as client:
        headers=sign_in(client); first=create(client,headers); run,_=sent(client,headers,first)
        client.post('/api/assistant/runs/'+run['id']+'/cancel',headers=headers,json={'request_id':str(uuid4())})
    with database.session() as db:
        db.add(storage.RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    app=local_server.build_local_app(root,data_parent=root.parent.parent)
    with TestClient(app) as recovered:
        h=sign_in(recovered); url='/api/assistant/conversations/'+first['scope']['conversation_id']
        assert recovered.get(url).status_code==200
        assert recovered.get('/api/assistant/conversations').status_code==200
        assert recovered.get('/api/assistant/skills').status_code==200
        assert recovered.get('/api/assistant/runs/'+run['id']).status_code==200
        assert recovered.get('/api/assistant/runs/'+run['id']+'/events').status_code==200
        assert recovered.post(url+'/messages',headers=h,json={}).status_code==409
        assert recovered.post('/api/assistant/runs/'+run['id']+'/cancel',headers=h,json={}).status_code==409
        assert recovered.request('DELETE',url,headers=h,json={}).status_code==409
        assert recovered.get('/api/assistant/unreviewed').status_code==409


@contextmanager
def serve(app):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); sock.listen(32)
        server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
        thread=Thread(target=lambda:server.run(sockets=[sock]),daemon=True); thread.start()
        deadline=time.monotonic()+10
        try:
            while not server.started:
                assert thread.is_alive() and time.monotonic()<deadline
                time.sleep(.01)
            yield 'http://127.0.0.1:'+str(sock.getsockname()[1])
        finally:
            server.should_exit=True; thread.join(15)
            assert not thread.is_alive()


def test_tcp_stream_releases_transaction_and_rechecks_revocation(native):
    app,_=native
    with serve(app) as url, httpx.Client(base_url=url,trust_env=False,timeout=3) as client:
        headers=sign_in(client); first=create(client,headers); run,_=sent(client,headers,first)
        with client.stream('GET','/api/assistant/runs/'+run['id']+'/events') as response:
            assert response.status_code==200
            lines=response.iter_lines()
            assert next(lines)=='id: 1'
            # The stream remains open while another request commits a draft.
            with httpx.Client(base_url=url,cookies=client.cookies,trust_env=False,timeout=2) as second:
                view=second.get('/api/assistant/conversations/'+first['scope']['conversation_id']).json()
                saved=second.put('/api/assistant/conversations/'+first['scope']['conversation_id']+'/draft',headers=headers,
                    json={'expected_scope':view['scope'],'expected_composer_revision':view['composer_revision'],'content':'流连接中保存合成草稿'})
                assert saved.status_code==200
            with app.state.database.session() as db: db.execute(text('UPDATE sessions SET revoked=1'))
            remaining='\n'.join(lines)
            assert 'access.revoked' in remaining
            assert '流连接中保存合成草稿' not in remaining
        with app.state.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs'))==1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_run_events'))==1


def test_slow_http_body_does_not_hold_database_transaction(native, monkeypatch):
    from cn_contract.web import assistant
    app,_=native; reading=Event(); release=Event(); responses=[]
    original=assistant.body_input
    async def observe(request,model):
        if request.headers.get('X-Synthetic-Slow')=='yes': reading.set()
        return await original(request,model)
    monkeypatch.setattr(assistant,'body_input',observe)
    with serve(app) as url, httpx.Client(base_url=url,trust_env=False,timeout=3) as client:
        headers=sign_in(client); cookies=dict(client.cookies)
        body=json.dumps({'request_id':str(uuid4())}).encode()
        def chunks():
            yield body[:1]
            assert release.wait(8)
            yield body[1:]
        def upload():
            with httpx.Client(base_url=url,cookies=cookies,trust_env=False,timeout=10) as slow:
                responses.append(slow.post('/api/assistant/conversations',
                    headers={**headers,'X-Synthetic-Slow':'yes'},content=chunks()))
        thread=Thread(target=upload); thread.start()
        try:
            assert reading.wait(4)
            # This is a real concurrent write while the first body is unfinished.
            with httpx.Client(base_url=url,cookies=cookies,trust_env=False,timeout=2) as second:
                assert create(second,headers)['scope']['input_revision']==0
        finally:
            release.set(); thread.join(12)
        assert not thread.is_alive() and len(responses)==1
        assert responses[0].status_code==201


def test_elapsed_poll_window_does_not_send_late_batch(chat, monkeypatch):
    from cn_contract.web import assistant
    from cn_contract import domain as d
    client,database,_=chat; h=sign_in(client); first=create(client,h); run,_=sent(client,h,first)
    clock=[0.0]; calls=[]
    monkeypatch.setattr(assistant.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(assistant.time,'sleep',lambda duration:clock.__setitem__(0,clock[0]+duration))
    page=d.AssistantEventPage(run_id=run['id'],conversation_id=first['scope']['conversation_id'],
        state='queued',events=(),next_after_seq=0,has_more=False)
    def delayed_read(after):
        calls.append(after); clock[0]=assistant.STREAM_SECONDS+1
        return page.model_copy(update={'events':(d.AssistantRunEvent.model_validate(run['events'][0]),),
                                      'next_after_seq':1})
    frames=list(assistant._events(delayed_read,page))
    assert calls==[0]
    assert all('message.accepted' not in frame for frame in frames)


def test_elapsed_window_during_send_stops_before_another_read(chat, monkeypatch):
    from cn_contract.web import assistant
    from cn_contract import domain as d
    client,_,_=chat; h=sign_in(client); first=create(client,h); run,_=sent(client,h,first)
    clock=[0.0]
    monkeypatch.setattr(assistant.time,'monotonic',lambda:clock[0])
    event=d.AssistantRunEvent.model_validate(run['events'][0])
    page=d.AssistantEventPage(run_id=run['id'],conversation_id=first['scope']['conversation_id'],state='queued',
        events=(event,event.model_copy(update={'seq':2})),next_after_seq=2,has_more=True)
    def unread(after): raise AssertionError('expired stream must not read again')
    stream=assistant._events(unread,page)
    assert next(stream).startswith('id: 1')
    clock[0]=assistant.STREAM_SECONDS+1
    assert list(stream)==[]
