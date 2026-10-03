"""Independent T10 replay defect regression: T09 approval revocation still wins."""
from uuid import UUID
import pytest
from sqlalchemy import select,func
from tests.integration.test_api import api,reviewed_case


@pytest.mark.parametrize('action',['patch','preview'])
def test_revoked_patch_cannot_be_resurrected_by_idempotent_http_replay(api,action):
    client,database,_,_=api;matter,run,headers,sent=reviewed_case(api)
    finding=next(f for f in run['findings'] if f['severity']!='high')
    anchors=client.get(f'/api/matters/{matter}/documents/{sent["version_id"]}/anchors').json()['anchors']
    anchor=next(a for a in anchors if a['id'] in finding['anchor_ids']+finding['cross_anchor_ids'])
    body={'run_id':run['id'],'run_sha256':run['run_sha256'],'finding_id':finding['id'],'anchor_id':anchor['id'],
        'new_text':'独立虚构修改后整段','reason':'核对虚构原文','audiences':['internal']}
    path=f'/api/matters/{matter}/patches/approve';h={**headers,'Idempotency-Key':'current-patch'}
    response=client.post(path,headers=h,json=body);assert response.status_code==201,response.text
    patch=response.json()
    if action=='preview':
        body={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'internal','patch_ids':[patch['id']]}
        path=f'/api/matters/{matter}/exports/preview';h={**headers,'Idempotency-Key':'current-preview'}
        response=client.post(path,headers=h,json=body);assert response.status_code==201,response.text
    from cn_contract.exports.approvals import revoke_patch
    from cn_contract.security import authenticate
    from cn_contract.exports.storage import ExportRecordRow
    with database.session() as db:
        actor=authenticate(client.cookies.get('qx_session'),db)
        revoke_patch(UUID(matter),UUID(patch['id']),actor,db=db)
        count=db.scalar(select(func.count()).select_from(ExportRecordRow))
    replay=client.post(path,headers=h,json=body)
    assert replay.status_code==409,replay.text
    with database.session() as db:assert db.scalar(select(func.count()).select_from(ExportRecordRow))==count
