"""Immutable query snapshots; approvals are actual backend records."""
from datetime import timedelta, datetime
import json
from uuid import UUID, uuid4
from sqlalchemy import select
from ..domain import QueryPlan, QueryPlanInput, QueryPlanItem, QueryItemInput, Party
from ..security import ServiceError
from ..persistence import configured_database
from ..facts.storage import PartyRow, PartyDecisionRow
from ..providers import qcc_registry as registry
from ..providers.storage import ProviderRecordRow
from . import storage as s


def current_party(matter_id, party_id, actor, db):
    s.authorize_query(actor, matter_id, db)
    row = db.scalar(select(PartyRow).where(PartyRow.matter_id==str(matter_id), PartyRow.party_id==str(party_id)).order_by(PartyRow.revision.desc()))
    if not row: raise ServiceError('PARTY_AMBIGUOUS', 409)
    party = Party.model_validate_json(row.payload)
    decision = db.scalar(select(PartyDecisionRow).where(PartyDecisionRow.matter_id==str(matter_id),
        PartyDecisionRow.party_id==str(party_id), PartyDecisionRow.target_revision==row.revision))
    if not decision or party.resolution_status != 'confirmed' or not party.name_confirmed or decision.after_hash != row.sha256:
        raise ServiceError('PARTY_AMBIGUOUS', 409)
    return party, {'revision': row.revision, 'sha256': row.sha256, 'record_id': row.record_id}


def approve_case_budget(matter_id, actor, *, db, credits=None, max_calls=None, expires_at=None, unit='synthetic_credit'):
    s.authorize_query(actor, matter_id, db)
    settings = configured_database(db).settings
    credits = s.decimal(credits if credits is not None else settings.qcc_case_budget_credits)
    calls = max_calls if max_calls is not None else settings.qcc_max_calls
    if unit != 'synthetic_credit' or credits > settings.qcc_case_budget_credits or type(calls) is not int or not 0 <= calls <= settings.qcc_max_calls:
        raise ServiceError('BUDGET_EXCEEDED', 403)
    end = expires_at or s.now()+timedelta(days=1)
    if end.tzinfo is None or end <= s.now(): raise ServiceError('PLAN_EXPIRED', 409)
    with db.begin_nested():
        return UUID(s.append('case_budget', matter_id, {'approved': True, 'credits': str(credits), 'max_calls': calls,
            'unit': unit, 'expires_at': end.isoformat(), 'synthetic': True}, actor.user_id, matter_id, db).ref)


def revoke_case_budget(matter_id, actor, *, db):
    s.authorize_query(actor, matter_id, db)
    with db.begin_nested():
        s.append('case_budget', matter_id, {'approved': False}, actor.user_id, matter_id, db)


def current_budget(matter_id, db):
    row = s.latest('case_budget', matter_id, db)
    if not row or not json.loads(row.payload).get('approved') or not s.approver_valid(row.actor_id, matter_id, db):
        raise ServiceError('BUDGET_UNAPPROVED', 403)
    data = json.loads(row.payload)
    if datetime.fromisoformat(data['expires_at']) <= s.now(): raise ServiceError('PLAN_EXPIRED', 409)
    return row, data


def approve_query_scope(matter_id, party_id, purpose, scope, actor, *, db, max_pages=1, extra_party_ids=(), relation_depth=0, expires_at=None):
    s.authorize_query(actor, matter_id, db)
    party, stamp = current_party(matter_id, party_id, actor, db)
    budget, _ = current_budget(matter_id, db)
    if (scope not in {'Q1','Q2','Q3'} or type(max_pages) is not int or not 1 <= max_pages <= 6
            or type(relation_depth) is not int or not 0 <= relation_depth <= 1 or len(set(extra_party_ids)) != len(extra_party_ids)
            or len(extra_party_ids) > 2 or party_id in extra_party_ids or (extra_party_ids and relation_depth != 1)):
        raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
    stamps = {str(party_id): stamp}
    for extra in extra_party_ids:
        _, stamps[str(extra)] = current_party(matter_id, extra, actor, db)
    end = expires_at or s.now()+timedelta(hours=24)
    if end.tzinfo is None or end <= s.now(): raise ServiceError('PLAN_EXPIRED', 409)
    with db.begin_nested():
        return UUID(s.append('scope_authorization', matter_id, {'approved': True, 'party_id': str(party_id), 'parties': stamps,
            'purpose': purpose, 'scope': scope, 'max_pages': max_pages, 'extra_party_ids': [str(p) for p in extra_party_ids],
            'relation_depth': relation_depth, 'budget_ref': budget.ref, 'expires_at': end.isoformat()}, actor.user_id, matter_id, db).ref)


def revoke_query_scope(ref, actor, *, matter_id, db):
    s.authorize_query(actor, matter_id, db)
    row = s.by_ref(ref, 'scope_authorization', db)
    if not row or row.matter_id != str(matter_id): raise ServiceError('CROSS_MATTER_DENIED', 403)
    with db.begin_nested():
        s.append('scope_revocation', ref, {'revoked': True}, actor.user_id, matter_id, db)


def _scope(value, actor, db):
    if value.authorization_id is None:
        if value.scope in {'Q2','Q3'} or any(i.pages > 1 or i.capability_key=='entity.related' for i in value.items):
            raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
        return None
    row = s.by_ref(value.authorization_id, 'scope_authorization', db)
    if not row or row.matter_id != str(value.matter_id) or not s.approver_valid(row.actor_id, value.matter_id, db) or s.latest('scope_revocation', row.ref, db):
        raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
    data = json.loads(row.payload); budget, _ = current_budget(value.matter_id, db)
    if (not data['approved'] or data['purpose'] != value.purpose or data['scope'] != value.scope
            or str(value.party_id) not in data['parties'] or data['budget_ref'] != budget.ref
            or datetime.fromisoformat(data['expires_at']) <= s.now() or any(i.pages > data['max_pages'] for i in value.items)):
        raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
    if any(i.capability_key=='entity.related' for i in value.items) and (not data['extra_party_ids'] or data['relation_depth'] != 1):
        raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
    for identifier, expected in data['parties'].items():
        _, stamp = current_party(value.matter_id, UUID(identifier), actor, db)
        if stamp != expected: raise ServiceError('PLAN_CHANGED', 409)
    return {'ref': row.ref, 'sha256': row.sha256}


def _binding(capability, actor, matter_id, db):
    for row in db.scalars(select(ProviderRecordRow).where(ProviderRecordRow.kind=='binding').order_by(ProviderRecordRow.sequence.desc())):
        if json.loads(row.payload)['capability_key'] != capability: continue
        try:
            binding = registry.read_binding(row.ref, actor=actor, matter_id=matter_id, db=db)
        except ServiceError: continue
        if binding.enabled:
            price = registry.read_current_price(binding.endpoint_config_ref, actor=actor, matter_id=matter_id, db=db)
            amount = s.decimal(price['unit_price'])
            if price['unit'] != 'synthetic_credit/call' or not price['synthetic']: raise ServiceError('PRICE_UNKNOWN', 403)
            return row.ref, binding, price, amount
    raise ServiceError('TOOL_UNBOUND', 403)


def create_query_plan(value, actor, *, db, plan_id=None):
    try: value = QueryPlanInput.model_validate(value.model_dump(mode='python'))
    except Exception: raise ServiceError('PLAN_CHANGED', 422) from None
    s.authorize_query(actor, value.matter_id, db)
    party, stamp = current_party(value.matter_id, value.party_id, actor, db)
    scope = _scope(value, actor, db)
    if value.scope == 'Q0' and value.items: raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
    if len({i.capability_key for i in value.items}) != len(value.items): raise ServiceError('PLAN_CHANGED', 422)
    items=[]; bindings={}
    for item in value.items:
        ref, binding, price, amount = _binding(item.capability_key, actor, value.matter_id, db)
        properties = binding.input_schema_snapshot.get('properties', {})
        if 'name' not in properties: raise ServiceError('TOOL_UNBOUND', 403)
        params={'name': party.name_confirmed}
        if item.pages > 1:
            if 'page' not in properties: raise ServiceError('TOOL_UNBOUND', 403)
            params['page'] = 1
        registry.schema_validator(binding.input_schema_snapshot).validate(params)
        identifier=uuid4()
        items.append(QueryPlanItem(id=identifier, capability_key=item.capability_key, pages=item.pages,
            tool_binding_ref=ref, parameters=params, max_credits=s.multiply(amount, item.pages), price_snapshot_id=UUID(price['id'])))
        from ..providers.storage import latest as provider_latest
        actual_approval = provider_latest('approval', ref, db)
        bindings[str(identifier)]={'binding': binding.model_dump(mode='json'), 'price': price,
            'approval_ref': actual_approval.ref if actual_approval else None, 'binding_ref': ref}
    identifier=plan_id or uuid4(); previous=_row(identifier, value.matter_id, db) if plan_id else None
    version=previous.version+1 if previous else 1
    end=s.now()+timedelta(hours=24)
    metadata={'party': stamp, 'bindings': bindings, 'scope': scope,
        'freshness_window': {'start': s.now().isoformat(), 'end': end.isoformat()}, 'unit': 'synthetic_credit',
        'limitations': ['SYNTHETIC_ONLY', 'OFFICIAL_SCHEMA_PRICE_LICENSE_REGION_NOT_APPROVED', 'NO_CROSS_MATTER_CACHE']}
    payload={'id':identifier,'matter_id':value.matter_id,'version':version,'party_id':value.party_id,'purpose':value.purpose,
        'items':tuple(items),'estimated_max_credits':s.total(i.max_credits for i in items),'max_calls':sum(i.pages for i in items),
        'scope':value.scope,'authorization_id':value.authorization_id,'status':'draft','expires_at':end,'plan_sha256':'0'*64}
    draft=QueryPlan(**payload)
    preimage=draft.model_dump(mode='json', exclude={'status','plan_sha256'})
    draft=draft.model_copy(update={'plan_sha256':s.sha({'plan':preimage,'metadata':metadata})})
    with db.begin_nested():
        db.add(s.QueryPlanRow(ref=str(uuid4()), plan_id=str(identifier), matter_id=str(value.matter_id), version=version,
            payload=draft.model_dump_json(), metadata_json=s.encode(metadata), timestamp=s.now())); db.flush()
    return draft


def _row(plan_id, matter_id, db):
    return db.scalar(select(s.QueryPlanRow).where(s.QueryPlanRow.plan_id==str(plan_id), s.QueryPlanRow.matter_id==str(matter_id)).order_by(s.QueryPlanRow.version.desc()))


def read_plan(plan_id, actor, *, matter_id, db, require_approved=False):
    s.authorize_query(actor, matter_id, db)
    row=_row(plan_id, matter_id, db)
    if not row: raise ServiceError('CROSS_MATTER_DENIED', 403)
    plan=QueryPlan.model_validate_json(row.payload); metadata=json.loads(row.metadata_json)
    if plan.expires_at <= s.now(): raise ServiceError('PLAN_EXPIRED', 409)
    _, stamp=current_party(matter_id, plan.party_id, actor, db)
    if stamp != metadata['party']: raise ServiceError('PLAN_CHANGED', 409)
    value=QueryPlanInput(matter_id=plan.matter_id,party_id=plan.party_id,purpose=plan.purpose,
        items=tuple(QueryItemInput(capability_key=i.capability_key,pages=i.pages) for i in plan.items),
        authorization_id=plan.authorization_id,scope=plan.scope)
    if _scope(value, actor, db) != metadata['scope']: raise ServiceError('PLAN_CHANGED', 409)
    from ..providers.storage import latest as provider_latest
    for item in plan.items:
        binding=registry.read_binding(item.tool_binding_ref,actor=actor,matter_id=matter_id,db=db)
        price=registry.read_current_price(binding.endpoint_config_ref,actor=actor,matter_id=matter_id,db=db)
        expected=metadata['bindings'][str(item.id)]; approval=provider_latest('approval', item.tool_binding_ref, db)
        if not binding.enabled or binding.model_dump(mode='json') != expected['binding'] or price != expected['price'] or approval.ref != expected['approval_ref']:
            raise ServiceError('PLAN_CHANGED', 409)
    approved=s.latest('plan_approval', row.ref, db)
    valid=bool(approved and json.loads(approved.payload).get('approved') and s.approver_valid(approved.actor_id,matter_id,db))
    if valid and plan.scope!='Q0':
        budget, _=current_budget(matter_id,db)
        valid=json.loads(approved.payload)['budget_ref']==budget.ref
    if require_approved and not valid: raise ServiceError('PLAN_UNAPPROVED',403)
    return QueryPlan.model_validate({**plan.model_dump(mode='python'),'status':'approved' if valid else 'draft'})


def approve_plan(plan_id, expected_hash, actor, *, matter_id, db):
    plan=read_plan(plan_id,actor,matter_id=matter_id,db=db)
    if expected_hash != plan.plan_sha256: raise ServiceError('PLAN_CHANGED',409)
    budget_ref=None
    if plan.scope!='Q0':
        budget,data=current_budget(matter_id,db);budget_ref=budget.ref
        if plan.estimated_max_credits > s.decimal(data['credits']) or plan.max_calls > data['max_calls']:
            raise ServiceError('BUDGET_EXCEEDED',403)
    row=_row(plan_id,matter_id,db)
    with db.begin_nested():
        s.append('plan_approval',row.ref,{'approved':True,'plan_sha256':plan.plan_sha256,'budget_ref':budget_ref},actor.user_id,matter_id,db)
        return read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=True)


def revoke_plan(plan_id, actor, *, matter_id, db):
    s.authorize_query(actor,matter_id,db);row=_row(plan_id,matter_id,db)
    if not row: raise ServiceError('CROSS_MATTER_DENIED',403)
    with db.begin_nested():
        s.append('plan_approval',row.ref,{'approved':False},actor.user_id,matter_id,db)
