"""Credential-free synthetic accounts and immutable exact peer mappings."""
from contextlib import contextmanager
from datetime import datetime, timedelta
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
    if active and (value.revoked_at is not None or _has_generations(value.id, db)):
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


def _mapping_reason(current, account, mapping, db, *, scope=None):
    """Classify current authority without audit writes or transaction side effects."""
    if account.revoked_at is not None or mapping.revoked_at is not None:
        return 'binding_revoked'
    try:
        current = _current(current, db)
        workspace = _workspace_id(db)
        scope = scope if scope is not None else _effective_scope(mapping, db)
        if (account.owner_id != current.user_id or account.workspace_id != workspace
                or mapping.account_id != account.id or scope.workspace_id != workspace):
            return 'scope_denied'
        if _has_generations(account.id, db):
            return 'scope_stale'
        return _scope_reason(current, account, mapping.task_binding_id, scope, db, active=True)
    except (ServiceError, ValueError, TypeError):
        return 'scope_denied'
    return None


def _scope_reason(current, account, binding_id, scope, db, *, active):
    """Check a synthetic target without audit writes or transaction side effects."""
    try:
        current = _current(current, db)
        workspace = _workspace_id(db)
        if (account.owner_id != current.user_id or account.workspace_id != workspace
                or scope.workspace_id != workspace):
            return 'scope_denied'
        binding = db.execute(text('SELECT * FROM task_channel_bindings WHERE id=:id'),
                             {'id':str(binding_id)}).mappings().first()
        if binding is None or binding['channel'] != 'synthetic':
            return 'scope_denied'
        row = db.execute(text('SELECT * FROM assistant_conversations WHERE id=:id'),
                         {'id':binding['conversation_id']}).mappings().first()
        if (row is None or row['owner_id'] != str(current.user_id)
                or row['workspace_id'] != str(workspace)
                or row['id'] != str(scope.conversation_id)):
            return 'scope_denied'
        if active and (row['archived_at'] is not None or _snapshot(row) != scope):
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


def _activity_time(account_id, db, *, now, after=False, floor=()):
    """Keep UTC causal order when the wall clock repeats or moves backwards."""
    queries = [
        'SELECT created_at stamp FROM weixin_accounts WHERE id=:id',
        'SELECT revoked_at stamp FROM weixin_accounts WHERE id=:id',
        'SELECT created_at stamp FROM weixin_peer_bindings WHERE account_id=:id',
        'SELECT revoked_at stamp FROM weixin_peer_bindings WHERE account_id=:id',
        'SELECT created_at stamp FROM weixin_poll_receipts WHERE account_id=:id',
    ]
    if db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_dispatch_receipts'")):
        queries.append('SELECT created_at stamp FROM weixin_dispatch_receipts WHERE account_id=:id')
    if db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_peer_scope_grants'")):
        queries.append('''SELECT grant_record.created_at stamp FROM weixin_peer_scope_grants grant_record
            JOIN weixin_peer_bindings mapping ON mapping.id=grant_record.mapping_id WHERE mapping.account_id=:id''')
    if db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_peer_generations'")):
        queries.append('''SELECT generation.created_at stamp FROM weixin_peer_generations generation
            JOIN weixin_peer_bindings mapping ON mapping.id=generation.root_mapping_id WHERE mapping.account_id=:id''')
    stamps = db.scalars(text('SELECT stamp FROM ('+
        ' UNION ALL '.join(queries)+') WHERE stamp IS NOT NULL'), {'id':str(account_id)})
    try:
        current = datetime.fromisoformat(now.replace('Z','+00:00'))
        previous = [datetime.fromisoformat(value.replace('Z','+00:00'))
                    for value in (*stamps,*floor) if value is not None]
        if any(value.utcoffset() != timedelta(0) for value in (current,*previous)):
            raise ValueError('UTC required')
        if previous:
            bound = max(previous) + (timedelta(microseconds=1) if after else timedelta(0))
            current = max(current,bound)
        return current.isoformat().replace('+00:00','Z')
    except (ValueError,TypeError,OverflowError):
        raise ServiceError('VERSION_CONFLICT',409) from None


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
            created_at=_activity_time(account.id,db,now=_at(),floor=(db.scalar(text(
                'SELECT created_at FROM task_channel_bindings WHERE id=:id'),
                {'id':str(request.task_binding_id)}),)))
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
        changes = {'revoked_at':_activity_time(value.account_id if peer else value.id,db,now=_at(),after=True),
                   'revoked_by':str(current.user_id), 'revoke_reason':request.reason}
        table = 'weixin_peer_bindings' if peer else 'weixin_accounts'
        db.execute(text('UPDATE '+table+''' SET revoked_at=:revoked_at,revoked_by=:revoked_by,
            revoke_reason=:revoke_reason WHERE id=:id'''), {**changes, 'id':str(identifier)})
        return type(value).model_validate({**value.model_dump(mode='python'), **changes})


def revoke_synthetic_account(actor, account_id, request, *, database):
    return _revoke(actor, account_id, request, database, peer=False)


def revoke_synthetic_peer(actor, mapping_id, request, *, database):
    return _revoke(actor, mapping_id, request, database, peer=True)


def _same_target(left, right):
    return all(getattr(left,key)==getattr(right,key) for key in (
        'workspace_id','conversation_id','scope_kind','scope_ref','binding_revision'))


def _newer_scope(previous, current):
    return (_same_target(previous,current) and current!=previous
        and current.input_revision>=previous.input_revision
        and current.materials_revision>=previous.materials_revision)


def _grant_table(db):
    if db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_peer_scope_grants'")):
        return True
    from ..storage_schema import identify_schema
    rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    try:
        identify_schema(rows,native=any(row[0]=='table' and row[1]=='local_workspace_identity' for row in rows))
    except ValueError:
        raise ServiceError('VERSION_CONFLICT',409) from None
    return False


def _has_generations(account_id, db):
    """Keep legacy write paths paused after explicit target history."""
    if db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_peer_generations'")):
        return db.scalar(text('''SELECT 1 FROM weixin_peer_generations generation
            JOIN weixin_peer_bindings mapping ON mapping.id=generation.root_mapping_id
            WHERE mapping.account_id=:id LIMIT 1'''), {'id':str(account_id)}) is not None
    from ..storage_schema import identify_schema
    rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
    try:
        identify_schema(rows, native=any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in rows))
    except ValueError:
        raise ServiceError('VERSION_CONFLICT', 409) from None
    return False


def _grant(row):
    try:
        values=dict(row);raw=values.pop('scope_json')
        values['scope']=d.ScopeSnapshot.model_validate_json(raw)
        if raw!=canonical_json(values['scope'].model_dump(mode='json')):
            raise ValueError('noncanonical scope')
        return d.WeixinPeerScopeGrant(**values)
    except (ValueError,TypeError):
        raise ServiceError('VERSION_CONFLICT',409) from None


def _grant_history(mapping, db):
    if not _grant_table(db):
        return ()
    history=tuple(_grant(row) for row in db.execute(text('''SELECT * FROM weixin_peer_scope_grants
        WHERE mapping_id=:id ORDER BY revision'''),{'id':str(mapping.id)}).mappings())
    previous=mapping.scope;at=mapping.created_at
    owner=db.scalar(text('SELECT owner_id FROM weixin_accounts WHERE id=:id'),{'id':str(mapping.account_id)})
    for revision,value in enumerate(history,1):
        if (value.mapping_id!=mapping.id or str(value.actor_id)!=owner or value.revision!=revision
                or value.previous_scope_sha256!=_digest(previous.model_dump(mode='json'))
                or not _newer_scope(previous,value.scope) or value.created_at<=at):
            raise ServiceError('VERSION_CONFLICT',409)
        previous=value.scope;at=value.created_at
    return history


def _effective_scope(mapping, db, *, at=None):
    history=_grant_history(mapping,db)
    if at is not None:
        try:
            boundary=at if isinstance(at,datetime) else datetime.fromisoformat(at.replace('Z','+00:00'))
            if boundary.utcoffset()!=timedelta(0):raise ValueError('UTC required')
        except (ValueError,TypeError,AttributeError):
            raise ServiceError('VERSION_CONFLICT',409) from None
        history=tuple(value for value in history if value.created_at<=boundary)
    return history[-1].scope if history else mapping.scope


def refresh_synthetic_peer(actor, mapping_id, request, *, database):
    """Explicitly authorize newer input/material versions; never change the target."""
    request=d.WeixinPeerRefreshInput.model_validate(request.model_dump(mode='python'))
    with _transaction(database) as db:
        current=_current(actor,db)
        row=_mapping_row(mapping_id,db)
        account,current=_account(current,row['account_id'],db)
        mapping=_mapping(row)
        history=_grant_history(mapping,db)
        existing=next((value for value in history if value.request_id==request.request_id),None)
        if existing is not None:
            if (request.expected_grant_revision!=existing.revision-1
                    or request.expected_scope_sha256!=existing.previous_scope_sha256
                    or request.expected_scope!=existing.scope or request.reason!=existing.reason):
                raise ServiceError('VERSION_CONFLICT',409)
            _require_mapping(_mapping_reason(current,account,mapping,db))
            return existing
        previous=history[-1].scope if history else mapping.scope
        if (request.expected_grant_revision!=len(history)
                or request.expected_scope_sha256!=_digest(previous.model_dump(mode='json'))
                or not _newer_scope(previous,request.expected_scope)):
            raise ServiceError('VERSION_CONFLICT',409)
        _require_mapping(_mapping_reason(current,account,mapping,db,scope=request.expected_scope))
        if not _grant_table(db):
            raise ServiceError('VERSION_CONFLICT',409)
        values=dict(id=str(uuid4()),mapping_id=str(mapping.id),request_id=str(request.request_id),
            actor_id=str(current.user_id),revision=len(history)+1,
            previous_scope_sha256=request.expected_scope_sha256,scope=request.expected_scope.model_dump(mode='json'),
            scope_sha256=_digest(request.expected_scope.model_dump(mode='json')),
            checkpoint_revision=account.checkpoint_revision,reason=request.reason,
            created_at=_activity_time(account.id,db,now=_at(),after=True))
        grant=d.WeixinPeerScopeGrant(**values,grant_sha256=_digest(values))
        stored=grant.model_dump(mode='json',exclude={'scope'})
        stored['scope_json']=canonical_json(grant.scope.model_dump(mode='json'))
        db.execute(text('INSERT INTO weixin_peer_scope_grants ('+','.join(stored)+') VALUES ('+
            ','.join(':'+key for key in stored)+')'),stored)
    return grant


def find_peer_scope_grant(actor, mapping_id, request_id, *, database):
    """Read a fixed refresh result under current authority, including restored copies."""
    with _transaction(database) as db:
        current=_current(actor,db)
        row=_mapping_row(mapping_id,db)
        account,current=_account(current,row['account_id'],db,active=False)
        mapping=_mapping(row)
        _require_mapping(_mapping_reason(current,account,mapping,db))
        return next((value for value in _grant_history(mapping,db) if str(value.request_id)==str(request_id)),None)
