from pathlib import Path
import json,hashlib,runpy
from uuid import UUID
from sqlalchemy import select
from docx import Document
from cn_contract.config import load_settings
from cn_contract.persistence import Database,UserRow,SessionRow
from cn_contract.security import _principal
from cn_contract.domain import SyntheticAssistedPolicy
from cn_contract.review.proposals import configure
from cn_contract.review.storage import read_run
from cn_contract.exports.approvals import prepare_exports,download_artifact
from cn_contract.web.app import initialize_storage
ROOT=Path.cwd();OUT=ROOT/'.audit-local/client-readability-20261009'
snapshot=runpy.run_path(str(ROOT/'src/cn_contract/mcp/bound_entry.py'),run_name='binding_helper')['build_binding_snapshot'](ROOT)
binding=ROOT/'plugins/qx-contract-offline-codex/runtime-binding.json'
binding.write_bytes((json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
(OUT/'binding.json').write_text(json.dumps({'build_id':snapshot['build_id'],'sha256':hashlib.sha256(binding.read_bytes()).hexdigest()},indent=2)+'\n',encoding='utf8')
root=ROOT/'.local/ocr-quality-preview-20261009'
database=Database('sqlite:///'+str(root/'workbench.db'),root/'protected',load_settings(),initialize_schema=False)
initialize_storage(database)
configure(database,'assisted_draft',SyntheticAssistedPolicy(policy_id='ocr-quality-preview-20261009',purpose='assisted_draft',document_hashes=('017866f3c56b2fad241fc048e6440e30314db41bef53391eabd7bc706117ae9b',),candidate_source='manual_synthetic'))
records=[]
with database.session() as db:
    user=db.scalar(select(UserRow).where(UserRow.username=='lawyer'))
    session=db.scalar(select(SessionRow).where(SessionRow.user_id==user.id,SessionRow.revoked==False))
    actor=_principal(session,db)
    run=read_run(UUID('95701fd1-d2fb-4f39-9540-81bdd5d12e64'),UUID('24d08640-4349-4db5-89e4-f282f5a8ddff'),actor,db=db,current=True)
    old=ROOT/'docs/testing/ocr-quality-20261009/browser-final-draft.docx'
    assert download_artifact(UUID('08363003-e614-4a6b-8ac2-6353d08d8ea3'),actor,db=db).getvalue()==old.read_bytes()
    for audience in ('client','internal'):
        bundle=prepare_exports(run,audience,[],actor,db=db)
        artifact=bundle.artifacts[0]
        raw=download_artifact(artifact.id,actor,db=db).getvalue()
        target=OUT/(audience+'.docx');target.write_bytes(raw)
        doc=Document(target);text='\n'.join(p.text for p in doc.paragraphs)
        for value in ['28473','可见原文核对','非PDF文字层','b17b8fc7-825b-4021-93da-a8a2fb5d94ee','017866f3c56b2fad',str(run.id)]:assert value in text,value
        if audience=='client':
            assert '页码范围：1–48' in text and 'OCR_NOT_DEPLOYED' not in text
            assert '未支持或未读项：第1–48页' in text
        else:assert 'OCR_NOT_DEPLOYED:page:48' in text and '事实快照：' in text
        records.append({'audience':audience,'artifact_id':str(artifact.id),'bundle_id':str(bundle.id),'file':target.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    assert download_artifact(UUID('08363003-e614-4a6b-8ac2-6353d08d8ea3'),actor,db=db).getvalue()==old.read_bytes()
receipt={'run_id':str(run.id),'old_draft_unchanged_and_downloadable':True,'records':records,'real_model_qcc_calls':0,'production':False}
(OUT/'exports.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(receipt,ensure_ascii=False))
