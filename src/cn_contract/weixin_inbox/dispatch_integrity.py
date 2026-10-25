"""Verify fixed synthetic dispatch provenance without replaying or granting access."""
import hashlib

from sqlalchemy import text

from .. import domain as d
from ..assistant.profile_integrity import _scope
from ..config import canonical_json
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..task_drafts.integrity import _at
from ..weixin_offline import event_id
from .integrity import _canonical_model, _row_ids, _uuid


def _fail():
    raise ValueError('WEIXIN_DISPATCH_INTEGRITY')


def _rows(db, table):
    return {row['id']:row for row in db.execute(text('SELECT * FROM '+table)).mappings()}


def _validate(db, rows, workspace, *, generation_dispatch=False):
    from .grant_integrity import _histories, _scope_at
    from .provenance_integrity import _targets

    grant_histories = _histories(db, workspace)
    targets = _targets(db)
    accounts = _rows(db, 'weixin_accounts')
    mappings = _rows(db, 'weixin_peer_bindings')
    bindings = _rows(db, 'task_channel_bindings')
    conversations = _rows(db, 'assistant_conversations')
    events = _rows(db, 'task_inbox_events')
    users = set(db.scalars(text('SELECT id FROM users')))
    descriptors, grouped = {}, {}
    for row in db.execute(text('SELECT * FROM weixin_inbox_descriptors ORDER BY poll_id,ordinal')).mappings():
        _row_ids(row, ('id', 'poll_id', 'mapping_id', 'prior_descriptor_id'))
        payload = _canonical_model(d.TaskInboxEventInput, row['payload_json']) if row['payload_json'] is not None else None
        value = d.WeixinInboxDescriptor(**{key:item for key,item in row.items() if key != 'payload_json'}, payload=payload)
        descriptors[row['id']] = value
        grouped.setdefault(row['poll_id'], []).append(value)
    polls = {}
    for row in db.execute(text('SELECT * FROM weixin_poll_receipts')).mappings():
        _row_ids(row, ('id', 'account_id', 'request_id'))
        polls[row['id']] = d.WeixinPollReceipt(**row, descriptors=tuple(grouped.pop(row['id'], ())))
    if grouped:
        _fail()

    dispatched, intervals = {}, {}
    for row in rows:
        _row_ids(row, ('id', 'descriptor_id', 'account_id', 'mapping_id', 'actor_id', 'task_binding_id', 'task_event_id'))
        receipt = d.WeixinDispatchReceipt(**row)
        descriptor = descriptors[str(receipt.descriptor_id)]
        target = targets.get(str(descriptor.id))
        if target is not None and not generation_dispatch:
            _fail()
        poll = polls[str(descriptor.poll_id)]
        account_row = accounts[str(receipt.account_id)]
        _row_ids(account_row, ('id', 'workspace_id', 'owner_id', 'revoked_by'))
        account = d.WeixinAccountSnapshot(**account_row)
        mapping_row = mappings[str(receipt.mapping_id)]
        _row_ids(mapping_row, ('id', 'account_id', 'task_binding_id', 'revoked_by'))
        scope = _canonical_model(d.ScopeSnapshot, mapping_row['scope_json'])
        mapping = d.WeixinPeerBindingSnapshot(**{key:item for key,item in mapping_row.items() if key != 'scope_json'}, scope=scope)
        effective_scope = target.scope if target else _scope_at(mapping, grant_histories.get(str(mapping.id), ()), receipt.created_at)
        fixed_binding_id = target.task_binding_id if target else mapping.task_binding_id
        root_binding = bindings[str(mapping.task_binding_id)]
        root_conversation = conversations[root_binding['conversation_id']]
        binding_row = bindings[str(receipt.task_binding_id)]
        _row_ids(binding_row, ('id', 'conversation_id'))
        binding = d.TaskChannelBindingView(**binding_row)
        conversation = conversations[str(binding.conversation_id)]
        _row_ids(conversation, ('id', 'workspace_id', 'owner_id'))
        event = events[str(receipt.task_event_id)]
        _row_ids(event, ('id', 'binding_id'))
        payload = _canonical_model(d.TaskInboxEventInput, event['payload_json'])
        event_at = _at(event['created_at'])
        _scope(db, effective_scope, conversation, workspace, receipt.created_at)
        if (descriptor.status != 'accepted_pending_dispatch' or descriptor.prior_descriptor_id is not None
                or descriptor.mapping_id != mapping.id or descriptor.payload is None
                or poll.account_id != account.id or mapping.account_id != account.id
                or account.owner_id != receipt.actor_id or str(receipt.actor_id) not in users
                or str(account.workspace_id) != workspace
                or mapping.sender_peer_id != descriptor.sender_peer_id
                or fixed_binding_id != receipt.task_binding_id
                or conversation['owner_id'] != str(receipt.actor_id) or conversation['workspace_id'] != workspace
                or str(scope.workspace_id) != workspace or str(effective_scope.workspace_id) != workspace
                or effective_scope.conversation_id != binding.conversation_id
                or event['binding_id'] != str(binding.id)
                or descriptor.source_event_id != event_id(account.bot_account_id, descriptor.sender_peer_id, descriptor.upstream_message_id)
                or receipt.source_event_id != descriptor.source_event_id
                or event['event_id'] != receipt.source_event_id or payload.event_id != receipt.source_event_id
                or event['payload_json'] != canonical_json(descriptor.payload.model_dump(mode='json'))
                or hashlib.sha256(event['payload_json'].encode('utf-8')).hexdigest() != receipt.payload_sha256
                or event['payload_sha256'] != receipt.payload_sha256
                or mapping.created_at < account.created_at or mapping.created_at < _at(root_binding['created_at'])
                or mapping.created_at < _at(root_conversation['created_at']) or poll.created_at < mapping.created_at
                or target is not None and receipt.created_at < target.created_at
                or receipt.created_at < event_at
                or receipt.created_at < mapping.created_at or receipt.created_at < poll.created_at
                or account.revoked_at is not None and account.revoked_at <= receipt.created_at
                or mapping.revoked_at is not None and mapping.revoked_at <= receipt.created_at
                or type(binding_row['cursor']) is not int or binding.cursor < receipt.next_task_cursor):
            _fail()
        if str(descriptor.id) in dispatched:
            _fail()
        dispatched[str(descriptor.id)] = receipt
        intervals.setdefault(str(binding.id), []).append(receipt)

    for history in intervals.values():
        previous = None
        for receipt in sorted(history, key=lambda item:(item.created_at, item.expected_task_cursor)):
            if previous is not None and receipt.expected_task_cursor < previous.next_task_cursor:
                _fail()
            previous = receipt

    prefixes = {}
    for descriptor in sorted(descriptors.values(), key=lambda item:(
            str(item.mapping_id), polls[str(item.poll_id)].next_revision, item.ordinal)):
        if descriptor.status != 'accepted_pending_dispatch':
            continue
        mapping_id = str(descriptor.mapping_id)
        target = targets.get(str(descriptor.id))
        binding_id = str(target.task_binding_id) if target else mappings[mapping_id]['task_binding_id']
        stream = (mapping_id, binding_id) if generation_dispatch else mapping_id
        missing, previous = prefixes.get(stream, (False, None))
        receipt = dispatched.get(str(descriptor.id))
        if receipt is not None:
            if missing or previous is not None and (receipt.created_at < previous.created_at
                    or receipt.expected_task_cursor < previous.next_task_cursor):
                _fail()
            previous = receipt
        prefixes[stream] = (missing or receipt is None, previous)


def validate_dispatch_records(db, *, allow_dispatch=False):
    """Return no file refs; dispatched history belongs only in a full native archive."""
    try:
        schema = [tuple(row) for row in db.execute(text(
            'SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native = any(row[0] == 'table' and row[1] == 'local_workspace_identity' for row in schema)
        version = identify_schema(schema, native=native)
        if version not in ('weixin-dispatch-v1', 'weixin-reauthorization-v1', 'weixin-generations-v1', 'weixin-target-provenance-v1', 'weixin-generation-dispatch-v1'):
            return []
        rows = db.execute(text('SELECT * FROM weixin_dispatch_receipts ORDER BY created_at,id')).mappings().all()
        if not rows:
            return []
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_DISPATCH_INTEGRITY') from None
    if not allow_dispatch:
        raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    try:
        identities = db.scalars(text('SELECT id FROM local_workspace_identity')).all() if native else []
        if len(identities) != 1:
            _fail()
        workspace = _uuid(identities[0])
        generation_dispatch = version == 'weixin-generation-dispatch-v1'
        _validate(db, rows, workspace, generation_dispatch=generation_dispatch)
        if generation_dispatch:
            from .integrity import validate_weixin_records
            from .grant_integrity import validate_peer_scope_grants
            from .generation_integrity import _validate as validate_generation_chain
            validate_weixin_records(db, allow_inbox=True)
            validate_peer_scope_grants(db, allow_grants=True)
            generation_rows = db.execute(text(
                'SELECT * FROM weixin_peer_generations ORDER BY root_mapping_id,generation')).mappings().all()
            # Call the pure parent check; public generation validation also checks dispatch.
            validate_generation_chain(db, generation_rows, workspace, allow_target_polls=True, allow_target_dispatch=True)
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError, ServiceError):
        raise ValueError('WEIXIN_DISPATCH_INTEGRITY') from None
    return []
