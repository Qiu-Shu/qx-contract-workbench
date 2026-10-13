"""Thin current-snapshot adapters over T02–T09, not a second review engine."""
import json
import hashlib
from uuid import UUID, uuid4
from sqlalchemy import select, update

from ..domain import (Matter, Role, PolicySnapshot, FactSnapshot, ReviewContext, CoverageId,
    Patch, HumanDecision, PartyCandidate, Party, PartyDecision)
from ..persistence import (provision_matter, read_matter, DocumentRow, read_version, get_parse_result,
    get_fact_snapshot, save_fact_snapshot, fact_snapshot_sha256, MatterRow, transition_matter, ExportRow, ApprovalRow)
from ..security import ServiceError, authorize, deny
from ..rules.loader import register_default_cards, save_policy, read_rule_snapshot, read_policy
from ..rules.storage import policy_sha256
from ..review.workflow import extract_document_candidates, run_review
from ..review.model_adapter import MockProvider
from ..review.storage import read_run
from ..facts.storage import trusted_parse, PartyRow
from ..facts.party import resolve_party
from ..documents.ingest import parse_document
from ..exports import approvals
from ..exports import storage as exports_storage
from . import storage as s


def create_matter(value, actor, db):
    from ..security import _principal
    from ..persistence import SessionRow
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if principal is None: raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    if not principal.roles & {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER}:
        deny(actor, UUID(int=0), 'authorization_denied', db)
    reviewer=None
    if value.reviewer_username:
        from ..persistence import UserRow
        reviewer=db.scalar(select(UserRow).where(UserRow.username==value.reviewer_username))
        if reviewer is None or reviewer.disabled or 'reviewing_lawyer' not in json.loads(reviewer.roles):
            raise ServiceError('AUTHORIZATION_REQUIRED',403)
    local_materials = value.material_mode == 'local'
    matter = Matter(id=uuid4(), client_ref=('LOCAL-' if local_materials else 'SYNTHETIC-')+uuid4().hex, title=value.title,
        jurisdiction='CN-mainland', contract_type=value.contract_type, review_mode=value.review_mode,
        position=value.position, objectives=value.objectives,
        member_ids={principal.user_id}|({UUID(reviewer.id)} if reviewer else set()), status='intake',
        active_fact_version=None, active_policy_version=None, gate_issues=())
    with db.begin_nested():
        provision_matter(matter, db)
        if local_materials:
            from ..documents.local_materials import record_case
            record_case(matter.id, principal, db)
        register_default_cards(principal, matter_id=matter.id, db=db)
        policy = PolicySnapshot(client_ref=matter.client_ref, version=1, sha256=policy_sha256(matter.client_ref,1,()),
            preferences=(), approved_by=None, approved_at=None)
        save_policy(policy, principal, matter_id=matter.id, db=db)
    return read_matter(matter.id, principal, db)


def current_versions(matter_id, actor, db):
    authorize(actor, matter_id, 'read', db)
    rows = list(db.scalars(select(DocumentRow).where(DocumentRow.matter_id == str(matter_id))))
    old = {r.supersedes_id for r in rows if r.supersedes_id}
    return tuple(read_version(matter_id, UUID(r.id), actor, db) for r in rows if r.id not in old)


def public_version(version):
    return version.model_dump(mode='json', exclude={'storage_ref'})


def candidate_parse(matter_id, version_id, actor, db):
    version = read_version(matter_id, version_id, actor, db)
    if version.id not in {v.id for v in current_versions(matter_id, actor, db)}:
        raise ServiceError('VERSION_CONFLICT', 409)
    from ..review.proposals import is_assisted,require_policy,require_documents
    if is_assisted(db):
        require_documents(require_policy(db,matter_id),(version,),actor,db)
    parsed = parse_document(version, None, actor=actor, db=db)
    if is_assisted(db):
        facts=()
    else:
        facts = extract_document_candidates(parsed, MockProvider(), matter_id=matter_id, actor=actor, db=db)
    matter = read_matter(matter_id, actor, db)
    next_version = (matter.active_fact_version or 0) + 1
    old = get_fact_snapshot(matter_id, matter.active_fact_version, actor, db).facts if matter.active_fact_version else ()
    current_anchors = set()
    for v in current_versions(matter_id, actor, db):
        p = get_parse_result(matter_id, v.id, actor, db)
        if p: current_anchors.update(a.id for a in trusted_parse(matter_id, v.id, actor, db, p).anchors)
    # A new parse makes previous confirmations candidates again; exact anchors stay.
    all_facts = [f for f in old if set(f.anchor_ids) <= current_anchors and not set(f.anchor_ids) & {a.id for a in parsed.anchors}] + list(facts)
    all_facts = tuple(type(f).model_validate({**f.model_dump(mode='python'), 'version':next_version,
        'confirmation_status':'unconfirmed','confirmed_by':None,'confirmed_at':None}) for f in all_facts)
    snapshot = FactSnapshot(version=next_version, facts=all_facts, sha256=fact_snapshot_sha256(all_facts))
    save_fact_snapshot(matter_id, snapshot, actor, db)
    return str(version_id)


def context(matter_id, actor, db):
    matter = read_matter(matter_id, actor, db)
    if matter.active_fact_version is None or matter.position is None:
        raise ServiceError('FACTS_UNCONFIRMED', 409)
    facts = get_fact_snapshot(matter_id, matter.active_fact_version, actor, db)
    snapshot = read_rule_snapshot(actor, matter_id=matter_id, db=db)
    policy = read_policy(matter.active_policy_version, actor, matter_id=matter_id, db=db)
    return ReviewContext(matter=matter, document_versions=current_versions(matter_id, actor, db), fact_snapshot=facts,
        position=matter.position, rules=snapshot.rules, policy=policy, authority_ids=(), allowed_scope=tuple(CoverageId))


def verify_review_input(matter_id, value, actor, db):
    authorize(actor, matter_id, 'review', db)
    ctx = context(matter_id, actor, db)
    if ctx.matter.status != 'ready_for_review': raise ServiceError('STATE_CONFLICT',409)
    if value.fact_version != ctx.fact_snapshot.version or dict(value.document_hashes) != {v.id:v.sha256 for v in ctx.document_versions}:
        raise ServiceError('VERSION_CONFLICT',409)
    if not ctx.fact_snapshot.facts or any(f.confirmation_status not in {'confirmed','corrected','rejected'} for f in ctx.fact_snapshot.facts):
        raise ServiceError('FACTS_UNCONFIRMED',409)
    return ctx


def review(matter_id, value, actor, db):
    from ..review.proposals import is_assisted
    if is_assisted(db):raise ServiceError('NOT_SUPPORTED',409)
    ctx = verify_review_input(matter_id, value, actor, db)
    return str(run_review(ctx, MockProvider(), actor=actor, db=db).id)


def current_run(matter_id, run_id, digest, actor, db):
    run = read_run(matter_id, run_id, actor, db=db)
    if digest != s.sha(run.model_dump(mode='json')): raise ServiceError('APPROVAL_STALE',409)
    return run


def decisions(matter_id, run_id, actor, db):
    from ..review.decisions import read_history
    _, history = read_history(matter_id, run_id, actor, db=db)
    return [{'id':str(r.id), 'finding_id':str(r.finding_id), 'decision':r.decision.model_dump(mode='json')} for r in history]


def save_decision(matter_id, finding_id, value, actor, db):
    authorize(actor,matter_id,'confirm_facts',db)
    run = current_run(matter_id,value.run_id,value.run_sha256,actor,db)
    if run.status!='completed' or finding_id not in {f.id for f in run.findings}: raise ServiceError('VERSION_CONFLICT',409)
    from ..review.basis import check_basis
    basis=check_basis(value.basis_review,run,actor,db) if value.basis_review else None
    decision = HumanDecision(decision=value.decision, reason=value.reason, actor_id=actor.user_id, decided_at=s.now(),
        basis_review=basis,
        edited_analysis=value.edited_analysis, edited_recommendation=value.edited_recommendation,
        edited_replacement_text=value.edited_replacement_text)
    identifier=uuid4()
    with db.begin_nested():
        db.add(s.FindingDecisionRow(id=str(identifier), matter_id=str(matter_id), run_id=str(run.id),
            finding_id=str(finding_id), run_sha256=value.run_sha256,actor_id=str(actor.user_id),payload=decision.model_dump_json()))
        db.flush()
        for row in db.scalars(select(ExportRow).where(ExportRow.matter_id==str(matter_id))):
            if json.loads(row.payload)['run_id'] == str(run.id): row.superseded=True
        # Approval has no run_id; a changed conclusion invalidates this matter's
        # valid approval candidates without changing facts or case state.
        db.execute(update(ApprovalRow).where(ApprovalRow.matter_id==str(matter_id),
            ApprovalRow.status=='valid').values(status='stale'))
        from ..review.decisions import read_snapshot
        snapshot=read_snapshot(matter_id,run.id,actor,db=db,require_authority=False)
        exports_storage.audit(actor,matter_id,'finding_decided','FINDING_DECISION_RECORDED',db,
            entity_id=identifier,after_hash=snapshot.sha256)
    return {'id':str(identifier),'finding_id':str(finding_id),'decision':decision.model_dump(mode='json')}


def approve_exact_patch(matter_id,value,actor,db):
    authorize(actor,matter_id,'confirm_facts',db)
    run=current_run(matter_id,value.run_id,value.run_sha256,actor,db)
    finding=next((f for f in run.findings if f.id==value.finding_id),None)
    if not finding or value.anchor_id not in (*finding.anchor_ids,*finding.cross_anchor_ids): raise ServiceError('VERSION_CONFLICT',409)
    anchor=None
    for version in current_versions(matter_id,actor,db):
        parsed=get_parse_result(matter_id,version.id,actor,db)
        if parsed:
            parsed=trusted_parse(matter_id,version.id,actor,db,parsed)
            anchor=next((a for a in parsed.anchors if a.id==value.anchor_id),None)
            if anchor:break
    if not anchor:raise ServiceError('VERSION_CONFLICT',409)
    patch=Patch(id=uuid4(),finding_id=value.finding_id,document_version_id=anchor.document_version_id,
        anchor_id=anchor.id,old_text=anchor.quote,new_text=value.new_text,reason=value.reason,
        old_text_sha256=hashlib.sha256(anchor.quote.encode()).hexdigest(),status='proposed',approved_by=None)
    return approvals.approve_patch(matter_id,run.id,patch,actor,db=db,audiences=value.audiences)


def approved_patches(matter_id,ids,actor,db):
    authorize(actor,matter_id,'confirm_facts',db)
    if len(set(ids))!=len(ids):raise ServiceError('VERSION_CONFLICT',409)
    result=[]
    for identifier in ids:
        row=exports_storage.latest('patch_approval',identifier,db)
        if not row or row.matter_id!=str(matter_id):raise ServiceError('CROSS_MATTER_DENIED',403)
        patch=Patch.model_validate(json.loads(row.payload)['patch'])
        result.append(patch)
    return tuple(result)


def read_parties(matter_id,actor,db):
    authorize(actor,matter_id,'read',db)
    seen=set();out=[]
    for row in db.scalars(select(PartyRow).where(PartyRow.matter_id==str(matter_id)).order_by(PartyRow.revision.desc())):
        if row.party_id not in seen:
            seen.add(row.party_id);out.append(Party.model_validate_json(row.payload))
    return tuple(out)


def register_document_party(matter_id,actor,db):
    authorize(actor,matter_id,'candidate_facts',db)
    if read_parties(matter_id,actor,db):return read_parties(matter_id,actor,db)
    # Candidates remain literal original document text, not entity search results.
    versions=current_versions(matter_id,actor,db)
    for version in versions:
        parsed=get_parse_result(matter_id,version.id,actor,db)
        if parsed:
            parsed=trusted_parse(matter_id,version.id,actor,db,parsed)
            first=next((a for a in parsed.anchors if a.quote.strip()),None)
            if first:
                candidate=PartyCandidate(candidate_id=uuid4(),name=first.quote,credit_code=None,
                    source='document_literal_synthetic_candidate')
                resolve_party((candidate,),None,matter_id=matter_id,role='document_party',name_raw=first.quote,actor=actor,db=db)
                break
    return read_parties(matter_id,actor,db)
