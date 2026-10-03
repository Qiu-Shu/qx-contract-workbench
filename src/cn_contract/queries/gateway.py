"""Explicit durable factory boundary: A reserve, B mark, network, C settle."""
from uuid import UUID, uuid4
import json
from ..domain import ProviderResult, BudgetEntry
from ..persistence import Database
from ..security import ServiceError
from ..providers.qcc_mcp import FactoryQccTransport
from ..providers import qcc_registry as registry
from . import planner,ledger,storage as s


def _phase(name,entry_id):
    """Private no-op checkpoint for deterministic crash tests, not config input."""


def authenticate_execution(database,token,csrf,*,matter_id):
    """HTTP handoff: authenticate/CSRF in a short transaction, close before run.

    Future routes must use this factory dependency instead of a yield get_db
    Session that remains open while awaiting the gateway.
    """
    from ..security import authenticate
    from ..persistence import SessionRow
    import hashlib,hmac
    if not isinstance(database,Database): raise TypeError('explicit Database required')
    with database.session() as db:
        actor=authenticate(token,db)
    with s.factory_transaction(database,actor,matter_id) as db:
        session=db.get(SessionRow,str(actor.session_id),populate_existing=True)
        if (not isinstance(csrf,str) or len(csrf)>256 or not csrf or session is None
                or not hmac.compare_digest(session.csrf_hash,hashlib.sha256(csrf.encode()).hexdigest())):
            error=ServiceError('CROSS_MATTER_DENIED',403)
            error._audit_action='csrf_denied'
            raise error
        s.authorize_query(actor,matter_id,db)
    return actor


async def execute_plan(plan_id,actor,transport=None,*,database,matter_id):
    if not isinstance(database,Database): raise TypeError('explicit Database required')
    if transport is None: transport=FactoryQccTransport(database,actor=actor,matter_id=matter_id)
    with s.factory_transaction(database,actor,matter_id) as db:
        if (type(transport) is not FactoryQccTransport or transport.database is not database
                or transport.actor.user_id != actor.user_id or transport.actor.session_id != actor.session_id
                or transport.matter_id != matter_id):
            raise ServiceError('BLOCKED_LIVE',403)
        from ..ops.storage import require_active
        require_active(db)
        plan=planner.read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=False)
        if plan.scope=='Q0': return []
        plan=planner.read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=True)
    results=[]
    for item in plan.items:
        for page in range(1,item.pages+1):
            with s.factory_transaction(database,actor,matter_id) as db:
                current=planner.read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=True)
                if current!=plan: raise ServiceError('PLAN_CHANGED',409)
                existing,_,_,_,_=ledger.lookup_reservation(plan,item.id,page=page,db=db)
                if existing:
                    receipt=ledger.read_receipt(UUID(existing.id),actor,db=db,matter_id=matter_id)
                    if not receipt: raise ServiceError('QUERY_STATE_UNKNOWN',409)
                    results.append(receipt)
                    if receipt.billing_state!='confirmed': return results
                    continue
                reservation=ledger.reserve_call(plan,item.id,actor,db,page=page)
            _phase('after_reserve',reservation.ledger_id)
            try:
                with s.factory_transaction(database,actor,matter_id) as db:
                    token=ledger._mark_send(reservation.ledger_id,plan,actor,db)
            except Exception:
                with s.factory_transaction(database,actor,matter_id) as db:
                    row=ledger._get(reservation.ledger_id,db)
                    if BudgetEntry.model_validate_json(row.payload).status=='reserved':
                        ledger._change(row,'cancelled_before_send',actor.user_id,db,calls=0)
                raise
            _phase('after_mark_send',reservation.ledger_id)
            parameters=dict(item.parameters)
            if 'page' in parameters: parameters['page']=page
            before=False
            try:
                with s.factory_transaction(database,actor,matter_id) as db:
                    binding=registry.read_binding(item.tool_binding_ref,actor=actor,matter_id=matter_id,db=db)
                result=await transport.invoke(binding,parameters,uuid4(),dispatch_entry_id=reservation.ledger_id,dispatch_token=token)
            except Exception as exc:
                # The persisted single-use claim is the trusted proof; provider
                # strings/exception flags cannot release an already sent call.
                with database.session() as db:
                    before=ledger._certify_unsent(reservation.ledger_id,token,db)
                result=ProviderResult(status='blocked' if before else 'sent_unknown',trace_id=None,raw_ref=None,
                    raw_sha256=None,billing_known=False,charged_credits=None)
            _phase('after_network',reservation.ledger_id)
            with s.factory_transaction(database,actor,matter_id) as db:
                receipt=ledger._settle(reservation.ledger_id,token,result,actor.user_id,db,before_send=before)
            _phase('after_settle',reservation.ledger_id)
            with s.factory_transaction(database,actor,matter_id) as db:
                s.authorize_query(actor,matter_id,db)
                planner.read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=True)
            results.append(receipt)
            if receipt.billing_state!='confirmed': return results
    return results
