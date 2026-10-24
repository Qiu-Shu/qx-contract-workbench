"""Atomic synthetic poll journals; no dispatch, downloads or remote authentication."""
import hashlib
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _at, _digest
from ..config import canonical_json
from ..review.model_adapter import MAX_RAW_BYTES, strict_json
from ..security import ServiceError
from .. import weixin_offline as wire
from . import accounts


def _fail(code='STATE_CONFLICT', status=422):
    raise ServiceError(code, status)


def _descriptor(row):
    try:
        values = dict(row)
        raw = values.pop('payload_json')
        values['payload'] = d.TaskInboxEventInput.model_validate_json(raw) if raw is not None else None
        return d.WeixinInboxDescriptor(**values)
    except (ValueError, TypeError):
        _fail('VERSION_CONFLICT', 409)


def _receipt(account, request_id, db):
    row = db.execute(text('''SELECT * FROM weixin_poll_receipts
        WHERE account_id=:account AND request_id=:request'''),
        {'account':str(account.id), 'request':str(request_id)}).mappings().first()
    if row is None:
        return None
    descriptors = tuple(_descriptor(item) for item in db.execute(text('''
        SELECT * FROM weixin_inbox_descriptors WHERE poll_id=:id ORDER BY ordinal'''),
        {'id':row['id']}).mappings())
    try:
        return d.WeixinPollReceipt(**row, descriptors=descriptors)
    except (ValueError, TypeError):
        _fail('VERSION_CONFLICT', 409)


def _readable(current, account, receipt, db):
    # A stored receipt cannot grant access after its mapped conversation changes.
    for value in receipt.descriptors:
        if value.status == 'accepted_pending_dispatch':
            row = db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'),
                {'id':str(value.mapping_id)}).mappings().first()
            if row is None:
                _fail('VERSION_CONFLICT', 409)
            mapping = accounts._mapping(row)
            accounts._require_mapping(accounts._mapping_reason(current, account, mapping, db))
    return receipt


def find_poll_receipt(actor, account_id, request_id, *, database):
    """Recover a committed receipt without advancing cursors or resending work."""
    with accounts._transaction(database) as db:
        account, current = accounts._account(actor, account_id, db, active=False)
        receipt = _receipt(account, request_id, db)
        if receipt is not None:
            _readable(current, account, receipt, db)
    return receipt


def _envelope(raw_response, previous_cursor):
    try:
        value = wire._keys(strict_json(raw_response.decode('utf-8')), wire._RESPONSE)
        for key in ('ret', 'errcode'):
            if key in value and wire._integer(value[key]) != 0:
                _fail('BLOCKED_LIVE', 409)
        if 'msgs' not in value and not ({'ret', 'errcode'} & value.keys()):
            _fail()
        if 'errmsg' in value:
            wire._string(value['errmsg'])
        wire._metadata(value, numbers=('longpolling_timeout_ms',))
        if 'sync_buf' in value:
            wire._string(value['sync_buf'])
        cursor = wire._string(value['get_updates_buf']) if 'get_updates_buf' in value else previous_cursor
        if len(cursor) > 262144:
            _fail('FILE_LIMIT', 413)
        cursor.encode('utf-8')
        messages = value.get('msgs', [])
        if type(messages) is not list:
            _fail()
        if len(messages) > 100:
            _fail('FILE_LIMIT', 413)
        return cursor, messages
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        _fail()


def _source(account, message):
    try:
        if type(message) is not dict:
            return {}
        peer = wire._string(message['from_user_id'])
        if len(peer) > 256:
            return {}
        d._weixin_identity(peer)
        identifier = wire._message_id(message['message_id'])
        source = wire.event_id(account.bot_account_id, peer, identifier)
        return dict(sender_peer_id=peer, upstream_message_id=identifier, source_event_id=source)
    except (ServiceError, ValueError, TypeError, KeyError, UnicodeError):
        return {}


def _original(account, source, db):
    row = db.execute(text('''SELECT descriptor.* FROM weixin_inbox_descriptors AS descriptor
        JOIN weixin_poll_receipts AS poll ON poll.id=descriptor.poll_id
        WHERE poll.account_id=:account AND descriptor.source_event_id=:source
        AND descriptor.prior_descriptor_id IS NULL
        ORDER BY poll.next_revision,descriptor.ordinal LIMIT 1'''),
        {'account':str(account.id), 'source':source}).mappings().first()
    return _descriptor(row) if row is not None else None


def _describe(current, account, message, poll_id, ordinal, originals, db, settings):
    source = _source(account, message)
    # Invalid Unicode is still accounted for by a digest, never stored as raw text.
    digest = hashlib.sha256(canonical_json(message).encode('utf-8', errors='surrogatepass')).hexdigest()
    values = dict(id=uuid4(), poll_id=poll_id, ordinal=ordinal, source_sha256=digest,
        status='blocked', reason='message_invalid', **source)
    if not source:
        return d.WeixinInboxDescriptor(**values)
    event_id = source['source_event_id']
    if event_id not in originals:
        originals[event_id] = _original(account, event_id, db)
    prior = originals[event_id]
    if prior is not None:
        values.update(prior_descriptor_id=prior.id, mapping_id=prior.mapping_id)
        if prior.source_sha256 != digest:
            values['reason'] = 'event_conflict'
        elif prior.status == 'accepted_pending_dispatch':
            values.update(status='duplicate', reason='replayed')
        else:
            values['reason'] = 'previously_blocked'
        return d.WeixinInboxDescriptor(**values)

    try:
        if wire._string(message.get('to_user_id')) != account.bot_account_id:
            values['reason'] = 'recipient_mismatch'
        else:
            row = db.execute(text('''SELECT * FROM weixin_peer_bindings
                WHERE account_id=:account AND sender_peer_id=:peer'''),
                {'account':str(account.id), 'peer':source['sender_peer_id']}).mappings().first()
            if row is None:
                values['reason'] = 'sender_unbound'
            else:
                mapping = accounts._mapping(row)
                values['mapping_id'] = mapping.id
                reason = accounts._mapping_reason(current, account, mapping, db)
                if reason is not None:
                    values['reason'] = reason
                else:
                    scope = d.WeixinOfflineScope(bot_account_id=account.bot_account_id,
                        sender_peer_id=mapping.sender_peer_id, owner_id=current.user_id,
                        session_id=current.session_id, binding_id=mapping.task_binding_id,
                        expected_scope=mapping.scope, task_cursor=0, upstream_cursor=account.upstream_cursor)
                    payload = wire._event(message, scope, settings)
                    canonical_json(payload.model_dump(mode='json')).encode('utf-8')
                    values.update(status='accepted_pending_dispatch', reason=None, payload=payload)
    except ServiceError as error:
        values['reason'] = 'message_unsupported' if error.code == 'NOT_SUPPORTED' else 'message_invalid'
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        values['reason'] = 'message_invalid'
    result = d.WeixinInboxDescriptor(**values)
    originals[event_id] = result
    return result


def _insert(table, values, db):
    db.execute(text('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+
        ','.join(':'+key for key in values)+')'), values)


def record_synthetic_poll(actor, account_id, request, raw_response, *, database):
    """Commit the complete synthetic poll and its account checkpoint atomically."""
    request = d.WeixinPollInput.model_validate(request.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        account, current = accounts._account(actor, account_id, db)
        if type(raw_response) is not bytes:
            _fail()
        if len(raw_response) > MAX_RAW_BYTES:
            _fail('FILE_LIMIT', 413)
        request_hash = _digest(request.model_dump(mode='json'))
        response_hash = hashlib.sha256(raw_response).hexdigest()
        previous = _receipt(account, request.request_id, db)
        if previous is not None:
            if previous.request_sha256 != request_hash or previous.response_sha256 != response_hash:
                _fail('VERSION_CONFLICT', 409)
            receipt = _readable(current, account, previous, db)
        else:
            if (request.expected_revision != account.checkpoint_revision
                    or request.expected_cursor != account.upstream_cursor):
                _fail('VERSION_CONFLICT', 409)
            cursor, messages = _envelope(raw_response, account.upstream_cursor)
            identifier, originals = uuid4(), {}
            descriptors = tuple(_describe(current, account, message, identifier, ordinal, originals,
                db, database.settings) for ordinal, message in enumerate(messages, 1))
            values = dict(id=str(identifier), account_id=str(account.id), request_id=str(request.request_id),
                request_sha256=request_hash, response_sha256=response_hash,
                expected_revision=request.expected_revision, next_revision=request.expected_revision+1,
                expected_cursor=request.expected_cursor, next_cursor=cursor,
                descriptor_count=len(descriptors), created_at=_at().replace('+00:00', 'Z'),
                descriptors=[item.model_dump(mode='json') for item in descriptors])
            receipt = d.WeixinPollReceipt(**values, receipt_sha256=_digest(values))
            _insert('weixin_poll_receipts', receipt.model_dump(mode='json', exclude={'descriptors'}), db)
            for descriptor in descriptors:
                row = descriptor.model_dump(mode='json', exclude={'payload'})
                row['payload_json'] = canonical_json(descriptor.payload.model_dump(mode='json')) if descriptor.payload else None
                _insert('weixin_inbox_descriptors', row, db)
            changed = db.execute(text('''UPDATE weixin_accounts
                SET checkpoint_revision=:next,upstream_cursor=:cursor
                WHERE id=:id AND checkpoint_revision=:expected AND upstream_cursor=:before'''),
                {'next':receipt.next_revision, 'cursor':receipt.next_cursor, 'id':str(account.id),
                    'expected':request.expected_revision, 'before':request.expected_cursor}).rowcount
            if changed != 1:
                _fail('VERSION_CONFLICT', 409)
    return receipt
