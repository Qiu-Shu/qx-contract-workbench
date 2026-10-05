"""Current working-draft bytes acknowledged by a case lawyer; never signoff."""
from uuid import UUID, uuid4

from .. import domain as d
from ..security import ServiceError
from ..review.proposals import require_assisted_policy
from ..review.decisions import read_snapshot, disposition
from . import storage as s
from .approvals import _bundle, download_artifact

KIND = 'working_draft_confirmation'


def _artifact_rows(bundle, actor, db):
    # Reuse the actual download gate as well as frozen bundle bytes: a mutable
    # artifact row may have been superseded or may differ from that bundle.
    for artifact in bundle.artifacts:
        download_artifact(artifact.id, actor, db=db)


def _current(matter_id, bundle_id, actor, db):
    s.authorize(actor, matter_id, db, write=True)
    require_assisted_policy(db)
    bundle, run = _bundle(bundle_id, actor, db)
    if bundle.matter_id != matter_id:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    _artifact_rows(bundle, actor, db)
    snapshot = read_snapshot(matter_id, run.id, actor, db=db)
    if any(disposition(f) in {'unreviewed', 'pending_edit'} for f in snapshot.resolved_findings):
        raise ServiceError('STATE_CONFLICT', 409)
    unresolved = tuple(f.id for f in snapshot.resolved_findings
        if disposition(f) in {'request_info', 'refer'})
    return bundle, snapshot, unresolved


def confirm_working_draft(matter_id, value, actor, *, db):
    value = d.WorkingDraftConfirmationInput.model_validate_json(value.model_dump_json())
    bundle, snapshot, unresolved = _current(matter_id, value.bundle_id, actor, db)
    if (value.bundle_manifest_sha256 != bundle.manifest_sha256
            or value.decision_snapshot_sha256 != snapshot.sha256 or value.audience != bundle.audience):
        raise ServiceError('VERSION_CONFLICT', 409)
    if (len(set(value.acknowledged_unresolved_finding_ids)) != len(value.acknowledged_unresolved_finding_ids)
            or set(value.acknowledged_unresolved_finding_ids) != set(unresolved)):
        raise ServiceError('STATE_CONFLICT', 409)
    receipt = d.WorkingDraftConfirmation(id=uuid4(), matter_id=matter_id, run_id=bundle.run_id,
        bundle_id=bundle.id, bundle_manifest_sha256=bundle.manifest_sha256,
        decision_snapshot_sha256=snapshot.sha256, audience=bundle.audience,
        artifact_hashes={a.id: a.content_sha256 for a in bundle.artifacts},
        acknowledged_unresolved_finding_ids=unresolved, reason=value.reason,
        actor_id=actor.user_id, confirmed_at=s.now(), purpose='working_draft', formal_signoff=False)
    with db.begin_nested():
        row = s.append(KIND, receipt.id, receipt.model_dump(mode='json'), actor, matter_id, db)
        s.audit(actor, matter_id, 'working_draft_confirmed', 'SPECIFIC_WORKING_DRAFT_ACKNOWLEDGED', db,
            entity_id=receipt.id, after_hash=row.sha256)
        # Re-enter actual artifact/current decision/authority checks before commit.
        read_working_draft_confirmation(matter_id, receipt.id, actor, db=db)
    return receipt


def read_working_draft_confirmation(matter_id, identifier, actor, *, db):
    s.authorize(actor, matter_id, db)
    require_assisted_policy(db)
    row = s.latest(KIND, identifier, db)
    if not row or row.matter_id != str(matter_id):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    try:
        receipt = d.WorkingDraftConfirmation.model_validate_json(row.payload)
        if (receipt.id != identifier or receipt.matter_id != matter_id
                or str(receipt.actor_id) != row.actor_id):
            raise ValueError('receipt binding differs')
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    if not s.approver_valid(receipt.actor_id, matter_id, db):
        raise ServiceError('APPROVAL_STALE', 409)
    # Readers retain existing member read rights; confirming remains a lawyer
    # write. Bundle checks still include latest decision-author qualification.
    bundle, run = _bundle(receipt.bundle_id, actor, db)
    _artifact_rows(bundle, actor, db)
    snapshot = read_snapshot(matter_id, run.id, actor, db=db)
    unresolved = tuple(f.id for f in snapshot.resolved_findings
        if disposition(f) in {'request_info', 'refer'})
    if (bundle.matter_id != matter_id or bundle.run_id != receipt.run_id
            or bundle.manifest_sha256 != receipt.bundle_manifest_sha256
            or snapshot.sha256 != receipt.decision_snapshot_sha256 or bundle.audience != receipt.audience
            or dict(receipt.artifact_hashes) != {a.id: a.content_sha256 for a in bundle.artifacts}
            or unresolved != receipt.acknowledged_unresolved_finding_ids):
        raise ServiceError('APPROVAL_STALE', 409)
    return receipt
