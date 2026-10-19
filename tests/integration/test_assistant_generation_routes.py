"""Synthetic native HTTP generation; lifecycle, authority and receipt recovery."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import workspace_backup
from cn_contract.security import provision_user
from cn_contract.web import local_server
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world


DEFAULT=object()


@contextmanager
def boot(world, tmp_path, *, runtime=DEFAULT, root=None):
    database, actor, conversation, message, configured = world
    root=root or Path(database.engine.url.database).parent
    app=local_server.build_local_app(root,data_parent=tmp_path,
        assistant_model_runtime=configured if runtime is DEFAULT else runtime)
    with TestClient(app) as client:
        headers=signin(client)
        yield SimpleNamespace(client=client,app=app,database=app.state.database,root=root,
            actor=actor,conversation=conversation,body=message.model_dump(mode='json'),
            runtime=configured,headers=headers,
            url='/api/assistant/conversations/'+str(conversation.scope.conversation_id))


def signin(client, username='lawyer'):
    response=client.post('/api/login',json={'username':username,'password':'fixture123'})
    assert response.status_code==200,response.text
    return {'X-CSRF-Token':response.json()['csrf_token']}


def test_authorized_unicode_text_over_model_wire_limit_returns_fixed_error(world, tmp_path):
    from cn_contract.assistant.providers.policy import sha
    database, _, _, _, runtime = world
    content = '🦊' * 20000
    runtime.policy = runtime.policy.model_copy(update={'allowed_content_sha256s':(sha(content),)})
    with boot(world,tmp_path) as http:
        save_draft(http,content)
        assert http.client.get(http.url+'/generation-capability').json()['state']=='unsupported'
        response = http.client.post(http.url+'/generations',headers=http.headers,json={**http.body,'content':content})
        assert response.status_code==422
        assert response.json()['code']=='STATE_CONFLICT'
        assert http.client.get(http.url).json()['draft_input']==content
        assert count(database)==count(database,'assistant_messages')==0
        assert runtime.provider.calls==[]


def save_draft(http, content=None):
    view=http.client.get(http.url).json()
    response=http.client.put(http.url+'/draft',headers=http.headers,json={
        'expected_scope':view['scope'],'expected_composer_revision':view['composer_revision'],
        'content':http.body['content'] if content is None else content})
    assert response.status_code==200,response.text
    view=response.json()
    http.body.update(expected_scope=view['scope'],expected_composer_revision=view['composer_revision'])
    return view


def count(database, table='assistant_model_attempts'):
    with database.session() as db:
        return db.scalar(text(f'SELECT COUNT(*) FROM {table}'))


def wait_attempt(http, identifier):
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        response=http.client.get('/api/assistant/attempts/'+identifier)
        assert response.status_code==200,response.text
        if response.json()['state'] not in {'reserved','sending'}:
            return response.json()
        time.sleep(.01)
    pytest.fail('synthetic attempt did not settle')


class DelayedProvider:
    def __init__(self, config):
        self.config=config;self.calls=[];self.started=Event();self.release=Event()

    async def generate(self, request, *, expected_config=None):
        self.calls.append(request);self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(.01)
        return d.MainReply(state='received',usage=d.MainUsage(prompt_tokens=10,completion_tokens=5,total_tokens=15),
            output=d.MainCandidate(text='独立合成待核候选。',citations=(d.MainCitation(
                message_id=request.message_id,quote_sha256=request.source_sha256),)))


def test_default_runtime_disabled_without_blocking_local_drafts(world,tmp_path):
    with boot(world,tmp_path,runtime=None) as http:
        save_draft(http)
        capability=http.client.get(http.url+'/generation-capability')
        assert capability.status_code==200,capability.text
        assert capability.json()['state']=='unconfigured'
        denied=http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
        assert denied.status_code==403
        assert count(http.database)==count(http.database,'assistant_messages')==0
        assert http.client.get(http.url).json()['draft_input']==http.body['content']


def test_saved_draft_capability_does_not_probe_provider_or_expose_policy(world,tmp_path):
    with boot(world,tmp_path) as http:
        first=http.client.get(http.url+'/generation-capability')
        assert first.status_code==200,first.text
        assert first.json()['state']=='empty'
        draft=save_draft(http)
        result=http.client.get(http.url+'/generation-capability').json()
        assert result['state']=='ready' and result['basis']=='saved_draft'
        assert result['scope']==draft['scope'] and result['composer_revision']==draft['composer_revision']
        assert len(result['content_sha256'])==64
        assert set(result)=={'scope','composer_revision','basis','content_sha256','state'}
        assert http.runtime.provider.calls==[] and count(http.database)==0


@pytest.mark.parametrize('change,expected',[
    ('disabled','unconfigured'),('missing_policy','unapproved'),('expired','unapproved'),
    ('wrong_actor','unapproved'),('wrong_source','unapproved'),('tiny_budget','budget_exhausted')])
def test_capability_and_post_recheck_actual_policy(world,tmp_path,change,expected):
    runtime=world[-1]
    if change=='disabled':runtime.provider.config=runtime.provider.config.model_copy(update={'enabled':False})
    elif change=='missing_policy':runtime.policy=None
    else:
        field,value={'expired':('expires_at',datetime.now(timezone.utc)-timedelta(seconds=1)),
            'wrong_actor':('actor_id',uuid4()),'wrong_source':('allowed_content_sha256s',('0'*64,)),
            'tiny_budget':('max_total_usd','0.000001')}[change]
        runtime.policy=d.MainModelPolicy.model_validate({**runtime.policy.model_dump(mode='python'),field:value})
    with boot(world,tmp_path) as http:
        save_draft(http)
        response=http.client.get(http.url+'/generation-capability')
        assert response.status_code==200,response.text
        assert response.json()['state']==expected
        assert http.client.post(http.url+'/generations',headers=http.headers,json=http.body).status_code==403
        assert count(http.database)==0 and runtime.provider.calls==[]


def test_async_submission_returns_before_provider_and_replay_only_reads_same_attempt(world,tmp_path):
    runtime=world[-1];runtime.provider=DelayedProvider(runtime.provider.config)
    with boot(world,tmp_path) as http:
        try:
            response=http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
            assert response.status_code==202,response.text
            first=response.json();assert runtime.provider.started.wait(1)
            assert not runtime.provider.release.is_set()
            assert http.client.get(http.url+'/generation-capability').json()['state']=='busy'
            replay=http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
            assert replay.status_code==202 and replay.json()['id']==first['id']
            changed=http.client.post(http.url+'/generations',headers=http.headers,
                json={**http.body,'content':'同一请求编号不能替换的合成内容'})
            assert changed.status_code==409
            found=http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
            assert found.status_code==200 and found.json()['id']==first['id']
            assert http.client.get('/api/assistant/attempts/'+first['id']).status_code==200
            save_draft(http,'网络仍在等待时保存的下一句合成草稿')
            assert len(runtime.provider.calls)==1 and count(http.database)==1
            runtime.provider.release.set()
            completed=wait_attempt(http,first['id'])
            assert completed['state']=='received' and completed['receipt']['cost_status']=='estimated'
            assert completed['output']['audience']=='internal' and completed['output']['review_status']=='unverified'
        finally:
            runtime.provider.release.set()


def test_auth_csrf_and_ownership_are_checked_before_body(world,tmp_path,monkeypatch):
    database=world[0]
    with database.session() as db:
        provision_user('other','fixture123',{d.Role.HANDLING_LAWYER},db,local_workbench_password=True)
    with boot(world,tmp_path) as http:
        from cn_contract.web import assistant_generation
        async def unread(*args):pytest.fail('unauthorized body was read')
        monkeypatch.setattr(assistant_generation,'body_input',unread)
        assert http.client.post(http.url+'/generations',content='bad').status_code==403
        assert http.client.post(http.url+'/generations',headers={**http.headers,'Origin':'https://example.invalid'},content='bad').status_code==403
        other=signin(http.client,'other')
        assert http.client.post(http.url+'/generations',headers=other,content='bad').status_code==403
        assert http.client.get(http.url+'/generation-capability').status_code==403
        assert http.client.get(http.url+'/generations/by-request/'+http.body['request_id']).status_code==403
        http.client.cookies.clear()
        assert http.client.post(http.url+'/generations',content='bad').status_code==401
        assert count(database)==0


def test_session_revoked_while_body_arrives_cannot_create_attempt(world,tmp_path,monkeypatch):
    with boot(world,tmp_path) as http:
        from cn_contract.web import assistant_generation
        async def revoke_after_read(request,model):
            with http.database.session() as db:
                db.execute(text('UPDATE sessions SET revoked=1'))
            return d.AssistantMessageInput.model_validate(http.body)
        monkeypatch.setattr(assistant_generation,'body_input',revoke_after_read)
        assert http.client.post(http.url+'/generations',headers=http.headers,json=http.body).status_code==401
        assert count(http.database)==0 and http.runtime.provider.calls==[]


@pytest.mark.parametrize('body_change',[
    {'policy':{'enabled':True}},{'config':{'model':'override'}},{'key':'SYNTHETIC-KEY'},
    {'requested_skill':'contract_review'},{'attachment_ids':[str(uuid4())]}])
def test_http_never_accepts_runtime_policy_skill_or_attachment_egress(world,tmp_path,body_change):
    with boot(world,tmp_path) as http:
        response=http.client.post(http.url+'/generations',headers=http.headers,json={**http.body,**body_change})
        assert response.status_code in {403,422},response.text
        assert count(http.database)==0 and http.runtime.provider.calls==[]


def test_oversized_or_duplicate_json_is_rejected_without_registration(world,tmp_path):
    with boot(world,tmp_path) as http:
        response=http.client.post(http.url+'/generations',headers=http.headers,content='x'*(256*1024+1))
        assert response.status_code==413
        assert http.client.post(http.url+'/generations',headers=http.headers,
            content='{"request_id":"a","request_id":"b"}').status_code==422
        assert count(http.database)==0


def test_old_queued_message_and_lookup_never_gain_execution(world,tmp_path):
    with boot(world,tmp_path) as http:
        old=http.client.post(http.url+'/messages',headers=http.headers,json=http.body)
        assert old.status_code==202 and old.json()['state']=='queued'
        found=http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
        assert found.status_code==200 and found.json() is None
        assert http.client.post(http.url+'/generations',headers=http.headers,json=http.body).status_code==409
        assert http.client.get(http.url+'/generations/by-request/'+str(uuid4())).json() is None
        assert http.runtime.provider.calls==[] and count(http.database)==0


def test_attempt_read_uses_current_owner_and_session(world,tmp_path):
    database=world[0]
    with database.session() as db:
        provision_user('other','fixture123',{d.Role.HANDLING_LAWYER},db,local_workbench_password=True)
    with boot(world,tmp_path) as http:
        response=http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
        assert response.status_code==202,response.text
        identifier=response.json()['id'];wait_attempt(http,identifier)
        signin(http.client,'other')
        assert http.client.get('/api/assistant/attempts/'+identifier).status_code==403
        signin(http.client)
        with database.session() as db:db.execute(text('UPDATE sessions SET revoked=1'))
        assert http.client.get('/api/assistant/attempts/'+identifier).status_code==401


def test_native_shutdown_seals_inflight_before_database_disposal_and_restart_never_resends(world,tmp_path,monkeypatch):
    runtime=world[-1];runtime.provider=DelayedProvider(runtime.provider.config)
    with boot(world,tmp_path) as http:
        response=http.client.post(http.url+'/generations',headers=http.headers,json=http.body)
        assert response.status_code==202,response.text
        identifier=response.json()['id'];assert runtime.provider.started.wait(1)
        dispose=http.database.engine.dispose;observed=[]
        def checked_dispose(*args,**kwargs):
            with world[0].session() as db:
                state=db.scalar(text('SELECT state FROM assistant_model_attempts WHERE id=:id'),{'id':identifier})
                assert state=='sent_unknown'
            observed.append(True)
            return dispose(*args,**kwargs)
        monkeypatch.setattr(http.database.engine,'dispose',checked_dispose)
        with pytest.raises(ValueError,match='WORKSPACE_IN_USE'):
            with local_server._worker_lock(http.root):pass
    assert observed and len(runtime.provider.calls)==1
    with boot(world,tmp_path) as reopened:
        result=reopened.client.get('/api/assistant/attempts/'+identifier).json()
        assert result['state']=='sent_unknown' and result['receipt']['cost_status']=='unknown'
        assert reopened.client.get(reopened.url+'/generations/by-request/'+reopened.body['request_id']).json()['id']==identifier
        assert len(runtime.provider.calls)==1


def test_restored_copy_exposes_only_exact_generation_reads(world,tmp_path,monkeypatch):
    database,actor,conversation,message,runtime=world
    with database.session() as db:
        first=attempts.enqueue_generation(actor,conversation.scope.conversation_id,message,db,runtime)
    asyncio.run(execute_attempt(actor,first.id,database,runtime))
    root=Path(database.engine.url.database).parent;archive=tmp_path/'generation.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    with boot(world,tmp_path,root=Path(restored['restored_root'])) as http:
        from cn_contract.web import assistant_generation
        async def unread(*args):pytest.fail('restored write body was read')
        monkeypatch.setattr(assistant_generation,'body_input',unread)
        capability=http.client.get(http.url+'/generation-capability')
        assert capability.status_code==200 and capability.json()['state']=='restored_read_only'
        assert http.client.get('/api/assistant/attempts/'+str(first.id)).json()['id']==str(first.id)
        assert http.client.get(http.url+'/generations/by-request/'+str(message.request_id)).json()['id']==str(first.id)
        for path in (http.url+'/generation-capability/extra','/api/assistant/attempts/'+str(first.id)+'/extra',
                http.url+'/generations/by-request/'+str(message.request_id)+'/extra'):
            assert http.client.get(path).status_code==409
        assert http.client.post(http.url+'/generations',headers=http.headers,content='bad').status_code==409
        assert len(runtime.provider.calls)==1


def test_without_started_lifespan_capability_and_post_cannot_claim_ready(world,tmp_path):
    database,_,conversation,message,runtime=world
    root=Path(database.engine.url.database).parent
    app=local_server.build_local_app(root,data_parent=tmp_path,assistant_model_runtime=runtime)
    try:
        client=TestClient(app)
        headers=signin(client)
        base='/api/assistant/conversations/'+str(conversation.scope.conversation_id)
        capability=client.get(base+'/generation-capability')
        assert capability.status_code==200 and capability.json()['state']=='busy'
        response=client.post(base+'/generations',headers=headers,json=message.model_dump(mode='json'))
        assert response.status_code==409
        assert count(database)==0 and runtime.provider.calls==[]
    finally:
        client.close();app.state.database.engine.dispose()


def test_selected_local_attachment_blocks_capability_and_plain_text_dispatch(world,tmp_path):
    from tests.integration.test_assistant_attachments import sample
    raw=sample();mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    with boot(world,tmp_path) as http:
        http.database._assistant_synthetic_hashes=frozenset({hashlib.sha256(raw).hexdigest()})
        metadata={'request_id':str(uuid4()),'expected_scope':http.body['expected_scope'],
            'original_name':'独立合成.docx','mime':mime,'policy':{'local_processing_accepted':True}}
        uploaded=http.client.post(http.url+'/attachments',headers=http.headers,files=[
            ('file',('独立合成.docx',raw,mime)),('metadata',(None,json.dumps(metadata),'application/json'))])
        assert uploaded.status_code==201,uploaded.text
        save_draft(http)
        assert http.client.get(http.url+'/generation-capability').json()['state']=='unsupported'
        assert http.client.post(http.url+'/generations',headers=http.headers,json=http.body).status_code==403
        assert count(http.database)==0 and http.runtime.provider.calls==[]


def test_generation_lifecycle_is_nested_inside_live_worker_and_can_restart(world,tmp_path,monkeypatch):
    from cn_contract.assistant.task_manager import GenerationTasks
    database,_,_,_,runtime=world
    root=Path(database.engine.url.database).parent
    app=local_server.build_local_app(root,data_parent=tmp_path,assistant_model_runtime=runtime)
    start,close=GenerationTasks.start,GenerationTasks.close
    events=[]
    def checked_start(manager):
        assert app.state.worker_thread.is_alive()
        events.append('start')
        return start(manager)
    async def checked_close(manager):
        assert app.state.worker_thread.is_alive()
        await close(manager)
        events.append('close')
    monkeypatch.setattr(GenerationTasks,'start',checked_start)
    monkeypatch.setattr(GenerationTasks,'close',checked_close)
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get('/login').status_code==200
            assert app.state.worker_thread.is_alive()
        assert not app.state.worker_thread.is_alive()
    assert events==['start','close','start','close']


def test_capability_observes_task_capacity_on_lifespan_loop(world,tmp_path,monkeypatch):
    from cn_contract.assistant.task_manager import GenerationTasks
    start,accepting=GenerationTasks.start,GenerationTasks.accepting
    owner=[]
    def recorded_start(manager):
        owner.append(asyncio.get_running_loop())
        return start(manager)
    def checked_accepting(manager):
        assert asyncio.get_running_loop() is owner[-1]
        return accepting.fget(manager)
    monkeypatch.setattr(GenerationTasks,'start',recorded_start)
    monkeypatch.setattr(GenerationTasks,'accepting',property(checked_accepting))
    with boot(world,tmp_path) as http:
        save_draft(http)
        response=http.client.get(http.url+'/generation-capability')
        assert response.status_code==200 and response.json()['state']=='ready'
