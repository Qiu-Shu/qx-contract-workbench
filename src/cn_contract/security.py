"""Server identity, role and case authorization. No Actor claims are trusted."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from uuid import UUID, uuid4

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import Actor, AuditEvent, Role
from .persistence import MembershipRow, SessionRow, UserRow

PASSWORD_HASH = PasswordHash.recommended()
SESSION_DURATION = timedelta(hours=8)
_DUMMY_HASH = PASSWORD_HASH.hash(secrets.token_urlsafe(32))


class ServiceError(Exception):
    def __init__(self, code: str, status_code: int, *, retryable: bool = False):
        self.code = code
        self.status_code = status_code
        self.retryable = retryable
        self.correlation_id = uuid4()
        super().__init__('request not authorized' if status_code in (401, 403) else 'request blocked')


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def provision_user(username: str, password: str, roles: set[Role], db: Session) -> UUID:
    """Explicit trusted server initialization; never exposed to cookie clients."""
    roles = frozenset(Role(role) for role in roles)
    if not username.strip() or len(password) < 12 or not roles:
        raise ValueError('username, at least 12 password characters and known roles required')
    identifier = uuid4()
    db.add(UserRow(id=str(identifier), username=username, password_hash=PASSWORD_HASH.hash(password),
                   roles=json.dumps(sorted(role.value for role in roles)), disabled=False))
    db.flush()
    return identifier


def set_membership(matter_id: UUID, user_id: UUID, db: Session, *, can_sign: bool = False) -> None:
    """Trusted membership-management service primitive, not an end-user write API."""
    row = db.get(MembershipRow, (str(matter_id), str(user_id)))
    if row is None:
        db.add(MembershipRow(matter_id=str(matter_id), user_id=str(user_id), can_sign=can_sign))
    else:
        row.can_sign = can_sign
    db.flush()


def remove_membership(matter_id: UUID, user_id: UUID, db: Session) -> None:
    row = db.get(MembershipRow, (str(matter_id), str(user_id)))
    if row is not None:
        db.delete(row)
        db.flush()


def login(username: str, password: str, db: Session) -> tuple[str, str]:
    user = db.scalar(select(UserRow).where(UserRow.username == username))
    checked_hash = user.password_hash if user is not None else _DUMMY_HASH
    valid = PASSWORD_HASH.verify(password, checked_hash)
    if user is None or user.disabled or not valid:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(SessionRow(id=str(uuid4()), user_id=user.id, token_hash=_hash(token), csrf_hash=_hash(csrf),
                      expires_at=datetime.now(timezone.utc) + SESSION_DURATION, revoked=False))
    db.flush()
    return token, csrf


def _principal(session: SessionRow | None, db: Session, *, user_id: UUID | None = None):
    if session is None or session.revoked or session.expires_at <= datetime.now(timezone.utc):
        return None
    if user_id is not None and session.user_id != str(user_id):
        return None
    user = db.get(UserRow, session.user_id, populate_existing=True)
    if user is None or user.disabled:
        return None
    return Actor(user_id=UUID(user.id), session_id=UUID(session.id),
                 roles=frozenset(Role(role) for role in json.loads(user.roles)))


def authenticate(token: str | None, db: Session) -> Actor:
    if not token or len(token) > 256:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    session = db.scalar(select(SessionRow).where(SessionRow.token_hash == _hash(token))
                        .execution_options(populate_existing=True))
    actor = _principal(session, db)
    if actor is None:
        raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    return actor


def revoke_session(session_id: UUID, db: Session) -> None:
    """Trusted revocation by the server auth/admin service."""
    session = db.get(SessionRow, str(session_id))
    if session is not None:
        session.revoked = True
        db.flush()


def deny(actor: Actor, matter_id: UUID, action: str, db: Session, *, code='CROSS_MATTER_DENIED', status=403):
    """Rollback caller work; commit a separate short denial audit before raising.

    This intentional transaction boundary prevents outer HTTP exception rollback
    from erasing the denial and prevents that audit commit from committing business
    work pending in the rejected request.
    """
    from .audit import append_event
    error = ServiceError(code, status)
    db.rollback()
    append_event(AuditEvent(id=uuid4(), matter_id=matter_id, actor_id=actor.user_id,
                           action=action, entity_type='matter', entity_id=matter_id,
                           before_hash=None, after_hash=None, timestamp=datetime.now(timezone.utc),
                           reason=code, correlation_id=error.correlation_id), db)
    db.commit()
    raise error


_READ_ROLES = {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER, Role.ASSISTANT}
_ACTIONS = {
    'read': _READ_ROLES,
    'upload': _READ_ROLES,
    'candidate_facts': _READ_ROLES,
    'confirm_facts': {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER},
    'confirm_baseline': {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER},
    'update_position': {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER},
    'review': {Role.HANDLING_LAWYER},
    'transition': {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER},
    'approve': {Role.REVIEWING_LAWYER},
}


def authorize(actor: Actor, matter_id: UUID, action: str, db: Session) -> None:
    # Flush local auth changes before checking them; these are rolled back on denial.
    db.flush()
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if principal is None:
        deny(actor, matter_id, 'authorization_denied', db, code='AUTHORIZATION_REQUIRED', status=401)
    membership = db.get(MembershipRow, (str(matter_id), str(principal.user_id)), populate_existing=True)
    if (membership is None or action not in _ACTIONS or not principal.roles & _ACTIONS[action]
            or (action == 'approve' and not membership.can_sign)):
        deny(actor, matter_id, 'authorization_denied', db)


def verify_csrf(actor: Actor, token: str | None, matter_id: UUID, db: Session) -> None:
    session = db.get(SessionRow, str(actor.session_id), populate_existing=True)
    if not token or len(token) > 256 or session is None or not hmac.compare_digest(session.csrf_hash, _hash(token)):
        deny(actor, matter_id, 'csrf_denied', db)


def provision_rule_manager_grant(user_id: UUID, db: Session) -> None:
    """Trusted server provisioning only; deliberately absent from HTTP routes.

    Grant records prove engineering authorization, never a lawyer's license or
    a substantive rule approval. Default databases have no such grant.
    """
    from .authorities.storage import RuleManagerGrantRow, require_storage
    require_storage(db)
    user = db.get(UserRow, str(user_id), populate_existing=True)
    if user is None or user.disabled or not set(json.loads(user.roles)) & {'handling_lawyer','reviewing_lawyer'}:
        raise ServiceError('RULE_UNAPPROVED',403)
    db.add(RuleManagerGrantRow(user_id=str(user_id),enabled='yes',timestamp=datetime.now(timezone.utc)))
    db.flush()


def revoke_rule_manager_grant(user_id: UUID, db: Session) -> None:
    """Append a trusted revocation, preserving historical grant evidence."""
    from .authorities.storage import RuleManagerGrantRow, require_storage
    require_storage(db)
    db.add(RuleManagerGrantRow(user_id=str(user_id),enabled='no',timestamp=datetime.now(timezone.utc)))
    db.flush()


def rule_reviewer_valid(user_id: UUID, db: Session) -> bool:
    from .authorities.storage import current_grant
    user=db.get(UserRow,str(user_id),populate_existing=True)
    return bool(user and not user.disabled and set(json.loads(user.roles)) &
        {'handling_lawyer','reviewing_lawyer'} and current_grant(user_id,db))


def authorize_rule_manager(actor: Actor, matter_id: UUID, db: Session) -> None:
    """Re-read session, server roles, membership, then the server-owned grant."""
    authorize(actor,matter_id,'confirm_facts',db)
    if not rule_reviewer_valid(actor.user_id,db):
        raise ServiceError('RULE_UNAPPROVED',403)
