"""Registered case candidates, explicit human selection, zero external requests."""
from datetime import datetime, timezone
import hashlib
from uuid import uuid4
from sqlalchemy import select
from ..audit import append_event
from ..domain import AuditEvent, Party, PartyCandidate, PartyDecision
from ..persistence import read_matter, party_material_changed
from ..security import ServiceError, authorize
from .storage import PartyRow, PartyDecisionRow, require_storage


def resolve_party(candidates, decision, *, matter_id, role, name_raw, actor, db, party_id=None):
    """First register candidates with no decision; later select current saved evidence.

    party_id is server-issued on registration. Caller evidence must exactly match
    current evidence for a decision; new lists must be registered separately.
    Candidate UUIDs never become authoritative company entity UUIDs.
    """
    authorize(actor,matter_id,'confirm_facts' if decision is not None else 'candidate_facts',db)
    require_storage(db)
    matter = read_matter(matter_id,actor,db)
    if matter.status == 'archived':
        raise ServiceError('STATE_CONFLICT',409)
    cs = tuple(PartyCandidate.model_validate(c.model_dump(mode='python')) for c in candidates)
    if len({c.candidate_id for c in cs}) != len(cs):
        raise ValueError('duplicate candidate IDs')
    previous_row = None
    previous = None
    if party_id is not None:
        previous_row = db.scalar(select(PartyRow).where(PartyRow.matter_id==str(matter_id),
            PartyRow.party_id==str(party_id)).order_by(PartyRow.revision.desc()).limit(1))
        if previous_row is None:
            raise ServiceError('VERSION_CONFLICT',409)
        previous = Party.model_validate_json(previous_row.payload)
        if previous.role != role or previous.name_raw != name_raw:
            raise ServiceError('VERSION_CONFLICT',409)
    elif decision is not None:
        raise ServiceError('VERSION_CONFLICT',409)
    selected = None
    if decision is not None:
        decision = PartyDecision.model_validate(decision.model_dump(mode='python'))
        if decision.confirmed_by != actor.user_id:
            raise ServiceError('CROSS_MATTER_DENIED',403)
        if cs != previous.candidate_evidence:
            raise ServiceError('VERSION_CONFLICT',409)
        selected = next((c for c in cs if c.candidate_id==decision.selected_candidate_id),None)
        if selected is None:
            raise ServiceError('VERSION_CONFLICT',409)
    party = Party(id=previous.id if previous else uuid4(),matter_id=matter_id,role=role,name_raw=name_raw,
        name_confirmed=selected.name if selected else None,credit_code=selected.credit_code if selected else None,
        entity_id=None,resolution_status='confirmed' if selected else ('ambiguous' if len(cs)>1 else 'unresolved'),
        candidate_evidence=cs,confirmed_by=actor.user_id if selected else None)
    now = datetime.now(timezone.utc)
    revision = previous_row.revision+1 if previous_row else 1
    digest = hashlib.sha256(party.model_dump_json().encode()).hexdigest()
    with db.begin_nested():
        db.add(PartyRow(matter_id=str(matter_id),party_id=str(party.id),revision=revision,record_id=str(uuid4()),
            actor_id=str(actor.user_id),timestamp=now,payload=party.model_dump_json(),sha256=digest))
        db.flush()
        if decision:
            db.add(PartyDecisionRow(id=str(uuid4()),matter_id=str(matter_id),party_id=str(party.id),
                source_revision=previous_row.revision,target_revision=revision,actor_id=str(actor.user_id),
                timestamp=now,payload=decision.model_dump_json(),before_hash=previous_row.sha256,after_hash=digest))
        party_material_changed(matter_id,actor,db)
        append_event(AuditEvent(id=uuid4(),matter_id=matter_id,actor_id=actor.user_id,action='party_changed',
            entity_type='party',entity_id=party.id,before_hash=previous_row.sha256 if previous_row else None,
            after_hash=digest,timestamp=now,reason=decision.reason if decision else 'candidate_registration',correlation_id=uuid4()),db)
        db.flush()
    return party
