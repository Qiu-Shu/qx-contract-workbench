"""Independent lawyer statements must never become PDF text-layer anchors."""
import pytest
from sqlalchemy import delete, text
from cn_contract.persistence import MembershipRow
from tests.integration.test_assisted_review import assisted_api
from tests.integration.test_pdf_original_viewer import uploaded


def setup(assisted_api):
    client, database, ids, headers, matter, sent, raw, url = uploaded(assisted_api)
    current = client.get(f'/api/matters/{matter}/facts').json()
    value = dict(document_version_id=sent['version_id'], document_sha256=sent['sha256'],
        fact_version=current['version'], page=2, source_kind='lawyer_transcription',
        observed_text='SYNTHETIC no automatic acceptance', field='other_literal',
        typed_value={'kind':'text','value':'no automatic acceptance'},unit=None,
        reason='Lawyer independently checked the fictional page', original_page_checked=True,
        previous_id=None,candidate_id=None,candidate_sha256=None)
    return client,database,ids,headers,matter,sent,value


def submit(client,headers,matter,value,key='proofreading-1'):
    return client.post(f'/api/matters/{matter}/page-verifications',json=value,
        headers={**headers,'Idempotency-Key':key})


@pytest.mark.parametrize('kind',['visible_original','lawyer_transcription','provider_clarification'])
def test_verified_source_is_immutable_separate_candidate(assisted_api,kind):
    client,database,ids,headers,matter,sent,value=setup(assisted_api);value['source_kind']=kind
    response=submit(client,headers,matter,value)
    assert response.status_code==200,response.text
    record=response.json()
    assert record['input']==value and record['actor_id']==str(ids['lawyer'])
    facts=client.get(f'/api/matters/{matter}/facts').json()
    assert facts['version']==value['fact_version']+1
    fact=facts['facts'][-1]
    assert fact['confirmation_status']=='unconfirmed' and fact['anchor_ids']==[]
    assert fact['provenance_type']=='source_verification' and fact['verification_ids']==[record['id']]
    history=client.get(f'/api/matters/{matter}/page-verifications').json()
    assert history[0]['id']==record['id']
    replay=submit(client,headers,matter,value)
    assert replay.status_code==200 and replay.json()==record
    with database.session() as db:
        with pytest.raises(Exception,match='IMMUTABLE_RECORD'):
            db.execute(text('UPDATE page_verifications SET payload=:payload'),{'payload':'tampered'})


@pytest.mark.parametrize('change,expected',[
    ('hash',409),('version',409),('page',409),('blank_reason',422),('unchecked',422),
    ('fake_candidate',409),('claimed_actor',422),('missing_source',422),('csrf',403),
    ('anonymous',401),('revoked',403),('cross_matter',403)])
def test_untrusted_proofreading_rejected_without_new_fact(assisted_api,change,expected):
    client,database,ids,headers,matter,sent,value=setup(assisted_api)
    if change=='hash':value['document_sha256']='0'*64
    elif change=='version':value['fact_version']+=1
    elif change=='page':value['page']=3
    elif change=='blank_reason':value['reason']=' '
    elif change=='unchecked':value['original_page_checked']=False
    elif change=='fake_candidate':value.update(candidate_id=sent['version_id'],candidate_sha256='0'*64)
    elif change=='claimed_actor':value['actor_id']=str(ids['lawyer'])
    elif change=='missing_source':value.pop('source_kind')
    elif change=='csrf':headers={}
    elif change=='anonymous':client.cookies.clear()
    elif change=='revoked':
        with database.session() as db: db.execute(delete(MembershipRow).where(MembershipRow.matter_id==matter,MembershipRow.user_id==str(ids['lawyer'])))
    else:
        from tests.integration.test_api import create_case
        matter=create_case(client,headers)
    response=submit(client,headers,matter,value)
    assert response.status_code==expected,response.text


def test_verification_transaction_rolls_back_fact_and_record(assisted_api,monkeypatch):
    client,database,ids,headers,matter,sent,value=setup(assisted_api)
    import importlib.util
    assert importlib.util.find_spec('cn_contract.documents.proofreading'), 'source verification service missing'
    from cn_contract.documents import proofreading
    original=proofreading.save_fact_snapshot
    def fail(*args,**kwargs):
        original(*args,**kwargs)
        from cn_contract.security import ServiceError
        raise ServiceError('VERSION_CONFLICT',409)
    monkeypatch.setattr(proofreading,'save_fact_snapshot',fail)
    assert submit(client,headers,matter,value).status_code==409
    assert client.get(f'/api/matters/{matter}/facts').json()['version']==value['fact_version']
    assert client.get(f'/api/matters/{matter}/page-verifications').json()==[]


def test_confirmation_does_not_silently_change_source_statement(assisted_api):
    client,_,_,headers,matter,_,value=setup(assisted_api)
    assert submit(client,headers,matter,value).status_code==200
    snapshot=client.get(f'/api/matters/{matter}/facts').json();fact=snapshot['facts'][-1]
    response=client.post(f'/api/matters/{matter}/facts/confirm',headers=headers,json={
        'fact_version':snapshot['version'],'decisions':[{'fact_id':fact['id'],'decision':'corrected',
        'confirmed_value':{'kind':'text','value':'changed without updated source record'},'reason':'fictional change'}]})
    assert response.status_code==409,response.text


def test_replay_rechecks_original_integrity(assisted_api):
    from cn_contract.persistence import read_version
    from cn_contract.security import authenticate
    from uuid import UUID
    client,database,_,headers,matter,sent,value=setup(assisted_api)
    assert submit(client,headers,matter,value).status_code==200
    with database.session() as db:
        actor=authenticate(client.cookies.get('qx_session'),db)
        version=read_version(UUID(matter),UUID(sent['version_id']),actor,db)
    path=database.storage_root/version.storage_ref;path.chmod(0o600);path.write_bytes(b'tampered synthetic original')
    assert submit(client,headers,matter,value).status_code==409


def test_numeric_checkbox_is_not_explicit_source_confirmation(assisted_api):
    client,_,_,headers,matter,_,value=setup(assisted_api);value['original_page_checked']=1
    assert submit(client,headers,matter,value).status_code==422


def test_source_update_replaces_candidate_and_invalidates_old_replay(assisted_api):
    client,_,_,headers,matter,_,value=setup(assisted_api)
    first=submit(client,headers,matter,value).json()
    changed={**value,'fact_version':value['fact_version']+1,'previous_id':first['id'],
        'typed_value':{'kind':'text','value':'clarified fictional acceptance'},'source_kind':'provider_clarification'}
    response=submit(client,headers,matter,changed,'proofreading-2')
    assert response.status_code==200,response.text
    snapshot=client.get(f'/api/matters/{matter}/facts').json()
    assert len(snapshot['facts'])==1 and snapshot['facts'][0]['typed_value']==changed['typed_value']
    assert snapshot['facts'][0]['verification_ids']==[response.json()['id']]
    assert len(client.get(f'/api/matters/{matter}/page-verifications').json())==2
    assert submit(client,headers,matter,value).status_code==409


def test_ocr_candidate_must_be_server_owned_and_lawyer_verified(assisted_api,monkeypatch):
    """Stub only for ordinary CI's routing/transaction check; not an OCR positive."""
    import importlib.util
    assert importlib.util.find_spec('cn_contract.documents.ocr_candidates'), 'OCR candidate store missing'
    from cn_contract.documents import ocr_candidates
    from cn_contract.domain import OCRResult,OCRPageSource,OCRBlock
    from datetime import datetime,timezone
    from uuid import uuid4
    def fake(raw,source):
        source=OCRPageSource.model_validate(source)
        return OCRResult(id=uuid4(),source=source,created_at=datetime.now(timezone.utc),
            engine='PaddleOCR-3.7.0/PaddleX-3.7.0/PaddlePaddle-3.3.0-CPU',asset_manifest_sha256='0'*64,raw_output_sha256='1'*64,
            blocks=(OCRBlock(raw_text='SYNTHETIC CI ONLY',confidence=.99,polygon=((1,1),(30,1),(30,15),(1,15))),),
            bitmap_to_page=(source.page_width_points/source.bitmap_width,0,0,source.page_height_points/source.bitmap_height,0,0),reasons=('CI_STUB_ONLY',))
    monkeypatch.setattr(ocr_candidates,'run_ocr_page',fake)
    client,_,_,headers,matter,sent,value=setup(assisted_api)
    request={k:value[k] for k in ('document_version_id','document_sha256','page')}
    response=client.post(f'/api/matters/{matter}/page-ocr',headers={**headers,'Idempotency-Key':'ocr-1'},json=request)
    assert response.status_code==200,response.text
    candidate=response.json()
    assert candidate['result']['blocks'][0]['verification_state']=='unverified'
    assert client.get(f'/api/matters/{matter}/facts').json()['facts']==[]
    value.update(candidate_id=candidate['result']['id'],candidate_sha256=candidate['sha256'])
    assert submit(client,headers,matter,{**value,'candidate_sha256':'0'*64}).status_code==409
    response=submit(client,headers,matter,value)
    assert response.status_code==200,response.text
    assert client.get(f'/api/matters/{matter}/facts').json()['facts'][0]['confirmation_status']=='unconfirmed'


def test_verified_page_source_reaches_draft_without_fake_text_layer(assisted_api):
    from tests.integration.test_assisted_review import docx_text
    client,_,_,headers,matter,sent,value=setup(assisted_api)
    record=submit(client,headers,matter,value).json()
    facts=client.get(f'/api/matters/{matter}/facts').json()
    response=client.post(f'/api/matters/{matter}/facts/confirm',headers=headers,json={
        'fact_version':facts['version'],'decisions':[{'fact_id':facts['facts'][0]['id'],'decision':'confirmed',
        'confirmed_value':value['typed_value'],'reason':'independent fictional page checked'}]})
    assert response.status_code==200,response.text
    context=client.get(f'/api/matters/{matter}/review-context').json()
    opinion={'coverage_ids':['C06'],'issue_type':'fictional_page_statement','severity':'low','evidence_state':'unconfirmed',
        'anchor_ids':[],'verification_ids':[record['id']],'analysis':'虚构核对意见','business_effect':'需人工核对约定',
        'recommendation':'保留人工来源记录','basis_kind':'material_observation','authority_refs':[],'unknowns':['法律依据未核']}
    body={'context_sha256':context['context_sha256'],'fact_version':context['fact_version'],'document_hashes':context['document_hashes'],
        'examined_anchor_ids':[],'examined_verification_ids':[record['id']],'opinions':[opinion]}
    response=client.post(f'/api/matters/{matter}/review-proposals',headers=headers,json=body)
    assert response.status_code==201,response.text
    run=client.get(f'/api/matters/{matter}/reviews/{response.json()["id"]}').json()
    finding=run['findings'][0];assert finding['anchor_ids']==[] and finding['verification_ids']==[record['id']]
    response=client.post(f'/api/matters/{matter}/findings/{finding["id"]}/decision',headers=headers,json={
        'run_id':run['id'],'run_sha256':run['run_sha256'],'decision':'accept','reason':'fictional lawyer disposition'})
    assert response.status_code==201,response.text
    run=client.get(f'/api/matters/{matter}/reviews/{run["id"]}').json()
    response=client.post(f'/api/matters/{matter}/exports/preview',headers=headers,json={
        'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':'client','patch_ids':[]})
    assert response.status_code==201,response.text
    bundle=response.json()
    output=client.get(f'/api/matters/{matter}/exports/{bundle["artifacts"][0]["id"]}/download')
    assert output.status_code==200
    text=docx_text(output.content)
    assert '律师转录' in text and value['observed_text'] in text
    response=client.post(f'/api/matters/{matter}/working-draft-confirmations',headers=headers,json={
        'bundle_id':bundle['id'],'bundle_manifest_sha256':bundle['manifest_sha256'],
        'decision_snapshot_sha256':run['decision_snapshot']['sha256'],'audience':'client',
        'acknowledged_unresolved_finding_ids':[],'reason':'independent fictional work draft'})
    assert response.status_code==201,response.text
    changed={**value,'fact_version':client.get(f'/api/matters/{matter}/facts').json()['version'],
        'previous_id':record['id'],'typed_value':{'kind':'text','value':'corrected fictional source'}}
    assert submit(client,headers,matter,changed,'new-source').status_code==200
    assert client.get(f'/api/matters/{matter}/exports/{bundle["artifacts"][0]["id"]}/download').status_code==409


def test_ocr_wait_releases_database_and_rechecks_revoked_member(assisted_api,monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from cn_contract.documents import ocr_candidates
    from cn_contract.domain import OCRResult,OCRPageSource
    from datetime import datetime,timezone
    from uuid import uuid4
    entered=threading.Event();release=threading.Event()
    def pending_ocr(raw,metadata):
        source=OCRPageSource.model_validate(metadata);entered.set();assert release.wait(25)
        return OCRResult(id=uuid4(),source=source,created_at=datetime.now(timezone.utc),
            engine='PaddleOCR-3.7.0/PaddleX-3.7.0/PaddlePaddle-3.3.0-CPU',asset_manifest_sha256='0'*64,
            raw_output_sha256='1'*64,blocks=(),bitmap_to_page=(.5,0,0,.5,0,0),reasons=('CI_STUB',))
    monkeypatch.setattr(ocr_candidates,'run_ocr_page',pending_ocr)
    client,database,ids,headers,matter,_,value=setup(assisted_api)
    request={k:value[k] for k in ('document_version_id','document_sha256','page')}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(client.post,f'/api/matters/{matter}/page-ocr',headers=headers,json=request)
        assert entered.wait(5)
        try:
            with database.session() as db:
                db.execute(delete(MembershipRow).where(MembershipRow.matter_id==matter,MembershipRow.user_id==str(ids['lawyer'])))
        finally:release.set()
        response=pending.result(timeout=5)
        assert response.status_code==403,response.text
    with database.session() as db:
        assert db.execute(text('SELECT COUNT(*) FROM ocr_candidates')).scalar()==0
