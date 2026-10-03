"""Technical rows only. Domain query/billing DTOs remain in domain.py."""
from datetime import datetime, timezone
from decimal import Decimal, Context, localcontext
import hashlib
import json
from uuid import UUID, uuid4
from contextlib import contextmanager
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column
from ..persistence import Base, Database, UTCDateTime, configured_database, SessionRow
from ..security import _principal, ServiceError
from ..domain import Role
from ..providers import qcc_registry as registry
from ..providers.storage import append as provider_append


class QueryPlanRow(Base):
    __tablename__ = 'query_plan_versions'
    __table_args__ = (UniqueConstraint('plan_id', 'version'),)
    ref: Mapped[str] = mapped_column(String(36), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(36))
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


class QueryRecordRow(Base):
    __tablename__ = 'query_records'
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ref: Mapped[str] = mapped_column(String(36), unique=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    kind: Mapped[str] = mapped_column(String(32))
    parent: Mapped[str] = mapped_column(String(128))
    actor_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime())


class QueryLedgerRow(Base):
    __tablename__ = 'query_ledger'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    matter_id: Mapped[str] = mapped_column(ForeignKey('matters.id'))
    plan_ref: Mapped[str] = mapped_column(ForeignKey('query_plan_versions.ref'))
    item_id: Mapped[str] = mapped_column(String(36))
    page: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    preimage: Mapped[str] = mapped_column(Text)
    payload: Mapped[str] = mapped_column(Text)
    call_count: Mapped[int] = mapped_column(Integer)
    dispatch_token_sha256: Mapped[str | None] = mapped_column(String(64))
    send_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer)


def initialize_storage(database):
    if not isinstance(database, Database): raise TypeError('explicit Database required')
    tables = [QueryPlanRow.__table__, QueryRecordRow.__table__, QueryLedgerRow.__table__]
    with database.engine.begin() as connection:
        Base.metadata.create_all(connection, tables=tables)
        for table in tables[:2]:
            for operation in ('UPDATE', 'DELETE'):
                connection.exec_driver_sql(f'CREATE TRIGGER IF NOT EXISTS immutable_{table.name}_{operation.lower()} '
                    f"BEFORE {operation} ON {table.name} BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS immutable_query_ledger_delete BEFORE DELETE ON query_ledger BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_RECORD'); END")
    database._query_storage_initialized = True


def require_storage(db):
    if not getattr(configured_database(db), '_query_storage_initialized', False):
        raise RuntimeError('initialize_storage(Database) required')


def now(): return datetime.now(timezone.utc)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(value): return hashlib.sha256(encode(value).encode()).hexdigest()


def decimal(value):
    if isinstance(value, (bool, float)): raise ServiceError('PRICE_UNKNOWN', 422)
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or len(result.as_tuple().digits) > 100 or abs(result.as_tuple().exponent) > 100:
            raise ValueError()
        return result
    except Exception:
        raise ServiceError('PRICE_UNKNOWN', 422) from None


def total(values):
    with localcontext(Context(prec=512, Emin=-9999, Emax=9999)):
        return sum(values, Decimal('0'))


def difference(a, b):
    with localcontext(Context(prec=512, Emin=-9999, Emax=9999)): return a-b


def multiply(a, b):
    with localcontext(Context(prec=512, Emin=-9999, Emax=9999)): return a*b


def authorize_query(actor, matter_id, db, *, write=True):
    require_storage(db)
    try:
        registry.authorize_case(actor, matter_id, db)
        principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
        if write and not principal.roles & {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER}:
            raise ServiceError('CROSS_MATTER_DENIED', 403)
    except ServiceError as error:
        record_denial(actor,matter_id,error,db)
        raise


def record_denial(actor,matter_id,error,db):
    """Fixed hashed reason only; joins caller transaction, never commits it."""
    from ..domain import AuditEvent
    from ..audit import append_event
    append_event(AuditEvent(id=uuid4(),matter_id=matter_id,actor_id=actor.user_id,
        action='csrf_denied' if getattr(error,'_audit_action',None)=='csrf_denied' else 'authorization_denied',entity_type='matter',entity_id=matter_id,
        before_hash=None,after_hash=None,timestamp=now(),reason=error.code,correlation_id=error.correlation_id),db)


@contextmanager
def factory_transaction(database,actor,matter_id):
    """Explicit gateway short transaction. Denial audit follows its rollback.

    This owns only a newly created Session. It never commits/rolls back an
    application caller Session, nor erases earlier durable send/settle receipts.
    Caller services use record_denial in their own transaction instead.
    """
    try:
        with database.session() as db:
            yield db
    except ServiceError as error:
        with database.session() as audit_db:
            record_denial(actor,matter_id,error,audit_db)
        raise


def approver_valid(user_id, matter_id, db):
    from ..persistence import UserRow, MembershipRow
    user = db.get(UserRow, str(user_id), populate_existing=True)
    member = db.get(MembershipRow, (str(matter_id), str(user_id)), populate_existing=True)
    return bool(user and member and not user.disabled and set(json.loads(user.roles)) & {'handling_lawyer', 'reviewing_lawyer'})


def append(kind, parent, payload, actor_id, matter_id, db):
    require_storage(db)
    row = QueryRecordRow(ref=str(uuid4()), kind=kind, parent=str(parent), actor_id=str(actor_id),
        matter_id=str(matter_id), payload=encode(payload), sha256=sha(payload), timestamp=now())
    db.add(row); db.flush(); return row


def latest(kind, parent, db):
    require_storage(db)
    return db.scalar(select(QueryRecordRow).where(QueryRecordRow.kind==kind, QueryRecordRow.parent==str(parent)).order_by(QueryRecordRow.sequence.desc()))


def by_ref(ref, kind, db):
    require_storage(db)
    return db.scalar(select(QueryRecordRow).where(QueryRecordRow.ref==str(ref), QueryRecordRow.kind==kind))


def register_synthetic_price(endpoint_ref, credits, *, actor, db):
    endpoint = registry.read_endpoint(endpoint_ref, actor=actor, db=db)
    if not endpoint['synthetic'] or endpoint['live_allowed']: raise ServiceError('BLOCKED_LIVE', 403)
    amount = decimal(credits)
    return UUID(provider_append('price', endpoint_ref, {'unit_price': str(amount), 'unit': 'synthetic_credit/call',
        'synthetic': True, 'production_approval': None}, actor.user_id, db).ref)


def register_synthetic_behavior(endpoint_ref, mode, *, actor, db, matter_id=None, delay_seconds=0):
    endpoint = registry.read_endpoint(endpoint_ref, actor=actor, db=db)
    if not endpoint['synthetic'] or endpoint['provider'] != 'synthetic_mock_qcc': raise ServiceError('BLOCKED_LIVE', 403)
    if mode not in {'success','timeout','unknown','failed_unknown','success_billing_unknown','before_send','overcharge','zero'}:
        raise ServiceError('BLOCKED_LIVE', 403)
    if isinstance(delay_seconds, bool) or not isinstance(delay_seconds, (int, float)) or not 0 <= delay_seconds <= 3:
        raise ServiceError('BLOCKED_LIVE', 403)
    # Provider technical configuration contains no case material or result.
    return provider_append('query_behavior', endpoint_ref, {'mode': mode, 'delay_seconds': delay_seconds,
        'synthetic': True}, actor.user_id, db).ref
