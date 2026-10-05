"""Authorized stable reduction of append-only decisions; original runs stay intact."""
import hashlib
import json
from uuid import UUID
from sqlalchemy import select

from ..domain import Finding, HumanDecision, FindingDecisionRecord, ReviewDecisionSnapshot, ReviewDecisionAuthorityStatus
from ..persistence import UserRow, MembershipRow
from ..security import ServiceError
from .storage import read_run, ReviewRunRow, FindingDecisionRow


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def resolved(finding):
    """Pure counterpart also honors HumanDecision already present on a finding."""
    decision = finding.human_decision
    if decision and decision.decision == 'edit' and not decision.pending_edit:
        return Finding.model_validate({**finding.model_dump(mode='python'),
            'analysis': decision.edited_analysis, 'recommendation': decision.edited_recommendation,
            'replacement_text': decision.edited_replacement_text})
    return finding


def disposition(finding):
    decision = finding.human_decision
    return ('pending_edit' if decision.pending_edit else decision.decision.value) if decision else 'unreviewed'


def read_history(matter_id, run_id, actor, *, db):
    run = read_run(matter_id, run_id, actor, db=db, current=True)
    digest = sha(run.model_dump(mode='json')); findings = {f.id for f in run.findings}
    records = []
    # Query by globally unique run, then verify matter too; never silently omit
    # a corrupt cross-case binding from a purportedly valid snapshot.
    for row in db.scalars(select(FindingDecisionRow).where(FindingDecisionRow.run_id == str(run_id))
                          .order_by(FindingDecisionRow.sequence)):
        try:
            decision = HumanDecision.model_validate_json(row.payload)
            record = FindingDecisionRecord(id=UUID(row.id), sequence=row.sequence, matter_id=UUID(row.matter_id),
                run_id=UUID(row.run_id), finding_id=UUID(row.finding_id), run_sha256=row.run_sha256, decision=decision)
            if record.matter_id != matter_id or record.finding_id not in findings or row.run_sha256 != digest or row.actor_id != str(decision.actor_id):
                raise ValueError('decision binding differs')
        except (ValueError, TypeError):
            raise ServiceError('APPROVAL_STALE', 409) from None
        records.append(record)
    return run, tuple(records)


def read_snapshot(matter_id, run_id, actor, *, db, require_authority=True):
    """Server-owned structural snapshot; delivery callers always use the default.

    Only internal record/recovery reads skip the live author gate. This option
    is not accepted from HTTP inputs and never changes historical decisions.
    """
    run, history = read_history(matter_id, run_id, actor, db=db)
    latest = {record.finding_id: record for record in history}
    ordered = tuple(sorted(latest.values(), key=lambda record: record.sequence))
    findings = tuple(resolved(Finding.model_validate({**finding.model_dump(mode='python'),
        'human_decision': latest[finding.id].decision}) if finding.id in latest else finding) for finding in run.findings)
    row = db.get(ReviewRunRow, str(run_id), populate_existing=True)
    payload = {'matter_id': str(matter_id), 'run_id': str(run_id), 'run_sha256': sha(run.model_dump(mode='json')),
        'version': history[-1].sequence if history else 0,
        'ordered_decisions': [r.model_dump(mode='json') for r in ordered],
        'resolved_findings': [f.model_dump(mode='json') for f in findings],
        'actor_id': str(history[-1].decision.actor_id) if history else row.actor_id,
        'timestamp': (history[-1].decision.decided_at if history else (run.finished_at or row.timestamp)).isoformat()}
    # Normalize UTC serialization before hashing, consistently with the DTO.
    from ..domain import UTCDatetime
    from pydantic import TypeAdapter
    payload['timestamp'] = TypeAdapter(UTCDatetime).dump_python(TypeAdapter(UTCDatetime).validate_python(payload['timestamp']), mode='json')
    snapshot=ReviewDecisionSnapshot.model_validate({**payload, 'sha256': sha(payload)})
    if require_authority and read_authority(snapshot,db=db).status!='current':
        raise ServiceError('APPROVAL_STALE',409)
    return snapshot


def read_authority(snapshot, *, db):
    """Live view of the server snapshot, separate from its stable content hash.

    Every historical object's binding is checked by read_snapshot. Current
    qualification belongs to the latest effective records, without falling
    back to earlier advice. Recording a partial correction must remain possible
    while other effective findings still block delivery.
    """
    recheck=[]
    for record in snapshot.ordered_decisions:
        user_id=str(record.decision.actor_id)
        user=db.get(UserRow,user_id,populate_existing=True)
        member=db.get(MembershipRow,(str(snapshot.matter_id),user_id),populate_existing=True)
        if not user or user.disabled or not member or not set(json.loads(user.roles)) & {'handling_lawyer','reviewing_lawyer'}:
            recheck.append(record.finding_id)
    return ReviewDecisionAuthorityStatus(matter_id=snapshot.matter_id,run_id=snapshot.run_id,
        decision_snapshot_sha256=snapshot.sha256,status='recheck_required' if recheck else 'current',
        recheck_finding_ids=tuple(recheck))


def finding_fingerprint(snapshot, finding_id):
    finding = next((f for f in snapshot.resolved_findings if f.id == finding_id), None)
    if finding is None: raise ServiceError('APPROVAL_STALE', 409)
    record = next((r for r in snapshot.ordered_decisions if r.finding_id == finding_id), None)
    return sha({'matter_id': str(snapshot.matter_id), 'run_id': str(snapshot.run_id),
        'run_sha256': snapshot.run_sha256, 'finding_id': str(finding_id),
        'decision': record.model_dump(mode='json') if record else None,
        'original_decision': finding.human_decision.model_dump(mode='json') if finding.human_decision else None})


def check_patch_disposition(snapshot, patch):
    finding = next((f for f in snapshot.resolved_findings if f.id == patch.finding_id), None)
    return check_finding_patch_disposition(finding,patch)


def check_finding_patch_disposition(finding, patch):
    if finding is None or disposition(finding) in {'reject','pending_edit','request_info','refer'}:
        raise ServiceError('APPROVAL_STALE', 409)
    if disposition(finding) == 'edit' and (finding.replacement_text is None or finding.replacement_text != patch.new_text):
        raise ServiceError('APPROVAL_STALE', 409)
    return finding
