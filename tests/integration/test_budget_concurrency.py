from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from cn_contract.security import ServiceError
from tests.helpers.synthetic_queries import setup, plan, api, execute


def test_parallel_reserve_twice15_only_one_succeeds(tmp_path):
    world = setup(tmp_path); values = [plan(world), plan(world)]
    database, _, actor, matter, _, _ = world
    barrier = Barrier(2)
    def reserve(value):
        barrier.wait(timeout=5)
        try:
            with database.session() as db:
                api('ledger').reserve_call(value, value.items[0].id, actor, db)
            return 'ok'
        except ServiceError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, values))
    assert sorted(outcomes) == ['BUDGET_EXCEEDED', 'ok']
    with database.session() as db:
        balance = api('ledger').read_budget(matter.id, actor, db=db)
        assert balance['remaining'] == 5 and balance['calls'] == 1


def test_six_zero_charge_calls_count_across_plans(tmp_path):
    world = setup(tmp_path, price='0')
    for _ in range(6):
        receipts, _ = execute(world, plan(world)); assert receipts[0].billing_state.value == 'confirmed'
    with pytest.raises(ServiceError) as error: execute(world, plan(world))
    assert error.value.code == 'CALL_LIMIT_EXCEEDED'


def test_network_has_durable_marker_and_no_database_write_lock(tmp_path):
    import time
    from sqlalchemy import select
    from cn_contract.domain import BudgetEntry
    from tests.helpers.synthetic_queries import reopened
    world=setup(tmp_path); value=plan(world)
    database,owner,actor,matter,_,endpoint=world
    with database.session() as db:
        api('storage').register_synthetic_behavior(endpoint,'success',delay_seconds=2,actor=owner,db=db)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(execute,world,value)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            with database.session() as db:
                rows=list(db.scalars(select(api('storage').QueryLedgerRow)))
                active=bool(rows and rows[0].send_claimed)
            if active: break
            time.sleep(.01)
        assert active and not future.done()
        started=time.monotonic(); second=reopened(database)
        with second.session() as db:
            row=db.scalar(select(api('storage').QueryLedgerRow))
            assert BudgetEntry.model_validate_json(row.payload).status=='dispatching'
            api('storage').append('diagnostic','independent-writer',{'synthetic':True},actor.user_id,matter.id,db)
        assert time.monotonic()-started<1 and not future.done()
        future.result(timeout=5)


def test_parallel_same_key_has_one_dispatch(tmp_path):
    world=setup(tmp_path); value=plan(world)
    database,owner,actor,matter,_,endpoint=world
    with database.session() as db:
        api('storage').register_synthetic_behavior(endpoint,'success',delay_seconds=.3,actor=owner,db=db)
    barrier=Barrier(2)
    def worker():
        barrier.wait(timeout=5)
        try: return execute(world,value)
        except ServiceError as exc: return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs=list(pool.map(lambda _:worker(),range(2)))
    assert sum(t.dispatch_count for item in outputs if isinstance(item,tuple) for t in [item[1]])==1
    assert sum(item=='QUERY_STATE_UNKNOWN' for item in outputs)==1


def test_installed_sdk_pages_are_individual_calls_keys_and_case_limit(tmp_path):
    from tests.helpers.synthetic_qcc import sdk_server
    from tests.helpers.synthetic_queries import bind_loopback
    from sqlalchemy import select
    world=setup(tmp_path,price='0')
    pages=[]
    with sdk_server(state='success') as (cfg,counts,server):
        server.remove_tool('synthetic_identity')
        def identity(name:str,page:int=1)->dict[str,str|bool|int]:
            counts['call']+=1;pages.append(page)
            return {'synthetic':True,'state':'success','pages_complete':False,'page':page}
        server.add_tool(identity,name='synthetic_identity',structured_output=True)
        world=bind_loopback(world,cfg)
        database,_,actor,matter,party,_=world
        with database.session() as db:
            scope=api().approve_query_scope(matter.id,party.id,'独立虚构履约身份核验','Q1',actor,db=db,max_pages=6)
        value=plan(world,pages=6,authorization_id=scope)
        receipts,transport=execute(world,value)
        assert pages==[1,2,3,4,5,6] and counts['call']==transport.dispatch_count==6
        assert all('NO_RISK_CLEARANCE' in r.coverage_limit for r in receipts)
        with database.session() as db:
            rows=list(db.scalars(select(api('storage').QueryLedgerRow)))
            assert len({r.idempotency_key for r in rows})==6 and sorted(r.page for r in rows)==pages
            assert api('ledger').read_budget(matter.id,actor,db=db)['calls']==6
        with pytest.raises(ServiceError) as error: execute(world,plan(world))
        assert error.value.code=='CALL_LIMIT_EXCEEDED' and counts['call']==6
