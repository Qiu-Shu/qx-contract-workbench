"""Credential-free synthetic accounts and immutable exact peer mappings."""
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from .. import domain as d
from ..assistant.service import _at, _current, _digest, _snapshot, _workspace_id
from ..config import canonical_json
from ..ops.storage import require_active
from ..persistence import MatterRow, MembershipRow
from ..security import ServiceError, _ACTIONS


@contextmanager
def _transaction(database):
    # Database's begin listener obtains BEGIN IMMEDIATE before any identity read.
    try:
        with database.session() as db:
            db.connection()
            yield db
    except IntegrityError:
        raise ServiceError('VERSION_CONFLICT', 409) from None


def _account(actor, identifier, db, *, active=True):
    current = _current(actor, db)
    if active:
        require_active(db)
    row = db.execute(text('SELECT * FROM weixin_accounts WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if (row is None or row['owner_id'] != str(current.user_id)
            or row['workspace_id'] != str(_workspace_id(db))):
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    try:
        value = d.WeixinAccountSnapshot(**row)
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None
    if active and value.revoked_at is not None:
        raise ServiceError('STATE_CONFLICT', 409)
    return value, current


def _mapping(row):
    try:
        values = dict(row)
        values['scope'] = d.ScopeSnapshot.model_validate_json(values.pop('scope_json'))
        return d.WeixinPeerBindingSnapshot(**values)
    except (ValueError, TypeError):
        raise ServiceError('VERSION_CONFLICT', 409) from None


def _mapping_row(identifier, db):
    row = db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'),
                     {'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return row


def _mapping_reason(current, account, mapping, db):
    """Classify current authority without audit writes or transaction side effects."""
    if account.revoked_at is not None or mapping.revoked_at is not None:
        return 'binding_revoked'
    try:
        current = _current(current, db)
        workspace = _workspace_id(db)
        if (account.owner_id != current.user_id or account.workspace_id != workspace
                or mapping.account_id != account.id or mapping.scope.workspace_id != workspace):
            return 'scope_denied'
        binding = db.execute(text('SELECT * FROM task_channel_bindings WHERE id=:id'),
                             {'id':str(mapping.task_binding_id)}).mappings().first()
        if binding is None or binding['channel'] != 'synthetic':
            return 'scope_denied'
        row = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'),
                         {'id':binding['conversation_id']}).mappings().first()
        if (row is None or row['owner_id'] != str(current.user_id)
                or row['workspace_id'] != str(workspace)
                or row['id'] != str(mapping.scope.conversation_id)):
            return 'scope_denied'
        if row['archived_at'] is not None or _snapshot(row) != mapping.scope:
            return 'scope_stale'

        def matter_access(identifier):
            matter = db.get(MatterRow, str(identifier), populate_existing=True)
            return (matter is not None and matter.status != 'archived'
                    and bool(current.roles & _ACTIONS['read']) and db.get(MembershipRow,
                        (str(identifier), str(current.user_id)), populate_existing=True) is not None)

        def intake_access(identifier):
            intake = db.execute(text('SELECT owner_id,matter_id FROM intake_cases WHERE id=:id'),
                                {'id':str(identifier)}).mappings().first()
            return (intake is not None and intake['owner_id'] == str(current.user_id)
                    and (intake['matter_id'] is None or matter_access(intake['matter_id'])))

        if row['scope_kind'] == 'matter' and not matter_access(row['scope_ref']):
            return 'scope_denied'
        if row['scope_kind'] == 'intake' and not intake_access(row['scope_ref']):
            return 'scope_denied'
        if row['projection_intake_id'] is not None and not intake_access(row['projection_intake_id']):
            return 'scope_denied'
    except (ServiceError, ValueError, TypeError):
        return 'scope_denied'
    return None


def _require_mapping(reason):
    if reason == 'binding_revoked':
        raise ServiceError('STATE_CONFLICT', 409)
    if reason == 'scope_stale':
        raise ServiceError('VERSION_CONFLICT', 409)
    if reason is not None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)


def create_synthetic_account(actor, request, *, database):
    request = d.WeixinAccountCreateInput.model_validate(request.model_dump(mode='python'))
    with _transaction(database) as db:
        current = _current(actor, db)
        require_active(db)
        workspace = _workspace_id(db)
        previous = db.execute(text('''SELECT id FROM weixin_accounts
            WHERE workspace_id=:workspace AND bot_account_id=:bot'''),
            {'workspace':str(workspace), 'bot':request.bot_account_id}).mappings().first()
        if previous:
            value, _ = _account(current, previous['id'], db)
            if value.initial_cursor != request.initial_cursor:
                raise ServiceError('VERSION_CONFLICT', 409)
            return value
        value = d.WeixinAccountSnapshot(id=uuid4(), workspace_id=workspace, owner_id=current.user_id,
            bot_account_id=request.bot_account_id, initial_cursor=request.initial_cursor,
            upstream_cursor=request.initial_cursor, checkpoint_revision=0, created_at=_at())
        values = value.model_dump(mode='json')
        db.execute(text('INSERT INTO weixin_accounts ('+','.join(values)+') VALUES ('+
                        ','.join(':'+key for key in values)+')'), values)
        return value


def read_synthetic_account(actor, account_id, *, database):
    with _transaction(database) as db:
        return _account(actor, account_id, db, active=False)[0]


def bind_synthetic_peer(actor, account_id, request, *, database):
    request = d.WeixinPeerBindInput.model_validate(request.model_dump(mode='python'))
    with _transaction(database) as db:
        account, current = _account(actor, account_id, db)
        value = d.WeixinPeerBindingSnapshot(id=uuid4(), account_id=account.id,
            sender_peer_id=request.sender_peer_id, task_binding_id=request.task_binding_id,
            scope=request.expected_scope, scope_sha256=_digest(request.expected_scope.model_dump(mode='json')),
            created_at=_at())
        _require_mapping(_mapping_reason(current, account, value, db))
        previous = db.execute(text('''SELECT * FROM weixin_peer_bindings
            WHERE (account_id=:account AND sender_peer_id=:peer) OR task_binding_id=:binding'''),
            {'account':str(account.id), 'peer':request.sender_peer_id,
             'binding':str(request.task_binding_id)}).mappings().all()
        if previous:
            if len(previous) != 1:
                raise ServiceError('VERSION_CONFLICT', 409)
            existing = _mapping(previous[0])
            if (existing.account_id != account.id or existing.sender_peer_id != value.sender_peer_id
                    or existing.task_binding_id != value.task_binding_id or existing.scope != value.scope):
                raise ServiceError('VERSION_CONFLICT', 409)
            _require_mapping(_mapping_reason(current, account, existing, db))
            return existing
        values = value.model_dump(mode='json', exclude={'scope'})
        values['scope_json'] = canonical_json(value.scope.model_dump(mode='json'))
        db.execute(text('INSERT INTO weixin_peer_bindings ('+','.join(values)+') VALUES ('+
                        ','.join(':'+key for key in values)+')'), values)
        return value


def read_synthetic_peer(actor, mapping_id, *, database):
    with _transaction(database) as db:
        current = _current(actor, db)
        row = _mapping_row(mapping_id, db)
        _account(current, row['account_id'], db, active=False)
        return _mapping(row)


def _revoke(actor, identifier, request, database, *, peer):
    request = d.WeixinRevokeInput.model_validate(request.model_dump(mode='python'))
    with _transaction(database) as db:
        current = _current(actor, db)
        if peer:
            row = _mapping_row(identifier, db)
            _, current = _account(current, row['account_id'], db, active=False)
            value = _mapping(row)
        else:
            value, current = _account(current, identifier, db, active=False)
        require_active(db)
        if value.revoked_at is not None:
            if value.revoke_reason != request.reason:
                raise ServiceError('VERSION_CONFLICT', 409)
            return value
        changes = {'revoked_at':_at(), 'revoked_by':str(current.user_id), 'revoke_reason':request.reason}
        table = 'weixin_peer_bindings' if peer else 'weixin_accounts'
        db.execute(text('UPDATE '+table+''' SET revoked_at=:revoked_at,revoked_by=:revoked_by,
            revoke_reason=:revoke_reason WHERE id=:id'''), {**changes, 'id':str(identifier)})
        return type(value).model_validate({**value.model_dump(mode='python'), **changes})


def revoke_synthetic_account(actor, account_id, request, *, database):
    return _revoke(actor, account_id, request, database, peer=False)


def revoke_synthetic_peer(actor, mapping_id, request, *, database):
    return _revoke(actor, mapping_id, request, database, peer=True)
