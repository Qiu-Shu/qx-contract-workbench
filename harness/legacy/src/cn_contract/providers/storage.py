"""Append-only technical registry/evidence; joins the caller transaction."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from sqlalchemy import Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from ..persistence import Base, Database, UTCDateTime, configured_database


class ProviderRecordRow(Base):
    __tablename__ = 'provider_records'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(36), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    parent: Mapped[str] = mapped_column(String(128))
    actor_id: Mapped[str] = mapped_column(String(36))
    matter_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


def initialize_storage(database):
    if not isinstance(database, Database):
        raise TypeError('explicit Database required')
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection, tables=[ProviderRecordRow.__table__])
        for operation in ('UPDATE', 'DELETE'):
            connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_provider_records_{operation.lower()} '
                f"BEFORE {operation} ON provider_records BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._provider_storage_initialized = True


def require_storage(db):
    if not getattr(configured_database(db), '_provider_storage_initialized', False):
        raise RuntimeError('initialize_storage(database) required at startup')


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def append(kind, parent, payload, actor_id, db, *, matter_id=None):
    require_storage(db)
    raw = encode(payload)
    row = ProviderRecordRow(ref=str(uuid4()), kind=kind, parent=str(parent), actor_id=str(actor_id),
        matter_id=str(matter_id) if matter_id else None, payload=raw,
        sha256=hashlib.sha256(raw.encode()).hexdigest(), timestamp=datetime.now(timezone.utc))
    db.add(row); db.flush()
    return row


def latest(kind, parent, db):
    require_storage(db)
    return db.scalar(select(ProviderRecordRow).where(ProviderRecordRow.kind == kind,
        ProviderRecordRow.parent == str(parent)).order_by(ProviderRecordRow.sequence.desc()))


def by_ref(ref, kind, db):
    require_storage(db)
    return db.scalar(select(ProviderRecordRow).where(ProviderRecordRow.ref == str(ref), ProviderRecordRow.kind == kind))
