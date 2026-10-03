"""T10 real TestClient/SQLite checks, never a browser or legal acceptance claim."""
from pathlib import Path
import importlib
import importlib.util
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cn_contract.config import load_settings
from cn_contract.domain import Role
from cn_contract.persistence import Database
from cn_contract.security import provision_user
from cn_contract.review.synthetic import select_fixture
from cn_contract.documents.ingest import DOCX_MIME


def api_module():
    assert importlib.util.find_spec('cn_contract.web.app') is not None, 'T10 requires actual explicit app and routes'
    return importlib.import_module('cn_contract.web.app')


@pytest.fixture
def api(tmp_path):
    # Resolve feature requirements inside test execution, not fixture collection.
    class LazyAPI:
        value = None
        def setup(self):
            if self.value is None:
                module = api_module()
                database = Database('sqlite:///' + str(tmp_path / 'api.db'), tmp_path / 'store', load_settings())
                module.initialize_storage(database)
                with database.session() as db:
                    identities = {}
                    for name, role in [('lawyer', Role.HANDLING_LAWYER), ('reviewer', Role.REVIEWING_LAWYER),
                                       ('assistant', Role.ASSISTANT), ('admin', Role.ADMIN)]:
                        identities[name] = provision_user(name, 'fictional-pass-12345', {role}, db)
                app = module.create_app(load_settings(), database=database)
                self.value = TestClient(app), database, identities, module
                self.value[0].__enter__()
            return self.value
        def __iter__(self): return iter(self.setup())
        def __getitem__(self, key): return self.setup()[key]
    lazy = LazyAPI()
    yield lazy
    if lazy.value:
        lazy.value[0].__exit__(None, None, None)


def sign_in(client, name='lawyer'):
    response = client.post('/api/login', json={'username': name, 'password': 'fictional-pass-12345'})
    assert response.status_code == 200, response.text
    return {'X-CSRF-Token': response.json()['csrf_token']}


def create_case(client, headers, kind='sales', title='独立虚构浏览器合同',reviewer=None):
    position = {'sales': 'buyer', 'service': 'customer', 'lease': 'lessee', 'nda': 'recipient'}[kind]
    response = client.post('/api/matters', headers=headers, json={'title': title, 'contract_type': kind,
        'position': position, 'review_mode': 'pre_sign', 'objectives': ['仅测试材料内审查'],'reviewer_username':reviewer})
    assert response.status_code == 201, response.text
    return response.json()['id']


def upload(client, headers, matter, kind='sales'):
    _, _, path, data = select_fixture(kind)
    response = client.post(f'/api/matters/{matter}/documents', headers={**headers, 'Idempotency-Key': 'upload-'+kind},
        files={'file': (path.name, data, DOCX_MIME)}, data={'baseline_view': 'original'})
    assert response.status_code == 202, response.text
    return response.json()


def work(api, job_id):
    client, database, _, module = api
    module.run_next_job(database)
    response = client.get('/api/jobs/' + job_id)
    assert response.status_code == 200, response.text
    return response.json()


def reviewed_case(api, kind='sales',reviewer=None):
    client, _, _, _ = api
    headers = sign_in(client)
    matter = create_case(client, headers, kind,reviewer=reviewer)
    sent = upload(client, headers, matter, kind)
    status = work(api, sent['job_id'])
    assert status['state'] == 'completed', status
    facts = client.get(f'/api/matters/{matter}/facts').json()
    confirmation = client.post(f'/api/matters/{matter}/facts/confirm', headers=headers,
        json={'fact_version': facts['version'], 'decisions': [{'fact_id': f['id'], 'decision': 'confirmed',
            'confirmed_value': f['typed_value'], 'reason': '实际核对独立虚构原文'} for f in facts['facts']]})
    assert confirmation.status_code == 200, confirmation.text
    response = client.post(f'/api/matters/{matter}/reviews', headers={**headers, 'Idempotency-Key': 'review-'+kind},
        json={'fact_version': confirmation.json()['version'], 'document_hashes': {sent['version_id']: sent['sha256']}})
    assert response.status_code == 202, response.text
    status = work(api, response.json()['job_id'])
    assert status['state'] == 'completed', status
    run_id = status['result_ref']
    run = client.get(f'/api/matters/{matter}/reviews/{run_id}')
    assert run.status_code == 200, run.text
    return matter, run.json(), headers, sent


def test_app_import_and_construction_do_not_start_worker_or_provision_users(api):
    client, database, ids, _ = api
    assert client.get('/api/matters').status_code == 401
    assert len(ids) == 4 and not getattr(client.app.state, 'worker_thread', None)


def test_cookie_login_csrf_no_store_and_same_origin(api):
    client, _, _, _ = api
    headers = sign_in(client)
    assert 'HttpOnly' in client.post('/api/login', json={'username':'lawyer','password':'fictional-pass-12345'}).headers['set-cookie']
    assert client.post('/api/matters', json={'title':'虚构','contract_type':'sales','position':'buyer','review_mode':'pre_sign','objectives':['测试']}).status_code == 403
    assert client.post('/api/logout', headers={**headers,'Origin':'https://untrusted.invalid'}).status_code == 403
    assert client.get('/').headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('name', ['assistant', 'admin'])
def test_create_requires_actual_lawyer_role(api, name):
    client, _, _, _ = api
    headers = sign_in(client, name)
    response = client.post('/api/matters', headers=headers, json={'title':'虚构','contract_type':'sales','position':'buyer','review_mode':'pre_sign','objectives':['测试']})
    assert response.status_code == 403


def test_raw_real_or_unregistered_upload_blocked_before_original(api):
    client, database, _, _ = api
    headers = sign_in(client); matter = create_case(client, headers)
    response = client.post(f'/api/matters/{matter}/documents', headers=headers,
        files={'file':('sales_basic.docx',b'not-a-registered-synthetic-file',DOCX_MIME)}, data={'baseline_view':'original','synthetic':'true'})
    assert response.status_code == 409 and response.json()['code'] == 'DATA_POLICY_UNAPPROVED'
    assert not list(database.storage_root.glob('*/*/original.bin'))
    from sqlalchemy import select,func
    from cn_contract.persistence import DocumentRow
    from cn_contract.web.storage import JobRow
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(DocumentRow).where(DocumentRow.matter_id==matter))==0
        assert db.scalar(select(func.count()).select_from(JobRow).where(JobRow.matter_id==matter))==0


def test_idempotent_upload_one_original_conflicting_bytes(api):
    client, database, _, _ = api
    headers = sign_in(client); matter = create_case(client, headers)
    first = upload(client, headers, matter); second = upload(client, headers, matter)
    assert first == second
    _, _, path, data = select_fixture('service')
    response = client.post(f'/api/matters/{matter}/documents', headers={**headers,'Idempotency-Key':'upload-sales'},
        files={'file':(path.name,data,DOCX_MIME)},data={'baseline_view':'original'})
    assert response.status_code == 409
    assert len(list(database.storage_root.glob('*/*/original.bin'))) == 1


def test_cross_case_job_version_and_admin_do_not_reveal(api):
    client, _, _, _ = api
    headers = sign_in(client); matter = create_case(client, headers); sent = upload(client, headers, matter)
    sign_in(client, 'admin')
    assert client.get(f'/api/matters/{matter}').status_code == 403
    assert client.get('/api/jobs/'+sent['job_id']).status_code == 403
    assert client.get('/api/jobs/'+str(uuid4())).status_code == 403
    assert client.get('/api/matters').json() == []


@pytest.mark.parametrize('decision', ['accept','edit','reject','request_info','refer'])
def test_decisions_append_server_identity_and_preserve_original(api, decision):
    client, database, ids, _ = api
    matter, run, headers, sent = reviewed_case(api)
    finding = run['findings'][0]
    response = client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision', headers=headers,
        json={'run_id':run['id'],'decision':decision,'reason':'独立虚构人工核对','run_sha256':run['run_sha256']})
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved['decision']['actor_id'] == str(ids['lawyer']) and saved['decision']['decision'] == decision
    assert client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()['findings'][0]['human_decision'] is None
    assert len(list(database.storage_root.glob('*/*/original.bin'))) == 1


def test_mock_cannot_sign_and_qcc_off_review_continues(api):
    client, _, _, _ = api
    matter, run, headers, _ = reviewed_case(api,reviewer='reviewer')
    assert len(run['coverage']) == 18 and run['manifest']['model_provider'] == 'mock'
    assert client.get(f'/api/matters/{matter}/query-status').json()['enabled'] is False
    preview = client.post(f'/api/matters/{matter}/exports/preview', headers=headers,
        json={'run_id':run['id'],'audience':'internal','patch_ids':[],'run_sha256':run['run_sha256']})
    assert preview.status_code == 201, preview.text
    bundle = preview.json()
    # Real mock cannot be issued even by this case's reviewing can_sign member.
    from cn_contract.security import set_membership
    with api[1].session() as db:
        set_membership(__import__('uuid').UUID(matter), api[2]['reviewer'], db, can_sign=True)
    headers = sign_in(client, 'reviewer')
    response = client.post(f'/api/matters/{matter}/approvals', headers=headers,
        json={'bundle_id':bundle['id'],'artifact_manifest_hash':bundle['manifest_sha256'],'review_snapshot_hash':run['run_sha256'],'scope':'internal'})
    assert response.status_code == 403 and response.json()['code'] == 'BLOCKED_LIVE'


def test_restart_running_jobs_blocked_never_auto_resend(api):
    client, database, _, module = api
    headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter)
    module.claim_next_job(database)
    assert client.get('/api/jobs/'+sent['job_id']).json()['state']=='running'
    assert module.recover_jobs(database)==1
    assert client.get('/api/jobs/'+sent['job_id']).json()['state']=='blocked'
    assert module.run_next_job(database) is None


def test_revoked_actor_worker_cannot_parse_or_write_candidates(api):
    client,database,_,module=api
    headers=sign_in(client);matter=create_case(client,headers);sent=upload(client,headers,matter)
    client.post('/api/logout',headers=headers)
    module.run_next_job(database)
    headers=sign_in(client)
    status=client.get('/api/jobs/'+sent['job_id']).json()
    assert status['state']=='blocked' and status['error_code']=='AUTHORIZATION_REQUIRED'
    assert client.get(f'/api/matters/{matter}/facts').status_code==409


def test_six_pages_escape_untrusted_title_and_no_external_resources(api):
    client,_,_,_=api
    headers=sign_in(client);matter=create_case(client,headers,title='<script>window.syntheticAttack=1</script>')
    for path in ['/',f'/matters/{matter}',f'/matters/{matter}/facts',f'/matters/{matter}/review',f'/matters/{matter}/queries',f'/matters/{matter}/exports']:
        response=client.get(path)
        assert response.status_code==200 and '<script>window.syntheticAttack' not in response.text
        assert 'https://' not in response.text and 'http://' not in response.text
