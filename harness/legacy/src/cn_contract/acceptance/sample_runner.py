"""Forty registered short materials through actual T02–T06, never legal gold."""
from collections import Counter
from datetime import datetime,timezone
from io import BytesIO
import json
from pathlib import Path
from uuid import uuid4

from ..config import load_settings
from ..domain import MatterCreateInput,Role,UploadMeta,FactDecision,SampleEvaluationResult
from ..persistence import Database,read_matter,get_parse_result,get_fact_snapshot,transition_matter
from ..security import provision_user,login,authenticate,ServiceError
from ..documents.ingest import ingest,DOCX_MIME
from ..facts.confirm import confirm_facts
from ..review.model_adapter import MockProvider
from ..review.workflow import run_review
from ..review.storage import read_attempts,read_intakes
from ..storage_bootstrap import initialize_storage
from ..web.services import create_matter,candidate_parse,context
from .registry import validate_dataset,safe_file,BASE,hash_bytes


def run_samples(samples,output_root):
    samples=validate_dataset(samples)
    parent=Path(output_root).resolve();parent.mkdir(parents=True,exist_ok=True)
    root=parent/('samples-'+uuid4().hex);root.mkdir(exist_ok=False)
    database=Database('sqlite:///'+str(root/'protected-state.db'),root/'protected',load_settings())
    initialize_storage(database)
    with database.session() as db:
        provision_user('T11-synthetic-engineer','synthetic-local-evaluation-only',{Role.HANDLING_LAWYER},db)
        token,_=login('T11-synthetic-engineer','synthetic-local-evaluation-only',db)
        actor=authenticate(token,db)
    results=[]
    for sample in samples:
        limits=(*sample.limitations,'仅真实工程解析/确认/18维mock；现实律师金标准和法律规则未批准。')
        try:
            data=safe_file(sample.path,within=BASE)
            if hash_bytes(data)!=sample.sha256:raise ValueError('FIXTURE_HASH_CHANGED')
            with database.session() as db:
                position={'sales':'buyer','service':'customer','lease':'lessee','nda':'recipient','unknown':'buyer'}[sample.contract_type]
                matter=create_matter(MatterCreateInput(title='T11独立虚构 '+sample.id,contract_type=sample.contract_type,
                    review_mode='pre_sign',position=position,objectives=('仅工程材料处理，不作现实法律结论',)),actor,db)
                version=ingest(BytesIO(data),UploadMeta(matter_id=matter.id,original_name=Path(sample.path).name,
                    mime=DOCX_MIME,baseline_view='original',supersedes_id=None),actor,db=db)
                candidate_parse(matter.id,version.id,actor,db)
                parsed=get_parse_result(matter.id,version.id,actor,db)
                active=read_matter(matter.id,actor,db)
                facts=get_fact_snapshot(matter.id,active.active_fact_version,actor,db)
                confirmed=confirm_facts(matter.id,facts.version,[FactDecision(fact_id=f.id,decision='confirmed',
                    confirmed_value=f.typed_value,reason='工程身份只核对独立虚构原文；不是现实法律gold') for f in facts.facts],actor,db=db)
                transition_matter(matter.id,'ready_for_review',actor,db)
                run=run_review(context(matter.id,actor,db),MockProvider(),actor=actor,db=db)
                attempts=read_attempts(matter.id,run.id,actor,db=db);intakes=read_intakes(matter.id,actor,db=db)
                evidence={'sample_id':sample.id,'fixture_sha256':sample.sha256,'executed_at':datetime.now(timezone.utc).isoformat(),
                    'parse':parsed.model_dump(mode='json'),'facts':confirmed.model_dump(mode='json'),
                    'run':run.model_dump(mode='json'),'attempts':attempts,'intakes':intakes,
                    'gold':{'status':'pending','reviewer_1':None,'reviewer_2':None},'qcc_requests':0}
            path=root/(sample.id+'.json')
            with path.open('x',encoding='utf-8') as stream:json.dump(evidence,stream,ensure_ascii=False,indent=2);stream.write('\n')
            results.append(SampleEvaluationResult(sample_id=sample.id,family=sample.family,partition=sample.partition,
                contract_type=sample.contract_type,fixture_sha256=sample.sha256,
                status='FAIL' if run.status=='failed' else 'NOT_SUPPORTED' if parsed.unsupported_parts else 'PASS',
                parse_status='completed',facts_confirmed=len(confirmed.facts),coverage_count=len(run.coverage),
                unsupported_parts=len(parsed.unsupported_parts),model_usage=run.model_usage,attempts=len(attempts),
                run_id=run.id,error_code=run.error_code,evidence_ref=str(path),evidence_sha256=hash_bytes(path.read_bytes()),limitations=limits))
        except ServiceError as error:
            results.append(SampleEvaluationResult(sample_id=sample.id,family=sample.family,partition=sample.partition,
                contract_type=sample.contract_type,fixture_sha256=sample.sha256,status='FAIL',parse_status='failed',
                error_code=error.code,limitations=limits))
    database.engine.dispose()
    return results
