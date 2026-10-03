"""Actual HTTP -> durable queue -> exact Factory -> installed localhost SDK."""
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from cn_contract.config import load_settings
from cn_contract.domain import Position
from cn_contract.web.app import create_app,initialize_storage,run_next_job,recover_jobs
from cn_contract.queries import storage as query_storage
from cn_contract.persistence import set_position
from tests.helpers.synthetic_queries import setup,bind_loopback
from tests.helpers.synthetic_qcc import sdk_server


@pytest.mark.parametrize('mode',['default_off','success','failed','unknown','material_changed'])
def test_http_factory_uses_closed_transactions_and_persists_unknown(tmp_path,mode):
    world=setup(tmp_path,price='0');database,owner,lawyer,matter,party,_=world
    writes=[]
    with sdk_server() as (cfg,counts,server):
        server.remove_tool('synthetic_identity')
        def identity(name:str,page:int=1)->dict[str,str|bool|int]:
            counts['call']+=1
            # A different DB connection must actually write while SDK is active.
            with database.session() as db:
                query_storage.append('diagnostic','T10-network-unlocked',{'synthetic':True},lawyer.user_id,matter.id,db)
                if mode=='material_changed':set_position(matter.id,Position.SELLER if matter.position!=Position.SELLER else Position.BUYER,lawyer,db)
            writes.append(True)
            return {'synthetic':True,'state':'unknown' if mode=='unknown' else 'failed' if mode=='failed' else 'success','pages_complete':False,'page':page}
        server.add_tool(identity,name='synthetic_identity',structured_output=True)
        world=bind_loopback(world,cfg)
        initialize_storage(database)
        app=create_app(load_settings(),database=database,
            synthetic_loopback_endpoints=() if mode=='default_off' else {cfg.endpoint})
        with TestClient(app) as client:
            login=client.post('/api/login',json={'username':'query-lawyer','password':'local-test-password'})
            assert login.status_code==200,login.text
            h={'X-CSRF-Token':login.json()['csrf_token']}
            created=client.post(f'/api/matters/{matter.id}/query-plans',headers=h,json={'matter_id':str(matter.id),
                'party_id':str(party.id),'purpose':'独立虚构T10 SDK技术核对','items':[{'capability_key':'synthetic.identity','pages':1}],
                'authorization_id':None,'scope':'Q1'})
            assert created.status_code==201,created.text
            plan=created.json()
            approval=client.post(f'/api/matters/{matter.id}/query-plans/{plan["id"]}/approve',headers=h,json={'plan_sha256':plan['plan_sha256']})
            assert approval.status_code==200,approval.text
            path=f'/api/matters/{matter.id}/query-plans/{plan["id"]}/execute'
            queued=client.post(path,headers={**h,'Idempotency-Key':'actual-sdk-1'},json={'plan_sha256':plan['plan_sha256']})
            if mode=='default_off':
                assert queued.status_code==409 and queued.json()['code']=='BLOCKED_LIVE'
                assert counts['call']==0 and not writes
                return
            assert queued.status_code==202,queued.text
            job_id=queued.json()['job_id'];run_next_job(database)
            result=client.get('/api/jobs/'+job_id).json()
            assert writes==[True] and counts['call']==1
            if mode=='success':assert result['state']=='completed',result
            elif mode=='failed':assert result['state']=='failed',result
            else:assert result['state']=='blocked',result
            with database.session() as db:
                rows=list(db.scalars(select(query_storage.QueryLedgerRow).where(query_storage.QueryLedgerRow.matter_id==str(matter.id))))
                assert len(rows)==1
                if mode=='unknown':assert 'sent_unknown' in rows[0].payload
                else:assert 'confirmed' in rows[0].payload
            recover_jobs(database)
            assert run_next_job(database) is None and counts['call']==1
            if mode=='unknown':
                again=client.post(path,headers={**h,'Idempotency-Key':'new-job-same-plan'},json={'plan_sha256':plan['plan_sha256']})
                assert again.status_code==202,again.text
                run_next_job(database)
                assert client.get('/api/jobs/'+again.json()['job_id']).json()['state']=='blocked'
                assert counts['call']==1
