"""Case creation shared by reception and HTTP, within the caller's transaction."""
import json
from uuid import UUID, uuid4

from sqlalchemy import select

from .domain import Matter, Role, PolicySnapshot
from .persistence import provision_matter, read_matter
from .security import ServiceError, deny
from .rules.loader import register_default_cards, save_policy
from .rules.storage import policy_sha256


def create_matter(value, actor, db):
    from .security import _principal
    from .persistence import SessionRow
    principal = _principal(db.get(SessionRow, str(actor.session_id), populate_existing=True), db, user_id=actor.user_id)
    if principal is None: raise ServiceError('AUTHORIZATION_REQUIRED', 401)
    if not principal.roles & {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER}:
        deny(actor, UUID(int=0), 'authorization_denied', db)
    reviewer=None
    if value.reviewer_username:
        from .persistence import UserRow
        reviewer=db.scalar(select(UserRow).where(UserRow.username==value.reviewer_username))
        if reviewer is None or reviewer.disabled or 'reviewing_lawyer' not in json.loads(reviewer.roles):
            raise ServiceError('AUTHORIZATION_REQUIRED',403)
    local_materials = value.material_mode == 'local'
    matter = Matter(id=uuid4(), client_ref=('LOCAL-' if local_materials else 'SYNTHETIC-')+uuid4().hex, title=value.title,
        jurisdiction='CN-mainland', contract_type=value.contract_type, review_mode=value.review_mode,
        position=value.position, objectives=value.objectives,
        member_ids={principal.user_id}|({UUID(reviewer.id)} if reviewer else set()), status='intake',
        active_fact_version=None, active_policy_version=None, gate_issues=())
    with db.begin_nested():
        provision_matter(matter, db)
        if local_materials:
            from .documents.local_materials import record_case
            record_case(matter.id, principal, db)
        register_default_cards(principal, matter_id=matter.id, db=db)
        policy = PolicySnapshot(client_ref=matter.client_ref, version=1, sha256=policy_sha256(matter.client_ref,1,()),
            preferences=(), approved_by=None, approved_at=None)
        save_policy(policy, principal, matter_id=matter.id, db=db)
    return read_matter(matter.id, principal, db)
