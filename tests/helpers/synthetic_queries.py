"""T08 independent fictional budget/identity setup, actual confirmation APIs."""
import asyncio
import importlib
from decimal import Decimal
from uuid import uuid4
from cn_contract.domain import PartyCandidate, PartyDecision, QueryPlanInput, QueryItemInput, Role
from tests.helpers.synthetic_qcc import setup as provider_setup, config


def api(name='planner'):
    try:
        module = importlib.import_module('cn_contract.queries.'+name)
    except ModuleNotFoundError as exc:
        assert exc.name not in {'cn_contract.queries', 'cn_contract.queries.'+name}, 'T08 durable query services must exist'
        raise
    return module


def setup(tmp_path, *, price='15', mode='success'):
    database, owner, matter, registry = provider_setup(tmp_path)
    store = api('storage'); store.initialize_storage(database)
    from cn_contract.facts.storage import initialize_storage
    from cn_contract.facts.party import resolve_party
    from cn_contract.security import provision_user, set_membership, login, authenticate
    initialize_storage(database)
    with database.session() as db:
        user = provision_user('query-lawyer', 'local-test-password', {Role.HANDLING_LAWYER}, db)
        set_membership(matter.id, user, db)
        token, _ = login('query-lawyer', 'local-test-password', db); lawyer = authenticate(token, db)
        cs = (PartyCandidate(candidate_id=uuid4(), name='独立虚构T08示例企业', credit_code='SYNTHETIC-ONLY-CODE', source='Independent fictional client material'),)
        party = resolve_party(cs, None, matter_id=matter.id, role='supplier', name_raw='独立虚构T08示例企业', actor=lawyer, db=db)
        party = resolve_party(cs, PartyDecision(selected_candidate_id=cs[0].candidate_id, confirmed_by=lawyer.user_id,
            reason='SYNTHETIC technical confirmation; no real lawyer approval'), matter_id=matter.id, role=party.role,
            name_raw=party.name_raw, party_id=party.id, actor=lawyer, db=db)
        endpoint = registry.register_endpoint(config(), actor=owner, db=db)
        catalog = asyncio.run(registry.discover_tools(endpoint, actor=owner, matter_id=matter.id, db=db))
        price_id = store.register_synthetic_price(endpoint, Decimal(price), actor=owner, db=db)
        from cn_contract.domain import BindingInput
        tool = catalog.tools[0]
        pending = registry.bind_capability(BindingInput(capability_key='synthetic.identity', provider=catalog.provider,
            tool_name=tool.name, input_schema_snapshot=tool.input_schema_snapshot, output_schema_snapshot=tool.output_schema_snapshot,
            schema_hash=registry.schema_hash(tool), endpoint_config_ref=endpoint, unit_price=Decimal(price),
            price_unit='synthetic_credit/call', price_snapshot_id=price_id, approved_by=None, approved_at=None), owner, db=db)
        binding_ref = registry.binding_reference(pending, actor=owner, db=db); registry.approve_binding(binding_ref, actor=owner, db=db)
        store.register_synthetic_behavior(endpoint, mode, actor=owner, db=db)
        api().approve_case_budget(matter.id, lawyer, db=db)
    return database, owner, lawyer, matter, party, endpoint


def plan(world, *, pages=1, scope='Q1', authorization_id=None):
    database, owner, actor, matter, party, endpoint = world
    p = api()
    with database.session() as db:
        result = p.create_query_plan(QueryPlanInput(matter_id=matter.id, party_id=party.id, purpose='独立虚构履约身份核验',
            items=() if scope == 'Q0' else (QueryItemInput(capability_key='synthetic.identity', pages=pages),),
            authorization_id=authorization_id, scope=scope), actor, db=db)
        result = p.approve_plan(result.id, result.plan_sha256, actor, matter_id=matter.id, db=db)
    return result


def execute(world, value, transport=None):
    database, owner, actor, matter, party, endpoint = world
    from cn_contract.providers.qcc_mcp import FactoryQccTransport
    transport = transport or FactoryQccTransport(database, actor=actor, matter_id=matter.id)
    result = asyncio.run(api('gateway').execute_plan(value.id, actor, transport, database=database, matter_id=matter.id))
    return result, transport


def reopened(database):
    from cn_contract.persistence import Database
    from cn_contract.facts.storage import initialize_storage as facts_init
    from cn_contract.providers.storage import initialize_storage as providers_init
    result=Database(str(database.engine.url),database.storage_root,database.settings)
    facts_init(result);providers_init(result);api('storage').initialize_storage(result)
    return result


def bind_loopback(world,cfg):
    """Actual installed SDK discovery/approval; no mocked protocol or real fees."""
    from tests.helpers.synthetic_qcc import ready
    database,owner,_,matter,_,_=world
    from cn_contract.providers import qcc_registry
    endpoint,_,_,_=asyncio.run(ready(database,owner,matter,qcc_registry,cfg=cfg))
    return (*world[:5],endpoint)


def confirmed_extra(world,index):
    from cn_contract.facts.party import resolve_party
    database,_,actor,matter,_,_=world
    candidate=PartyCandidate(candidate_id=uuid4(),name=f'独立虚构关联示例{index}',credit_code=None,
        source='Independent fictional relation material')
    with database.session() as db:
        pending=resolve_party((candidate,),None,matter_id=matter.id,role='supplier',name_raw=candidate.name,actor=actor,db=db)
        return resolve_party((candidate,),PartyDecision(selected_candidate_id=candidate.candidate_id,
            confirmed_by=actor.user_id,reason='SYNTHETIC confirmation'),matter_id=matter.id,role=pending.role,
            name_raw=pending.name_raw,party_id=pending.id,actor=actor,db=db)
