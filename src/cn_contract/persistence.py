"""SQLite pilot persistence. Configure a Database explicitly; no default DB exists.

Service functions join the caller's transaction. Database.session commits only on
success; rollback removes originals created by that transaction. SQLite transactions
use BEGIN IMMEDIATE to serialize quota checks for the supported single-instance pilot.
Provisioning functions are server administration primitives, never client routes.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import (Boolean, ForeignKey, ForeignKeyConstraint, Integer, String,
                        Text, UniqueConstraint, create_engine, event, select, update)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import Settings, canonical_json
from .domain import (Actor, Approval, AuditEvent, DocumentVersion, ExportArtifact,
                     FactSnapshot, Matter, MatterStatus, ParseResult, ParseStatus, Position, VersionInput)


class UTCDateTime(TypeDecorator):
    """SQLite stores canonical aware UTC ISO text, never local naive times."""
    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('aware timestamp required')
        return value.astimezone(timezone.utc).isoformat()

    def process_result_value(self, value, dialect):
        return datetime.fromisoformat(value).astimezone(timezone.utc) if value else None


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    roles: Mapped[str] = mapped_column(Text)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class SessionRow(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class MatterRow(Base):
    __tablename__ = 'matters'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40))
    payload: Mapped[str] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)


class MembershipRow(Base):
    __tablename__ = 'matter_memberships'
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    can_sign: Mapped[bool] = mapped_column(Boolean, default=False)


class DocumentRow(Base):
    __tablename__ = 'document_versions'
    __table_args__ = (
        UniqueConstraint('matter_id', 'id'),
        ForeignKeyConstraint(['matter_id', 'supersedes_id'],
                             ['document_versions.matter_id', 'document_versions.id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    uploaded_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    supersedes_id: Mapped[str | None] = mapped_column(String(36))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)


class AuditRow(Base):
    __tablename__ = 'audit_events'
    # These IDs are attack/evidence targets, not business references. A denial may
    # target a nonexistent case or user; do not create that case to record it.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ParseRow(Base):
    __tablename__ = 'parse_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_version_id: Mapped[str] = mapped_column(ForeignKey('document_versions.id'))
    payload: Mapped[str] = mapped_column(Text)


class FactSnapshotRow(Base):
    __tablename__ = 'fact_snapshots'
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class ApprovalRow(Base):
    """Foundation only; no T02 endpoint creates a formal Approval."""
    __tablename__ = 'approvals'
    __table_args__ = (UniqueConstraint('matter_id', 'id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    approver_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(20))
    payload: Mapped[str] = mapped_column(Text)


class ExportRow(Base):
    """Status foundation; artifact bytes/issuance are supplied and checked in T09."""
    __tablename__ = 'exports'
    __table_args__ = (ForeignKeyConstraint(['matter_id', 'approval_id'], ['approvals.matter_id', 'approvals.id']),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    approval_id: Mapped[str | None] = mapped_column(String(36))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[str] = mapped_column(Text)


def _remove_created(path: Path, root: Path):
    """Remove only this transaction's checked original; never recurse."""
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError('unsafe original cleanup path')
    if path.exists():
        path.chmod(stat.S_IREAD | stat.S_IWRITE)
        path.unlink()
    if path.parent.exists() and not any(path.parent.iterdir()):
        path.parent.rmdir()


class Database:
    def __init__(self, url: str, storage_root: Path, settings: Settings):
        if not url.startswith('sqlite:'):
            raise ValueError('T02 supports local SQLite only; migration requires review')
        # model_copy does not validate Pydantic values or recompute private hashes.
        self.settings = Settings.model_validate(settings.model_dump(mode='python'))
        self.settings._config_sha256 = hashlib.sha256(
            canonical_json(self.settings.model_dump(mode='python')).encode('utf-8')).hexdigest()
        self.storage_root = Path(storage_root).resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 15})

        @event.listens_for(self.engine, 'connect')
        def configure_connection(connection, record):
            connection.isolation_level = None
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=15000')

        @event.listens_for(self.engine, 'begin')
        def serialize(connection):
            connection.exec_driver_sql('BEGIN IMMEDIATE')

        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            for table in ('document_versions', 'audit_events', 'parse_snapshots', 'fact_snapshots'):
                for operation in ('UPDATE', 'DELETE'):
                    connection.exec_driver_sql(
                        f'CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} '
                        f'BEFORE {operation} ON {table} BEGIN '
                        "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False,
                                           info={'database': self})

    @contextmanager
    def session(self):
        with self.session_factory() as db:
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise


@event.listens_for(Session, 'after_commit')
def _committed(db):
    transaction = db.get_nested_transaction() or db.get_transaction()
    if transaction is not None:
        db.info.setdefault('committed_original_transactions', set()).add(transaction)


@event.listens_for(Session, 'after_transaction_end')
def _transaction_ended(db, transaction):
    # Flush may create an internal child transaction; it is not a savepoint and
    # never owns an original. Real ownership belongs to the root or nested scope.
    if transaction.parent is not None and not transaction.nested:
        return
    owners = db.info.setdefault('originals_by_transaction', {})
    paths = owners.pop(transaction, [])
    committed = db.info.setdefault('committed_original_transactions', set())
    if transaction in committed:
        committed.remove(transaction)
        if transaction.parent is not None:
            # A RELEASE SAVEPOINT is still uncommitted until its parent commits.
            owners.setdefault(transaction.parent, []).extend(paths)
    else:
        # Also runs for Session.close(), which silently rolls back its connection
        # without firing the explicit after_rollback event.
        for path, root in paths:
            _remove_created(path, root)


def _remember_original(db: Session, path: Path, root: Path):
    transaction = db.get_nested_transaction() or db.get_transaction()
    if transaction is None:
        raise RuntimeError('original registration requires an active transaction')
    db.info.setdefault('originals_by_transaction', {}).setdefault(transaction, []).append((path, root))


def configured_database(db: Session) -> Database:
    database = db.info.get('database')
    if not isinstance(database, Database):
        raise RuntimeError('Database/session_factory must be explicitly configured')
    return database


def provision_matter(matter: Matter, db: Session) -> None:
    """Server provisioning only. Every initial member must be an existing user."""
    db.add(MatterRow(id=str(matter.id), title=matter.title, status=matter.status,
                     payload=matter.model_dump_json(), file_count=0, total_bytes=0))
    db.flush()
    for identifier in matter.member_ids:
        db.add(MembershipRow(matter_id=str(matter.id), user_id=str(identifier), can_sign=False))
    db.flush()


def read_matter(matter_id: UUID, actor: Actor, db: Session) -> Matter:
    from .security import authorize
    authorize(actor, matter_id, 'read', db)
    row = db.get(MatterRow, str(matter_id), populate_existing=True)
    members = db.scalars(select(MembershipRow.user_id).where(MembershipRow.matter_id == str(matter_id))).all()
    payload = json.loads(row.payload)
    payload.update(title=row.title, status=row.status, member_ids=members)
    return Matter.model_validate(payload)


def read_version(matter_id: UUID, version_id: UUID, actor: Actor, db: Session) -> DocumentVersion:
    from .security import authorize, deny
    authorize(actor, matter_id, 'read', db)
    row = db.scalar(select(DocumentRow).where(DocumentRow.id == str(version_id),
                                               DocumentRow.matter_id == str(matter_id)))
    if row is None:
        deny(actor, matter_id, 'authorization_denied', db)
    return DocumentVersion.model_validate_json(row.payload)


def read_original(matter_id: UUID, version_id: UUID, actor: Actor, db: Session) -> bytes:
    from .security import ServiceError
    version = read_version(matter_id, version_id, actor, db)
    database = configured_database(db)
    path = database.storage_root / version.storage_ref
    if not path.resolve().is_relative_to(database.storage_root) or path.is_symlink():
        raise ServiceError('VERSION_CONFLICT', 409)
    try:
        data = path.read_bytes()
    except OSError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    if len(data) != version.byte_size or hashlib.sha256(data).hexdigest() != version.sha256:
        raise ServiceError('VERSION_CONFLICT', 409)
    return data


def create_version(input: VersionInput, actor: Actor, db: Session, *,
                   content: BinaryIO | None = None) -> DocumentVersion:
    from .audit import append_event
    from .security import ServiceError, authorize
    authorize(actor, input.matter_id, 'upload', db)
    _editable(input.matter_id, db)
    database = configured_database(db)
    settings = database.settings
    if content is None:
        raise ServiceError('FILE_UNSUPPORTED', 400)
    if input.baseline_view is None:
        raise ServiceError('BASELINE_REQUIRED', 400)
    if input.supersedes_id is not None:
        predecessor = db.get(DocumentRow, str(input.supersedes_id))
        if predecessor is None or predecessor.matter_id != str(input.matter_id):
            raise ServiceError('VERSION_CONFLICT', 409)
    identifier = uuid4()
    relative = Path(str(input.matter_id)) / str(identifier) / 'original.bin'
    path = database.storage_root / relative
    if not path.resolve().is_relative_to(database.storage_root):
        raise ServiceError('FILE_UNSUPPORTED', 400)
    path.parent.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open('xb') as target:
            while chunk := content.read(64 * 1024):
                if not isinstance(chunk, bytes):
                    raise ServiceError('FILE_UNSUPPORTED', 400)
                size += len(chunk)
                if size > settings.upload_max_file_mib * 1024 * 1024:
                    raise ServiceError('FILE_LIMIT', 413)
                target.write(chunk)
                digest.update(chunk)
            target.flush()
            os.fsync(target.fileno())
        if size == 0:
            raise ServiceError('FILE_UNSUPPORTED', 400)
        reserved = db.execute(update(MatterRow).where(
            MatterRow.id == str(input.matter_id),
            MatterRow.file_count < settings.upload_max_matter_files,
            MatterRow.total_bytes + size <= settings.upload_max_matter_mib * 1024 * 1024,
        ).values(file_count=MatterRow.file_count + 1,
                 total_bytes=MatterRow.total_bytes + size)).rowcount
        if reserved != 1:
            raise ServiceError('FILE_LIMIT', 413)
        created = datetime.now(timezone.utc)
        version = DocumentVersion(id=identifier, matter_id=input.matter_id,
                                  original_name=input.original_name, mime=input.mime,
                                  sha256=digest.hexdigest(), storage_ref=relative.as_posix(),
                                  byte_size=size, uploaded_by=actor.user_id, created_at=created,
                                  baseline_view=input.baseline_view, part_inventory=(), page_count=None,
                                  parse_status=ParseStatus.PENDING, unsupported_parts=(),
                                  supersedes_id=input.supersedes_id)
        db.add(DocumentRow(id=str(identifier), matter_id=str(input.matter_id), uploaded_by=str(actor.user_id),
                           supersedes_id=str(input.supersedes_id) if input.supersedes_id else None,
                           sha256=version.sha256, byte_size=size, payload=version.model_dump_json()))
        path.chmod(stat.S_IREAD)
        _remember_original(db, path, database.storage_root)
        append_event(AuditEvent(id=uuid4(), matter_id=input.matter_id, actor_id=actor.user_id,
                               action='document_created', entity_type='document', entity_id=identifier,
                               before_hash=None, after_hash=version.sha256, timestamp=created,
                               reason='original_registered', correlation_id=uuid4()), db)
        _material_changed(input.matter_id, db, 'intake')
        db.flush()
        return version
    except BaseException:
        # No partial counter/document/audit survives a failed registration.
        db.rollback()
        _remove_created(path, database.storage_root)
        raise


def _audit_change(matter_id: UUID, actor: Actor, action: str, entity_type: str, db: Session,
                  *, entity_id: UUID | None = None, after_hash: str | None = None):
    from .audit import append_event
    append_event(AuditEvent(id=uuid4(), matter_id=matter_id, actor_id=actor.user_id,
                           action=action, entity_type=entity_type, entity_id=entity_id or matter_id,
                           before_hash=None, after_hash=after_hash, timestamp=datetime.now(timezone.utc),
                           reason=action, correlation_id=uuid4()), db)


def _material_changed(matter_id: UUID, db: Session, target_status: str):
    row = db.get(MatterRow, str(matter_id), populate_existing=True)
    row.status = target_status
    db.execute(update(ApprovalRow).where(ApprovalRow.matter_id == str(matter_id),
                                         ApprovalRow.status == 'valid').values(status='stale'))
    db.execute(update(ExportRow).where(ExportRow.matter_id == str(matter_id)).values(superseded=True))


def party_material_changed(matter_id: UUID, actor: Actor, db: Session) -> None:
    """Narrow party service integration: real case permission and existing invalidation."""
    from .security import authorize
    authorize(actor, matter_id, 'candidate_facts', db)
    _editable(matter_id, db)
    _material_changed(matter_id, db, 'awaiting_fact_confirmation')


def policy_material_changed(matter_id: UUID, version: int, actor: Actor, db: Session) -> None:
    """Case-scoped policy activation: no propagation to another client's cases."""
    from .security import authorize
    authorize(actor,matter_id,'confirm_facts',db)
    row=_editable(matter_id,db)
    payload=json.loads(row.payload)
    payload['active_policy_version']=version
    row.payload=Matter.model_validate(payload).model_dump_json()
    _material_changed(matter_id,db,'awaiting_fact_confirmation')


_TRANSITIONS = {
    'intake': {'parsed', 'failed', 'archived'},
    'parsed': {'awaiting_fact_confirmation', 'failed', 'archived'},
    'awaiting_fact_confirmation': {'ready_for_review', 'failed', 'archived'},
    'ready_for_review': {'reviewing', 'failed', 'archived'},
    'reviewing': {'awaiting_lawyer', 'failed'},
    'awaiting_lawyer': {'approved', 'failed', 'archived'},
    'approved': {'superseded', 'archived'},
    'superseded': {'archived'},
    'failed': {'intake', 'archived'},
    'archived': set(),
}


def transition_matter(matter_id: UUID, target: MatterStatus, actor: Actor, db: Session) -> Matter:
    from .security import ServiceError, authorize
    authorize(actor, matter_id, 'transition', db)
    row = db.get(MatterRow, str(matter_id), populate_existing=True)
    if target not in _TRANSITIONS.get(row.status, set()):
        raise ServiceError('STATE_CONFLICT', 409)
    if target == 'approved':
        # Neither login nor a valid graph edge authorizes formal legal issuance.
        raise ServiceError('NOT_IMPLEMENTED', 409)
    row.status = MatterStatus(target).value
    _audit_change(matter_id, actor, 'state_changed', 'matter', db)
    return read_matter(matter_id, actor, db)


def review_status_changed(matter_id: UUID, actor: Actor, db: Session, *, success: bool) -> Matter:
    """Narrow review completion service; joins caller's atomic savepoint."""
    from .security import ServiceError, authorize
    authorize(actor,matter_id,'review',db)
    if type(success) is not bool: raise ValueError('bool required')
    row=db.get(MatterRow,str(matter_id),populate_existing=True)
    if row.status!='ready_for_review': raise ServiceError('STATE_CONFLICT',409)
    row.status='awaiting_lawyer' if success else 'failed'
    _audit_change(matter_id,actor,'state_changed','matter',db)
    return read_matter(matter_id,actor,db)


def _editable(matter_id: UUID, db: Session):
    from .security import ServiceError
    row = db.get(MatterRow, str(matter_id), populate_existing=True)
    if row.status == 'archived':
        raise ServiceError('STATE_CONFLICT', 409)
    return row


def set_position(matter_id: UUID, position: Position, actor: Actor, db: Session) -> Matter:
    from .security import authorize
    authorize(actor, matter_id, 'update_position', db)
    row = _editable(matter_id, db)
    payload = json.loads(row.payload)
    position = Position(position)
    if payload['position'] != position:
        payload['position'] = position.value
        row.payload = Matter.model_validate(payload).model_dump_json()
        _material_changed(matter_id, db, 'awaiting_fact_confirmation')
        _audit_change(matter_id, actor, 'position_changed', 'matter', db)
    return read_matter(matter_id, actor, db)


def fact_snapshot_sha256(facts) -> str:
    """Hash contract: sorted compact UTF-8 JSON list, Decimal encoded as strings."""
    payload = json.dumps([fact.model_dump(mode='json') for fact in facts], sort_keys=True,
                         ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def save_fact_snapshot(matter_id: UUID, snapshot: FactSnapshot, actor: Actor, db: Session) -> FactSnapshot:
    from .security import ServiceError, authorize, deny
    authorize(actor, matter_id, 'candidate_facts', db)
    # Revalidation also rejects unsupported model_copy changes in incoming snapshots.
    snapshot = FactSnapshot.model_validate_json(snapshot.model_dump_json())
    action = 'confirm_facts' if any(f.confirmation_status in {'confirmed', 'corrected'} for f in snapshot.facts) else 'candidate_facts'
    authorize(actor, matter_id, action, db)
    row = _editable(matter_id, db)
    if any(fact.matter_id != matter_id for fact in snapshot.facts):
        deny(actor, matter_id, 'authorization_denied', db)
    current = db.scalar(select(FactSnapshotRow.version).where(FactSnapshotRow.matter_id == str(matter_id))
                        .order_by(FactSnapshotRow.version.desc()).limit(1)) or 0
    if snapshot.version != current + 1 or snapshot.sha256 != fact_snapshot_sha256(snapshot.facts):
        raise ServiceError('VERSION_CONFLICT', 409)
    previous_row = db.get(FactSnapshotRow, (str(matter_id), current)) if current else None
    previous = ({fact.id: fact for fact in FactSnapshot.model_validate_json(previous_row.payload).facts}
                if previous_row else {})
    for fact in snapshot.facts:
        if fact.confirmation_status in {'confirmed', 'corrected'} and fact.confirmed_by != actor.user_id:
            old = previous.get(fact.id)
            # Preserve already verified historical confirmations when a full snapshot
            # advances; any changed confirmation requires the actual current lawyer.
            if old is None or old.model_dump(exclude={'version'}) != fact.model_dump(exclude={'version'}):
                deny(actor, matter_id, 'authorization_denied', db)
    payload = json.loads(row.payload)
    payload['active_fact_version'] = snapshot.version
    row.payload = Matter.model_validate(payload).model_dump_json()
    db.add(FactSnapshotRow(matter_id=str(matter_id), version=snapshot.version,
                           sha256=snapshot.sha256, payload=snapshot.model_dump_json()))
    _material_changed(matter_id, db, 'awaiting_fact_confirmation')
    _audit_change(matter_id, actor, 'facts_changed', 'facts', db, after_hash=snapshot.sha256)
    return snapshot


def get_fact_snapshot(matter_id: UUID, version: int, actor: Actor, db: Session) -> FactSnapshot:
    from .security import ServiceError, authorize
    authorize(actor, matter_id, 'read', db)
    row = db.get(FactSnapshotRow, (str(matter_id), version))
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return FactSnapshot.model_validate_json(row.payload)


def save_parse_result(matter_id: UUID, result: ParseResult, actor: Actor, db: Session) -> ParseResult:
    from .security import authorize
    authorize(actor, matter_id, 'upload', db)
    _editable(matter_id, db)
    result = ParseResult.model_validate_json(result.model_dump_json())
    read_version(matter_id, result.version_id, actor, db)
    db.add(ParseRow(document_version_id=str(result.version_id), payload=result.model_dump_json()))
    _audit_change(matter_id, actor, 'parse_saved', 'parse', db, entity_id=result.version_id)
    return result


def get_parse_result(matter_id: UUID, version_id: UUID, actor: Actor, db: Session) -> ParseResult | None:
    read_version(matter_id, version_id, actor, db)
    row = db.scalar(select(ParseRow).where(ParseRow.document_version_id == str(version_id))
                    .order_by(ParseRow.id.desc()).limit(1))
    return ParseResult.model_validate_json(row.payload) if row else None


def read_approval(matter_id: UUID, approval_id: UUID, actor: Actor, db: Session) -> Approval:
    from .security import ServiceError, authorize
    authorize(actor, matter_id, 'read', db)
    row = db.scalar(select(ApprovalRow).where(ApprovalRow.id == str(approval_id), ApprovalRow.matter_id == str(matter_id))
                    .execution_options(populate_existing=True))
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    payload = json.loads(row.payload)
    payload['status'] = row.status
    return Approval.model_validate(payload)


def read_export(matter_id: UUID, artifact_id: UUID, actor: Actor, db: Session) -> ExportArtifact:
    from .security import ServiceError, authorize
    authorize(actor, matter_id, 'read', db)
    row = db.scalar(select(ExportRow).where(ExportRow.id == str(artifact_id), ExportRow.matter_id == str(matter_id))
                    .execution_options(populate_existing=True))
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    payload = json.loads(row.payload)
    payload['superseded'] = row.superseded
    return ExportArtifact.model_validate(payload)
