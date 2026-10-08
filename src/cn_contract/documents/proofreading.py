"""Append-only lawyer source statements, distinct from parser/OCR evidence."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from ..domain import Fact, FactSnapshot, PageVerification, PageVerificationInput
from ..persistence import (Base, UTCDateTime, read_matter, read_version, read_original,
    get_parse_result, get_fact_snapshot, save_fact_snapshot, fact_snapshot_sha256)
from ..review.proposals import digest, require_policy
from ..security import ServiceError, authorize


class PageVerificationRow(Base):
    __tablename__ = 'page_verifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


def initialize_storage(database):
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[PageVerificationRow.__table__])
        for operation in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_page_verifications_{operation.lower()} '
                f"BEFORE {operation} ON page_verifications BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")


def _document(matter_id, value, actor, db):
    from ..web.services import current_versions
    policy = require_policy(db)
    from ..persistence import DocumentRow
    row=db.get(DocumentRow,str(value.document_version_id))
    if row is None or row.matter_id!=str(matter_id): raise ServiceError('CROSS_MATTER_DENIED',403)
    version = read_version(matter_id, value.document_version_id, actor, db)
    current = current_versions(matter_id, actor, db)
    if version.id not in {v.id for v in current} or version.sha256 != value.document_sha256:
        raise ServiceError('VERSION_CONFLICT',409)
    if any(v.sha256 not in policy.document_hashes for v in current):
        raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    if version.mime != 'application/pdf': raise ServiceError('FILE_UNSUPPORTED',415)
    read_original(matter_id,version.id,actor,db)
    from ..facts.storage import trusted_parse
    parsed = get_parse_result(matter_id,version.id,actor,db)
    if parsed is None: raise ServiceError('FACTS_UNCONFIRMED',409)
    parsed = trusted_parse(matter_id,version.id,actor,db,parsed)
    if value.page not in parsed.pages: raise ServiceError('VERSION_CONFLICT',409)


def history(matter_id, actor, db):
    authorize(actor,matter_id,'read',db)
    result=[]
    for row in db.scalars(select(PageVerificationRow).where(PageVerificationRow.matter_id==str(matter_id))
                          .order_by(PageVerificationRow.created_at,PageVerificationRow.id)):
        record=PageVerification.model_validate_json(row.payload)
        if (record.sha256 != digest(record.model_dump(mode='json',exclude={'sha256'}))
            or record.sha256!=row.sha256 or str(record.id)!=row.id or str(record.matter_id)!=row.matter_id
            or str(record.actor_id)!=row.actor_id or record.created_at!=row.created_at):
            raise ServiceError('VERSION_CONFLICT',409)
        result.append(record)
    return tuple(result)


def read_current_verification(matter_id, identifier, actor, db):
    records=history(matter_id,actor,db)
    record=next((r for r in records if r.id==identifier),None)
    if record is None or any(r.input.previous_id==identifier for r in records):
        raise ServiceError('VERSION_CONFLICT',409)
    _document(matter_id,record.input,actor,db)
    _candidate(matter_id,record.input,actor,db)
    return record


def _candidate(matter_id,value,actor,db):
    if value.candidate_id is None:return
    from .ocr_candidates import read_candidate
    candidate=read_candidate(matter_id,value.candidate_id,actor,db)
    source=candidate.result.source
    if (candidate.sha256!=value.candidate_sha256 or source.document_version_id!=value.document_version_id
        or source.document_sha256!=value.document_sha256 or source.page!=value.page):
        raise ServiceError('VERSION_CONFLICT',409)


def submit_page_verification(matter_id, value, actor, db):
    authorize(actor,matter_id,'confirm_facts',db)
    from ..ops.storage import require_active
    require_active(db)
    value=PageVerificationInput.model_validate_json(value.model_dump_json())
    _document(matter_id,value,actor,db)
    matter=read_matter(matter_id,actor,db)
    if matter.status=='archived' or matter.active_fact_version!=value.fact_version:
        raise ServiceError('VERSION_CONFLICT',409)
    _candidate(matter_id,value,actor,db)
    records=history(matter_id,actor,db)
    same=[r for r in records if (r.input.document_version_id,r.input.page,r.input.field)==
          (value.document_version_id,value.page,value.field)]
    latest=next((r for r in same if not any(other.input.previous_id==r.id for other in same)),None)
    if value.previous_id!=(latest.id if latest else None): raise ServiceError('VERSION_CONFLICT',409)
    identifier,fact_id=uuid4(),uuid4()
    payload=dict(id=identifier,matter_id=matter_id,fact_id=fact_id,actor_id=actor.user_id,
                 created_at=datetime.now(timezone.utc),input=value)
    # Pydantic's typed JSON encoding is the persisted hash contract.
    temporary=PageVerification(**payload,sha256='0'*64)
    record=PageVerification(**payload,sha256=digest(temporary.model_dump(mode='json',exclude={'sha256'})))
    previous=get_fact_snapshot(matter_id,value.fact_version,actor,db)
    old=[f for f in previous.facts if not latest or latest.id not in f.verification_ids]
    fresh=Fact(id=fact_id,matter_id=matter_id,version=value.fact_version+1,field=value.field,
        typed_value=value.typed_value,unit=value.unit,provenance_type='source_verification',anchor_ids=(),receipt_ids=(),
        verification_ids=(identifier,),confirmation_status='unconfirmed',confirmed_by=None,confirmed_at=None)
    facts=tuple(Fact.model_validate({**f.model_dump(mode='python'),'version':value.fact_version+1,
        'confirmation_status':'unconfirmed','confirmed_by':None,'confirmed_at':None}) for f in (*old,fresh))
    if len(facts)>256: raise ServiceError('FILE_LIMIT',413)
    snapshot=FactSnapshot(version=value.fact_version+1,facts=facts,sha256=fact_snapshot_sha256(facts))
    with db.begin_nested():
        db.add(PageVerificationRow(id=str(identifier),matter_id=str(matter_id),actor_id=str(actor.user_id),
            created_at=record.created_at,payload=record.model_dump_json(),sha256=record.sha256))
        db.flush()
        save_fact_snapshot(matter_id,snapshot,actor,db)
        authorize(actor,matter_id,'confirm_facts',db)
    return record


def require_verified_fact(matter_id,fact,actor,db):
    if len(fact.verification_ids)!=1: raise ServiceError('VERSION_CONFLICT',409)
    record=read_current_verification(matter_id,fact.verification_ids[0],actor,db)
    if (record.fact_id!=fact.id or record.input.field!=fact.field or record.input.typed_value!=fact.typed_value
        or record.input.unit!=fact.unit or fact.anchor_ids or fact.receipt_ids):
        raise ServiceError('VERSION_CONFLICT',409)
    return record
