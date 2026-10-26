"""Explicit schema18 synthetic intake; legacy writes and all delivery stay paused."""
from sqlalchemy import text

from .. import domain as d
from ..assistant.service import _digest
from ..ops.storage import require_active
from ..security import ServiceError
from ..storage_schema import identify_schema
from . import accounts,generations,ingress
from .provenance_integrity import _targets,validate_descriptor_generations


def _validate(db):
    try:
        rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        native=any(row[0]=='table' and row[1]=='local_workspace_identity' for row in rows)
        if not native or identify_schema(rows,native=True) not in ('weixin-target-provenance-v1','weixin-generation-dispatch-v1', 'assistant-evidence-v1', 'assistant-followups-v1'):
            raise ValueError('schema18 or schema19 required')
        validate_descriptor_generations(db,allow_provenance=True)
    except (ValueError,TypeError,KeyError,ArithmeticError,RecursionError,ServiceError):
        raise ServiceError('VERSION_CONFLICT',409) from None


def _latest(mapping_id,db):
    row=db.execute(text('SELECT * FROM weixin_peer_generations WHERE root_mapping_id=:id ORDER BY generation DESC LIMIT 1'),
        {'id':str(mapping_id)}).mappings().first()
    return generations._generation(row) if row is not None else None


def _root_reason(current,account,mapping,db):
    if mapping.account_id!=account.id:
        return 'scope_denied'
    return accounts._scope_reason(current,account,mapping.task_binding_id,mapping.scope,db,active=False)


def _scope(current,account,mapping,db):
    """Pure per-message classification; never release the poll lock to audit denial."""
    target=_latest(mapping.id,db)
    binding_id=target.task_binding_id if target else mapping.task_binding_id
    scope=target.scope if target else accounts._effective_scope(mapping,db)
    reason=_root_reason(current,account,mapping,db)
    if reason is None and mapping.revoked_at is not None:
        reason='binding_revoked'
    if reason is None and db.scalar(text('SELECT archived_at FROM assistant_conversations WHERE id=:id'),
            {'id':str(mapping.scope.conversation_id)}) is not None:
        reason='scope_stale'
    if reason is None:
        reason=accounts._scope_reason(current,account,binding_id,scope,db,active=True)
    return binding_id,scope,reason


def _readable(current,account,receipt,db):
    targets=_targets(db)
    for descriptor in receipt.descriptors:
        if descriptor.status!='accepted_pending_dispatch':
            continue
        mapping=accounts._mapping(accounts._mapping_row(descriptor.mapping_id,db))
        accounts._require_mapping(_root_reason(current,account,mapping,db))
        target=targets.get(str(descriptor.id))
        accounts._require_mapping(accounts._scope_reason(current,account,
            target.task_binding_id if target else mapping.task_binding_id,
            target.scope if target else mapping.scope,db,active=False))
    return receipt


def _store_targets(receipt,db):
    for descriptor in receipt.descriptors:
        if descriptor.status!='accepted_pending_dispatch':
            continue
        target=_latest(descriptor.mapping_id,db)
        if target is None:
            continue
        values=dict(descriptor_id=str(descriptor.id),generation_id=str(target.id),
            generation_sha256=target.generation_sha256,task_binding_id=str(target.task_binding_id),
            scope_sha256=target.scope_sha256,payload_sha256=_digest(descriptor.payload.model_dump(mode='json')))
        value=d.WeixinDescriptorGeneration(**values,provenance_sha256=_digest(values))
        ingress._insert('weixin_descriptor_generations',value.model_dump(mode='json'),db)


def record_generation_poll(actor,account_id,request,raw_response,*,database):
    """Record synthetic originals and fixed targets atomically, with no task delivery."""
    request=d.WeixinPollInput.model_validate(request.model_dump(mode='python'))
    with accounts._transaction(database) as db:
        account,current=accounts._account(actor,account_id,db,active=False)
        require_active(db)
        if account.revoked_at is not None:
            raise ServiceError('STATE_CONFLICT',409)
        _validate(db)
        if not accounts._has_generations(account.id,db):
            raise ServiceError('STATE_CONFLICT',409)
        receipt=ingress._record_poll(current,account,request,raw_response,db,database,generation_aware=True)
    return receipt


def find_generation_poll_receipt(actor,account_id,request_id,*,database):
    """Read only the fixed receipt under current root and recorded-target authority."""
    with accounts._transaction(database) as db:
        account,current=accounts._account(actor,account_id,db,active=False)
        _validate(db)
        receipt=ingress._receipt(account,request_id,db)
        if receipt is not None:
            _readable(current,account,receipt,db)
    return receipt
