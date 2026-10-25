"""Validate immutable cross-conversation target history without enabling runtime."""
import hashlib

from sqlalchemy import text

from .. import domain as d
from ..assistant.profile_integrity import _scope
from ..config import canonical_json
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..task_drafts.integrity import _at
from .grant_integrity import _histories, _scope_at
from .integrity import _canonical_model, _row_ids, _uuid


def _fail():
    raise ValueError('WEIXIN_GENERATION_INTEGRITY')


def _scope_sources(db, scope, at):
    for revision, query in (
        (scope.input_revision, '''SELECT created_at FROM assistant_messages
            WHERE conversation_id=:cid AND source_revision=:rev AND role='user' '''),
        (scope.materials_revision, '''SELECT created_at FROM assistant_material_snapshots
            WHERE conversation_id=:cid AND revision=:rev'''),
    ):
        if revision:
            created_at = db.scalar(text(query), {'cid':str(scope.conversation_id), 'rev':revision})
            if created_at is None or _at(created_at) > at:
                _fail()


def _validate(db, rows, workspace, *, allow_target_polls=False):
    tables = {}
    for table in ('weixin_accounts', 'weixin_peer_bindings', 'task_channel_bindings', 'assistant_conversations'):
        tables[table] = {row['id']:row for row in db.execute(text('SELECT * FROM '+table)).mappings()}
    users = set(db.scalars(text('SELECT id FROM users')))
    occupied = {row['task_binding_id'] for row in tables['weixin_peer_bindings'].values()}
    grants = _histories(db, workspace)
    activities, polls = {}, {}
    for row in db.execute(text('SELECT account_id,next_revision,created_at FROM weixin_poll_receipts')).mappings():
        at = _at(row['created_at'])
        if not allow_target_polls:
            activities.setdefault(row['account_id'], []).append(at)
        polls.setdefault(row['account_id'], []).append((row['next_revision'], at))
    for row in db.execute(text('SELECT account_id,created_at FROM weixin_dispatch_receipts')).mappings():
        activities.setdefault(row['account_id'], []).append(_at(row['created_at']))
    for mapping_id, history in grants.items():
        account_id = tables['weixin_peer_bindings'][mapping_id]['account_id']
        activities.setdefault(account_id, []).extend(value.created_at for value in history)

    histories, used_bindings = {}, set()
    for row in rows:
        _row_ids(row, ('id', 'root_mapping_id', 'request_id', 'actor_id', 'task_binding_id'))
        scope = _canonical_model(d.ScopeSnapshot, row['scope_json'])
        value = d.WeixinPeerGeneration(**{key:item for key,item in row.items() if key != 'scope_json'}, scope=scope)
        root_row = tables['weixin_peer_bindings'][str(value.root_mapping_id)]
        _row_ids(root_row, ('id', 'account_id', 'task_binding_id', 'revoked_by'))
        root_scope = _canonical_model(d.ScopeSnapshot, root_row['scope_json'])
        root = d.WeixinPeerBindingSnapshot(**{key:item for key,item in root_row.items() if key != 'scope_json'}, scope=root_scope)
        account_row = tables['weixin_accounts'][str(root.account_id)]
        _row_ids(account_row, ('id', 'workspace_id', 'owner_id', 'revoked_by'))
        account = d.WeixinAccountSnapshot(**account_row)
        binding_row = tables['task_channel_bindings'][str(value.task_binding_id)]
        _row_ids(binding_row, ('id', 'conversation_id'))
        binding = d.TaskChannelBindingView(**binding_row)
        conversation = tables['assistant_conversations'][str(binding.conversation_id)]
        _row_ids(conversation, ('id', 'workspace_id', 'owner_id'))
        history = histories.setdefault(str(root.id), [])
        previous = history[-1] if history else None
        previous_scope = previous.scope if previous else _scope_at(root, grants.get(str(root.id), ()), value.created_at)
        previous_scope_hash = hashlib.sha256(canonical_json(previous_scope.model_dump(mode='json')).encode('utf-8')).hexdigest()
        checkpoint = max((revision for revision,at in polls.get(str(account.id), ()) if at < value.created_at), default=0)
        if (value.actor_id != account.owner_id or str(value.actor_id) not in users
                or str(account.workspace_id) != workspace or conversation['workspace_id'] != workspace
                or conversation['owner_id'] != str(account.owner_id) or scope.conversation_id != binding.conversation_id
                or str(scope.workspace_id) != workspace or binding_row['id'] in occupied
                or binding_row['id'] in used_bindings or scope.conversation_id == root.scope.conversation_id
                or any(scope.conversation_id == prior.scope.conversation_id for prior in history)
                or value.generation != len(history)+1
                or value.previous_generation_sha256 != (previous.generation_sha256 if previous else None)
                or value.previous_scope_sha256 != previous_scope_hash
                or value.created_at <= root.created_at or value.created_at <= account.created_at
                or value.created_at <= binding.created_at or value.created_at <= _at(conversation['created_at'])
                or previous is not None and value.created_at <= previous.created_at
                or any(at >= value.created_at for at in activities.get(str(account.id), ()))
                or value.checkpoint_revision != checkpoint or checkpoint > account.checkpoint_revision
                or not allow_target_polls and checkpoint != account.checkpoint_revision
                or any((revision <= checkpoint) != (at < value.created_at) or at == value.created_at
                       for revision,at in polls.get(str(account.id), ()))
                or account.revoked_at is not None and account.revoked_at <= value.created_at
                or root.revoked_at is not None and root.revoked_at <= value.created_at):
            _fail()
        _scope(db, scope, conversation, workspace, value.created_at)
        _scope_sources(db, scope, value.created_at)
        used_bindings.add(binding_row['id'])
        history.append(value)


def validate_peer_generations(db, *, allow_generations=False):
    """Return no file refs; nonempty generations require a complete native archive."""
    try:
        schema = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
        version = identify_schema(schema, native=native)
        if version not in ('weixin-generations-v1', 'weixin-target-provenance-v1'):
            return []
        rows = db.execute(text('SELECT * FROM weixin_peer_generations ORDER BY root_mapping_id,generation')).mappings().all()
        if not rows:
            return []
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_GENERATION_INTEGRITY') from None
    if not allow_generations:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        from .integrity import validate_weixin_records
        from .dispatch_integrity import validate_dispatch_records
        from .grant_integrity import validate_peer_scope_grants
        validate_weixin_records(db, allow_inbox=True)
        validate_dispatch_records(db, allow_dispatch=True)
        validate_peer_scope_grants(db, allow_grants=True)
        _validate(db, rows, _uuid(identities[0]), allow_target_polls=version=='weixin-target-provenance-v1')
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_GENERATION_INTEGRITY') from None
    return []
