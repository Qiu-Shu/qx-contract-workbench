"""Protected HTTP job inputs and append-only decisions/events; explicit startup."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from ..domain import Actor, JobStatus, HumanDecision
from ..persistence import Base, Database, UTCDateTime, SessionRow, DocumentRow, read_matter
from ..security import ServiceError, authorize, _principal
from ..review.storage import FindingDecisionRow
from ..record_codec import now, encode, sha


class JobRow(Base):
    __tablename__ = 'web_jobs'
    __table_args__ = (UniqueConstraint('matter_id', 'actor_id', 'kind', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id'))
    kind: Mapped[str] = mapped_column(String(20))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    input_sha256: Mapped[str] = mapped_column(String(64))
    matter_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20))
    stage: Mapped[str] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(80))
    result_ref: Mapped[str | None] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


class JobEventRow(Base):
    __tablename__ = 'web_job_events'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('web_jobs.id'))
    state: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(80))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


class HttpWriteRow(Base):
    __tablename__='web_http_writes'
    __table_args__=(UniqueConstraint('matter_scope','actor_id','action','idempotency_key'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    matter_scope:Mapped[str]=mapped_column(String(36))
    response_matter_id:Mapped[str]=mapped_column(ForeignKey('matters.id'))
    actor_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    action:Mapped[str]=mapped_column(String(128))
    idempotency_key:Mapped[str]=mapped_column(String(128))
    request_sha256:Mapped[str]=mapped_column(String(64))
    response_matter_sha256:Mapped[str]=mapped_column(String(64))
    payload:Mapped[str]=mapped_column(Text)


def initialize_storage(database):
    if not isinstance(database, Database): raise TypeError('explicit Database required')
    tables = [JobRow.__table__, JobEventRow.__table__, FindingDecisionRow.__table__,HttpWriteRow.__table__]
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection, tables=tables)
        for table in ('web_job_events', 'web_finding_decisions','web_http_writes'):
            for operation in ('UPDATE', 'DELETE'):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} '
                    f'BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, \'IMMUTABLE_RECORD\'); END')
        connection.exec_driver_sql('CREATE TRIGGER IF NOT EXISTS immutable_web_job_input BEFORE UPDATE OF '
            'id,matter_id,actor_id,session_id,kind,idempotency_key,input_sha256,matter_sha256,payload,timestamp ON web_jobs '
            "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS immutable_web_job_delete BEFORE DELETE ON web_jobs BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._web_storage_initialized = True


def require_storage(database):
    if not getattr(database, '_web_storage_initialized', False):
        raise RuntimeError('initialize_storage(database) required explicitly')


def fingerprint(matter_id, actor, db):
    matter = read_matter(matter_id, actor, db)
    versions = list(db.scalars(select(DocumentRow).where(DocumentRow.matter_id == str(matter_id))))
    old = {r.supersedes_id for r in versions if r.supersedes_id}
    return sha({'matter': matter.model_dump(mode='json', exclude={'status'}),
                'documents': sorted((r.id, r.sha256) for r in versions if r.id not in old)})


def valid_actor(row, db):
    actor = _principal(db.get(SessionRow, row.session_id, populate_existing=True), db, user_id=UUID(row.actor_id))
    if actor is None: raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    authorize(actor, UUID(row.matter_id), {'parse':'upload','reparse':'confirm_facts','review':'review','query':'confirm_facts'}[row.kind], db)
    return actor


def status(row):
    # Domain JobStatus deliberately carries no case or sensitive job parameters.
    return JobStatus(id=UUID(row.id), state=row.state, stage=row.stage,
                     error_code=row.error_code, result_ref=row.result_ref)


def event(row, db):
    db.add(JobEventRow(job_id=row.id, state=row.state, error_code=row.error_code, timestamp=now()))
    db.flush()


def find_idempotent(matter_id, actor, kind, key, digest, db):
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii() or any(ord(c)<33 or ord(c)>126 for c in key):
        raise ServiceError('STATE_CONFLICT', 422)
    row = db.scalar(select(JobRow).where(JobRow.matter_id == str(matter_id), JobRow.actor_id == str(actor.user_id),
        JobRow.kind == kind, JobRow.idempotency_key == key))
    if row and row.input_sha256 != digest: raise ServiceError('VERSION_CONFLICT', 409)
    return row


def enqueue(matter_id, actor, kind, key, payload, db, *, digest=None):
    digest = digest or sha(payload)
    previous = find_idempotent(matter_id, actor, kind, key, digest, db)
    if previous: return previous
    actual_fingerprint=fingerprint(matter_id,actor,db)
    with db.begin_nested():
        row = JobRow(id=str(uuid4()), matter_id=str(matter_id), actor_id=str(actor.user_id), session_id=str(actor.session_id),
            kind=kind, idempotency_key=key, input_sha256=digest, matter_sha256=actual_fingerprint,
            payload=encode(payload), state='queued', stage='已排队', error_code=None, result_ref=None, timestamp=now())
        db.add(row); db.flush(); event(row, db)
    return row


def get_job(job_id, actor, *, database):
    with database.session() as db:
        row = db.get(JobRow, str(job_id))
        if row is None:
            # Unknown IDs and unrelated IDs share the same response.
            authorize(actor, UUID(int=0), 'read', db)
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        authorize(actor, UUID(row.matter_id), 'read', db)
        return status(row)
