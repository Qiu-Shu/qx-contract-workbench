"""Actual persisted review failures and public JobInput replay, API-only."""
from uuid import UUID
import pytest
from sqlalchemy import select,func

from tests.integration.test_api import api,sign_in,create_case,upload,work,reviewed_case


def test_invalid_sealed_mock_output_leaves_failed_job_and_durable_attempts(api,monkeypatch):
    client,database,_,module=api
    headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter)
    assert work(api,sent['job_id'])['state']=='completed'
    facts=client.get(f'/api/matters/{matter}/facts').json()
    confirmation=client.post(f'/api/matters/{matter}/facts/confirm',headers=headers,json={
        'fact_version':facts['version'],'decisions':[{'fact_id':f['id'],'decision':'confirmed',
        'confirmed_value':f['typed_value'],'reason':'独立虚构原文核对'} for f in facts['facts']]})
    assert confirmation.status_code==200
    from cn_contract.web import services
    from cn_contract.review.model_adapter import MockProvider
    # Server-owned instance remains the real sealed T06 provider; requests do
    # not choose a provider or replace its dispatch/validation/storage code.
    monkeypatch.setattr(services,'MockProvider',lambda:MockProvider(raw_outputs=('{broken','{broken')))
    queued=client.post(f'/api/matters/{matter}/reviews',headers={**headers,'Idempotency-Key':'failed-review'},json={
        'fact_version':confirmation.json()['version'],'document_hashes':{sent['version_id']:sent['sha256']}})
    assert queued.status_code==202
    status=work(api,queued.json()['job_id'])
    assert status['state']=='failed',status
    assert status['error_code']=='MODEL_OUTPUT_INVALID' and status['result_ref']
    run=client.get(f'/api/matters/{matter}/reviews/{status["result_ref"]}')
    assert run.status_code==200 and run.json()['status']=='failed'
    assert len(run.json()['model_usage'])==2
    from cn_contract.review.storage import ModelAttemptRow
    with database.session() as db:
        attempts=list(db.scalars(select(ModelAttemptRow).where(ModelAttemptRow.run_id==status['result_ref'])))
        assert len(attempts)==2 and all(a.raw=='{broken' for a in attempts)


def test_public_review_job_completed_replay_revalidates_current_run(api):
    client,database,_,module=api
    matter,run,headers,sent=reviewed_case(api)
    from cn_contract.domain import JobInput
    from cn_contract.security import authenticate,ServiceError
    from cn_contract.persistence import set_position
    from cn_contract.web.storage import sha,JobRow
    from cn_contract.review.storage import ReviewRunRow
    payload={'fact_version':client.get(f'/api/matters/{matter}/facts').json()['version'],
        'document_hashes':{sent['version_id']:sent['sha256']}}
    value=JobInput(matter_id=matter,job_type='review',parameters_sha256=sha(payload))
    with database.session() as db:actor=authenticate(client.cookies.get('qx_session'),db)
    replay=module.start_job(value,actor,database=database,parameters=payload,idempotency_key='review-sales')
    assert replay.state=='completed' and replay.result_ref==run['id']
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(ReviewRunRow))==1
        assert db.scalar(select(func.count()).select_from(JobRow).where(JobRow.kind=='review'))==1
        set_position(UUID(matter),'seller',actor,db)
    with pytest.raises(ServiceError) as error:
        module.start_job(value,actor,database=database,parameters=payload,idempotency_key='review-sales')
    assert error.value.code in {'VERSION_CONFLICT','APPROVAL_STALE'}


def test_http_completed_review_replay_rechecks_changed_rule_evidence(api):
    client,database,_,_=api
    matter,run,headers,sent=reviewed_case(api)
    payload={'fact_version':client.get(f'/api/matters/{matter}/facts').json()['version'],
        'document_hashes':{sent['version_id']:sent['sha256']}}
    from cn_contract.security import authenticate
    from cn_contract.web.storage import fingerprint,now
    from cn_contract.rules.storage import RuleSnapshotRow,RuleInvalidationRow
    with database.session() as db:
        actor=authenticate(client.cookies.get('qx_session'),db)
        old=fingerprint(UUID(matter),actor,db)
        rule=db.scalar(select(RuleSnapshotRow).where(RuleSnapshotRow.matter_id==matter))
        # Technical server-state fixture appends actual protected rule evidence;
        # it claims neither real law approval nor an end-user UI workflow.
        db.add(RuleInvalidationRow(matter_id=matter,rule_id=rule.rule_id,version=rule.version,
            timestamp=now(),reason='synthetic-review-recheck'))
    with database.session() as db:assert fingerprint(UUID(matter),actor,db)==old
    replay=client.post(f'/api/matters/{matter}/reviews',headers={**headers,'Idempotency-Key':'review-sales'},json=payload)
    assert replay.status_code==409,replay.text
    assert client.get(f'/api/matters/{matter}/reviews/{run["id"]}').status_code==409
