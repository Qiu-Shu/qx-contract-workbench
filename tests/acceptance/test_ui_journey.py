"""API-driven four-type journey. Actual browser evidence belongs to parent QA."""
import pytest
from tests.integration.test_api import api, reviewed_case


@pytest.mark.parametrize('kind',['sales','service','lease','nda'])
def test_four_types_journey(api,kind):
    client,_,_,_=api
    matter,run,headers,sent=reviewed_case(api,kind)
    assert len(run['coverage'])==18
    finding=next(f for f in run['findings'] if f['severity']!='high')
    decision=client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision',headers=headers,
        json={'run_id':run['id'],'run_sha256':run['run_sha256'],'decision':'edit','reason':'虚构数据人工核对后拟订草案'})
    assert decision.status_code==201,decision.text
    anchors=client.get(f'/api/matters/{matter}/documents/{sent["version_id"]}/anchors').json()['anchors']
    anchor=next(a for a in anchors if a['id'] in finding['anchor_ids']+finding['cross_anchor_ids'])
    patch=client.post(f'/api/matters/{matter}/patches/approve',headers=headers,json={
        'run_id':run['id'],'run_sha256':run['run_sha256'],'finding_id':finding['id'],'anchor_id':anchor['id'],
        'new_text':'虚构测试：由双方书面确认具体安排。','reason':'已核对整段原文','audiences':['internal','client','counterparty']})
    assert patch.status_code==201,patch.text
    for audience in ['internal','client','counterparty']:
        response=client.post(f'/api/matters/{matter}/exports/preview',headers=headers,json={
            'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':audience,'patch_ids':[patch.json()['id']]})
        assert response.status_code==201,response.text
        for artifact in response.json()['artifacts']:
            download=client.get(f'/api/matters/{matter}/exports/{artifact["id"]}/download')
            assert download.status_code==200 and download.content.startswith(b'PK')
        assert response.json()['draft'] is True
