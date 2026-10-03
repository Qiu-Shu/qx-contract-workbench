import pytest
from cn_contract.security import ServiceError
from tests.helpers.synthetic_queries import setup, plan, api, execute


def test_duplicate_call_is_one_dispatch(tmp_path):
    world = setup(tmp_path); value = plan(world)
    receipts, transport = execute(world, value)
    again, _ = execute(world, value, transport)
    assert transport.dispatch_count == 1 and receipts[0].id == again[0].id


def test_timeout_unknown_retains_budget_and_no_retry(tmp_path):
    world = setup(tmp_path, mode='timeout'); value = plan(world)
    receipts, transport = execute(world, value)
    again, _ = execute(world, value, transport)
    assert receipts[0].billing_state.value == 'sent_unknown' and transport.dispatch_count == 1
    with world[0].session() as db:
        state = api('ledger').read_budget(world[3].id, world[2], db=db)
        assert state['remaining'] == 5 and state['calls'] == 1


def test_overcharge_preserves_negative_balance(tmp_path):
    world = setup(tmp_path, mode='overcharge'); value = plan(world)
    receipts, _ = execute(world, value)
    assert receipts[0].charged_credits == 25
    with world[0].session() as db:
        state = api('ledger').read_budget(world[3].id, world[2], db=db)
        assert state['remaining'] == -5 and state['incident']


def test_caller_rollback_reservation_is_not_a_send(tmp_path):
    world = setup(tmp_path); value = plan(world)
    database, _, actor, matter, _, _ = world
    with database.session_factory() as db:
        api('ledger').reserve_call(value, value.items[0].id, actor, db)
        db.rollback()
    with database.session() as db:
        assert api('ledger').read_budget(matter.id, actor, db=db)['calls'] == 0


def test_factory_without_dispatch_authority_cannot_send(tmp_path):
    import asyncio
    from uuid import uuid4
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    from cn_contract.providers import qcc_registry as registry
    world=setup(tmp_path); value=plan(world)
    database,_,actor,matter,_,_=world
    with database.session() as db:
        binding=registry.read_binding(value.items[0].tool_binding_ref,actor=actor,matter_id=matter.id,db=db)
    transport=FactoryQccTransport(database,actor=actor,matter_id=matter.id)
    with pytest.raises(ServiceError):
        asyncio.run(transport.invoke(binding,dict(value.items[0].parameters),uuid4()))
    assert transport.dispatch_count==0


@pytest.mark.parametrize('mode', ['unknown','failed_unknown','success_billing_unknown'])
def test_received_unknown_billing_still_holds(mode,tmp_path):
    world=setup(tmp_path,mode=mode); value=plan(world)
    receipts,transport=execute(world,value)
    assert receipts[0].billing_state=='sent_unknown' and receipts[0].charged_credits is None
    with world[0].session() as db:
        assert api('ledger').read_budget(world[3].id,world[2],db=db)['remaining']==5
    execute(world,value,transport)
    assert transport.dispatch_count==1


def test_certified_before_send_cancels_without_call(tmp_path):
    world=setup(tmp_path,mode='before_send'); value=plan(world)
    receipts,transport=execute(world,value)
    assert transport.dispatch_count==0 and receipts[0].billing_state=='cancelled_before_send'
    with world[0].session() as db:
        state=api('ledger').read_budget(world[3].id,world[2],db=db)
        assert state['remaining']==20 and state['calls']==0


@pytest.mark.parametrize('phase', ['after_reserve','after_mark_send','after_network','after_settle'])
def test_crash_restart_never_resends(phase,tmp_path,monkeypatch):
    from tests.helpers.synthetic_queries import reopened
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    from sqlalchemy import select
    world=setup(tmp_path); value=plan(world)
    gateway=api('gateway')
    class SyntheticCrash(BaseException): pass
    def crash(name,entry):
        if name==phase: raise SyntheticCrash()
    monkeypatch.setattr(gateway,'_phase',crash)
    with pytest.raises(SyntheticCrash): execute(world,value)
    monkeypatch.setattr(gateway,'_phase',lambda *args:None)
    new_db=reopened(world[0]); api('ledger').recover_inflight(new_db)
    new_world=(new_db,*world[1:])
    transport=FactoryQccTransport(new_db,actor=world[2],matter_id=world[3].id)
    if phase=='after_settle':
        receipts,_=execute(new_world,value,transport);assert receipts[0].billing_state=='confirmed'
    else:
        with pytest.raises(ServiceError) as error: execute(new_world,value,transport)
        assert error.value.code=='QUERY_STATE_UNKNOWN'
    assert transport.dispatch_count==0
    with new_db.session() as db:
        state=api('ledger').read_budget(world[3].id,world[2],db=db)
        assert state['calls']==1 and state['remaining']==5


def test_registered_approved_bill_can_reconcile_unknown(tmp_path):
    from sqlalchemy import select
    import json
    world=setup(tmp_path,mode='timeout'); value=plan(world);execute(world,value)
    database,_,actor,matter,_,_=world
    ledger=api('ledger')
    with database.session() as db:
        entry=db.scalar(select(api('storage').QueryLedgerRow))
        raw=json.dumps({'synthetic':True,'lines':[{'line_id':'fictional-1','entry_id':entry.id,'credits':'25','unit':'synthetic_credit'}]}).encode()
        ref=ledger.register_bill_line(entry.id,raw,'fictional-1',actor,db=db)
        evidence=ledger.approve_bill_line(ref,actor,db=db)
        final=ledger.reconcile(entry.id,evidence,actor,db=db)
        assert final.confirmed_credits==25 and final.status=='confirmed'
        assert ledger.reconcile(entry.id,evidence,actor,db=db)==final
        assert ledger.read_budget(matter.id,actor,db=db)['remaining']==-5


def test_fake_bill_and_conflicting_reconcile_rejected(tmp_path):
    from sqlalchemy import select
    from uuid import uuid4
    from datetime import datetime,timezone
    from cn_contract.domain import BillingEvidence
    world=setup(tmp_path,mode='timeout');value=plan(world);execute(world,value)
    database,_,actor,matter,_,_=world
    with database.session() as db:
        entry=db.scalar(select(api('storage').QueryLedgerRow))
        forged=BillingEvidence(bill_sha256='0'*64,recorded_at=datetime.now(timezone.utc),charged_credits=0,unit='synthetic_credit',approved_by=actor.user_id)
        with pytest.raises(ServiceError): api('ledger').reconcile(entry.id,forged,actor,db=db)
        assert api('ledger').read_entry(entry.id,actor,db=db).status=='sent_unknown'


def test_two_lines_in_same_bill_are_distinct_and_prior_evidence_stays(tmp_path):
    from sqlalchemy import select
    import json
    world=setup(tmp_path,price='5',mode='unknown')
    execute(world,plan(world));execute(world,plan(world))
    database,_,actor,matter,_,_=world;ledger=api('ledger')
    with database.session() as db:
        rows=list(db.scalars(select(api('storage').QueryLedgerRow)))
        raw=json.dumps({'synthetic':True,'lines':[{'line_id':str(i),'entry_id':row.id,'credits':'0','unit':'synthetic_credit'}
            for i,row in enumerate(rows)]}).encode()
        for i,row in enumerate(rows):
            ref=ledger.register_bill_line(row.id,raw,str(i),actor,db=db)
            evidence=ledger.approve_bill_line(ref,actor,db=db)
            final=ledger.reconcile(row.id,evidence,actor,db=db)
            assert final.confirmed_credits==0
            with pytest.raises(ServiceError):
                ledger.reconcile(row.id,evidence.model_copy(update={'charged_credits':__import__('decimal').Decimal('1')}),actor,db=db)
        state=ledger.read_budget(matter.id,actor,db=db)
        assert state['remaining']==20 and state['calls']==2


def test_low_global_decimal_context_does_not_round_budget(tmp_path):
    from decimal import localcontext,Inexact
    world=setup(tmp_path,price='0.123456789012345678901234567890');value=plan(world)
    with localcontext() as context:
        context.prec=2;context.traps[Inexact]=True
        receipts,_=execute(world,value)
        with world[0].session() as db:
            state=api('ledger').read_budget(world[3].id,world[2],db=db)
            assert str(receipts[0].charged_credits)=='0.123456789012345678901234567890'
            assert str(state['remaining'])=='19.876543210987654321098765432110'


def test_cookie_auth_transaction_closes_before_factory_execution(tmp_path):
    from cn_contract.security import login
    world=setup(tmp_path);value=plan(world)
    with world[0].session() as db: token,csrf=login('query-lawyer','local-test-password',db)
    actor=api('gateway').authenticate_execution(world[0],token,csrf,matter_id=world[3].id)
    updated=(world[0],world[1],actor,*world[3:])
    receipts,transport=execute(updated,value)
    assert transport.dispatch_count==1 and receipts[0].billing_state=='confirmed'


@pytest.mark.parametrize('operation',['budget','scope','plan','bill'])
def test_approval_service_failure_caught_commit_keeps_no_half_record(tmp_path,monkeypatch,operation):
    from sqlalchemy import select,func
    import json
    world=setup(tmp_path,mode='unknown');value=plan(world)
    database,_,actor,matter,party,_=world
    ledger=api('ledger');store=api('storage')
    line=None
    if operation=='bill':
        execute(world,value)
        with database.session() as db:
            row=db.scalar(select(store.QueryLedgerRow))
            raw=json.dumps({'synthetic':True,'lines':[{'line_id':'atomic','entry_id':row.id,'credits':'0','unit':'synthetic_credit'}]}).encode()
            line=ledger.register_bill_line(row.id,raw,'atomic',actor,db=db)
    with database.session() as db:
        before=db.scalar(select(func.count()).select_from(store.QueryRecordRow))
        original=store.append
        def fail_after_append(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('SYNTHETIC persistence failure after actual insert')
        monkeypatch.setattr(store,'append',fail_after_append)
        with pytest.raises(RuntimeError):
            if operation=='budget': api().approve_case_budget(matter.id,actor,db=db)
            elif operation=='scope': api().approve_query_scope(matter.id,party.id,value.purpose,'Q3',actor,db=db)
            elif operation=='plan': api().approve_plan(value.id,value.plan_sha256,actor,matter_id=matter.id,db=db)
            else: ledger.approve_bill_line(line,actor,db=db)
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(store.QueryRecordRow))==before


def test_denied_budget_approval_audited_without_committing_caller_work(tmp_path):
    from sqlalchemy import select
    from cn_contract.persistence import AuditRow,UserRow
    from cn_contract.security import provision_user,set_membership,login,authenticate
    from cn_contract.domain import Role
    world=setup(tmp_path);database,_,_,matter,_,_=world
    with database.session() as db:
        user=provision_user('fee-assistant','local-test-password',{Role.ASSISTANT},db)
        set_membership(matter.id,user,db)
        token,_=login('fee-assistant','local-test-password',db);actor=authenticate(token,db)
    with database.session() as db:
        with pytest.raises(ServiceError): api().approve_case_budget(matter.id,actor,db=db)
    with database.session() as db:
        events=list(db.scalars(select(AuditRow).where(AuditRow.actor_id==str(user))))
        assert len(events)==1 and events[0].action=='authorization_denied'


def test_factory_denial_audit_survives_and_does_not_disclose_other_case(tmp_path):
    from sqlalchemy import select
    from uuid import uuid4
    from cn_contract.persistence import AuditRow
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    import asyncio
    world=setup(tmp_path);database,_,actor,_,_,_=world
    absent=uuid4();transport=FactoryQccTransport(database,actor=actor,matter_id=absent)
    with pytest.raises(ServiceError) as error:
        asyncio.run(api('gateway').execute_plan(uuid4(),actor,transport,database=database,matter_id=absent))
    assert error.value.code=='CROSS_MATTER_DENIED' and transport.dispatch_count==0
    with database.session() as db:
        events=list(db.scalars(select(AuditRow).where(AuditRow.matter_id==str(absent))))
        assert len(events)==1 and 'name' not in events[0].payload


def test_post_send_session_revocation_preserves_ledger_raw_and_denies_return(tmp_path,monkeypatch):
    from sqlalchemy import select
    from cn_contract.providers.storage import ProviderRecordRow
    from cn_contract.providers import qcc_registry
    from cn_contract.security import revoke_session,login,authenticate
    from cn_contract.persistence import AuditRow
    world=setup(tmp_path);value=plan(world)
    database,_,actor,matter,_,_=world
    def revoke_after(name,entry_id):
        if name=='after_network':
            with database.session() as db: revoke_session(actor.session_id,db)
    monkeypatch.setattr(api('gateway'),'_phase',revoke_after)
    with pytest.raises(ServiceError): execute(world,value)
    with database.session() as db:
        raw=db.scalar(select(ProviderRecordRow).where(ProviderRecordRow.kind=='raw'))
        assert raw is not None
        assert len(list(db.scalars(select(AuditRow).where(AuditRow.actor_id==str(actor.user_id),AuditRow.action=='authorization_denied'))))>=1
        with pytest.raises(ServiceError): qcc_registry.read_raw(raw.ref,actor=actor,matter_id=matter.id,db=db)
        token,_=login('query-lawyer','local-test-password',db);fresh=authenticate(token,db)
        state=api('ledger').read_budget(matter.id,fresh,db=db)
        assert state['remaining']==5 and state['calls']==1


def test_entry_and_receipt_missing_or_other_case_have_same_denial(tmp_path):
    from sqlalchemy import select
    from uuid import uuid4
    world=setup(tmp_path);value=plan(world);execute(world,value)
    database,_,actor,matter,_,_=world
    with database.session() as db:
        existing=db.scalar(select(api('storage').QueryLedgerRow)).id
        for reader in [api('ledger').read_entry,api('ledger').read_receipt]:
            errors=[]
            for entry_id in [existing,str(uuid4())]:
                with pytest.raises(ServiceError) as error: reader(entry_id,actor,matter_id=uuid4(),db=db)
                errors.append((error.value.code,error.value.status_code))
            assert errors[0]==errors[1]==('CROSS_MATTER_DENIED',403)


def test_reconciliation_updates_receipt_billing_without_claiming_provider_success(tmp_path):
    from sqlalchemy import select
    import json
    world=setup(tmp_path,mode='unknown');value=plan(world)
    original,_=execute(world,value)
    database,_,actor,matter,_,_=world
    with database.session() as db:
        row=db.scalar(select(api('storage').QueryLedgerRow))
        raw=json.dumps({'synthetic':True,'lines':[{'line_id':'receipt','entry_id':row.id,'credits':'0','unit':'synthetic_credit'}]}).encode()
        ref=api('ledger').register_bill_line(row.id,raw,'receipt',actor,db=db)
        evidence=api('ledger').approve_bill_line(ref,actor,db=db)
        api('ledger').reconcile(row.id,evidence,actor,db=db)
        receipt=api('ledger').read_receipt(row.id,actor,matter_id=matter.id,db=db)
        assert receipt.billing_state=='confirmed' and receipt.charged_credits==0
        assert receipt.status==original[0].status=='sent_unknown'
        assert receipt.raw_ref==original[0].raw_ref and receipt.query_at==original[0].query_at
        assert len(list(db.scalars(select(api('storage').QueryRecordRow).where(api('storage').QueryRecordRow.kind=='receipt'))))==2


def test_sdk_unknown_even_zero_price_does_not_implicitly_confirm_bill(tmp_path):
    from tests.helpers.synthetic_qcc import sdk_server
    from tests.helpers.synthetic_queries import bind_loopback
    world=setup(tmp_path,price='0')
    with sdk_server(state='unknown') as (cfg,counts,_):
        world=bind_loopback(world,cfg);value=plan(world)
        receipts,transport=execute(world,value)
        assert receipts[0].status=='sent_unknown' and receipts[0].billing_state=='sent_unknown'
        execute(world,value,transport)
        assert counts['call']==transport.dispatch_count==1


@pytest.mark.parametrize('change',['schema','price'])
def test_before_tool_schema_drift_is_certified_unsent_and_releases(tmp_path,monkeypatch,change):
    from cn_contract.providers import qcc_registry
    from sqlalchemy import select
    world=setup(tmp_path);value=plan(world)
    database,owner,actor,matter,_,endpoint=world
    def drift(name,entry):
        if name=='after_mark_send':
            with database.session() as db:
                if change=='schema': qcc_registry.register_mock_catalog_variant(endpoint,'output_changed',actor=owner,db=db)
                else: api('storage').register_synthetic_price(endpoint,10,actor=owner,db=db)
    monkeypatch.setattr(api('gateway'),'_phase',drift)
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    transport=FactoryQccTransport(database,actor=actor,matter_id=matter.id)
    with pytest.raises(ServiceError): execute(world,value,transport)
    with database.session() as db:
        row=db.scalar(select(api('storage').QueryLedgerRow))
        receipt=api('ledger').read_receipt(row.id,actor,matter_id=matter.id,db=db)
        assert transport.dispatch_count==0 and receipt.billing_state=='cancelled_before_send'
        state=api('ledger').read_budget(matter.id,actor,db=db)
        assert state['remaining']==20 and state['calls']==0


def test_unregistered_transport_zero_send_rejection_is_audited(tmp_path):
    import asyncio
    from sqlalchemy import select
    from cn_contract.persistence import AuditRow
    world=setup(tmp_path);value=plan(world)
    database,_,actor,matter,_,_=world
    class Unregistered:
        calls=0
        async def invoke(self,*args,**kwargs): self.calls+=1;raise AssertionError('must never be called')
    transport=Unregistered()
    with pytest.raises(ServiceError) as error:
        asyncio.run(api('gateway').execute_plan(value.id,actor,transport,database=database,matter_id=matter.id))
    assert error.value.code=='BLOCKED_LIVE' and transport.calls==0
    with database.session() as db:
        assert len(list(db.scalars(select(AuditRow).where(AuditRow.actor_id==str(actor.user_id),AuditRow.action=='authorization_denied'))))==1
        assert len(list(db.scalars(select(api('storage').QueryLedgerRow))))==0
