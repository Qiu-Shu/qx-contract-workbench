"""Immutable technical relationships, not additional business DTOs."""
from datetime import datetime
from sqlalchemy import ForeignKey, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..persistence import Base, Database, UTCDateTime, configured_database
from ..authorities.storage import digest


class RuleSnapshotRow(Base):
    __tablename__ = 'rule_snapshots'
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'),primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(36),primary_key=True)
    version: Mapped[int] = mapped_column(Integer,primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)
    policy_binding_json: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))


class RuleApprovalRow(Base):
    __tablename__ = 'rule_approvals'
    __table_args__ = (ForeignKeyConstraint(['matter_id','rule_id','version'],['rule_snapshots.matter_id','rule_snapshots.rule_id','rule_snapshots.version']),)
    sequence: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    matter_id: Mapped[str] = mapped_column(String(36))
    rule_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    rule_sha256: Mapped[str] = mapped_column(String(64))
    dependency_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)


class RuleInvalidationRow(Base):
    __tablename__ = 'rule_invalidations'
    __table_args__ = (ForeignKeyConstraint(['matter_id','rule_id','version'],['rule_snapshots.matter_id','rule_snapshots.rule_id','rule_snapshots.version']),)
    sequence: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    matter_id: Mapped[str] = mapped_column(String(36))
    rule_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    reason: Mapped[str] = mapped_column(String(80))


class PolicySnapshotRow(Base):
    __tablename__ = 'policy_snapshots'
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'),primary_key=True)
    version: Mapped[int] = mapped_column(Integer,primary_key=True)
    client_ref: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)


class PolicyApprovalRow(Base):
    __tablename__ = 'policy_approvals'
    __table_args__ = (ForeignKeyConstraint(['matter_id','version'],['policy_snapshots.matter_id','policy_snapshots.version']),)
    sequence: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    matter_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())
    sha256: Mapped[str] = mapped_column(String(64))
    evidence: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)


TABLES=(RuleSnapshotRow.__table__,RuleApprovalRow.__table__,RuleInvalidationRow.__table__,PolicySnapshotRow.__table__,PolicyApprovalRow.__table__)


def initialize_storage(database: Database):
    if not isinstance(database,Database): raise TypeError('explicit Database required')
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection,tables=TABLES)
        for table in TABLES:
            for operation in ('UPDATE','DELETE'):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_{table.name}_{operation.lower()} '
                    f'BEFORE {operation} ON {table.name} BEGIN '
                    "SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._rules_storage_initialized=True


def require_storage(db):
    if not getattr(configured_database(db),'_rules_storage_initialized',False):
        raise RuntimeError('rules.initialize_storage(database) required')


def rule_sha256(rule):
    return digest(rule.model_dump(mode='json'))


def policy_sha256(client_ref,version,preferences):
    return digest({'client_ref':client_ref,'version':version,'preferences':list(preferences)})
