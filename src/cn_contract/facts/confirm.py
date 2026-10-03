"""Human decisions advance complete snapshots atomically; originals stay immutable."""
from datetime import datetime, timezone
from uuid import uuid4
from ..domain import Fact, FactDecision, FactSnapshot
from sqlalchemy import select
from ..persistence import (read_matter, get_fact_snapshot, save_fact_snapshot, fact_snapshot_sha256,
    DocumentRow, ParseRow)
from ..domain import ParseResult
from ..security import ServiceError, authorize
from .storage import FactDecisionRow, require_storage, trusted_parse


def confirm_facts(matter_id, version, decisions, actor, *, db):
    """version is expected current fact version; a successful decision appends +1."""
    authorize(actor,matter_id,'confirm_facts',db)
    require_storage(db)
    matter = read_matter(matter_id,actor,db)
    if matter.status == 'archived':
        raise ServiceError('STATE_CONFLICT',409)
    if type(version) is not int or version != matter.active_fact_version:
        raise ServiceError('VERSION_CONFLICT',409)
    previous = get_fact_snapshot(matter_id,version,actor,db)
    validated = [FactDecision.model_validate(d.model_dump(mode='python')) for d in decisions]
    if not validated or len({d.fact_id for d in validated}) != len(validated):
        raise ServiceError('STATE_CONFLICT',409)
    old = {f.id:f for f in previous.facts}
    # Snapshot storage accepts candidate DTOs directly, so confirmation is a
    # separate trust boundary. Only latest saved parses of this case's immutable
    # document versions may supply anchors; receipts have no trusted store yet.
    anchors = set()
    seen_versions = set()
    rows = db.execute(select(ParseRow,DocumentRow.id).join(DocumentRow,
        ParseRow.document_version_id==DocumentRow.id).where(DocumentRow.matter_id==str(matter_id))
        .order_by(ParseRow.id.desc())).all()
    for row,document_id in rows:
        if document_id in seen_versions:
            continue
        seen_versions.add(document_id)
        parsed = ParseResult.model_validate_json(row.payload)
        if str(parsed.version_id)!=document_id:
            raise ServiceError('VERSION_CONFLICT',409)
        trusted_parse(matter_id,parsed.version_id,actor,db,parsed)
        anchors.update(a.id for a in parsed.anchors)
    for fact in previous.facts:
        if fact.provenance_type=='external' or fact.receipt_ids:
            raise ServiceError('NOT_SUPPORTED',409)
        if (len(set(fact.anchor_ids))!=len(fact.anchor_ids)
            or not set(fact.anchor_ids).issubset(anchors)
            or (fact.provenance_type=='document' and not fact.anchor_ids)):
            raise ServiceError('VERSION_CONFLICT',409)
    for decision in validated:
        fact = old.get(decision.fact_id)
        if fact is None or fact.matter_id != matter_id or fact.version != version:
            raise ServiceError('VERSION_CONFLICT',409)
        if decision.confirmed_value.kind != fact.typed_value.kind:
            raise ValueError('correction must preserve value kind and unit')
        if decision.decision != 'corrected' and decision.confirmed_value != fact.typed_value:
            raise ValueError('confirmed/rejected cannot change candidate value')
    chosen = {d.fact_id:d for d in validated}
    now = datetime.now(timezone.utc)
    facts = []
    for fact in previous.facts:
        payload = fact.model_dump(mode='python')
        payload['version'] = version+1
        decision = chosen.get(fact.id)
        if decision:
            payload.update(typed_value=decision.confirmed_value.model_dump(mode='python'),
                confirmation_status=decision.decision,confirmed_by=actor.user_id,confirmed_at=now)
        facts.append(Fact.model_validate(payload))
    snapshot = FactSnapshot(version=version+1,facts=tuple(facts),sha256=fact_snapshot_sha256(facts))
    with db.begin_nested():
        save_fact_snapshot(matter_id,snapshot,actor,db)
        db.flush()  # decision foreign keys reference the new snapshot
        for decision in validated:
            db.add(FactDecisionRow(id=str(uuid4()),matter_id=str(matter_id),source_version=version,
                target_version=version+1,fact_id=str(decision.fact_id),actor_id=str(actor.user_id),
                timestamp=now,payload=decision.model_dump_json()))
        db.flush()
    return snapshot
