from uuid import uuid4
import pytest
from cn_contract.security import ServiceError
from tests.helpers.synthetic_queries import setup, plan, api, execute


def test_confirmed_server_identity_and_frozen_plan(tmp_path):
    world = setup(tmp_path)
    value = plan(world)
    assert value.items[0].parameters == {'name': world[4].name_confirmed}
    assert str(world[4].id) not in str(value.items[0].parameters)
    assert value.max_calls == 1 and value.estimated_max_credits == 15


def test_no_relation_extension_without_scope_approval(tmp_path):
    world = setup(tmp_path)
    with pytest.raises(ServiceError): plan(world, scope='Q3')
    with pytest.raises(ServiceError): plan(world, pages=2)


def test_client_plan_mutation_cannot_authorize_reservation(tmp_path):
    world = setup(tmp_path); value = plan(world)
    database, _, actor, matter, _, _ = world
    with database.session() as db, pytest.raises(ServiceError):
        api('ledger').reserve_call(value.model_copy(update={'purpose': 'changed'}), value.items[0].id, actor, db)


def test_q0_is_zero_dispatch(tmp_path):
    world = setup(tmp_path); value = plan(world, scope='Q0')
    receipts, transport = execute(world, value)
    assert receipts == [] and transport.dispatch_count == 0


def test_unknown_price_blocks_without_call(tmp_path):
    world = setup(tmp_path)
    database, owner, actor, matter, party, endpoint = world
    from cn_contract.providers.storage import append
    with database.session() as db:
        append('price', endpoint, {'unit_price': None, 'unit': 'synthetic_credit/call', 'synthetic': True}, owner.user_id, db)
    with pytest.raises(ServiceError): plan(world)


def test_q0_needs_no_paid_budget_after_revocation(tmp_path):
    world=setup(tmp_path);value=plan(world,scope='Q0')
    with world[0].session() as db: api().revoke_case_budget(world[3].id,world[2],db=db)
    receipts,transport=execute(world,value)
    assert receipts==[] and transport.dispatch_count==0


@pytest.mark.parametrize('change',['case_budget','plan','price','party'])
def test_actual_changes_invalidate_approval_before_send(tmp_path,change):
    from cn_contract.providers import qcc_registry as registry
    from cn_contract.facts.party import resolve_party
    from cn_contract.domain import PartyDecision
    world=setup(tmp_path);value=plan(world)
    database,owner,actor,matter,party,endpoint=world
    with database.session() as db:
        if change=='case_budget': api().revoke_case_budget(matter.id,actor,db=db)
        elif change=='plan': api().revoke_plan(value.id,actor,matter_id=matter.id,db=db)
        elif change=='price': api('storage').register_synthetic_price(endpoint,10,actor=owner,db=db)
        else:
            resolve_party(party.candidate_evidence,PartyDecision(selected_candidate_id=party.candidate_evidence[0].candidate_id,
                confirmed_by=actor.user_id,reason='SYNTHETIC new confirmation revision'),matter_id=matter.id,role=party.role,
                name_raw=party.name_raw,party_id=party.id,actor=actor,db=db)
    with pytest.raises(ServiceError): execute(world,value)
    with database.session() as db:
        from sqlalchemy import select,func
        assert db.scalar(select(func.count()).select_from(api('storage').QueryLedgerRow))==0


@pytest.mark.parametrize('role',['assistant','admin'])
def test_role_claims_are_not_paid_query_permission(tmp_path,role):
    from cn_contract.security import provision_user,set_membership,login,authenticate
    from cn_contract.domain import Role,QueryPlanInput,QueryItemInput
    world=setup(tmp_path);database,_,_,matter,party,_=world
    with database.session() as db:
        user=provision_user('unpaid-'+role,'local-test-password',{Role(role)},db)
        set_membership(matter.id,user,db)
        token,_=login('unpaid-'+role,'local-test-password',db);actor=authenticate(token,db)
        actor=actor.model_copy(update={'roles':frozenset({Role.HANDLING_LAWYER,Role.ADMIN})})
        with pytest.raises(ServiceError):
            api().create_query_plan(QueryPlanInput(matter_id=matter.id,party_id=party.id,purpose='SYNTHETIC',
                items=(QueryItemInput(capability_key='synthetic.identity',pages=1),),scope='Q1',authorization_id=None),actor,db=db)


def test_fake_authorization_uuid_is_not_scope_permission(tmp_path):
    world=setup(tmp_path)
    with pytest.raises(ServiceError): plan(world,scope='Q3',authorization_id=uuid4())


def test_plan_version_keeps_old_history_and_new_needs_approval(tmp_path):
    from cn_contract.domain import QueryPlanInput,QueryItemInput
    from sqlalchemy import select
    world=setup(tmp_path);first=plan(world)
    database,_,actor,matter,party,_=world
    with database.session() as db:
        second=api().create_query_plan(QueryPlanInput(matter_id=matter.id,party_id=party.id,purpose='SYNTHETIC revised purpose',
            items=(QueryItemInput(capability_key='synthetic.identity',pages=1),),scope='Q1',authorization_id=None),actor,db=db,plan_id=first.id)
        assert second.version==2 and second.status=='draft' and second.plan_sha256!=first.plan_sha256
        assert len(list(db.scalars(select(api('storage').QueryPlanRow).where(api('storage').QueryPlanRow.plan_id==str(first.id)))))==2
        with pytest.raises(ServiceError): api('ledger').reserve_call(first,first.items[0].id,actor,db)


def test_relation_scope_limits_two_confirmed_extra_parties_depth_one_and_purpose(tmp_path):
    from tests.helpers.synthetic_queries import confirmed_extra
    world=setup(tmp_path);extras=[confirmed_extra(world,i) for i in range(3)]
    database,_,actor,matter,party,_=world
    with database.session() as db:
        for ids,depth in [(tuple(e.id for e in extras),1),((extras[0].id,),2),((extras[0].id,),0)]:
            with pytest.raises(ServiceError):
                api().approve_query_scope(matter.id,party.id,'SYNTHETIC scope','Q3',actor,db=db,
                    extra_party_ids=ids,relation_depth=depth)
        ref=api().approve_query_scope(matter.id,party.id,'独立虚构履约身份核验','Q3',actor,db=db,
            extra_party_ids=tuple(e.id for e in extras[:2]),relation_depth=1)
    extra_world=(*world[:4],extras[0],world[5])
    value=plan(extra_world,scope='Q3',authorization_id=ref)
    assert value.items[0].parameters['name']==extras[0].name_confirmed
    with pytest.raises(ServiceError): plan((*world[:4],extras[2],world[5]),scope='Q3',authorization_id=ref)


def test_frozen_freshness_expiration_blocks_zero_send(tmp_path,monkeypatch):
    from datetime import timedelta
    world=setup(tmp_path);value=plan(world)
    monkeypatch.setattr(api('storage'),'now',lambda:value.expires_at+timedelta(seconds=1))
    with pytest.raises(ServiceError) as error: execute(world,value)
    assert error.value.code=='PLAN_EXPIRED'
