"""Actual synthetic-only QCC-off engineering demonstration, with unique outputs."""
from datetime import datetime,timezone
from io import BytesIO
import json
from pathlib import Path
import secrets
from uuid import uuid4

from ..config import PROJECT_ROOT,load_settings
from ..domain import Matter,Role,PolicySnapshot,FactSnapshot,FactDecision,ReviewContext,EvidenceBundle,UploadMeta,CoverageId
from ..persistence import Database,provision_matter,save_fact_snapshot,fact_snapshot_sha256,transition_matter,read_matter
from ..security import provision_user,login,authenticate,ServiceError
from ..documents import ingest,parse_document
from ..documents.ingest import DOCX_MIME
from ..facts.confirm import confirm_facts
from ..facts.storage import initialize_storage as facts_init
from ..authorities.storage import initialize_storage as authorities_init
from ..rules.storage import initialize_storage as rules_init,policy_sha256
from ..rules.loader import save_policy,register_default_cards,read_rule_snapshot
from .storage import initialize_storage,read_attempts,read_intakes
from .model_adapter import MockProvider
from .workflow import extract_document_candidates,run_review
from .validator import validate_findings
from .synthetic import select_fixture


def run_demo(fixture,*,provider='mock',qcc='off',output_root=None):
    # Block before even opening a fixture or creating output on live requests.
    if provider!='mock' or qcc!='off': raise ServiceError('BLOCKED_LIVE',409)
    kind,position,path,data=select_fixture(fixture)
    parent=Path(output_root) if output_root is not None else PROJECT_ROOT/'.local'/'review-demo'
    root=parent/f'{kind}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}-{uuid4().hex}'
    root.mkdir(parents=True,exist_ok=False)
    database=Database('sqlite:///'+str(root/'evidence.db'),root/'originals',load_settings())
    authorities_init(database);rules_init(database);facts_init(database);initialize_storage(database)
    with database.session() as db:
        username='synthetic-demo-'+uuid4().hex
        password=secrets.token_urlsafe(24)
        uid=provision_user(username,password,{Role.HANDLING_LAWYER},db)
        token,_=login(username,password,db);actor=authenticate(token,db)
        matter=Matter(id=uuid4(),client_ref='SYNTHETIC-T06-'+kind,title='独立虚构'+kind,
            jurisdiction='CN-mainland',contract_type=kind,review_mode='pre_sign',position=position,
            objectives=('仅演示离线材料内审查',),member_ids={uid},status='intake',active_fact_version=None,active_policy_version=None,gate_issues=())
        provision_matter(matter,db)
        register_default_cards(actor,matter_id=matter.id,db=db)
        policy=PolicySnapshot(client_ref=matter.client_ref,version=1,sha256=policy_sha256(matter.client_ref,1,()),
            preferences=(),approved_by=None,approved_at=None)
        save_policy(policy,actor,matter_id=matter.id,db=db)
        version=ingest(BytesIO(data),UploadMeta(matter_id=matter.id,original_name=path.name,mime=DOCX_MIME,
            baseline_view=None,supersedes_id=None),actor,db=db)
        parsed=parse_document(version,None,actor=actor,db=db)
        facts=extract_document_candidates(parsed,MockProvider(),matter_id=matter.id,actor=actor,db=db)
        candidates=FactSnapshot(version=1,facts=facts,sha256=fact_snapshot_sha256(facts))
        save_fact_snapshot(matter.id,candidates,actor,db)
        decisions=tuple(FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,
            reason='独立虚构演示身份通过实际确认服务核对测试原文；非现实律师批准。') for f in facts)
        confirmed=confirm_facts(matter.id,1,decisions,actor,db=db)
        transition_matter(matter.id,'ready_for_review',actor,db)
        snapshot=read_rule_snapshot(actor,matter_id=matter.id,db=db)
        current=read_matter(matter.id,actor,db)
        context=ReviewContext(matter=current,document_versions=(version,),fact_snapshot=confirmed,position=current.position,
            rules=snapshot.rules,policy=policy,authority_ids=(),allowed_scope=tuple(CoverageId))
        run=run_review(context,MockProvider(),actor=actor,db=db)
        bundle=EvidenceBundle(anchors={a.id:a for a in parsed.anchors},authorities={},receipts={})
        validation=validate_findings(run,bundle,actor=actor,db=db)
        attempts=read_attempts(matter.id,run.id,actor,db=db)
        intakes=read_intakes(matter.id,actor,db=db)
        actual_matter=read_matter(matter.id,actor,db)
    payloads={'review.json':run.model_dump(mode='json'),'manifest.json':run.manifest.model_dump(mode='json'),
        'parse.json':parsed.model_dump(mode='json'),'facts-candidate.json':candidates.model_dump(mode='json'),
        'facts-confirmed.json':confirmed.model_dump(mode='json'),'validation.json':validation.model_dump(mode='json'),
        'attempts.json':list(attempts),'intakes.json':list(intakes)}
    paths={}
    for name,payload in payloads.items():
        target=root/name
        with target.open('x',encoding='utf-8') as output: output.write(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        paths[name]=str(target.resolve())
    summary={'synthetic':True,'fixture':str(path.resolve()),'contract_type':kind,'provider':'mock','qcc':'off','qcc_calls':0,
        'run_id':str(run.id),'matter_id':str(matter.id),'run_status':run.status,'matter_status':actual_matter.status,
        'coverage_count':len(run.coverage),'coverage':{c.coverage_id.value:c.status.value for c in run.coverage},
        'validation_ok':validation.ok,'fact_candidate_count':len(facts),'confirmed_fact_version':confirmed.version,
        'model_attempt_count':len(attempts),'model_cost':'0','model_cost_unit':'mock_credit',
        'intake_attempt_count':sum(len(i['attempts']) for i in intakes),
        'output_directory':str(root.resolve()),'outputs':paths,'limitations':list(run.limitations),
        'formal_artifacts':'本命令仅生成JSON与受保护数据库证据；Word草案使用导出服务，mock不可正式签发'}
    with (root/'summary.json').open('x',encoding='utf-8') as output:output.write(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary
