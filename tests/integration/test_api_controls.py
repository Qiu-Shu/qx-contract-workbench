"""Additional actual authorization, same-key replay and queue controls."""
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func

from tests.integration.test_api import api,sign_in,create_case,upload,work,reviewed_case


@pytest.mark.parametrize('content_type,body',[('application/json',b'{"private":"synthetic-canary"'),('multipart/form-data; boundary=none',b'synthetic-secret')])
def test_unauthenticated_malformed_payload_never_echoed(api,content_type,body):
    client,_,_,_=api
    response=client.post('/api/matters/'+str(uuid4())+'/documents',content=body,headers={'Content-Type':content_type})
    assert response.status_code==401 and 'synthetic-' not in response.text
    assert set(response.json())=={'code','message','correlation_id','retryable'}


@pytest.mark.parametrize('name',['assistant','admin'])
def test_creation_role_is_checked_before_reading_invalid_body(api,name):
    client,_,_,_=api;headers=sign_in(client,name)
    response=client.post('/api/matters',headers={**headers,'Content-Type':'application/json'},content=b'{synthetic-canary')
    assert response.status_code==403 and 'synthetic-canary' not in response.text


def test_authorized_bad_multipart_has_controlled_fixed_error(api):
    client,_,_,_=api;headers=sign_in(client);matter=create_case(client,headers)
    response=client.post(f'/api/matters/{matter}/documents',headers={**headers,'Content-Type':'multipart/form-data'},content=b'canary-no-boundary')
    assert response.status_code==400 and set(response.json())=={'code','message','correlation_id','retryable'}


def test_explicit_building_key_replays_once_and_changed_payload_conflicts(api):
    client,database,_,_=api;headers=sign_in(client)
    body={'title':'虚构幂等','contract_type':'sales','position':'buyer','review_mode':'pre_sign','objectives':['测试']}
    sent={**headers,'Idempotency-Key':'create-1'}
    first=client.post('/api/matters',headers=sent,json=body);second=client.post('/api/matters',headers=sent,json=body)
    assert first.status_code==201 and first.json()==second.json()
    assert client.post('/api/matters',headers=sent,json={**body,'title':'变更'}).status_code==409
    from cn_contract.persistence import MatterRow
    with database.session() as db:assert db.scalar(select(func.count()).select_from(MatterRow))==1


def test_facts_idempotent_explicit_key_advances_one_snapshot(api):
    client,_,_,_=api;headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter);work(api,sent['job_id'])
    facts=client.get(f'/api/matters/{matter}/facts').json()
    body={'fact_version':facts['version'],'decisions':[{'fact_id':f['id'],'decision':'confirmed','confirmed_value':f['typed_value'],'reason':'虚构核对'} for f in facts['facts']]}
    sent={**headers,'Idempotency-Key':'facts-1'}
    first=client.post(f'/api/matters/{matter}/facts/confirm',headers=sent,json=body)
    second=client.post(f'/api/matters/{matter}/facts/confirm',headers=sent,json=body)
    assert first.status_code==200 and second.json()==first.json()
    assert client.get(f'/api/matters/{matter}/facts').json()['version']==facts['version']+1


def test_decision_preview_and_patch_replay_once_current_authorization(api):
    client,database,ids,_=api;matter,run,headers,sent=reviewed_case(api)
    finding=next(f for f in run['findings'] if f['severity']!='high')
    body={'run_id':run['id'],'run_sha256':run['run_sha256'],'decision':'edit','reason':'虚构核对'}
    h={**headers,'Idempotency-Key':'decision-1'};path=f'/api/matters/{matter}/findings/{finding["id"]}/decision'
    first=client.post(path,headers=h,json=body);second=client.post(path,headers=h,json=body)
    assert first.status_code==201 and second.json()==first.json()
    assert client.post(path,headers=h,json={**body,'decision':'reject'}).status_code==409
    anchors=client.get(f'/api/matters/{matter}/documents/{sent["version_id"]}/anchors').json()['anchors']
    anchor=next(a for a in anchors if a['id'] in finding['anchor_ids']+finding['cross_anchor_ids'])
    patchbody={'run_id':run['id'],'run_sha256':run['run_sha256'],'finding_id':finding['id'],'anchor_id':anchor['id'],
        'new_text':'独立虚构精确替换','reason':'已核对虚构原文','audiences':['internal']}
    h={**headers,'Idempotency-Key':'patch-1'};path=f'/api/matters/{matter}/patches/approve'
    first=client.post(path,headers=h,json=patchbody);second=client.post(path,headers=h,json=patchbody)
    assert first.status_code==201 and second.json()==first.json()
    previewbody={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'internal','patch_ids':[first.json()['id']]}
    h={**headers,'Idempotency-Key':'preview-1'};path=f'/api/matters/{matter}/exports/preview'
    first=client.post(path,headers=h,json=previewbody);second=client.post(path,headers=h,json=previewbody)
    assert first.status_code==201 and second.json()==first.json()
    assert len(list(database.storage_root.glob('derived_exports/*.docx')))>0
    from cn_contract.security import remove_membership
    with database.session() as db:remove_membership(UUID(matter),ids['lawyer'],db)
    assert client.post(path,headers=h,json=previewbody).status_code==403


def test_q0_plan_through_http_job_has_zero_fee_and_calls(api):
    client,database,_,module=api;headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter);work(api,sent['job_id'])
    candidates=client.post(f'/api/matters/{matter}/parties/candidates',headers=headers)
    assert candidates.status_code==200,candidates.text
    party=candidates.json()[0]
    response=client.post(f'/api/matters/{matter}/parties/select',headers=headers,json={'party_id':party['id'],
        'candidate_id':party['candidate_evidence'][0]['candidate_id'],'reason':'仅确认虚构原文主体'})
    assert response.status_code==200,response.text
    response=client.post(f'/api/matters/{matter}/query-plans',headers=headers,json={
        'matter_id':matter,'party_id':party['id'],'purpose':'仅Q0关闭计划','items':[],'authorization_id':None,'scope':'Q0'})
    assert response.status_code==201,response.text
    plan=response.json()
    response=client.post(f'/api/matters/{matter}/query-plans/{plan["id"]}/approve',headers=headers,json={'plan_sha256':plan['plan_sha256']})
    assert response.status_code==200,response.text
    response=client.post(f'/api/matters/{matter}/query-plans/{plan["id"]}/execute',headers={**headers,'Idempotency-Key':'q0-1'},json={'plan_sha256':plan['plan_sha256']})
    assert response.status_code==202,response.text
    status=work(api,response.json()['job_id']);assert status['state']=='completed',status
    from cn_contract.queries.storage import QueryLedgerRow
    with database.session() as db:assert db.scalar(select(func.count()).select_from(QueryLedgerRow))==0


def test_no_budget_approval_is_fabricated_and_assets_no_untrusted_safe(api):
    client,_,_,_=api;headers=sign_in(client);matter=create_case(client,headers)
    budget=client.get(f'/api/matters/{matter}/query-status')
    assert budget.status_code==200 and budget.json()['budget']['approved'] is False
    assert budget.json()['budget']['case_limit']=='20'
    assert client.get('/static/workbench.js').status_code==200
    assert client.get('/static/original.bin').status_code==404
    assert client.app.state.template_environment.autoescape is True


def test_public_job_service_requires_real_actor_and_exact_parameter_hash(api):
    client,database,_,module=api
    assert callable(getattr(module,'start_job',None)), 'T10 public JobInput adapter must exist'
    from cn_contract.domain import JobInput
    from cn_contract.security import authenticate,ServiceError
    from cn_contract.web.storage import sha
    headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter)
    with database.session() as db:actor=authenticate(client.cookies.get('qx_session'),db)
    payload={'version_id':sent['version_id']}
    value=JobInput(matter_id=matter,job_type='parse',parameters_sha256=sha(payload))
    status=module.start_job(value,actor,database=database,parameters=payload,idempotency_key='explicit-service-job')
    assert status.state=='queued'
    assert module.start_job(value,actor,database=database,parameters=payload,idempotency_key='explicit-service-job').id==status.id
    with pytest.raises(ServiceError):
        module.start_job(value,actor,database=database,parameters={'version_id':str(uuid4())},idempotency_key='explicit-service-bad')
