"""Append-only source records. Business DTOs live exclusively in domain.py."""
from datetime import datetime
import hashlib
from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from ..config import canonical_json
from ..persistence import Base, Database, UTCDateTime, configured_database


def digest(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


class AuthoritySnapshotRow(Base):
    __tablename__ = 'authority_snapshots'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('authority_snapshots.id'))
    classification: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


class SourceAttestationRow(Base):
    __tablename__ = 'source_attestations'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    authority_id: Mapped[str] = mapped_column(ForeignKey('authority_snapshots.id'))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    classification: Mapped[str] = mapped_column(String(32))
    source_sha256: Mapped[str] = mapped_column(String(64))
    provenance_ref: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)


class SourceEvidenceRow(Base):
    __tablename__ = 'source_evidence'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    authority_id: Mapped[str] = mapped_column(ForeignKey('authority_snapshots.id'))
    acquired_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    source_sha256: Mapped[str] = mapped_column(String(64))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    original_bytes: Mapped[bytes] = mapped_column(LargeBinary)


class AuthorityVerificationRow(Base):
    __tablename__ = 'authority_verifications'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    authority_id: Mapped[str] = mapped_column(ForeignKey('authority_snapshots.id'))
    attestation_id: Mapped[str] = mapped_column(ForeignKey('source_attestations.id'))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)


class RuleManagerGrantRow(Base):
    __tablename__ = 'rule_manager_grants'
    sequence: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    enabled: Mapped[str] = mapped_column(String(8))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


TABLES = (AuthoritySnapshotRow.__table__,SourceEvidenceRow.__table__,SourceAttestationRow.__table__,AuthorityVerificationRow.__table__,RuleManagerGrantRow.__table__)


def initialize_storage(database: Database):
    if not isinstance(database,Database): raise TypeError('explicit Database required')
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=TABLES)
        for table in TABLES:
            for operation in ('UPDATE','DELETE'):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_{table.name}_{operation.lower()} '
                    f'BEFORE {operation} ON {table.name} BEGIN '
                    "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._authorities_storage_initialized = True


def require_storage(db):
    if not getattr(configured_database(db),'_authorities_storage_initialized',False):
        raise RuntimeError('authorities.initialize_storage(database) required')


def current_grant(user_id,db):
    require_storage(db)
    row=db.scalar(select(RuleManagerGrantRow).where(RuleManagerGrantRow.user_id==str(user_id))
        .order_by(RuleManagerGrantRow.sequence.desc()).limit(1))
    return bool(row and row.enabled=='yes')
