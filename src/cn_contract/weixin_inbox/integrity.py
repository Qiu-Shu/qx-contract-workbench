"""Validate synthetic poll provenance without authenticating accounts or dispatching work."""
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..assistant.attachment_integrity import _json
from ..assistant.profile_integrity import _scope
from ..config import canonical_json
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..weixin_offline import event_id


TABLES = ('weixin_accounts','weixin_peer_bindings','weixin_poll_receipts','weixin_inbox_descriptors')


def _fail():
    raise ValueError('WEIXIN_INBOX_INTEGRITY')


def _uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        _fail()
    return value


def _canonical_model(kind, raw):
    if type(raw) is not str or len(raw.encode('utf-8')) > 262144:
        _fail()
    value = kind.model_validate(_json(raw))
    if canonical_json(value.model_dump(mode='json')) != raw:
        _fail()
    return value


def _row_ids(row, keys):
    for key in keys:
        if row[key] is not None:
            _uuid(row[key])


def _validate(db, groups, workspace):
    from .grant_integrity import _histories, _scope_at

    grant_histories = _histories(db, workspace)
    accounts, mapping_rows, poll_rows, descriptor_rows = groups
    users = set(db.scalars(text('SELECT id FROM users')))
    conversations = {row['id']:row for row in db.execute(text('SELECT * FROM assistant_conversations')).mappings()}
    task_bindings = {row['id']:row for row in db.execute(text('SELECT * FROM task_channel_bindings')).mappings()}
    account_map, mappings = {}, {}
    for row in accounts:
        _row_ids(row, ('id','workspace_id','owner_id','revoked_by'))
        value = d.WeixinAccountSnapshot(**row)
        if (str(value.workspace_id) != workspace or str(value.owner_id) not in users
                or value.revoked_by is not None and str(value.revoked_by) not in users):
            _fail()
        account_map[row['id']] = value
    for row in mapping_rows:
        _row_ids(row, ('id','account_id','task_binding_id','revoked_by'))
        scope = _canonical_model(d.ScopeSnapshot, row['scope_json'])
        value = d.WeixinPeerBindingSnapshot(**{key:item for key,item in row.items() if key != 'scope_json'},scope=scope)
        account = account_map[str(value.account_id)]
        binding = d.TaskChannelBindingView(**task_bindings[str(value.task_binding_id)])
        conversation = conversations[str(binding.conversation_id)]
        if (conversation['workspace_id'] != workspace or conversation['owner_id'] != str(account.owner_id)
                or scope.conversation_id != binding.conversation_id
                or value.created_at < account.created_at or value.created_at < binding.created_at
                or value.revoked_by is not None and str(value.revoked_by) not in users):
            _fail()
        _scope(db, scope, conversation, workspace, value.created_at)
        mappings[row['id']] = value

    polls, by_account = {}, {}
    for row in descriptor_rows:
        _row_ids(row, ('id','poll_id','mapping_id','prior_descriptor_id'))
        payload = _canonical_model(d.TaskInboxEventInput,row['payload_json']) if row['payload_json'] is not None else None
        value = d.WeixinInboxDescriptor(**{key:item for key,item in row.items() if key != 'payload_json'},payload=payload)
        polls.setdefault(row['poll_id'],[]).append(value)
    for row in poll_rows:
        _row_ids(row, ('id','account_id','request_id'))
        value = d.WeixinPollReceipt(**row,descriptors=tuple(polls.pop(row['id'],())))
        if row['account_id'] not in account_map:
            _fail()
        by_account.setdefault(row['account_id'],[]).append(value)
    if polls:
        _fail()

    # Replies may name an original later in the archive, beyond the replay cursor.
    known_sources = {}
    for account_id, history in by_account.items():
        for poll in history:
            for value in poll.descriptors:
                if value.source_event_id is not None and value.prior_descriptor_id is None:
                    known_sources.setdefault(value.source_event_id,[]).append((account_id,value))

    for account_id, account in account_map.items():
        revision, cursor, at = 0, account.initial_cursor, account.created_at
        originals, seen = {}, {}
        for poll in by_account.get(account_id,()):
            if (poll.expected_revision != revision or poll.expected_cursor != cursor or poll.created_at < at):
                _fail()
            for value in poll.descriptors:
                mapping = mappings.get(str(value.mapping_id)) if value.mapping_id is not None else None
                if value.mapping_id is not None:
                    if (mapping is None or str(mapping.account_id) != account_id
                            or mapping.sender_peer_id != value.sender_peer_id or mapping.created_at > poll.created_at):
                        _fail()
                if value.source_event_id is not None:
                    if value.source_event_id != event_id(account.bot_account_id,value.sender_peer_id,value.upstream_message_id):
                        _fail()
                    prior = originals.get(value.source_event_id)
                    if value.prior_descriptor_id is not None:
                        previous = seen.get(str(value.prior_descriptor_id))
                        if (previous is None or previous is not prior or previous.prior_descriptor_id is not None
                                or previous.source_event_id != value.source_event_id):
                            _fail()
                        if value.status == 'duplicate' and previous.source_sha256 != value.source_sha256:
                            _fail()
                        if value.reason == 'event_conflict' and previous.source_sha256 == value.source_sha256:
                            _fail()
                        if value.reason == 'previously_blocked' and (
                                previous.status != 'blocked' or previous.source_sha256 != value.source_sha256):
                            _fail()
                    elif prior is not None:
                        _fail()
                    else:
                        originals[value.source_event_id] = value
                if value.status == 'accepted_pending_dispatch':
                    if (mapping is None or mapping.revoked_at is not None and mapping.revoked_at <= poll.created_at
                            or account.revoked_at is not None and account.revoked_at <= poll.created_at):
                        _fail()
                    scope = _scope_at(mapping, grant_histories.get(str(mapping.id), ()), poll.created_at)
                    binding = task_bindings[str(mapping.task_binding_id)]
                    _scope(db, scope, conversations[binding['conversation_id']], workspace, poll.created_at)
                    for source_account, source in known_sources.get(value.payload.reply_to_event_id,()):
                        if (source_account != account_id or source.sender_peer_id != value.sender_peer_id
                                or source.mapping_id != value.mapping_id):
                            _fail()
                if value.reason == 'binding_revoked' and (mapping is None
                        or mapping.revoked_at is None or mapping.revoked_at > poll.created_at):
                    _fail()
                seen[str(value.id)] = value
            revision, cursor, at = poll.next_revision, poll.next_cursor, poll.created_at
        if account.checkpoint_revision != revision or account.upstream_cursor != cursor:
            _fail()


def validate_weixin_records(db, *, allow_inbox=False):
    """Return no file refs; nonempty account history requires a complete workspace archive."""
    try:
        schema = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
        version = identify_schema(schema,native=native)
        if version not in ('weixin-inbox-v1', 'weixin-dispatch-v1', 'weixin-reauthorization-v1'):
            return []
        groups = [db.execute(text('SELECT * FROM '+table+(
            ' ORDER BY account_id,next_revision' if table == 'weixin_poll_receipts' else
            ' ORDER BY poll_id,ordinal' if table == 'weixin_inbox_descriptors' else ' ORDER BY id'))).mappings().all()
            for table in TABLES]
        if not any(groups):
            return []
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_INBOX_INTEGRITY') from None
    if not allow_inbox:
        raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        _validate(db,groups,_uuid(identities[0]))
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_INBOX_INTEGRITY') from None
    return []
