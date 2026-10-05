"""Explicit local fiction and manual candidate boundary; no model transport."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select

from ..domain import (SyntheticAssistedPolicy, AssistedFactsInput, AssistedReviewInput,
    AssistedReviewContextView, Fact, FactSnapshot, Finding, ManualCandidateReceipt, ReviewProposal, ReviewRun)
from ..persistence import (configured_database, read_matter, read_version, get_parse_result,
    get_fact_snapshot, fact_snapshot_sha256, save_fact_snapshot, review_status_changed)
from ..security import ServiceError, authorize
from ..facts.extract import build_fact_candidates
from ..facts.storage import trusted_parse, source_anchor_is_eligible

LIMITATIONS = ('独立虚构材料；律师辅助工作稿，不构成正式法律意见或签发。',
    '候选来源：离线人工/合成（manual_synthetic）；真实模型推理NOT_RUN，真实模型调用0。',
    'QCC关闭，查询调用0；未查询不能解释为现实记录不存在或无风险。',
    '每项人工候选与待核依据须由律师核对；待核引用未登记为已批准法源或规则。',
    '未涉及的维度保持材料不足；法律gold、完整补丁后法律与数值重审及生产均未完成。')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def configure(database, purpose, policy):
    if purpose == 'formal_release': raise ServiceError('BLOCKED_LIVE', 409)
    if purpose not in ('mock_demo', 'assisted_draft'):
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    if purpose == 'assisted_draft':
        if policy is None: raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
        try:
            policy = SyntheticAssistedPolicy.model_validate_json(policy.model_dump_json()) if isinstance(policy, SyntheticAssistedPolicy) else SyntheticAssistedPolicy.model_validate(policy)
        except (ValueError, TypeError): raise ServiceError('DATA_POLICY_UNAPPROVED', 409) from None
    elif policy is not None: raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    previous = getattr(database, '_review_purpose', None)
    if previous is not None and (previous != purpose or getattr(database, '_assisted_policy', None) != policy):
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    database._review_purpose = purpose
    database._assisted_policy = policy
    return policy


def is_assisted(db):
    return getattr(configured_database(db), '_review_purpose', 'mock_demo') == 'assisted_draft'


def require_policy(db):
    database = configured_database(db)
    policy = getattr(database, '_assisted_policy', None)
    if not is_assisted(db) or not isinstance(policy, SyntheticAssistedPolicy):
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    return SyntheticAssistedPolicy.model_validate_json(policy.model_dump_json())


def require_assisted_policy(db):
    """Stable trusted assisted-policy boundary reused by working-draft checks."""
    return require_policy(db)


def submit_fact_candidates(matter_id, value, actor, db):
    authorize(actor, matter_id, 'candidate_facts', db)
    from ..ops.storage import require_active
    require_active(db)
    from ..web.services import current_versions
    policy=require_policy(db)
    value=AssistedFactsInput.model_validate_json(value.model_dump_json())
    matter=read_matter(matter_id,actor,db)
    if matter.active_fact_version!=value.fact_version:raise ServiceError('VERSION_CONFLICT',409)
    version=read_version(matter_id,value.document_version_id,actor,db)
    versions=current_versions(matter_id,actor,db)
    if version.id not in {v.id for v in versions} or version.sha256!=value.document_sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    if any(v.sha256 not in policy.document_hashes for v in versions):
        raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    parsed=get_parse_result(matter_id,version.id,actor,db)
    if parsed is None:raise ServiceError('FACTS_UNCONFIRMED',409)
    parsed=trusted_parse(matter_id,version.id,actor,db,parsed)
    all_anchors={a.id:a for a in parsed.anchors}
    referenced={aid for candidate in value.candidates for aid in candidate.anchor_ids}
    if not referenced.issubset(all_anchors):raise ServiceError('VERSION_CONFLICT',409)
    if any(not source_anchor_is_eligible(all_anchors[aid],parsed) for aid in referenced):
        raise ServiceError('SOURCE_VISUAL_CONFIRMATION_REQUIRED',409)
    extraction={'facts':[{**c.model_dump(mode='json'),'provenance_type':'document','receipt_ids':[]}
        for c in value.candidates]}
    fresh=build_fact_candidates(parsed,extraction,matter_id=matter_id,version=value.fact_version+1,actor=actor,db=db)
    previous=get_fact_snapshot(matter_id,value.fact_version,actor,db)
    if len(previous.facts)+len(fresh)>256:raise ServiceError('FILE_LIMIT',413)
    # New evidence changes the full snapshot. Previous facts become candidates
    # again, so an assistant cannot carry a lawyer's old confirmation forward.
    facts=tuple(Fact.model_validate({**f.model_dump(mode='python'),'version':value.fact_version+1,
        'confirmation_status':'unconfirmed','confirmed_by':None,'confirmed_at':None})
        for f in (*previous.facts,*fresh))
    snapshot=FactSnapshot(version=value.fact_version+1,facts=facts,sha256=fact_snapshot_sha256(facts))
    with db.begin_nested():
        save_fact_snapshot(matter_id,snapshot,actor,db)
        require_policy(db)
        authorize(actor,matter_id,'candidate_facts',db)
    return snapshot


def assisted_configuration(policy):
    from .workflow import prompt_configuration
    return {**prompt_configuration({'provider':'assisted_manual','candidate_source':'manual_synthetic',
        'policy_sha256':digest(policy.model_dump(mode='json'))}), 'engine':'assisted-manual-v1'}


def context_digest(context, manifest, policy):
    payload=context.model_dump(mode='json')
    payload['matter'].pop('status')
    return digest({'context':payload,'manifest':manifest.model_dump(mode='json'),
        'policy':policy.model_dump(mode='json')})


def _context_state(matter_id,actor,db,*,allow_finished=False):
    from ..web.services import context
    from .workflow import current_manifest
    authorize(actor,matter_id,'read' if allow_finished else 'review',db)
    policy=require_policy(db)
    ctx=context(matter_id,actor,db)
    config=assisted_configuration(policy)
    state=current_manifest(ctx,actor,db,config,allow_finished=allow_finished)
    return policy,ctx,config,state


def review_context(matter_id, actor, db):
    policy,ctx,_,state=_context_state(matter_id,actor,db)
    manifest,anchors,_,_,actual=state
    return AssistedReviewContextView(matter_id=matter_id,purpose='assisted_draft',
        context_sha256=context_digest(actual,manifest,policy),policy_sha256=digest(policy.model_dump(mode='json')),
        fact_version=ctx.fact_snapshot.version,document_hashes=manifest.document_hashes,
        eligible_anchor_ids=tuple(anchors),candidate_source='manual_synthetic')


def _validate_input(value,context,manifest,anchors,policy):
    value=AssistedReviewInput.model_validate_json(value.model_dump_json())
    if (value.context_sha256!=context_digest(context,manifest,policy)
        or value.fact_version!=context.fact_snapshot.version or dict(value.document_hashes)!=dict(manifest.document_hashes)):
        raise ServiceError('VERSION_CONFLICT',409)
    examined=set(value.examined_anchor_ids)
    if not examined.issubset(anchors):raise ServiceError('VERSION_CONFLICT',409)
    if any(not set(item.anchor_ids).issubset(examined) for item in value.opinions):
        raise ServiceError('VERSION_CONFLICT',409)
    return value


def proposal_findings(proposal):
    labels={'material_observation':'材料观察（待律师核对）','business_preference':'商业偏好（待律师确认）',
        'pending_authority':'法源依据待核'}
    findings=[]
    for identifier,item in zip(proposal.finding_ids,proposal.input.opinions):
        effect=item.business_effect+'\n候选来源：离线人工/合成；依据类型：'+labels[item.basis_kind]
        effect+='\n待核引用：'+('；'.join(item.authority_refs) if item.authority_refs else '未提供，未形成已核法律依据')
        effect+='\n未知项：'+('；'.join(item.unknowns) if item.unknowns else '本候选未另列；不能据此认定完整或无风险')
        findings.append(Finding(id=identifier,run_id=proposal.run_id,coverage_ids=item.coverage_ids,
            issue_type=item.issue_type,severity=item.severity,evidence_state=item.evidence_state,
            anchor_ids=item.anchor_ids,cross_anchor_ids=(),rule_ids=(),authority_ids=(),
            analysis=item.analysis,business_effect=effect,recommendation=item.recommendation,
            replacement_text=None,fallback='待律师核对人工候选、来源状态及未完成维度。',human_decision=None))
    return tuple(findings)


def _save_proposal(proposal,actor,db):
    from .storage import ReviewProposalRow,require_storage
    require_storage(db)
    db.add(ReviewProposalRow(id=str(proposal.id),run_id=str(proposal.run_id),matter_id=str(proposal.matter_id),
        actor_id=str(actor.user_id),payload=proposal.model_dump_json(),sha256=proposal.sha256,
        timestamp=proposal.execution_receipt.submitted_at))
    db.flush()


def submit_proposal(matter_id, value, actor, db):
    from .workflow import current_manifest,coverage_for
    from .storage import _save
    from ..ops.storage import require_active
    require_active(db)
    policy,ctx,config,state=_context_state(matter_id,actor,db)
    manifest,anchors,parses,_,actual=state
    value=_validate_input(value,actual,manifest,anchors,policy)
    started=datetime.now(timezone.utc);run_id=uuid4()
    payload={'id':uuid4(),'matter_id':matter_id,'run_id':run_id,'policy_sha256':digest(policy.model_dump(mode='json')),
        'context_sha256':value.context_sha256,'input_sha256':digest(value.model_dump(mode='json')),
        'input':value,'finding_ids':tuple(uuid4() for _ in value.opinions),
        'execution_receipt':ManualCandidateReceipt(source='manual_synthetic',submitted_by=actor.user_id,submitted_at=started)}
    # Hash the exact typed JSON payload before constructing its frozen model.
    encoded={**payload,'id':str(payload['id']),'matter_id':str(matter_id),'run_id':str(run_id),
        'input':value.model_dump(mode='json'),'finding_ids':[str(v) for v in payload['finding_ids']],
        'execution_receipt':payload['execution_receipt'].model_dump(mode='json')}
    proposal=ReviewProposal(**payload,sha256=digest(encoded))
    findings=proposal_findings(proposal)
    run=ReviewRun(id=run_id,matter_id=matter_id,manifest=manifest,status='completed',
        coverage=coverage_for(actual,findings,value.examined_anchor_ids,parses),findings=findings,
        limitations=LIMITATIONS+('本轮明确检查的原文锚点：'+str(len(value.examined_anchor_ids))+
            '；当前可消费锚点：'+str(len(anchors))+'；不声明全文已经法律审查。',),
        model_usage=(),started_at=started,finished_at=datetime.now(timezone.utc),error_code=None)
    with db.begin_nested():
        end=current_manifest(ctx,actor,db,config)
        if end[0]!=manifest or context_digest(end[4],end[0],require_policy(db))!=value.context_sha256:
            raise ServiceError('VERSION_CONFLICT',409)
        _save(run,actual,config,value.examined_anchor_ids,[],actor,db)
        _save_proposal(proposal,actor,db)
        review_status_changed(matter_id,actor,db,success=True)
        validate_saved_run(run,None,actor,db)
        authorize(actor,matter_id,'review',db)
    return run


def read_proposal(matter_id,run_id,actor,db):
    from .storage import ReviewProposalRow,ReviewRunRow,require_storage
    authorize(actor,matter_id,'read',db);require_storage(db)
    row=db.scalar(select(ReviewProposalRow).where(ReviewProposalRow.run_id==str(run_id),
        ReviewProposalRow.matter_id==str(matter_id)))
    if row is None:raise ServiceError('VERSION_CONFLICT',409)
    try:proposal=ReviewProposal.model_validate_json(row.payload)
    except ValueError:raise ServiceError('VERSION_CONFLICT',409) from None
    run_row=db.get(ReviewRunRow,str(run_id))
    if (proposal.sha256!=row.sha256 or str(proposal.id)!=row.id or str(proposal.run_id)!=row.run_id
        or str(proposal.matter_id)!=row.matter_id or str(proposal.execution_receipt.submitted_by)!=row.actor_id
        or proposal.execution_receipt.submitted_at!=row.timestamp or run_row is None
        or run_row.actor_id!=row.actor_id or run_row.matter_id!=row.matter_id):
        raise ServiceError('VERSION_CONFLICT',409)
    return proposal


def validate_saved_run(run,row,actor,db,*,state=None):
    from .storage import ReviewRunRow
    from .workflow import current_manifest,coverage_for
    from ..domain import ReviewContext
    row=row or db.get(ReviewRunRow,str(run.id))
    if row is None or run!=ReviewRun.model_validate_json(row.payload):raise ServiceError('VERSION_CONFLICT',409)
    policy=require_policy(db);ctx=ReviewContext.model_validate_json(row.context_json)
    config=json.loads(row.config_json)
    state=state or current_manifest(ctx,actor,db,config,allow_finished=True)
    manifest,anchors,parses,_,actual=state
    proposal=read_proposal(run.matter_id,run.id,actor,db)
    value=_validate_input(proposal.input,actual,manifest,anchors,policy)
    findings=proposal_findings(proposal)
    expected=ReviewRun(id=run.id,matter_id=run.matter_id,manifest=manifest,status='completed',
        coverage=coverage_for(actual,findings,value.examined_anchor_ids,parses),findings=findings,
        limitations=LIMITATIONS+('本轮明确检查的原文锚点：'+str(len(value.examined_anchor_ids))+
            '；当前可消费锚点：'+str(len(anchors))+'；不声明全文已经法律审查。',),
        model_usage=(),started_at=proposal.execution_receipt.submitted_at,finished_at=run.finished_at,error_code=None)
    if (proposal.policy_sha256!=digest(policy.model_dump(mode='json')) or run!=expected
        or config!=assisted_configuration(policy) or json.loads(row.processed_json)!=[str(v) for v in value.examined_anchor_ids]):
        raise ServiceError('VERSION_CONFLICT',409)
    return proposal
