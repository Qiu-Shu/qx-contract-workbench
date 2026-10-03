"""Atomic caller-transaction reserves and append-only billing evidence."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from uuid import UUID, uuid4
from sqlalchemy import select
from ..domain import BudgetEntry, Reservation, BillingEvidence, QueryReceipt
from ..security import ServiceError
from . import storage as s
from . import planner


def read_budget(matter_id, actor, *, db):
    s.authorize_query(actor,matter_id,db,write=False)
    _, approved=planner.current_budget(matter_id,db)
    entries=[BudgetEntry.model_validate_json(row.payload) for row in db.scalars(select(s.QueryLedgerRow).where(s.QueryLedgerRow.matter_id==str(matter_id)))]
    used=s.total((e.confirmed_credits if e.status=='confirmed' else e.reserved_credits) for e in entries
        if e.status in {'reserved','dispatching','sent_unknown','confirmed'})
    calls=sum(row.call_count for row in db.scalars(select(s.QueryLedgerRow).where(s.QueryLedgerRow.matter_id==str(matter_id))))
    remaining=s.difference(s.decimal(approved['credits']),used)
    return {'approved_credits':s.decimal(approved['credits']),'unit':approved['unit'],'remaining':remaining,
        'used':used,'calls':calls,'max_calls':approved['max_calls'],
        'incident':bool(s.latest('incident',matter_id,db)) or remaining < 0}


def _key(plan,item,page,metadata):
    parameters=dict(item.parameters)
    if 'page' in parameters: parameters['page']=page
    value={'matter_id':str(plan.matter_id),'plan_id':str(plan.id),'plan_version':plan.version,'plan_sha256':plan.plan_sha256,
        'item_id':str(item.id),'party_id':str(plan.party_id),'party_snapshot':metadata['party'],
        'binding':metadata['bindings'][str(item.id)],'parameters':parameters,'page':page,'freshness_window':metadata['freshness_window']}
    return s.sha(value),s.encode(value)


def lookup_reservation(plan,item_id,*,page=1,db):
    row=planner._row(plan.id,plan.matter_id,db)
    item=next((i for i in plan.items if i.id==item_id),None)
    if not row or not item or type(page) is not int or not 1<=page<=item.pages: raise ServiceError('PLAN_CHANGED',409)
    key,preimage=_key(plan,item,page,json.loads(row.metadata_json))
    entry=db.scalar(select(s.QueryLedgerRow).where(s.QueryLedgerRow.idempotency_key==key))
    return entry,key,preimage,row,item


def reserve_call(plan,item_id,actor,db,*,page=1):
    current=planner.read_plan(plan.id,actor,matter_id=plan.matter_id,db=db,require_approved=True)
    if current != plan: raise ServiceError('PLAN_CHANGED',409)
    entry,key,preimage,plan_row,item=lookup_reservation(current,item_id,page=page,db=db)
    if entry:
        value=BudgetEntry.model_validate_json(entry.payload)
        return Reservation(ledger_id=value.id,credits=value.reserved_credits,calls=entry.call_count,idempotency_key=key,status=value.status)
    state=read_budget(plan.matter_id,actor,db=db)
    price=json.loads(plan_row.metadata_json)['bindings'][str(item.id)]['price']
    amount=s.decimal(price['unit_price'])
    if state['incident'] or state['remaining'] < amount: raise ServiceError('BUDGET_EXCEEDED',403)
    if state['calls'] >= state['max_calls']: raise ServiceError('CALL_LIMIT_EXCEEDED',403)
    timestamp=s.now()
    value=BudgetEntry(id=uuid4(),matter_id=plan.matter_id,plan_item_id=item.id,idempotency_key=key,
        reserved_credits=amount,confirmed_credits=None,status='reserved',price_snapshot_id=item.price_snapshot_id,
        created_at=timestamp,updated_at=timestamp,reconciliation_ref=None)
    with db.begin_nested():
        db.add(s.QueryLedgerRow(id=str(value.id),matter_id=str(plan.matter_id),plan_ref=plan_row.ref,item_id=str(item.id),page=page,
            idempotency_key=key,preimage=preimage,payload=value.model_dump_json(),call_count=1,dispatch_token_sha256=None,revision=1))
        s.append('ledger_event',value.id,{'status':'reserved','credits':str(amount),'calls':1},actor.user_id,plan.matter_id,db)
        db.flush()
    return Reservation(ledger_id=value.id,credits=amount,calls=1,idempotency_key=key,status='reserved')


def _get(entry_id,db):
    s.require_storage(db)
    row=db.get(s.QueryLedgerRow,str(entry_id),populate_existing=True)
    if not row: raise ServiceError('QUERY_STATE_UNKNOWN',409)
    return row


def read_entry(entry_id,actor,*,db,matter_id=None):
    row=_authorized_row(entry_id,actor,db,matter_id=matter_id,write=False)
    return BudgetEntry.model_validate_json(row.payload)


def _authorized_row(entry_id,actor,db,*,matter_id=None,write=True):
    """Public lookup never distinguishes absent IDs from another case's IDs."""
    s.require_storage(db)
    if matter_id is not None: s.authorize_query(actor,matter_id,db,write=write)
    row=db.get(s.QueryLedgerRow,str(entry_id),populate_existing=True)
    if not row or (matter_id is not None and row.matter_id!=str(matter_id)):
        error=ServiceError('CROSS_MATTER_DENIED',403)
        s.record_denial(actor,matter_id or UUID(int=0),error,db)
        raise error
    if matter_id is None: s.authorize_query(actor,UUID(row.matter_id),db,write=write)
    return row


def _change(row,status,actor_id,db,*,confirmed=None,reconciliation_ref=None,calls=None):
    current=BudgetEntry.model_validate_json(row.payload)
    updated=BudgetEntry.model_validate({**current.model_dump(mode='python'),'status':status,
        'confirmed_credits':confirmed,'updated_at':s.now(),'reconciliation_ref':reconciliation_ref})
    with db.begin_nested():
        row.payload=BudgetEntry.model_validate(updated.model_dump(mode='python')).model_dump_json()
        row.revision+=1
        if calls is not None: row.call_count=calls
        s.append('ledger_event',row.id,{'before':current.status.value,'status':status,'reserved':str(current.reserved_credits),
            'confirmed':str(confirmed) if confirmed is not None else None,'reconciliation_ref':reconciliation_ref,'calls':row.call_count},
            actor_id,UUID(row.matter_id),db)
        db.flush()
    return updated


def _mark_send(entry_id,plan,actor,db):
    current=planner.read_plan(plan.id,actor,matter_id=plan.matter_id,db=db,require_approved=True)
    if current != plan: raise ServiceError('PLAN_CHANGED',409)
    row=_get(entry_id,db); value=BudgetEntry.model_validate_json(row.payload)
    if row.plan_ref != planner._row(plan.id,plan.matter_id,db).ref or value.status != 'reserved': raise ServiceError('QUERY_STATE_UNKNOWN',409)
    token=uuid4().hex
    with db.begin_nested():
        row.dispatch_token_sha256=hashlib.sha256(token.encode()).hexdigest()
        _change(row,'dispatching',actor.user_id,db)
    return token


def _claim_send(entry_id,token,binding,parameters,actor,matter_id,db):
    """Internal single-use durable grant consumed before the actual tool call."""
    s.authorize_query(actor,matter_id,db)
    row=_get(entry_id,db); value=BudgetEntry.model_validate_json(row.payload)
    if (row.matter_id!=str(matter_id) or value.status!='dispatching' or row.send_claimed
            or row.dispatch_token_sha256!=hashlib.sha256(token.encode()).hexdigest()):
        raise ServiceError('QUERY_STATE_UNKNOWN',409)
    frozen=json.loads(row.preimage)
    current=planner.read_plan(UUID(frozen['plan_id']),actor,matter_id=matter_id,db=db,require_approved=True)
    if (current.plan_sha256!=frozen['plan_sha256'] or binding.model_dump(mode='json')!=frozen['binding']['binding']
            or parameters!=frozen['parameters'] or read_budget(matter_id,actor,db=db)['incident']):
        raise ServiceError('PLAN_CHANGED',409)
    with db.begin_nested():
        row.send_claimed=True
        s.append('send_claim',row.id,{'token_sha256':row.dispatch_token_sha256,'page':row.page},actor.user_id,matter_id,db)
        db.flush()


def _certify_unsent(entry_id,token,db):
    row=_get(entry_id,db)
    return bool(not row.send_claimed and row.dispatch_token_sha256==hashlib.sha256(token.encode()).hexdigest()
        and BudgetEntry.model_validate_json(row.payload).status=='dispatching')


def read_receipt(entry_id,actor,*,db,matter_id=None):
    read_entry(entry_id,actor,db=db,matter_id=matter_id)
    row=s.latest('receipt',entry_id,db)
    return QueryReceipt.model_validate_json(row.payload) if row else None


def _settle(entry_id,token,result,actor_id,db,*,before_send=False):
    """Internal trusted factory continuation, even if sending actor was revoked."""
    row=_get(entry_id,db); value=BudgetEntry.model_validate_json(row.payload)
    if row.dispatch_token_sha256 != hashlib.sha256(token.encode()).hexdigest() or value.status not in {'dispatching','sent_unknown'}:
        raise ServiceError('QUERY_STATE_UNKNOWN',409)
    known=not before_send and result.status in {'success','failed'} and result.billing_known and result.charged_credits is not None
    status='cancelled_before_send' if before_send else 'confirmed' if known else 'sent_unknown'
    confirmed=s.decimal(result.charged_credits) if known else None
    plan_row=db.get(s.QueryPlanRow,row.plan_ref)
    from ..domain import QueryPlan
    plan=QueryPlan.model_validate_json(plan_row.payload)
    limitations=['SYNTHETIC_ONLY','NO_RISK_CLEARANCE','ONLY_THIS_RETURNED_SCOPE']
    if not known: limitations.append('BILLING_OR_SEND_UNKNOWN')
    if result.status!='success': limitations.append('QUERY_UNAVAILABLE_OR_FAILED')
    limitations.append('PAGES_OR_CONTENT_MAY_BE_INCOMPLETE')
    receipt=QueryReceipt(id=uuid4(),plan_id=plan.id,item_id=UUID(row.item_id),idempotency_key=row.idempotency_key,
        status=result.status,query_at=s.now(),provider_trace_id=result.trace_id,price_snapshot_id=value.price_snapshot_id,
        raw_ref=result.raw_ref,raw_sha256=result.raw_sha256,normalized_summary='独立虚构查询；仅记录本次返回范围，不能据此确认无风险。',
        coverage_limit=tuple(limitations),charged_credits=confirmed,billing_state=status)
    with db.begin_nested():
        _change(row,status,actor_id,db,confirmed=confirmed,calls=0 if before_send else None)
        s.append('receipt',entry_id,receipt.model_dump(mode='json'),actor_id,plan.matter_id,db)
        if known and confirmed > value.reserved_credits:
            s.append('incident',plan.matter_id,{'entry_id':str(entry_id),'reserved':str(value.reserved_credits),
                'actual':str(confirmed),'code':'PROVIDER_OVERCHARGE'},actor_id,plan.matter_id,db)
    return receipt


def recover_inflight(database):
    """Explicit trusted startup recovery; never retries or assumes before-send."""
    if not isinstance(database,s.Database): raise TypeError('explicit Database required')
    with database.session() as db:
        s.require_storage(db)
        for row in db.scalars(select(s.QueryLedgerRow)):
            if BudgetEntry.model_validate_json(row.payload).status=='dispatching':
                _change(row,'sent_unknown',UUID(int=0),db)


def register_bill_line(entry_id,raw,line_id,actor,*,db):
    row=_authorized_row(entry_id,actor,db)
    if not isinstance(raw,bytes) or len(raw)>1048576: raise ServiceError('BILLING_EVIDENCE_REQUIRED',422)
    try:
        def pairs(items):
            result={}
            for k,v in items:
                if k in result: raise ValueError()
                result[k]=v
            return result
        data=json.loads(raw,object_pairs_hook=pairs)
        if data.get('synthetic') is not True: raise ValueError()
        lines=[line for line in data['lines'] if line['line_id']==line_id]
        if len(lines)!=1 or lines[0]['entry_id']!=str(entry_id) or lines[0]['unit']!='synthetic_credit': raise ValueError()
        amount=s.decimal(lines[0]['credits'])
    except Exception: raise ServiceError('BILLING_EVIDENCE_REQUIRED',422) from None
    digest=hashlib.sha256(raw).hexdigest(); key=s.sha({'bill':digest,'line':line_id})
    existing=s.latest('bill_line_key',key,db)
    if existing:
        line=s.by_ref(json.loads(existing.payload)['line_ref'],'bill_line',db)
        if line.parent != str(entry_id): raise ServiceError('BILLING_CONFLICT',409)
        return UUID(line.ref)
    with db.begin_nested():
        protected=s.append('bill_raw',digest,{'raw_hex':raw.hex(),'raw_sha256':digest},actor.user_id,UUID(row.matter_id),db)
        line=s.append('bill_line',entry_id,{'bill_sha256':digest,'bill_raw_ref':protected.ref,'line_id':line_id,
            'credits':str(amount),'unit':'synthetic_credit'},actor.user_id,UUID(row.matter_id),db)
        s.append('bill_line_key',key,{'line_ref':line.ref},actor.user_id,UUID(row.matter_id),db)
    return UUID(line.ref)


def approve_bill_line(line_ref,actor,*,db):
    line=s.by_ref(line_ref,'bill_line',db)
    if not line: raise ServiceError('BILLING_EVIDENCE_REQUIRED',403)
    s.authorize_query(actor,UUID(line.matter_id),db)
    data=json.loads(line.payload)
    evidence=BillingEvidence(bill_sha256=data['bill_sha256'],recorded_at=line.timestamp,
        charged_credits=s.decimal(data['credits']),unit=data['unit'],approved_by=actor.user_id)
    with db.begin_nested():
        s.append('bill_approval',line.ref,evidence.model_dump(mode='json'),actor.user_id,UUID(line.matter_id),db)
        return evidence


def reconcile(entry_id,evidence,actor,*,db,line_ref=None):
    row=_authorized_row(entry_id,actor,db)
    try: evidence=BillingEvidence.model_validate(evidence.model_dump(mode='python'))
    except Exception: raise ServiceError('BILLING_EVIDENCE_REQUIRED',422) from None
    matches=[]
    for line in db.scalars(select(s.QueryRecordRow).where(s.QueryRecordRow.kind=='bill_line',s.QueryRecordRow.parent==str(entry_id))):
        approval=s.latest('bill_approval',line.ref,db)
        if line_ref is not None and str(line_ref)!=line.ref: continue
        if approval and s.approver_valid(approval.actor_id,UUID(row.matter_id),db) and BillingEvidence.model_validate_json(approval.payload)==evidence:
            matches.append(line)
    if len(matches)!=1: raise ServiceError('BILLING_EVIDENCE_REQUIRED',403)
    line=matches[0]; data=json.loads(line.payload); protected=s.by_ref(data['bill_raw_ref'],'bill_raw',db)
    if not protected or hashlib.sha256(bytes.fromhex(json.loads(protected.payload)['raw_hex'])).hexdigest()!=evidence.bill_sha256:
        raise ServiceError('BILLING_EVIDENCE_REQUIRED',403)
    current=BudgetEntry.model_validate_json(row.payload)
    if current.status=='confirmed':
        if current.reconciliation_ref==line.ref and current.confirmed_credits==evidence.charged_credits: return current
        raise ServiceError('BILLING_CONFLICT',409)
    if current.status not in {'sent_unknown','dispatching'}: raise ServiceError('QUERY_STATE_UNKNOWN',409)
    with db.begin_nested():
        value=_change(row,'confirmed',actor.user_id,db,confirmed=s.decimal(evidence.charged_credits),reconciliation_ref=line.ref)
        receipt_row=s.latest('receipt',entry_id,db)
        if receipt_row:
            previous=QueryReceipt.model_validate_json(receipt_row.payload)
            updated=QueryReceipt.model_validate({**previous.model_dump(mode='python'),'id':uuid4(),
                'charged_credits':evidence.charged_credits,'billing_state':'confirmed',
                'coverage_limit':(*previous.coverage_limit,'BILL_RECONCILED_SEND_OR_CONTENT_STATUS_UNCHANGED')})
            s.append('receipt',entry_id,updated.model_dump(mode='json'),actor.user_id,UUID(row.matter_id),db)
        if evidence.charged_credits > current.reserved_credits:
            s.append('incident',UUID(row.matter_id),{'entry_id':str(entry_id),'actual':str(evidence.charged_credits),'code':'PROVIDER_OVERCHARGE'},actor.user_id,UUID(row.matter_id),db)
    return value
