"""Explicit append-only technical evidence and authorised immutable run reads."""
from datetime import datetime
import hashlib
import json
from uuid import UUID,uuid4
from sqlalchemy import ForeignKey,Integer,String,Text,select
from sqlalchemy.orm import Mapped,mapped_column
from ..domain import AuditEvent,ReviewRun,ReviewContext
from ..persistence import Base,Database,UTCDateTime,configured_database
from ..security import authorize,ServiceError


class ReviewRunRow(Base):
    __tablename__='review_runs'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    payload:Mapped[str]=mapped_column(Text)
    context_json:Mapped[str]=mapped_column(Text)
    config_json:Mapped[str]=mapped_column(Text)
    processed_json:Mapped[str]=mapped_column(Text)
    timestamp:Mapped[datetime]=mapped_column(UTCDateTime())


class ReviewProposalRow(Base):
    __tablename__='review_proposals'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    run_id:Mapped[str]=mapped_column(ForeignKey('review_runs.id'),unique=True)
    matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    payload:Mapped[str]=mapped_column(Text)
    sha256:Mapped[str]=mapped_column(String(64))
    timestamp:Mapped[datetime]=mapped_column(UTCDateTime())


class FindingDecisionRow(Base):
    __tablename__ = 'web_finding_decisions'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    run_id: Mapped[str] = mapped_column(ForeignKey('review_runs.id'))
    finding_id: Mapped[str] = mapped_column(String(36))
    run_sha256: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    payload: Mapped[str] = mapped_column(Text)


class ModelAttemptRow(Base):
    __tablename__='review_model_attempts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    run_id:Mapped[str]=mapped_column(ForeignKey('review_runs.id'))
    sequence:Mapped[int]=mapped_column(Integer)
    metadata_json:Mapped[str]=mapped_column(Text)
    raw:Mapped[str]=mapped_column(Text)


class ModelOperationRecordRow(Base):
    __tablename__='review_operation_records'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    timestamp:Mapped[datetime]=mapped_column(UTCDateTime())
    phase:Mapped[str]=mapped_column(String(32))
    metadata_json:Mapped[str]=mapped_column(Text)


class OperationAttemptRow(Base):
    __tablename__='review_operation_attempts'
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    record_id:Mapped[str]=mapped_column(ForeignKey('review_operation_records.id'))
    sequence:Mapped[int]=mapped_column(Integer)
    metadata_json:Mapped[str]=mapped_column(Text)
    raw:Mapped[str]=mapped_column(Text)


def initialize_storage(database):
    if not isinstance(database,Database): raise TypeError('explicit Database required')
    tables=[ReviewRunRow.__table__,ReviewProposalRow.__table__,FindingDecisionRow.__table__,ModelAttemptRow.__table__,ModelOperationRecordRow.__table__,OperationAttemptRow.__table__]
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=tables)
        for table in tables:
            for operation in ('UPDATE','DELETE'):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_{table.name}_{operation.lower()} '
                    f'BEFORE {operation} ON {table.name} BEGIN SELECT RAISE(ABORT, \'IMMUTABLE_RECORD\'); END')
    database._review_storage_initialized=True


def require_storage(db):
    if not getattr(configured_database(db),'_review_storage_initialized',False):
        raise RuntimeError('initialize_storage(database) required at server startup')


def _row(matter_id,run_id,actor,db):
    authorize(actor,matter_id,'read',db);require_storage(db)
    row=db.scalar(select(ReviewRunRow).where(ReviewRunRow.id==str(run_id),ReviewRunRow.matter_id==str(matter_id)))
    if row is None: raise ServiceError('CROSS_MATTER_DENIED',403)
    return row


def read_run(matter_id,run_id,actor,*,db,current=True):
    row=_row(matter_id,run_id,actor,db)
    run=ReviewRun.model_validate_json(row.payload)
    if current:
        from .workflow import current_manifest
        ctx=ReviewContext.model_validate_json(row.context_json)
        state=current_manifest(ctx,actor,db,json.loads(row.config_json),allow_finished=True)
        manifest=state[0]
        if manifest!=run.manifest: raise ServiceError('APPROVAL_STALE',409)
        if run.manifest.model_provider=='assisted_manual':
            from .proposals import validate_saved_run
            validate_saved_run(run,row,actor,db,state=state)
    return run


def read_attempts(matter_id,run_id,actor,*,db):
    _row(matter_id,run_id,actor,db)
    return tuple(json.loads(row.metadata_json) for row in db.scalars(select(ModelAttemptRow)
        .where(ModelAttemptRow.run_id==str(run_id)).order_by(ModelAttemptRow.sequence)))


def read_raw(matter_id,run_id,attempt_id,actor,*,db):
    _row(matter_id,run_id,actor,db)
    row=db.scalar(select(ModelAttemptRow).where(ModelAttemptRow.id==str(attempt_id),ModelAttemptRow.run_id==str(run_id)))
    if row is None: raise ServiceError('CROSS_MATTER_DENIED',403)
    if hashlib.sha256(row.raw.encode()).hexdigest()!=json.loads(row.metadata_json)['raw_sha256']:
        raise ServiceError('VERSION_CONFLICT',409)
    return row.raw


def read_execution_records(matter_id,actor,*,db):
    authorize(actor,matter_id,'read',db);require_storage(db)
    records=[]
    for row in db.scalars(select(ModelOperationRecordRow).where(ModelOperationRecordRow.matter_id==str(matter_id))
            .order_by(ModelOperationRecordRow.timestamp,ModelOperationRecordRow.id)):
        metadata=json.loads(row.metadata_json)
        metadata['attempts']=[json.loads(a.metadata_json) for a in db.scalars(select(OperationAttemptRow)
            .where(OperationAttemptRow.record_id==row.id).order_by(OperationAttemptRow.sequence))]
        records.append(metadata)
    return tuple(records)


def read_intakes(matter_id,actor,*,db):
    return tuple(row for row in read_execution_records(matter_id,actor,db=db) if row['phase']=='intake')


def read_operation_raw(matter_id,record_id,attempt_id,actor,*,db):
    authorize(actor,matter_id,'read',db);require_storage(db)
    record=db.scalar(select(ModelOperationRecordRow).where(ModelOperationRecordRow.id==str(record_id),ModelOperationRecordRow.matter_id==str(matter_id)))
    row=db.scalar(select(OperationAttemptRow).where(OperationAttemptRow.id==str(attempt_id),OperationAttemptRow.record_id==str(record_id))) if record else None
    if row is None: raise ServiceError('CROSS_MATTER_DENIED',403)
    if hashlib.sha256(row.raw.encode()).hexdigest()!=json.loads(row.metadata_json)['raw_sha256']:
        raise ServiceError('VERSION_CONFLICT',409)
    return row.raw


def _save_operation_record(matter_id,actor,phase,attempts,error_code,config,db):
    """Server-internal failed/successful operations; never asserts currentness.

    All evidence joins the caller transaction. An outer rollback also rolls this
    back; this local mock transaction is not a real-provider billing guarantee.
    Revocation does not expose raw bytes to the rejected caller.
    """
    from datetime import datetime,timezone
    from ..audit import append_event
    require_storage(db)
    identifier=uuid4();timestamp=datetime.now(timezone.utc)
    with db.begin_nested():
        payload={'id':str(identifier),'phase':phase,'error_code':error_code,'configuration':config}
        db.add(ModelOperationRecordRow(id=str(identifier),matter_id=str(matter_id),actor_id=str(actor.user_id),
            timestamp=timestamp,phase=phase,metadata_json=json.dumps(payload,sort_keys=True)))
        db.flush()
        for sequence,attempt in enumerate(attempts):
            metadata={k:v for k,v in attempt.items() if k!='_raw'}
            db.add(OperationAttemptRow(id=attempt['raw_ref'],record_id=str(identifier),sequence=sequence,
                metadata_json=json.dumps(metadata,sort_keys=True),raw=attempt['_raw']))
        db.flush()
        append_event(AuditEvent(id=uuid4(),matter_id=matter_id,actor_id=actor.user_id,action='intake_saved',
            entity_type='review',entity_id=identifier,before_hash=None,after_hash=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
            timestamp=timestamp,reason=error_code or 'completed',correlation_id=uuid4()),db)
    return identifier


def _save(run,context,config,processed,attempts,actor,db):
    from ..audit import append_event
    require_storage(db)
    db.add(ReviewRunRow(id=str(run.id),matter_id=str(run.matter_id),actor_id=str(actor.user_id),
        payload=run.model_dump_json(),context_json=context.model_dump_json(),config_json=json.dumps(config,sort_keys=True),
        processed_json=json.dumps([str(x) for x in processed]),timestamp=run.finished_at))
    db.flush()
    for sequence,attempt in enumerate(attempts):
        raw=attempt.pop('_raw')
        db.add(ModelAttemptRow(id=attempt['raw_ref'],run_id=str(run.id),sequence=sequence,
            metadata_json=json.dumps(attempt,sort_keys=True),raw=raw))
    db.flush()
    append_event(AuditEvent(id=uuid4(),matter_id=run.matter_id,actor_id=actor.user_id,
        action='review_saved',entity_type='review',entity_id=run.id,before_hash=None,
        after_hash=hashlib.sha256(run.model_dump_json().encode()).hexdigest(),timestamp=run.finished_at,
        reason=run.status,correlation_id=uuid4()),db)
