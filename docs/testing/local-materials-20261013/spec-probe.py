import json
from pathlib import Path
from io import BytesIO
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from docx import Document
from sqlalchemy import select
from cn_contract.web import local_server as module
from cn_contract.documents import local_materials
from cn_contract.persistence import AuditRow, DocumentRow
from tests.integration.test_local_materials import new_local_case, independent_docx, upload_and_parse, ready_local
from tests.integration.test_local_workbench import login, PASSWORD
from cn_contract.documents.ingest import DOCX_MIME
out=Path('.audit-local/local-materials-20261013/spec-review').resolve()
module.PROJECT_ROOT=out/('sandbox-'+uuid4().hex)
root=module.PROJECT_ROOT/'.local'/'workbench'
module.initialize_workspace(root,'local-lawyer',PASSWORD)
results={}
with TestClient(module.build_local_app(root)) as c:
    headers=login(c); m=new_local_case(c,headers); base='/api/matters/'+m
    raw=independent_docx(); sent=upload_and_parse(c,headers,m,raw)
    anchor,facts,ctx=ready_local(c,headers,m,sent)
    opinion={'coverage_ids':['C06'],'issue_type':'independent_price_scope','severity':'low','evidence_state':'unconfirmed','anchor_ids':[anchor['id']],'analysis':'本机虚构探针价款范围待核。','business_effect':'付款安排待核。','recommendation':'明确价款包含项目。','basis_kind':'material_observation','authority_refs':[],'unknowns':['履行凭证待核。']}
    prop=c.post(base+'/review-proposals',headers=headers,json={'context_sha256':ctx['context_sha256'],'fact_version':facts['version'],'document_hashes':{sent['version_id']:sent['sha256']},'examined_anchor_ids':[anchor['id']],'opinions':[opinion]})
    assert prop.status_code==201,prop.text
    run=c.get(base+'/reviews/'+prop.json()['id']).json()
    r=c.post(base+'/findings/'+run['findings'][0]['id']+'/decision',headers=headers,json={'run_id':run['id'],'run_sha256':run['run_sha256'],'decision':'accept','reason':'独立虚构审阅探针明确处置'})
    assert r.status_code==201,r.text
    bundles={}
    for audience in ('client','internal','counterparty'):
        r=c.post(base+'/exports/preview',headers=headers,json={'run_id':run['id'],'run_sha256':run['run_sha256'],'audience':audience,'patch_ids':[]})
        assert r.status_code==201,r.text
        bundle=r.json(); bundles[audience]=bundle
        data=c.get(base+'/exports/'+bundle['artifacts'][0]['id']+'/download').content
        (out/(audience+'.docx')).write_bytes(data)
        doc=Document(BytesIO(data)); texts=[p.text for p in doc.paragraphs]
        results[audience+'_simulation_labels']=[t for t in texts if '模拟' in t]
    run=c.get(base+'/reviews/'+prop.json()['id']).json(); bundle=bundles['client']
    r=c.post(base+'/working-draft-confirmations',headers=headers,json={'bundle_id':bundle['id'],'bundle_manifest_sha256':bundle['manifest_sha256'],'decision_snapshot_sha256':run['decision_snapshot']['sha256'],'audience':'client','acknowledged_unresolved_finding_ids':[],'reason':'独立探针本版核对'})
    results['working_draft_confirmation_status']=r.status_code
    r=c.post(base+'/approvals',headers=headers,json={'bundle_id':bundle['id'],'artifact_manifest_hash':bundle['manifest_sha256'],'review_snapshot_hash':run['run_sha256'],'scope':'client'})
    results['formal_approval_status']=r.status_code
    old_hash=local_materials.policy_hash
    local_materials.policy_hash=lambda:'0'*64
    results['changed_policy_context_status']=c.get(base+'/review-context').status_code
    results['changed_policy_download_status']=c.get(base+'/exports/'+bundle['artifacts'][0]['id']+'/download').status_code
    local_materials.policy_hash=old_hash
    with c.app.state.database.session() as db:
        rows=list(db.scalars(select(AuditRow).where(AuditRow.action=='local_material_admitted')))
        results['admission_count']=len(rows)
        results['admission_fields']=sorted(json.loads(rows[0].payload))
    r=c.post(base+'/facts/candidates',headers=headers,json={'document_version_id':sent['version_id'],'document_sha256':sent['sha256'],'fact_version':facts['version'],'candidates':[{'field':'total_price','typed_value':{'kind':'decimal','value':'12345'},'unit':'元','anchor_ids':[anchor['id']]}]})
    results['new_facts_status']=r.status_code
    results['old_export_after_new_fact_status']=c.get(base+'/exports/'+bundle['artifacts'][0]['id']+'/download').status_code
(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(results,ensure_ascii=False,indent=2))
