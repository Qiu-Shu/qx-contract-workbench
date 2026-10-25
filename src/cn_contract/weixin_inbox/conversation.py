"""Current CID-owned authorization projections and explicit same-target refreshes."""
from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _current, _owned, _snapshot
from ..ops.storage import quarantined, require_active
from ..persistence import MatterRow
from ..security import ServiceError
from . import accounts


def _active_targets(row, db):
    matters = {row['scope_ref']} if row['scope_kind'] == 'matter' else set()
    intakes = {row['scope_ref']} if row['scope_kind'] == 'intake' else set()
    if row['projection_intake_id'] is not None:
        intakes.add(row['projection_intake_id'])
    for identifier in intakes:
        target = db.scalar(text('SELECT matter_id FROM intake_cases WHERE id=:id'), {'id':identifier})
        if target is not None:
            matters.add(target)
    for identifier in matters:
        matter = db.get(MatterRow, identifier, populate_existing=True)
        if matter is None or matter.status == 'archived':
            raise ServiceError('CROSS_MATTER_DENIED', 403)


def _context(actor, cid, db):
    current = _current(actor, db)
    row = _owned(current, cid, db)
    _active_targets(row, db)
    mappings = db.execute(text('''SELECT mapping.* FROM weixin_peer_bindings mapping
        JOIN task_channel_bindings binding ON binding.id=mapping.task_binding_id
        WHERE binding.conversation_id=:cid AND binding.channel='synthetic' '''), {'cid':str(cid)}).mappings().all()
    if len(mappings) > 1:
        raise ServiceError('VERSION_CONFLICT', 409)
    if not mappings:
        return current, row, None, None, ()
    mapping = accounts._mapping(mappings[0])
    account, current = accounts._account(current, mapping.account_id, db, active=False)
    if (str(mapping.scope.conversation_id) != row['id']
            or str(mapping.scope.workspace_id) != row['workspace_id']):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return current, row, mapping, account, accounts._grant_history(mapping, db)


def _refresh_context(actor, cid, db):
    current, row, mapping, account, _ = _context(actor, cid, db)
    require_active(db)
    if (row['archived_at'] is not None or mapping is None
            or account.revoked_at is not None or mapping.revoked_at is not None
            or accounts._has_generations(account.id, db)):
        raise ServiceError('STATE_CONFLICT', 409)
    return current, mapping.id


def _generation_context(actor, cid, db):
    current, row, mapping, account, _ = _context(actor, cid, db)
    require_active(db)
    if (row['archived_at'] is not None or mapping is None
            or account.revoked_at is not None or mapping.revoked_at is not None):
        raise ServiceError('STATE_CONFLICT', 409)
    return current, mapping.id


def read_authorization(actor, cid, *, database):
    """Read actual local binding state without creating accounts, tasks or grants."""
    with database.session() as db:
        _, row, mapping, account, history = _context(actor, cid, db)
        current = _snapshot(row)
        authorized = history[-1].scope if history else mapping.scope if mapping else None
        digest = history[-1].scope_sha256 if history else mapping.scope_sha256 if mapping else None
        if quarantined(db):
            state = 'restored_blocked'
        elif row['archived_at'] is not None:
            state = 'archived'
        elif mapping is not None and (account.revoked_at is not None or mapping.revoked_at is not None):
            state = 'revoked'
        elif mapping is None:
            state = 'unbound'
        elif accounts._has_generations(account.id, db):
            state = 'target_changed'
        elif current == authorized:
            state = 'current'
        elif accounts._newer_scope(authorized, current):
            state = 'refresh_required'
        else:
            state = 'target_changed'
        return d.WeixinConversationAuthorizationView(state=state, current_scope=current,
            authorized_scope=authorized, grant_revision=len(history), scope_sha256=digest)


def refresh_authorization(actor, cid, request, *, database):
    """Resolve immutable CID→mapping ownership again before the separate grant transaction."""
    with database.session() as db:
        current, mapping_id = _refresh_context(actor, cid, db)
        if request.expected_scope.conversation_id != cid:
            raise ServiceError('VERSION_CONFLICT', 409)
    return accounts.refresh_synthetic_peer(current, mapping_id, request, database=database)


def find_refresh(actor, cid, request_id, *, database):
    """Unknown results are only queried and always retain current object authorization."""
    with database.session() as db:
        current, _, mapping, _, _ = _context(actor, cid, db)
        if mapping is None:
            return None
        mapping_id = mapping.id
    return accounts.find_peer_scope_grant(current, mapping_id, request_id, database=database)


def _generation_receipt(value):
    fields = set(d.WeixinGenerationReceiptView.model_fields) - {'mode', 'state'}
    return d.WeixinGenerationReceiptView(**value.model_dump(mode='python', include=fields))


def append_generation(actor, cid, request, *, database):
    """Resolve the root CID only; the atomic service authorizes the new target."""
    from . import generations
    with database.session() as db:
        current, mapping_id = _generation_context(actor, cid, db)
    return _generation_receipt(generations.append_synthetic_generation(
        current, mapping_id, request, database=database))


def find_generation(actor, cid, request_id, *, database):
    """A fixed receipt never resumes intake or inherits historical target access."""
    from . import generations
    with database.session() as db:
        current, _, mapping, _, _ = _context(actor, cid, db)
        if mapping is None:
            return None
        mapping_id = mapping.id
    value = generations.find_peer_generation(current, mapping_id, request_id, database=database)
    return _generation_receipt(value) if value is not None else None


def read_generation_head(actor, cid, *, database):
    """Resolve only the root CID; the head transaction rechecks latest target access."""
    from . import generations
    with database.session() as db:
        current, _, mapping, _, _ = _context(actor, cid, db)
        if mapping is None:
            return None
        mapping_id = mapping.id
    return generations.read_peer_generation_head(current, mapping_id, database=database)


def _dispatch_receipt(value, db):
    cid = db.scalar(text('SELECT conversation_id FROM task_channel_bindings WHERE id=:id'),
        {'id':str(value.task_binding_id)})
    if cid is None:
        raise ServiceError('VERSION_CONFLICT', 409)
    fields = set(d.WeixinGenerationDispatchReceiptView.model_fields) - {'mode', 'state', 'conversation_id'}
    return d.WeixinGenerationDispatchReceiptView(conversation_id=cid,
        **value.model_dump(mode='python', include=fields))


def dispatch_descriptor(actor, cid, request, *, database):
    """Resolve the root CID and fixed source in the same final delivery transaction."""
    from . import generation_dispatch
    request = d.WeixinGenerationDispatchInput.model_validate(request.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        current, mapping_id = _generation_context(actor, cid, db)
        value = generation_dispatch._dispatch(current, request.descriptor_id, db, root_mapping_id=mapping_id)
        result = _dispatch_receipt(value, db)
    return result


def find_dispatch(actor, cid, descriptor_id, *, database):
    """Query one fixed acknowledgement; a target CID cannot reverse-resolve its root."""
    from . import generation_dispatch
    with accounts._transaction(database) as db:
        current, _, mapping, _, _ = _context(actor, cid, db)
        if mapping is None:
            return None
        value = generation_dispatch._find(current, descriptor_id, db, root_mapping_id=mapping.id)
        result = _dispatch_receipt(value, db) if value is not None else None
    return result
