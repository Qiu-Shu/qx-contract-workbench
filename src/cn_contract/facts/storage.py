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


def source_anchor_is_eligible(anchor, parsed):
    """Whole-page PDF anchors are original evidence only on native read pages.

    Manual/OCR/unsupported text remains an uncertain candidate. This slice has
    no visual-confirmation record or independent lawyer-transcript provenance;
    a FactDecision reason cannot authorize risky extracted text as original.
    DOCX color and hidden-text gaps block their affected paragraph, without
    silently deleting characters and promoting the remainder to trusted text.
    """
    if anchor.kind != 'pdf_span':
        return not any(part.startswith(f'{anchor.part_name}:{kind}:') and
            (part == f'{anchor.part_name}:{kind}:{anchor.element_id}:manual_required'
             or anchor.element_id.startswith(part.removeprefix(f'{anchor.part_name}:{kind}:').removesuffix(':manual_required') + '/'))
            for kind in ('visibility', 'hidden', 'style_dependency') for part in parsed.unsupported_parts)
    return (anchor.page is not None and f'page:{anchor.page}:read' in parsed.parts
        and not any(part == f'page:{anchor.page}' or part.startswith(f'page:{anchor.page}:')
            for part in parsed.unsupported_parts))


def require_fact_sources(matter_id, facts, actor, db, *, visual_fact_ids=None):
    """Rebuild source trust before consuming facts, including historic snapshots.

    Caller-supplied/saved parse DTOs never prove eligibility. All latest stored
    parses are checked against immutable bytes under real case authorization.
    Optional IDs identify decisions that assert visibility; rejecting a valid
    but visually uncertain candidate is allowed. Integrity checks still apply.
    """
    from sqlalchemy import select
    from ..domain import ParseResult
    from ..persistence import DocumentRow, ParseRow
    from ..security import ServiceError
    facts = tuple(facts)
    sources, seen = {}, set()
    rows = db.execute(select(ParseRow, DocumentRow.id).join(DocumentRow,
        ParseRow.document_version_id == DocumentRow.id).where(DocumentRow.matter_id == str(matter_id))
        .order_by(ParseRow.id.desc())).all()
    for row, document_id in rows:
        if document_id in seen:
            continue
        seen.add(document_id)
        parsed = ParseResult.model_validate_json(row.payload)
        if str(parsed.version_id) != document_id:
            raise ServiceError('VERSION_CONFLICT', 409)
        parsed = trusted_parse(matter_id, parsed.version_id, actor, db, parsed)
        sources.update((anchor.id, (anchor, parsed)) for anchor in parsed.anchors)
    visual_ids = ({fact.id for fact in facts if fact.confirmation_status != 'rejected'}
        if visual_fact_ids is None else set(visual_fact_ids))
    for fact in facts:
        if fact.matter_id != matter_id:
            raise ServiceError('VERSION_CONFLICT', 409)
        if fact.provenance_type == 'source_verification':
            from ..documents.proofreading import require_verified_fact
            require_verified_fact(matter_id,fact,actor,db)
            continue
        if fact.provenance_type == 'external' or fact.receipt_ids:
            raise ServiceError('NOT_SUPPORTED', 409)
        if (len(set(fact.anchor_ids)) != len(fact.anchor_ids) or not set(fact.anchor_ids).issubset(sources)
            or fact.provenance_type == 'document' and not fact.anchor_ids):
            raise ServiceError('VERSION_CONFLICT', 409)
        if fact.id in visual_ids and any(not source_anchor_is_eligible(*sources[identifier]) for identifier in fact.anchor_ids):
            raise ServiceError('SOURCE_VISUAL_CONFIRMATION_REQUIRED', 409)
    return sources
