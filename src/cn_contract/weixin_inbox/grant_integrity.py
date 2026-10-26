"""Validate immutable same-target scope grants without current authorization or replay."""
from sqlalchemy import text

from .. import domain as d
from ..assistant.profile_integrity import _scope
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..task_drafts.integrity import _at
from .integrity import _canonical_model, _row_ids, _uuid


def _fail():
    raise ValueError('WEIXIN_GRANT_INTEGRITY')


def _scope_at(mapping, grants, at):
    """A future grant cannot supply authority for an older persisted activity."""
    return next((value.scope for value in reversed(grants) if value.created_at <= at), mapping.scope)


def _histories(db, workspace):
    if not db.scalar(text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='weixin_peer_scope_grants'")):
        return {}
    rows = db.execute(text('SELECT * FROM weixin_peer_scope_grants ORDER BY mapping_id,revision')).mappings().all()
    if not rows:
        return {}
    tables = {}
    for table in ('weixin_accounts', 'weixin_peer_bindings', 'task_channel_bindings', 'assistant_conversations'):
        tables[table] = {row['id']:row for row in db.execute(text('SELECT * FROM '+table)).mappings()}
    users = set(db.scalars(text('SELECT id FROM users')))
    polls = {}
    for row in db.execute(text('SELECT account_id,next_revision,created_at FROM weixin_poll_receipts')).mappings():
        if type(row['next_revision']) is not int or row['next_revision'] < 1:
            _fail()
        polls.setdefault(_uuid(row['account_id']), []).append((row['next_revision'], _at(row['created_at'])))

    result, account_times = {}, {}
    identities = ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision')
    for row in rows:
        _row_ids(row, ('id', 'mapping_id', 'request_id', 'actor_id'))
        scope = _canonical_model(d.ScopeSnapshot, row['scope_json'])
        grant = d.WeixinPeerScopeGrant(**{key:item for key,item in row.items() if key != 'scope_json'}, scope=scope)
        mapping_row = tables['weixin_peer_bindings'][str(grant.mapping_id)]
        _row_ids(mapping_row, ('id', 'account_id', 'task_binding_id', 'revoked_by'))
        original = _canonical_model(d.ScopeSnapshot, mapping_row['scope_json'])
        mapping = d.WeixinPeerBindingSnapshot(**{key:item for key,item in mapping_row.items() if key != 'scope_json'}, scope=original)
        account_row = tables['weixin_accounts'][str(mapping.account_id)]
        _row_ids(account_row, ('id', 'workspace_id', 'owner_id', 'revoked_by'))
        account = d.WeixinAccountSnapshot(**account_row)
        binding_row = tables['task_channel_bindings'][str(mapping.task_binding_id)]
        _row_ids(binding_row, ('id', 'conversation_id'))
        binding = d.TaskChannelBindingView(**binding_row)
        conversation = tables['assistant_conversations'][str(binding.conversation_id)]
        _row_ids(conversation, ('id', 'workspace_id', 'owner_id'))
        history = result.setdefault(str(mapping.id), [])
        previous = history[-1] if history else None
        prior_scope = previous.scope if previous else original
        prior_hash = previous.scope_sha256 if previous else mapping.scope_sha256
        prior_at = previous.created_at if previous else mapping.created_at
        stamps = account_times.setdefault(str(account.id), set())
        checkpoint = max((revision for revision,at in polls.get(str(account.id), ()) if at < grant.created_at), default=0)
        if (grant.actor_id != account.owner_id or str(grant.actor_id) not in users
                or str(account.workspace_id) != workspace or conversation['workspace_id'] != workspace
                or conversation['owner_id'] != str(account.owner_id) or original.conversation_id != binding.conversation_id
                or mapping.created_at < account.created_at or mapping.created_at < binding.created_at
                or grant.revision != len(history)+1 or grant.previous_scope_sha256 != prior_hash
                or any(getattr(scope, key) != getattr(prior_scope, key) for key in identities)
                or scope.input_revision < prior_scope.input_revision or scope.materials_revision < prior_scope.materials_revision
                or (scope.input_revision, scope.materials_revision) == (prior_scope.input_revision, prior_scope.materials_revision)
                or grant.created_at <= prior_at or grant.created_at <= account.created_at
                or grant.created_at in stamps or grant.checkpoint_revision != checkpoint
                or grant.checkpoint_revision > account.checkpoint_revision
                or any((revision <= grant.checkpoint_revision) != (at < grant.created_at)
                       for revision,at in polls.get(str(account.id), ()))
                or account.revoked_at is not None and account.revoked_at <= grant.created_at
                or mapping.revoked_at is not None and mapping.revoked_at <= grant.created_at):
            _fail()
        _scope(db, original, conversation, workspace, mapping.created_at)
        _scope(db, scope, conversation, workspace, grant.created_at)
        stamps.add(grant.created_at)
        history.append(grant)
    return {key:tuple(values) for key,values in result.items()}


def validate_peer_scope_grants(db, *, allow_grants=False):
    """Return no refs; nonempty grant history requires a complete native archive."""
    try:
        schema = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
        if identify_schema(schema, native=native) not in ('weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1'):
            return []
        rows = db.execute(text('SELECT * FROM weixin_peer_scope_grants')).mappings().all()
        if not rows:
            return []
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_GRANT_INTEGRITY') from None
    if not allow_grants:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        _histories(db, _uuid(identities[0]))
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_GRANT_INTEGRITY') from None
    return []
