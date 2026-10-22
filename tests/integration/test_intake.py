"""Independent fictional consultations; exercise real authenticated HTTP/SQLite."""
from io import BytesIO
import json
from uuid import uuid4

from docx import Document
import pytest
from sqlalchemy import text

from tests.integration.test_api import api, sign_in


def draft(**changes):
    return dict(title='合成买卖咨询', contact='合成联系人，不外发', consultation='原话：对方未交货',
        questions=['何时约定交货'], materials=[{'name':'交货约定', 'state':'needed'}],
        follow_up_at='2026-10-20T02:00:00Z', follow_up_note='合成跟进', status='open',
        client_reply='请补充交货约定。', internal_notes='INTERNAL_ONLY：需核对时效', **changes)


def create(client, headers, value=None, request_id=None):
    result = client.post('/api/intakes', headers=headers,
        json={'request_id':request_id or str(uuid4()), 'draft':value or draft()})
    assert result.status_code == 201, result.text
    return result.json()


def conversion(revision=1):
    return {'expected_revision':revision, 'matter':{'title':'合成接待转合同', 'contract_type':'sales',
        'position':'buyer', 'review_mode':'pre_sign', 'objectives':['仅核对合成材料']}}


def test_roundtrip_history_conflict_and_immutable_snapshot(api):
    client, database, _, _ = api
    headers = sign_in(client)
    first = create(client, headers)
    url = '/api/intakes/' + first['id']
    second = client.put(url, headers=headers, json={'expected_revision':1,
        'draft':{**draft(), 'client_reply':'第二版回复', 'status':'waiting'}})
    assert second.status_code == 200, second.text
    assert second.json()['revision'] == 2
    assert client.get(url + '/revisions/1').json()['client_reply'] == draft()['client_reply']
    assert client.get(url).json()['status'] == 'waiting'
    assert client.put(url, headers=headers, json={'expected_revision':1,'draft':draft()}).status_code == 409
    assert client.get(url + '/revisions/1').json()['internal_notes'].startswith('INTERNAL_ONLY')
    with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
        with database.session() as db:
            db.execute(text('UPDATE intake_revisions SET client_reply = :value'), {'value':'wrong'})


@pytest.mark.parametrize('name', ['reviewer','assistant','admin'])
def test_other_identity_cannot_access_or_export_or_convert(api, name):
    client, _, _, _ = api
    first = create(client, sign_in(client))
    headers = sign_in(client, name)
    url = '/api/intakes/' + first['id']
    assert client.get('/api/intakes').json()['items'] == []
    for path in (url, url+'/revisions/1', '/intakes/'+first['id']):
        assert client.get(path).status_code == 403
    assert client.put(url, headers=headers, json={'expected_revision':1,'draft':draft()}).status_code == 403
    assert client.post(url+'/convert', headers=headers, json=conversion()).status_code == 403
    assert client.post(url+'/export', headers=headers,
        json={'revision':1,'audience':'client','text_checked':True}).status_code == 403


def test_csrf_origin_roles_unknown_fields_and_login(api):
    client, _, _, _ = api
    assert client.get('/api/intakes').status_code == 401
    headers = sign_in(client)
    data={'request_id':str(uuid4()),'draft':draft()}
    assert client.post('/api/intakes', json=data).status_code == 403
    assert client.post('/api/intakes', json=data, headers={**headers,'Origin':'https://evil.invalid'}).status_code == 403
    assert client.post('/api/intakes', json={**data,'owner_id':str(uuid4())},headers=headers).status_code == 422
    for name in ('assistant','admin'):
        headers = sign_in(client,name)
        assert client.post('/api/intakes',json=data,headers=headers).status_code == 403


def test_creation_replay_and_payload_conflict(api):
    client, _, _, _ = api
    headers=sign_in(client); key=str(uuid4())
    first=create(client,headers,request_id=key)
    assert create(client,headers,request_id=key)['id'] == first['id']
    assert client.post('/api/intakes',headers=headers,json={'request_id':key,
        'draft':{**draft(),'title':'different'}}).status_code == 409
    assert len(client.get('/api/intakes').json()['items']) == 1


def test_export_only_explicit_current_audience(api):
    client, _, _, _ = api
    headers=sign_in(client); first=create(client,headers)
    url='/api/intakes/'+first['id']+'/export'
    for audience in ('client','internal'):
        result=client.post(url,headers=headers,json={'revision':1,'audience':audience,'text_checked':True})
        assert result.status_code == 200, result.text
        document=Document(BytesIO(result.content))
        content='\n'.join(p.text for p in document.paragraphs)
        if audience=='client':
            assert draft()['client_reply'] in content
            for forbidden in ('INTERNAL_ONLY', draft()['consultation'], draft()['contact'], draft()['title']):
                assert forbidden not in content
        else:
            assert 'INTERNAL_ONLY' in content and draft()['client_reply'] not in content
        assert '草稿' in content and '第 1 版' in content
    assert client.post(url,headers=headers,json={'revision':1,'audience':'client','text_checked':False}).status_code == 409
    assert client.post(url,headers=headers,json={'revision':2,'audience':'internal','text_checked':True}).status_code == 409
    assert client.post(url,headers=headers,json={'revision':1,'audience':'all','text_checked':True}).status_code == 422


def test_conversion_atomic_replay_and_membership_revocation(api):
    client, database, _, _ = api
    headers=sign_in(client); first=create(client,headers)
    url='/api/intakes/'+first['id']; value=conversion()
    converted=client.post(url+'/convert',headers=headers,json=value)
    assert converted.status_code == 200, converted.text
    mid=converted.json()['matter_id']
    assert client.post(url+'/convert',headers=headers,json=value).json()['matter_id'] == mid
    assert len(client.get('/api/matters').json()) == 1
    assert client.get(url).json()['revision'] == 1
    assert client.put(url,headers=headers,json={'expected_revision':1,'draft':draft()}).status_code == 409
    assert client.post(url+'/convert',headers=headers,json=conversion(2)).status_code == 409
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'),{'id':mid})
    assert client.get(url).status_code == 403
    assert client.post(url+'/convert',headers=headers,json=value).status_code == 403


def test_conversion_service_failure_rolls_back_created_matter(api, monkeypatch):
    client,database,_,_=api
    headers=sign_in(client); first=create(client,headers)
    from cn_contract import matters
    original=matters.create_matter
    def fail(value,actor,db):
        original(value,actor,db)
        from cn_contract.security import ServiceError
        raise ServiceError('STATE_CONFLICT',409)
    monkeypatch.setattr(matters,'create_matter',fail)
    result=client.post('/api/intakes/'+first['id']+'/convert',headers=headers,json=conversion())
    assert result.status_code==409
    assert client.get('/api/matters').json()==[]
    assert client.get('/api/intakes/'+first['id']).json()['matter_id'] is None


def test_closed_and_local_disabled_cannot_convert(api):
    client,_,_,_=api; headers=sign_in(client)
    first=create(client,headers,value={**draft(),'status':'closed'})
    assert client.post('/api/intakes/'+first['id']+'/convert',headers=headers,json=conversion()).status_code==409
    second=create(client,headers)
    value=conversion();value['matter']['material_mode']='local'
    assert client.post('/api/intakes/'+second['id']+'/convert',headers=headers,json=value).status_code==409


def test_limits_and_xml_controls_rejected(api):
    client,_,_,_=api;headers=sign_in(client)
    for change in ({'client_reply':'bad\x00data'}, {'questions':['x']*31},
                   {'follow_up_at':'2026-10-20T10:00:00'}, {'internal_notes':'x'*12001}):
        result=client.post('/api/intakes',headers=headers,
            json={'request_id':str(uuid4()),'draft':{**draft(),**change}})
        assert result.status_code==422, result.text


def test_page_escape_and_two_simultaneous_conversion_requests(api):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    client,_,_,_=api;headers=sign_in(client)
    first=create(client,headers,value={**draft(),'title':'<script>window.leak=1</script>'})
    page=client.get('/intakes/'+first['id'])
    assert page.status_code==200
    assert '<script>window.leak=1</script>' not in page.text
    assert '&lt;script&gt;' in page.text
    def convert_once(_):
        other=TestClient(client.app);other.cookies.update(client.cookies)
        return other.post('/api/intakes/'+first['id']+'/convert',headers=headers,json=conversion())
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(convert_once,range(2)))
    assert [r.status_code for r in responses]==[200,200]
    assert len({r.json()['matter_id'] for r in responses})==1
    assert len(client.get('/api/matters').json())==1


def test_task_overview_respects_role_revocation_with_membership_retained(api):
    from tests.integration.test_api import create_case, upload
    from cn_contract.persistence import UserRow
    client,database,ids,_=api;headers=sign_in(client)
    matter=create_case(client,headers,title='合成权限隔离标题');upload(client,headers,matter)
    assert client.get('/api/workspace/tasks').json()[0]['matter_id']==matter
    with database.session() as db:
        db.get(UserRow,str(ids['lawyer'])).roles=json.dumps(['admin'])
    assert client.get('/api/matters/'+matter).status_code==403
    assert client.get('/api/workspace/tasks').json()==[]
