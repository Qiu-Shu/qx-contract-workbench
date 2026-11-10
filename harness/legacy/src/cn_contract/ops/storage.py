"""Durable restored-state quarantine and protected historical file relocation."""
import hashlib
from pathlib import Path
from sqlalchemy import Integer, String, Text, select, inspect
from sqlalchemy.orm import Mapped, mapped_column
from ..persistence import Base, configured_database
from ..security import ServiceError


class RestoreFenceRow(Base):
    __tablename__ = 'ops_restore_fences'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(36), unique=True)
    archive_sha256: Mapped[str] = mapped_column(String(64))
    manifest_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class FileRelocationRow(Base):
    __tablename__ = 'ops_file_relocations'
    logical_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    physical_ref: Mapped[str] = mapped_column(Text)
    archive_sha256: Mapped[str] = mapped_column(String(64))
    record_refs: Mapped[str] = mapped_column(Text)


def initialize_storage(database):
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[RestoreFenceRow.__table__, FileRelocationRow.__table__])
        for table in ('ops_restore_fences', 'ops_file_relocations'):
            for operation in ('UPDATE', 'DELETE'):
                connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RECORD'); END")
    database._ops_storage_initialized = True


def quarantined(db):
    # Older partial service databases have no ops tables. Restored databases must
    # contain the verified complete schema and this persists across new instances.
    if not inspect(db.connection()).has_table('ops_restore_fences'):
        return False
    return db.scalar(select(RestoreFenceRow.ref).limit(1)) is not None


def require_active(db):
    if quarantined(db):
        raise ServiceError('BLOCKED_LIVE', 409)


def relocation(logical_ref, digest, db):
    if not quarantined(db):
        return Path(logical_ref)
    row = db.get(FileRelocationRow, (str(logical_ref), digest))
    if row is None:
        raise ServiceError('VERSION_CONFLICT', 409)
    root = configured_database(db).storage_root
    from .backup import safe_relative, checked_file
    path = root / safe_relative(row.physical_ref)
    data = checked_file(path, root)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ServiceError('VERSION_CONFLICT', 409)
    return path


def read_historical_artifact(record_ref, actor, *, db):
    """Authorized historical reconciliation only; never validates current approval."""
    import json
    from uuid import UUID
    from ..exports.storage import ExportRecordRow, authorize, sha, checked_bytes
    from ..persistence import ExportRow
    row = db.scalar(select(ExportRecordRow).where(ExportRecordRow.ref == str(record_ref)))
    if row is not None:
        authorize(actor, UUID(row.matter_id), db)
        value = json.loads(row.payload)
        if row.kind != 'patch_result' or value.get('status') != 'applied' or sha(value) != row.sha256:
            raise ServiceError('VERSION_CONFLICT', 409)
        return checked_bytes(value['storage_ref'], value['target_sha256'], db)
    row = db.get(ExportRow, str(record_ref))
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    authorize(actor, UUID(row.matter_id), db)
    from ..domain import ExportArtifact
    artifact = ExportArtifact.model_validate_json(row.payload)
    if str(artifact.id) != row.id or str(artifact.matter_id) != row.matter_id:
        raise ServiceError('VERSION_CONFLICT', 409)
    return checked_bytes(artifact.storage_ref, artifact.content_sha256, db)
