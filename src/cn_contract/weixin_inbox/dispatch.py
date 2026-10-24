"""Source-bound synthetic TaskInbox delivery, committed with an immutable acknowledgement."""
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _at, _current, _digest
from ..config import canonical_json
from ..ops.storage import require_active
from ..security import ServiceError
from ..task_drafts import service as tasks
from ..weixin_offline import event_id
from . import accounts, ingress


def _conflict():
    raise ServiceError('VERSION_CONFLICT',409)


def _source(actor, identifier, db, *, active):
    current=_current(actor,db)
    if active:
        require_active(db)
    row=db.execute(text('''SELECT descriptor.*,poll.account_id,poll.request_id
        FROM weixin_inbox_descriptors descriptor JOIN weixin_poll_receipts poll ON poll.id=descriptor.poll_id
        WHERE descriptor.id=:id'''),{'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED',403)
    account,current=accounts._account(current,row['account_id'],db,active=active)
    poll=ingress._receipt(account,row['request_id'],db)
    descriptor=next((value for value in poll.descriptors if str(value.id)==row['id']),None)
    if descriptor is None:
        _conflict()
    if descriptor.status!='accepted_pending_dispatch':
        return current,account,descriptor,None
    mapping_row=db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'),
        {'id':str(descriptor.mapping_id)}).mappings().first()
    if mapping_row is None:
        _conflict()
    mapping=accounts._mapping(mapping_row)
    if (mapping.account_id!=account.id or mapping.sender_peer_id!=descriptor.sender_peer_id
            or descriptor.source_event_id!=event_id(account.bot_account_id,descriptor.sender_peer_id,
                descriptor.upstream_message_id)):
        _conflict()
    accounts._require_mapping(accounts._mapping_reason(current,account,mapping,db))
    return current,account,descriptor,mapping


def _stored(identifier, db):
    row=db.execute(text('SELECT * FROM weixin_dispatch_receipts WHERE descriptor_id=:id'),
        {'id':str(identifier)}).mappings().first()
    if row is None:
        return None
    try:
        return d.WeixinDispatchReceipt(**row)
    except (ValueError,TypeError):
        _conflict()


def _verified(receipt, account, descriptor, mapping, db):
    if (receipt.account_id!=account.id or receipt.mapping_id!=mapping.id
            or receipt.actor_id!=account.owner_id or receipt.descriptor_id!=descriptor.id
            or receipt.task_binding_id!=mapping.task_binding_id
            or receipt.source_event_id!=descriptor.source_event_id
            or receipt.payload_sha256!=_digest(descriptor.payload.model_dump(mode='json'))):
        _conflict()
    row=db.execute(text('SELECT * FROM task_inbox_events WHERE id=:id'),
        {'id':str(receipt.task_event_id)}).mappings().first()
    cursor=db.scalar(text('SELECT cursor FROM task_channel_bindings WHERE id=:id'),
        {'id':str(mapping.task_binding_id)})
    if (row is None or row['binding_id']!=str(mapping.task_binding_id)
            or row['event_id']!=receipt.source_event_id or row['payload_sha256']!=receipt.payload_sha256
            or row['payload_json']!=canonical_json(descriptor.payload.model_dump(mode='json'))
            or cursor is None or cursor<receipt.next_task_cursor):
        _conflict()
    return receipt


def find_dispatch_receipt(actor, descriptor_id, *, database):
    """Query committed provenance; current permissions still guard restored history."""
    with accounts._transaction(database) as db:
        current,account,descriptor,mapping=_source(actor,descriptor_id,db,active=False)
        receipt=_stored(descriptor.id,db)
        if receipt is not None:
            if mapping is None:
                _conflict()
            _verified(receipt,account,descriptor,mapping,db)
    return receipt


def dispatch_synthetic_descriptor(actor, descriptor_id, *, database):
    """Receive one accepted source and its fixed acknowledgement in one transaction."""
    with accounts._transaction(database) as db:
        current,account,descriptor,mapping=_source(actor,descriptor_id,db,active=True)
        if mapping is None:
            raise ServiceError('STATE_CONFLICT',409)
        receipt=_stored(descriptor.id,db)
        if receipt is not None:
            _verified(receipt,account,descriptor,mapping,db)
        else:
            earliest=db.scalar(text('''SELECT descriptor.id FROM weixin_inbox_descriptors descriptor
                JOIN weixin_poll_receipts poll ON poll.id=descriptor.poll_id
                LEFT JOIN weixin_dispatch_receipts receipt ON receipt.descriptor_id=descriptor.id
                WHERE descriptor.mapping_id=:mapping AND descriptor.status='accepted_pending_dispatch'
                    AND receipt.id IS NULL ORDER BY poll.next_revision,descriptor.ordinal LIMIT 1'''),
                {'mapping':str(mapping.id)})
            if earliest!=str(descriptor.id):
                _conflict()
            collision=db.scalar(text('''SELECT id FROM task_inbox_events
                WHERE binding_id=:binding AND event_id=:event'''),
                {'binding':str(mapping.task_binding_id),'event':descriptor.source_event_id})
            if collision is not None:
                _conflict()
            binding=tasks.read_binding(current,mapping.task_binding_id,db)
            received=tasks.receive_batch(current,binding.id,d.TaskInboxBatchInput(expected_cursor=binding.cursor,
                next_cursor=binding.cursor+1,events=(descriptor.payload,)),db)
            if len(received.events)!=1 or received.binding.cursor!=binding.cursor+1:
                _conflict()
            values=dict(id=str(uuid4()),descriptor_id=str(descriptor.id),account_id=str(account.id),
                mapping_id=str(mapping.id),actor_id=str(current.user_id),task_binding_id=str(binding.id),
                task_event_id=str(received.events[0].id),source_event_id=descriptor.source_event_id,
                payload_sha256=_digest(descriptor.payload.model_dump(mode='json')),
                expected_task_cursor=binding.cursor,next_task_cursor=received.binding.cursor,
                created_at=accounts._activity_time(account.id,db,now=_at(),floor=(db.scalar(text(
                    'SELECT created_at FROM task_inbox_events WHERE id=:id'),
                    {'id':str(received.events[0].id)}),)))
            receipt=d.WeixinDispatchReceipt(**values,receipt_sha256=_digest(values))
            ingress._insert('weixin_dispatch_receipts',receipt.model_dump(mode='json'),db)
            _verified(receipt,account,descriptor,mapping,db)
    return receipt
