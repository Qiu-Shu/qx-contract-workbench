"""Explicit immutable target appends; the account remains paused for intake."""
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _at, _current, _digest, _owned, _snapshot
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError
from ..storage_schema import identify_schema
from . import accounts
from .conversation import _active_targets
from .generation_integrity import validate_peer_generations


def _conflict():
    raise ServiceError('VERSION_CONFLICT', 409)


def _generation(row):
    try:
        values = dict(row)
        raw = values.pop('scope_json')
        values['scope'] = d.ScopeSnapshot.model_validate_json(raw)
        if raw != canonical_json(values['scope'].model_dump(mode='json')):
            _conflict()
        return d.WeixinPeerGeneration(**values)
    except (ValueError, TypeError):
        _conflict()


def _schema(db):
    try:
        schema = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
        if identify_schema(schema, native=native) not in ('weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1', 'assistant-evidence-v1'):
            _conflict()
    except ValueError:
        _conflict()


def _history(mapping, db):
    try:
        _schema(db)
        if db.scalar(text('SELECT 1 FROM weixin_peer_generations LIMIT 1')) is None:
            from .integrity import validate_weixin_records
            from .dispatch_integrity import validate_dispatch_records
            from .grant_integrity import validate_peer_scope_grants
            validate_weixin_records(db, allow_inbox=True)
            validate_dispatch_records(db, allow_dispatch=True)
            validate_peer_scope_grants(db, allow_grants=True)
        validate_peer_generations(db, allow_generations=True)
        return tuple(_generation(row) for row in db.execute(text('''SELECT * FROM weixin_peer_generations
            WHERE root_mapping_id=:id ORDER BY generation'''), {'id':str(mapping.id)}).mappings())
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError):
        _conflict()


def _target(current, binding_id, db, *, active):
    row = db.execute(text('SELECT * FROM task_channel_bindings WHERE id=:id'),
        {'id':str(binding_id)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    try:
        binding = d.TaskChannelBindingView(**row)
    except (ValueError, TypeError):
        _conflict()
    conversation = _owned(current, binding.conversation_id, db)
    _active_targets(conversation, db)
    if active and conversation['archived_at'] is not None:
        raise ServiceError('STATE_CONFLICT', 409)
    return binding, conversation


def _root(actor, identifier, db, *, active):
    current = _current(actor, db)
    if active:
        require_active(db)
    _schema(db)
    row = accounts._mapping_row(identifier, db)
    account, current = accounts._account(current, row['account_id'], db, active=False)
    mapping = accounts._mapping(row)
    binding, conversation = _target(current, mapping.task_binding_id, db, active=active)
    if (binding.conversation_id != mapping.scope.conversation_id
            or mapping.scope.workspace_id != account.workspace_id):
        _conflict()
    if active and (account.revoked_at is not None or mapping.revoked_at is not None):
        raise ServiceError('STATE_CONFLICT', 409)
    return current, account, mapping


def _original_request(value):
    return d.WeixinPeerGenerationInput(request_id=value.request_id, expected_generation=value.generation-1,
        expected_previous_generation_sha256=value.previous_generation_sha256,
        expected_previous_scope_sha256=value.previous_scope_sha256,
        expected_checkpoint_revision=value.checkpoint_revision, task_binding_id=value.task_binding_id,
        expected_scope=value.scope, reason=value.reason)


def append_synthetic_generation(actor, root_mapping_id, request, *, database):
    """Append once under current object permissions and a complete predecessor CAS."""
    request = d.WeixinPeerGenerationInput.model_validate(request.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        current, account, mapping = _root(actor, root_mapping_id, db, active=True)
        history = _history(mapping, db)
        if history:
            _target(current, history[-1].task_binding_id, db, active=True)
        existing = next((value for value in history if value.request_id == request.request_id), None)
        binding, conversation = _target(current, existing.task_binding_id if existing else request.task_binding_id, db, active=True)
        if (existing.scope if existing else request.expected_scope) != _snapshot(conversation):
            _conflict()
        if existing is not None:
            if request != _original_request(existing):
                _conflict()
            return existing
        previous = history[-1] if history else None
        previous_scope_hash = (previous.scope_sha256 if previous else
            _digest(accounts._effective_scope(mapping, db).model_dump(mode='json')))
        if (request.expected_generation != len(history)
                or request.expected_previous_generation_sha256 != (previous.generation_sha256 if previous else None)
                or request.expected_previous_scope_sha256 != previous_scope_hash
                or request.expected_checkpoint_revision != account.checkpoint_revision
                or binding.conversation_id == mapping.scope.conversation_id
                or any(value.scope.conversation_id == binding.conversation_id for value in history)
                or db.scalar(text('SELECT 1 FROM weixin_peer_bindings WHERE task_binding_id=:id'),
                    {'id':str(binding.id)}) is not None
                or db.scalar(text('SELECT 1 FROM weixin_peer_generations WHERE task_binding_id=:id'),
                    {'id':str(binding.id)}) is not None):
            _conflict()
        floor = [conversation['created_at'], binding.created_at.isoformat()]
        for revision, query in (
            (request.expected_scope.input_revision, '''SELECT created_at FROM assistant_messages
                WHERE conversation_id=:cid AND source_revision=:rev AND role='user' '''),
            (request.expected_scope.materials_revision, '''SELECT created_at FROM assistant_material_snapshots
                WHERE conversation_id=:cid AND revision=:rev'''),
        ):
            if revision:
                stamp = db.scalar(text(query), {'cid':conversation['id'], 'rev':revision})
                if stamp is None:
                    _conflict()
                floor.append(stamp)
        values = dict(id=str(uuid4()), root_mapping_id=str(mapping.id), generation=len(history)+1,
            request_id=str(request.request_id), actor_id=str(current.user_id), task_binding_id=str(binding.id),
            scope=request.expected_scope.model_dump(mode='json'), scope_sha256=_digest(request.expected_scope.model_dump(mode='json')),
            previous_generation_sha256=request.expected_previous_generation_sha256,
            previous_scope_sha256=previous_scope_hash, checkpoint_revision=account.checkpoint_revision,
            created_at=accounts._activity_time(account.id, db, now=_at(), after=True, floor=floor), reason=request.reason)
        value = d.WeixinPeerGeneration(**values, generation_sha256=_digest(values))
        stored = value.model_dump(mode='json', exclude={'scope'})
        stored['scope_json'] = canonical_json(value.scope.model_dump(mode='json'))
        db.execute(text('INSERT INTO weixin_peer_generations ('+','.join(stored)+') VALUES ('+
            ','.join(':'+key for key in stored)+')'), stored)
        _history(mapping, db)
    return value


def find_peer_generation(actor, root_mapping_id, request_id, *, database):
    """Only query fixed metadata under current root and recorded target authority."""
    with accounts._transaction(database) as db:
        current, _, mapping = _root(actor, root_mapping_id, db, active=False)
        history = _history(mapping, db)
        value = next((value for value in history if str(value.request_id) == str(request_id)), None)
        if value is not None:
            _target(current, value.task_binding_id, db, active=False)
    return value


def read_peer_generation_head(actor, root_mapping_id, *, database):
    """Read root, history, latest target and checkpoint under one SQLite lock."""
    with accounts._transaction(database) as db:
        current, account, mapping = _root(actor, root_mapping_id, db, active=False)
        history = _history(mapping, db)
        latest = history[-1] if history else None
        if latest is not None:
            _target(current, latest.task_binding_id, db, active=False)
        scope = latest.scope if latest else accounts._effective_scope(mapping, db)
        return d.WeixinGenerationHeadView(generation=len(history),
            generation_sha256=latest.generation_sha256 if latest else None,
            scope=scope, scope_sha256=_digest(scope.model_dump(mode='json')),
            checkpoint_revision=account.checkpoint_revision)
