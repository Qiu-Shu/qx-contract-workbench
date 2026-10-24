"""Synthetic task transport keeps the existing account and CSRF boundaries."""
from uuid import uuid4
import pytest
from sqlalchemy import text

from test_assistant_routes import chat, native, sign_in, create
from test_assistant_attachment_routes import upload
from test_api import create_case


@pytest.fixture
def synthetic_attachments(tmp_path):
    """Use a dedicated Mock app, without changing a native assisted workspace."""
    from fastapi.testclient import TestClient
    from cn_contract.config import load_settings
    from cn_contract.persistence import Database
    from cn_contract.security import provision_user
    from cn_contract.domain import Role
    from cn_contract.storage_bootstrap import initialize_storage
    from cn_contract.web.app import create_app
    from cn_contract.review.synthetic import select_fixture
    from test_assistant_routes import USERNAME, PASSWORD
    from test_assistant_attachment_routes import MIME
    settings=load_settings();database=Database('sqlite:///'+str(tmp_path/'mock.sqlite'),tmp_path/'store',settings)
    initialize_storage(database)
    with database.session() as db:
        db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'),{'id':str(uuid4())})
        for name in (USERNAME,'另一合成律师'):
            provision_user(name,PASSWORD,{Role.HANDLING_LAWYER},db,local_workbench_password=True)
    app=create_app(settings,database=database,assistant_home_enabled=True)
    _,_,path,raw=select_fixture('sales')
    with TestClient(app) as client:
        headers=sign_in(client);conversation=create(client,headers)
        url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
        value={'request_id':str(uuid4()),'expected_scope':conversation['scope'],
            'original_name':path.name,'mime':MIME,'policy':{'local_processing_accepted':True}}
        yield client,database,headers,url,value,raw,tmp_path


def test_task_routes_authenticate_before_reading_body(chat):
    client, _, _ = chat
    cid = uuid4()
    assert client.post(f'/api/assistant/conversations/{cid}/task-bindings',
                       content='not-json').status_code == 401
    assert client.get(f'/api/assistant/conversations/{cid}/task-drafts').status_code == 401
    assert client.post(f'/api/task-bindings/{uuid4()}/batches', content='not-json').status_code == 401
    assert client.get(f'/api/task-drafts/{uuid4()}').status_code == 401
    assert client.post(f'/api/task-executions/{uuid4()}/cancel').status_code == 401


def test_task_binding_checks_owner_and_csrf(chat):
    client, _, _ = chat
    headers = sign_in(client)
    conversation = create(client, headers)
    base = '/api/assistant/conversations/' + conversation['scope']['conversation_id']
    assert client.post(base + '/task-bindings').status_code == 403
    assert client.post(base + '/task-bindings', headers={**headers, 'Origin':'https://other.invalid'}).status_code == 403
    other = sign_in(client, '另一合成律师')
    assert client.post(base + '/task-bindings', headers=other).status_code == 403
    assert client.get(base + '/task-drafts').status_code == 403


def test_simulated_task_card_is_separate_from_chat_and_shipped(chat):
    client, _, _ = chat
    headers = sign_in(client)
    conversation = create(client, headers)
    page = client.get('/assistant/' + conversation['scope']['conversation_id'])
    assert page.status_code == 200
    assert 'id="task-draft-panel"' in page.text
    assert '模拟合同任务' in page.text
    assert 'id="composer-form"' in page.text
    script = client.get('/static/assistant-tasks.mjs')
    assert script.status_code == 200
    assert script.headers['content-type'].startswith('text/javascript')


def batch(client, headers, binding, event, cursor=0):
    response = client.post('/api/task-bindings/'+binding['id']+'/batches', headers=headers,
        json={'expected_cursor':cursor,'next_cursor':cursor+1,'events':[event]})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('file_first', [True, False])
def test_http_task_survives_both_orders_then_freezes_and_prepares(synthetic_attachments, file_first):
    client, _, headers, url, _, raw, _ = synthetic_attachments
    uploaded = upload(synthetic_attachments).json()['attachment']
    parsed = client.post(url+'/attachments/'+uploaded['id']+'/parses',headers=headers,
        json={'request_id':str(uuid4()),'expected_scope':client.get(url+'/materials').json()['scope']})
    assert parsed.status_code == 200, parsed.text
    binding = client.post(url+'/task-bindings',headers=headers).json()
    media={'media_id':'original','name':uploaded['original_name'],'mime':uploaded['mime'],
        'status':'ready','attachment_id':uploaded['id'],'sha256':uploaded['sha256'],'parse_revision':1}
    events=[{'event_id':'instruction','text':'请核对合成付款约定'}, {'event_id':'file','media':[media]}]
    if file_first:events.reverse()
    first=batch(client,headers,binding,events[0])['drafts'][0]
    assert first['blockers']
    second=batch(client,headers,binding,{**events[1],'task_id':first['id']},1)['drafts'][0]
    assert second['id']==first['id'] and len(second['events'])==2 and not second['blockers']
    path='/api/task-drafts/'+second['id']
    for action,state in [('pause','paused'),('resume','collecting'),('cancel','cancelled'),('resume','collecting')]:
        second=client.patch(path,headers=headers,json={'expected_revision':second['revision'],'action':action}).json()
        assert second['state']==state
    task_rows=client.get('/api/workspace/tasks').json()
    assert any(row['id']==second['id'] and row['kind']=='draft' and row['href'].startswith('/assistant/') for row in task_rows)
    frozen=client.post(path+'/freeze',headers=headers,json={'expected_revision':second['revision'],'manifest_sha256':second['manifest_sha256']})
    assert frozen.status_code==200, frozen.text
    execution=frozen.json()
    assert client.get('/api/task-executions/'+execution['id']).json()==execution
    matter=create_case(client,headers)
    prepare=client.post('/api/task-executions/'+execution['id']+'/prepare',headers=headers,
        json={'matter_id':matter,'request_id':str(uuid4())})
    assert prepare.status_code==200, prepare.text
    assert prepare.json()['state']=='awaiting_facts' and prepare.json()['document_versions']
    assert client.get('/matters/'+matter+'/facts').status_code==200
    assert client.get(url+'/attachments/'+uploaded['id']+'/original').content==raw
    rows=client.get('/api/workspace/tasks').json()
    assert any(row['kind']=='execution' and row['matter_id']==matter and row['href'].endswith('#task-'+second['id']) for row in rows)
    cancel_url='/api/task-executions/'+execution['id']+'/cancel'
    assert client.post(cancel_url).status_code==403
    cancelled=client.post(cancel_url,headers=headers)
    assert cancelled.status_code==200, cancelled.text
    assert cancelled.json()['state']=='blocked' and cancelled.json()['error']=='TASK_CANCELLED'
    assert client.post(cancel_url,headers=headers).json()==cancelled.json()
    assert any(row['id']==execution['id'] and row['stage']=='已取消' for row in client.get('/api/workspace/tasks').json())
    other=sign_in(client,'另一合成律师')
    assert client.get(path).status_code==403
    assert client.post('/api/task-executions/'+execution['id']+'/prepare',headers=other,content='invalid').status_code==403
    assert all(row['id'] not in {second['id'],execution['id']} for row in client.get('/api/workspace/tasks').json())


def test_batch_reauthenticates_after_body_read(chat, monkeypatch):
    from cn_contract.web import task_drafts
    client,database,_=chat
    headers=sign_in(client);conversation=create(client,headers)
    binding=client.post('/api/assistant/conversations/'+conversation['scope']['conversation_id']+'/task-bindings',headers=headers).json()
    original=task_drafts.body_input
    async def revoke(request,model):
        value=await original(request,model)
        with database.session() as db:db.execute(text('UPDATE sessions SET revoked=1'))
        return value
    monkeypatch.setattr(task_drafts,'body_input',revoke)
    response=client.post('/api/task-bindings/'+binding['id']+'/batches',headers=headers,
        json={'expected_cursor':0,'next_cursor':1,'events':[{'event_id':'never','text':'不得保存'}]})
    assert response.status_code==401
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM task_inbox_events'))==0
        assert db.scalar(text('SELECT cursor FROM task_channel_bindings'))==0


def test_pending_media_stays_visible_and_can_be_excluded_with_reason(chat):
    client,_,_=chat;headers=sign_in(client);conversation=create(client,headers)
    url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
    binding=client.post(url+'/task-bindings',headers=headers).json()
    result=batch(client,headers,binding,{'event_id':'pending','text':'合成指令','media':[
        {'media_id':'audio','name':'合成录音.wav','mime':'audio/wav','status':'unsupported'}]})
    draft=result['drafts'][0];path='/api/task-drafts/'+draft['id']
    assert 'media_unsupported' in draft['blockers']
    assert client.post(path+'/freeze',headers=headers,json={'expected_revision':draft['revision'],
        'manifest_sha256':draft['manifest_sha256']}).status_code==409
    response=client.patch(path,headers=headers,json={'expected_revision':draft['revision'],
        'media_resolutions':[{'event_id':draft['events'][0]['id'],'media_id':'audio','action':'exclude','reason':'与本次合成合同无关'}]})
    assert response.status_code==200, response.text
    assert response.json()['events'][0]['media'][0]['status']=='unsupported'
    assert response.json()['media_resolutions'][0]['reason']=='与本次合成合同无关'
    assert 'media_unsupported' not in response.json()['blockers']


def test_workspace_omits_revoked_execution_without_hiding_other_tasks(synthetic_attachments):
    client,database,headers,url,_,_,_=synthetic_attachments
    uploaded=upload(synthetic_attachments).json()['attachment']
    parsed=client.post(url+'/attachments/'+uploaded['id']+'/parses',headers=headers,
        json={'request_id':str(uuid4()),'expected_scope':client.get(url+'/materials').json()['scope']})
    assert parsed.status_code==200
    binding=client.post(url+'/task-bindings',headers=headers).json()
    draft=batch(client,headers,binding,{'event_id':'restricted','text':'已撤权限内容',
        'media':[{'media_id':'file','name':uploaded['original_name'],'mime':uploaded['mime'],'status':'ready',
            'attachment_id':uploaded['id'],'sha256':uploaded['sha256'],'parse_revision':1}]})['drafts'][0]
    execution=client.post('/api/task-drafts/'+draft['id']+'/freeze',headers=headers,
        json={'expected_revision':draft['revision'],'manifest_sha256':draft['manifest_sha256']}).json()
    matter=create_case(client,headers)
    assert client.post('/api/task-executions/'+execution['id']+'/prepare',headers=headers,
        json={'matter_id':matter,'request_id':str(uuid4())}).status_code==200
    visible=batch(client,headers,binding,{'event_id':'visible','text':'仍有权限的任务','start_new':True},1)['drafts'][0]
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'),{'id':matter})
    assert client.get('/api/task-executions/'+execution['id']).status_code==403
    result=client.get('/api/workspace/tasks')
    assert result.status_code==200
    assert any(row['id']==visible['id'] for row in result.json())
    assert execution['id'] not in result.text and '已撤权限内容' not in result.text


@pytest.mark.parametrize('material_mode',['synthetic','local'])
def test_native_task_mock_requires_synthetic_policy_and_keeps_normal_review_blocked(native, material_mode):
    import json
    from fastapi.testclient import TestClient
    from cn_contract.acceptance.assisted_registry import SEED_MANIFEST
    from cn_contract.config import PROJECT_ROOT
    from test_assistant_attachment_routes import MIME
    app,root=native
    assert app.state.purpose=='assisted_draft'
    seed=next(item for item in json.loads(SEED_MANIFEST.read_text('utf-8'))['cases'] if item['contract_type']=='sales')
    path=PROJECT_ROOT/seed['path'];raw=path.read_bytes()
    with TestClient(app) as client:
        headers=sign_in(client);conversation=create(client,headers)
        url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
        value={'request_id':str(uuid4()),'expected_scope':conversation['scope'],'original_name':path.name,'mime':MIME,
            'policy':{'local_processing_accepted':True,'material_mode':material_mode}}
        fixture=(client,app.state.database,headers,url,value,raw,root)
        uploaded=upload(fixture)
        assert uploaded.status_code==201,uploaded.text
        file=uploaded.json()['attachment']
        parsed=client.post(url+'/attachments/'+file['id']+'/parses',headers=headers,
            json={'request_id':str(uuid4()),'expected_scope':client.get(url+'/materials').json()['scope']})
        assert parsed.status_code==200,parsed.text
        binding=client.post(url+'/task-bindings',headers=headers).json()
        draft=batch(client,headers,binding,{'event_id':'native','text':'仅审查独立合成合同','media':[
            {'media_id':'file','name':file['original_name'],'mime':MIME,'status':'ready',
                'attachment_id':file['id'],'sha256':file['sha256'],'parse_revision':1}]})['drafts'][0]
        frozen=client.post('/api/task-drafts/'+draft['id']+'/freeze',headers=headers,
            json={'expected_revision':draft['revision'],'manifest_sha256':draft['manifest_sha256']})
        assert frozen.status_code==200,frozen.text
        execution=frozen.json();base='/api/task-executions/'+execution['id']
        matter=create_case(client,headers)
        prepared=client.post(base+'/prepare',headers=headers,json={'matter_id':matter,'request_id':str(uuid4())})
        if material_mode=='local':
            assert prepared.status_code==409 and prepared.json()['code']=='DATA_POLICY_UNAPPROVED'
            assert not client.get('/api/matters/'+matter).json()['documents']
            return
        assert prepared.status_code==200,prepared.text
        execution=prepared.json();facts=client.get('/api/matters/'+matter+'/facts').json()
        review={'fact_version':facts['version'],'document_hashes':execution['document_versions']}
        assert client.post(base+'/review',headers=headers,json={'request_id':str(uuid4()),'review':review}).status_code==409
        confirmed=client.post('/api/matters/'+matter+'/facts/confirm',headers=headers,
            json={'fact_version':facts['version'],'decisions':[
                {'fact_id':item['id'],'decision':'confirmed','confirmed_value':item['typed_value'],'reason':'核对独立合成原文'} for item in facts['facts']]})
        assert confirmed.status_code==200,confirmed.text
        review['fact_version']=confirmed.json()['version']
        assert client.post('/api/matters/'+matter+'/reviews',headers=headers,json=review).status_code==409
        payload={'request_id':str(uuid4()),'review':review}
        result=client.post(base+'/review',headers=headers,json=payload)
        assert result.status_code==200,result.text
        assert result.json()['state']=='completed'
        assert client.post(base+'/review',headers=headers,json=payload).json()==result.json()
        run=client.get('/api/matters/'+matter+'/reviews/'+result.json()['review_run_id']).json()
        assert run['manifest']['model_provider']=='mock'
        assert len(run['coverage'])==18
        assert client.get('/matters/'+matter+'/review').status_code==200
        assert client.get(url+'/attachments/'+file['id']+'/original').content==raw
        with app.state.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM review_runs'))==1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_runs'))==0


def test_recovery_reads_saved_tasks_but_fences_every_task_write(chat):
    from fastapi.testclient import TestClient
    from cn_contract.ops.storage import RestoreFenceRow
    from cn_contract.web.app import create_app
    from cn_contract.web.recovery import attach_recovery
    from cn_contract.web.local_server import load_seed_policy
    client,database,_=chat;headers=sign_in(client);conversation=create(client,headers)
    url='/api/assistant/conversations/'+conversation['scope']['conversation_id']
    binding=client.post(url+'/task-bindings',headers=headers).json()
    draft=batch(client,headers,binding,{'event_id':'history','text':'只读恢复任务'})['drafts'][0]
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    recovered=create_app(database.settings,database=database,purpose='assisted_draft',assisted_policy=load_seed_policy())
    attach_recovery(recovered,database)
    with TestClient(recovered) as reader:
        auth=sign_in(reader)
        assert reader.get(url+'/task-drafts').status_code==200
        assert reader.get('/api/task-drafts/'+draft['id']).json()['instruction']=='只读恢复任务'
        assert reader.get('/api/task-executions/'+str(uuid4())).status_code==403
        for path in (url+'/task-bindings','/api/task-bindings/'+binding['id']+'/batches',
                     '/api/task-drafts/'+draft['id']+'/freeze','/api/task-executions/'+str(uuid4())+'/cancel'):
            assert reader.post(path,headers=auth).status_code==409
        assert reader.patch('/api/task-drafts/'+draft['id'],headers=auth,json={'action':'resume','expected_revision':draft['revision']}).status_code==409
        assert reader.get('/api/task-drafts/'+draft['id']+'/freeze').status_code==409


def test_recovery_history_page_reads_completed_result_with_current_acl(synthetic_attachments):
    from fastapi.testclient import TestClient
    from cn_contract.ops.storage import RestoreFenceRow
    from cn_contract.web.app import create_app
    from cn_contract.web.recovery import attach_recovery
    from cn_contract.review.storage import read_run
    from cn_contract.security import authenticate,ServiceError
    from uuid import UUID
    client,database,headers,url,_,_,_=synthetic_attachments
    file=upload(synthetic_attachments).json()['attachment']
    assert client.post(url+'/attachments/'+file['id']+'/parses',headers=headers,
        json={'request_id':str(uuid4()),'expected_scope':client.get(url+'/materials').json()['scope']}).status_code==200
    binding=client.post(url+'/task-bindings',headers=headers).json()
    draft=batch(client,headers,binding,{'event_id':'history','text':'历史独立模拟任务','media':[
        {'media_id':'original','name':file['original_name'],'mime':file['mime'],'status':'ready',
            'attachment_id':file['id'],'sha256':file['sha256'],'parse_revision':1}]})['drafts'][0]
    execution=client.post('/api/task-drafts/'+draft['id']+'/freeze',headers=headers,
        json={'expected_revision':draft['revision'],'manifest_sha256':draft['manifest_sha256']}).json()
    matter=create_case(client,headers);base='/api/task-executions/'+execution['id']
    prepared=client.post(base+'/prepare',headers=headers,json={'matter_id':matter,'request_id':str(uuid4())}).json()
    facts=client.get('/api/matters/'+matter+'/facts').json()
    confirmed=client.post('/api/matters/'+matter+'/facts/confirm',headers=headers,
        json={'fact_version':facts['version'],'decisions':[{'fact_id':item['id'],'decision':'confirmed',
            'confirmed_value':item['typed_value'],'reason':'独立合成历史测试确认'} for item in facts['facts']]}).json()
    completed=client.post(base+'/review',headers=headers,json={'request_id':str(uuid4()),
        'review':{'fact_version':confirmed['version'],'document_hashes':prepared['document_versions']}})
    assert completed.status_code==200,completed.text
    result=completed.json();assert result['state']=='completed'
    run=client.get('/api/matters/'+matter+'/reviews/'+result['review_run_id']).json()
    assert client.get('/recovery/task-executions/'+execution['id']).status_code==404
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    recovered=create_app(database.settings,database=database,assistant_home_enabled=True)
    attach_recovery(recovered,database)
    path='/recovery/task-executions/'+execution['id']
    with TestClient(recovered) as reader:
        assert reader.get(path).status_code==401
        auth=sign_in(reader)
        with database.session() as db:
            actor=authenticate(reader.cookies.get('qx_session'),db)
            with pytest.raises(ServiceError) as blocked:
                read_run(UUID(matter),UUID(result['review_run_id']),actor,db=db,current=True)
            assert blocked.value.code=='BLOCKED_LIVE'
        page=reader.get(path)
        assert page.status_code==200,page.text
        assert '历史模拟结果' in page.text and '历史独立模拟任务' in page.text
        assert page.text.count('data-coverage-id=')==18
        assert result['review_run_id'] in page.text and file['sha256'] in page.text
        assert 'href="/assistant/' in page.text and 'href="/recovery/matters/'+matter+'"' in page.text
        assert '<button' not in page.text and '<form' not in page.text
        for finding in run['findings']:assert finding['analysis'] in page.text
        for limitation in run['limitations']:assert limitation in page.text
        assert reader.post(path,headers=auth).status_code==409
        for suffix in ('/review','/prepare','/cancel'):
            assert reader.post(base+suffix,headers=auth,json={}).status_code==409
        sign_in(reader,'另一合成律师')
        assert reader.get(path).status_code==403
        sign_in(reader)
        with database.session() as db:
            db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'),{'id':matter})
        assert reader.get(path).status_code==403
