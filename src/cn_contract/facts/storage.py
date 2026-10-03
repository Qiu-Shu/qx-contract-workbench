"""Technical append-only records; business DTOs remain in domain.py."""
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..persistence import Base, Database, UTCDateTime, configured_database
from datetime import datetime


class FactDecisionRow(Base):
    __tablename__ = 'fact_decisions'
    __table_args__ = (
        ForeignKeyConstraint(['matter_id','source_version'],['fact_snapshots.matter_id','fact_snapshots.version']),
        ForeignKeyConstraint(['matter_id','target_version'],['fact_snapshots.matter_id','fact_snapshots.version']),
    )
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    source_version: Mapped[int] = mapped_column(Integer)
    target_version: Mapped[int] = mapped_column(Integer)
    fact_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)


class PartyRow(Base):
    __tablename__ = 'party_snapshots'
    __table_args__ = (UniqueConstraint('record_id'),)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'),primary_key=True)
    party_id: Mapped[str] = mapped_column(String(36),primary_key=True)
    revision: Mapped[int] = mapped_column(Integer,primary_key=True)
    record_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


class PartyDecisionRow(Base):
    __tablename__ = 'party_decisions'
    __table_args__ = (
        ForeignKeyConstraint(['matter_id','party_id','source_revision'],['party_snapshots.matter_id','party_snapshots.party_id','party_snapshots.revision']),
        ForeignKeyConstraint(['matter_id','party_id','target_revision'],['party_snapshots.matter_id','party_snapshots.party_id','party_snapshots.revision']),
    )
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    party_id: Mapped[str] = mapped_column(String(36))
    source_revision: Mapped[int] = mapped_column(Integer)
    target_revision: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    payload: Mapped[str] = mapped_column(Text)
    before_hash: Mapped[str] = mapped_column(String(64))
    after_hash: Mapped[str] = mapped_column(String(64))


def initialize_storage(database: Database) -> None:
    """Trusted server startup, never a client endpoint; no import-time DB or commit."""
    if not isinstance(database,Database):
        raise TypeError('explicit Database required')
    tables = [FactDecisionRow.__table__,PartyRow.__table__,PartyDecisionRow.__table__]
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=tables)
        for table in tables:
            for operation in ('UPDATE','DELETE'):
                connection.exec_driver_sql(
                    f'CREATE TRIGGER IF NOT EXISTS immutable_{table.name}_{operation.lower()} '
                    f'BEFORE {operation} ON {table.name} BEGIN '
                    "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._facts_storage_initialized = True


def require_storage(db) -> None:
    if not getattr(configured_database(db),'_facts_storage_initialized',False):
        raise RuntimeError('initialize_storage(database) required at server startup')


def trusted_parse(matter_id, version_id, actor, db, expected):
    """Reconstruct complete provenance from immutable bytes, without saving parses.

    T02's upload-authorized parse storage is an append-only record, not a proof
    that its content came from the parser. The T03 pure adapter dispatcher is
    reused here; all original reads still cross T02's real authorization gate.
    """
    from ..documents.ingest import _parse
    from ..persistence import read_version, read_original
    from ..security import ServiceError
    version = read_version(matter_id,version_id,actor,db)
    original = read_original(matter_id,version_id,actor,db)
    result = _parse(original,version,configured_database(db).settings)
    if expected != result:
        raise ServiceError('VERSION_CONFLICT',409)
    return result
