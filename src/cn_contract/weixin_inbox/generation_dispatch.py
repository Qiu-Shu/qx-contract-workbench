"""Explicit schema19 fixed-target delivery; legacy account write guards stay closed."""
from sqlalchemy import text

from ..assistant.service import _current
from ..ops.storage import require_active
from ..security import ServiceError
from ..storage_schema import identify_schema
from ..weixin_offline import event_id
from . import accounts, dispatch, generation_ingress, ingress
from .dispatch_integrity import validate_dispatch_records
from .grant_integrity import validate_peer_scope_grants
from .integrity import validate_weixin_records
from .provenance_integrity import _targets, validate_descriptor_generations


def _validate(db):
    try:
        rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native=any(row[0]=='table' and row[1]=='local_workspace_identity' for row in rows)
        if not native or identify_schema(rows,native=True) not in ('weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1', 'assistant-material-model-v1', 'weixin-personal-v1'):
            raise ValueError('schema19 required')
        # Empty generation history must not bypass the original inbox/dispatch/grant parents.
        validate_weixin_records(db,allow_inbox=True)
        validate_dispatch_records(db,allow_dispatch=True)
        validate_peer_scope_grants(db,allow_grants=True)
        validate_descriptor_generations(db,allow_provenance=True)
    except (ValueError,TypeError,KeyError,ArithmeticError,RecursionError,ServiceError):
        dispatch._conflict()


def _source(actor,identifier,db,*,active):
    current=_current(actor,db)
    if active:
        require_active(db)
    _validate(db)
    row=db.execute(text('''SELECT descriptor.*,poll.account_id,poll.request_id
        FROM weixin_inbox_descriptors descriptor JOIN weixin_poll_receipts poll ON poll.id=descriptor.poll_id
        WHERE descriptor.id=:id'''),{'id':str(identifier)}).mappings().first()
    if row is None:
        raise ServiceError('CROSS_MATTER_DENIED',403)
    account,current=accounts._account(current,row['account_id'],db,active=False)
    if active and (account.mode != 'synthetic' or account.revoked_at is not None or not accounts._has_generations(account.id,db)):
        raise ServiceError('STATE_CONFLICT',409)
    poll=ingress._receipt(account,row['request_id'],db)
    descriptor=next((value for value in poll.descriptors if str(value.id)==row['id']),None)
    if descriptor is None:
        dispatch._conflict()
    if descriptor.status!='accepted_pending_dispatch':
        return current,account,descriptor,None,None,None,poll,None
    mapping=accounts._mapping(accounts._mapping_row(descriptor.mapping_id,db))
    if (mapping.account_id!=account.id or mapping.sender_peer_id!=descriptor.sender_peer_id
            or descriptor.source_event_id!=event_id(account.bot_account_id,descriptor.sender_peer_id,
                descriptor.upstream_message_id)):
        dispatch._conflict()
    accounts._require_mapping(generation_ingress._root_reason(current,account,mapping,db))
    if active:
        if mapping.revoked_at is not None:
            raise ServiceError('STATE_CONFLICT',409)
        if db.scalar(text('SELECT archived_at FROM assistant_conversations WHERE id=:id'),
                {'id':str(mapping.scope.conversation_id)}) is not None:
            raise ServiceError('VERSION_CONFLICT',409)
    target=_targets(db).get(str(descriptor.id))
    binding_id=target.task_binding_id if target else mapping.task_binding_id
    scope=target.scope if target else accounts._effective_scope(mapping,db)
    accounts._require_mapping(accounts._scope_reason(current,account,binding_id,scope,db,active=False))
    return current,account,descriptor,mapping,binding_id,scope,poll,target


def _earliest(mapping_id,binding_id,db):
    return db.scalar(text('''SELECT descriptor.id FROM weixin_inbox_descriptors descriptor
        JOIN weixin_poll_receipts poll ON poll.id=descriptor.poll_id
        JOIN weixin_peer_bindings root ON root.id=descriptor.mapping_id
        LEFT JOIN weixin_descriptor_generations target ON target.descriptor_id=descriptor.id
        LEFT JOIN weixin_dispatch_receipts receipt ON receipt.descriptor_id=descriptor.id
        WHERE descriptor.mapping_id=:mapping AND descriptor.status='accepted_pending_dispatch'
            AND receipt.id IS NULL AND COALESCE(target.task_binding_id,root.task_binding_id)=:binding
        ORDER BY poll.next_revision,descriptor.ordinal LIMIT 1'''),
        {'mapping':str(mapping_id),'binding':str(binding_id)})


def _dispatch(actor,descriptor_id,db,*,root_mapping_id=None):
    current,account,descriptor,mapping,binding_id,scope,poll,target=_source(actor,descriptor_id,db,active=True)
    if root_mapping_id is not None and (mapping is None or mapping.id!=root_mapping_id):
        raise ServiceError('CROSS_MATTER_DENIED',403)
    if mapping is None:
        raise ServiceError('STATE_CONFLICT',409)
    receipt=dispatch._stored(descriptor.id,db)
    if receipt is not None:
        dispatch._verified(receipt,account,descriptor,mapping,db,binding_id=binding_id)
    else:
        accounts._require_mapping(accounts._scope_reason(current,account,binding_id,scope,db,active=True))
        if _earliest(mapping.id,binding_id,db)!=str(descriptor.id):
            dispatch._conflict()
        floor=(poll.created_at.isoformat(),)
        if target is not None:
            floor+=(target.created_at.isoformat(),)
        receipt=dispatch._deliver(current,account,descriptor,mapping,db,binding_id=binding_id,after=True,floor=floor)
    _validate(db)
    return receipt


def _find(actor,descriptor_id,db,*,root_mapping_id=None):
    _,account,descriptor,mapping,binding_id,_,_,_=_source(actor,descriptor_id,db,active=False)
    if root_mapping_id is not None and (mapping is None or mapping.id!=root_mapping_id):
        raise ServiceError('CROSS_MATTER_DENIED',403)
    receipt=dispatch._stored(descriptor.id,db)
    if receipt is not None:
        if mapping is None:
            dispatch._conflict()
        dispatch._verified(receipt,account,descriptor,mapping,db,binding_id=binding_id)
    return receipt


def dispatch_generation_descriptor(actor,descriptor_id,*,database):
    """Receive only the immutable historical target, never the account's latest target."""
    with accounts._transaction(database) as db:
        receipt=_dispatch(actor,descriptor_id,db)
    return receipt


def find_generation_dispatch_receipt(actor,descriptor_id,*,database):
    """Query the fixed acknowledgement after restore/revocation under current object ACL."""
    with accounts._transaction(database) as db:
        receipt=_find(actor,descriptor_id,db)
    return receipt
