"""T05 approved scope, chronology and isolated customer policy tests."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import importlib
import json
from uuid import uuid4

import pytest
from cn_contract.domain import (Fact, FactSnapshot, Rule, ReviewContext, PolicySnapshot, Role,Position,ConfirmationStatus)
from test_authorities import api, setup, evidence, source


def rule(**changes):
    values=dict(id=uuid4(),version=1,contract_types=['sales'],positions=['buyer'],trigger_facts=[],
        exception_facts=[],basis_kind='logic',authority_ids=[],finding_template='SYNTHETIC business observation only',
        coverage_ids=['C01'],status='draft',approved_by=None,approved_at=None)
    values.update(changes)
    return Rule(**values)


def fact(matter,actor,field,value,kind='text',unit=None):
    return Fact(id=uuid4(),matter_id=matter.id,version=1,field=field,typed_value={'kind':kind,'value':value},
        unit=unit,provenance_type='client_statement',anchor_ids=(),receipt_ids=(),confirmation_status='confirmed',
        confirmed_by=actor.user_id,confirmed_at=datetime.now(timezone.utc))


def prepare(tmp_path,facts=()):
    p,s,database,actor,matter=setup(tmp_path)
    with database.session() as db:
        items=tuple(fact(matter,actor,*item) for item in facts)
        fs=FactSnapshot(version=1,facts=items,sha256=p.fact_snapshot_sha256(items))
        p.save_fact_snapshot(matter.id,fs,actor,db)
        policy=PolicySnapshot(client_ref=matter.client_ref,version=1,
            sha256=api('rules.storage','policy_sha256')(matter.client_ref,1,()),preferences=(),approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(policy,actor,matter_id=matter.id,db=db)
    return p,s,database,actor,matter,fs,policy


def context(p,db,actor,matter,fs,policy,rules=(),**changes):
    current=p.read_matter(matter.id,actor,db)
    values=dict(matter=current,document_versions=(),fact_snapshot=fs,position=current.position,
        rules=tuple(rules),policy=policy,authority_ids=tuple(a for r in rules for a in r.authority_ids),allowed_scope=['C01'])
    values.update(changes)
    return ReviewContext(**values)


def approve(db,actor,matter,item):
    api('security','provision_rule_manager_grant')(actor.user_id,db)
    api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db)
    return api('rules.loader','approve_rule')(str(item.id),str(item.version),actor,
        evidence(actor,api('rules.storage','rule_sha256')(item)),matter_id=matter.id,db=db)


def snapshot(db,actor,matter):
    return api('rules.loader','read_rule_snapshot')(actor,matter_id=matter.id,db=db)


def test_draft_never_auto_applied(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        api('rules.loader','register_rule')(rule(),actor,matter_id=matter.id,db=db)
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db)
        assert selected.applied==() and selected.excluded[0].reason=='unapproved'


def test_no_uniform_30pct():
    cards=api('rules.loader','load_default_cards')()
    item=next(r for slug,r,meta in cards if slug=='CN-GEN-LIQUIDATED')
    assert item.status=='draft'
    assert '统一' in item.finding_template and '30%' in item.finding_template
    assert '待核实' in item.finding_template
    assert all(r.status=='draft' and not r.authority_ids for _,r,_ in cards)


def test_labor_route(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path,[('labor_relationship',True,'bool'),('noncompete_duration',Decimal('3'),'decimal','year')])
    with database.session() as db:
        api('rules.loader','register_default_cards')(actor,matter_id=matter.id,db=db)
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules,allowed_scope=['C12']),snap,actor=actor,db=db)
        item=next(e for e in selected.excluded if '劳动专项' in e.rationale)
        assert item.reason=='unsupported' and '期限待核实' in item.rationale
        assert '违法' not in item.rationale and not selected.applied


def test_client_policy_isolation(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        other=matter.model_copy(update={'id':uuid4(),'client_ref':'SYNTHETIC-B'})
        p.provision_matter(other,db)
        forged=policy.model_copy(update={'client_ref':other.client_ref})
        with pytest.raises(s.ServiceError): api('rules.loader','save_policy')(forged,actor,matter_id=matter.id,db=db)
        with pytest.raises(s.ServiceError): api('rules.loader','read_policy')(1,actor,matter_id=other.id,db=db)


@pytest.mark.parametrize('attack',['no_grant','bad_hash','wrong_reviewer','future_time','bad_uuid','bad_version','synthetic_law','law_without_source'])
def test_rule_approval_guards(tmp_path,attack):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        item=rule(basis_kind='law') if attack in ('synthetic_law','law_without_source') else rule()
        if attack=='synthetic_law':
            authority=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
            item=item.model_copy(update={'authority_ids':(authority.id,)})
        api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db)
        if attack!='no_grant': api('security','provision_rule_manager_grant')(actor.user_id,db)
        proof=evidence(actor,api('rules.storage','rule_sha256')(item))
        if attack=='bad_hash': proof=proof.model_copy(update={'text_snapshot_sha256':'0'*64})
        if attack=='wrong_reviewer': proof=proof.model_copy(update={'reviewer_id':uuid4()})
        if attack=='future_time': proof=proof.model_copy(update={'reviewed_at':datetime.now(timezone.utc)+timedelta(days=1)})
        with pytest.raises((s.ServiceError,ValueError)):
            api('rules.loader','approve_rule')('not-uuid' if attack=='bad_uuid' else str(item.id),'01' if attack=='bad_version' else '1',actor,proof,matter_id=matter.id,db=db)
        assert snapshot(db,actor,matter).rules[0].status=='draft'


def test_logic_approval_and_revoked_grant(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        item=approve(db,actor,matter,rule())
        snap=snapshot(db,actor,matter)
        assert api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db).applied==(item,)
        api('security','revoke_rule_manager_grant')(actor.user_id,db)
        assert not api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db).applied


@pytest.mark.parametrize('attack',['snapshot_hash','context_rule','duplicate','matter','position','fact_hash','policy_hash','policy_approved','unknown_authority'])
def test_selection_reloads_server_state(tmp_path,attack):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        item=approve(db,actor,matter,rule())
        snap=snapshot(db,actor,matter)
        ctx=context(p,db,actor,matter,fs,policy,snap.rules)
        if attack=='snapshot_hash': snap=snap.model_copy(update={'sha256':'0'*64})
        if attack=='context_rule': ctx=ctx.model_copy(update={'rules':(item.model_copy(update={'finding_template':'forged'}),)})
        if attack=='duplicate': snap=snap.model_copy(update={'rules':(item,item)})
        if attack=='matter': ctx=ctx.model_copy(update={'matter':ctx.matter.model_copy(update={'client_ref':'SYNTHETIC-B'})})
        if attack=='position': ctx=ctx.model_copy(update={'position':Position.SELLER})
        if attack=='fact_hash': ctx=ctx.model_copy(update={'fact_snapshot':fs.model_copy(update={'sha256':'0'*64})})
        if attack=='policy_hash': ctx=ctx.model_copy(update={'policy':policy.model_copy(update={'sha256':'0'*64})})
        if attack=='policy_approved': ctx=ctx.model_copy(update={'policy':policy.model_copy(update={'approved_by':actor.user_id,'approved_at':datetime.now(timezone.utc)})})
        if attack=='unknown_authority': ctx=ctx.model_copy(update={'authority_ids':(uuid4(),)})
        with pytest.raises((s.ServiceError,ValueError)): api('rules.evaluator','select_rules')(ctx,snap,actor=actor,db=db)


@pytest.mark.parametrize('change',['type','position','scope','jurisdiction'])
def test_scope_filters(tmp_path,change):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        values={}
        if change=='type': values['contract_types']=['nda']
        if change=='position': values['positions']=['seller']
        if change=='scope': values['coverage_ids']=['C18']
        item=rule(**values)
        approved=approve(db,actor,matter,item)
        if change=='jurisdiction':
            row=db.get(p.MatterRow,str(matter.id)); payload=json.loads(row.payload); payload['jurisdiction']='HK'; row.payload=type(matter).model_validate(payload).model_dump_json()
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db)
        assert not selected.applied and selected.excluded[0].reason in ('not_applicable','unsupported')


@pytest.mark.parametrize('exception',['absent','unconfirmed','true','false','conflict'])
def test_confirmed_trigger_and_explicit_exception(tmp_path,exception):
    rows=[('trigger',True,'bool')]
    if exception not in ('absent',): rows.append(('exception',exception=='true','bool'))
    if exception=='conflict': rows.append(('exception',True,'bool'))
    p,s,database,actor,matter,fs,policy=prepare(tmp_path,rows)
    with database.session() as db:
        if exception=='unconfirmed':
            new=tuple(f.model_copy(update={'version':2,'confirmation_status':ConfirmationStatus.UNCONFIRMED,'confirmed_by':None,'confirmed_at':None}) if f.field=='exception' else f.model_copy(update={'version':2}) for f in fs.facts)
            fs=FactSnapshot(version=2,facts=new,sha256=p.fact_snapshot_sha256(new)); p.save_fact_snapshot(matter.id,fs,actor,db)
        approve(db,actor,matter,rule(trigger_facts=['trigger'],exception_facts=['exception']))
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db)
        assert bool(selected.applied)==(exception=='false')


def test_nonempty_unapproved_policy_never_enters_context(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        prefs=('SYNTHETIC protected negotiation preference',)
        policy=PolicySnapshot(client_ref=matter.client_ref,version=2,sha256=api('rules.storage','policy_sha256')(matter.client_ref,2,prefs),preferences=prefs,approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(policy,actor,matter_id=matter.id,db=db)
        snap=snapshot(db,actor,matter)
        with pytest.raises(s.ServiceError) as exc: api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy),snap,actor=actor,db=db)
        assert exc.value.code=='RULE_UNAPPROVED'


def test_policy_approval_exact_binding_and_invalidation(tmp_path):
    from test_state import seed_approval
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        approval,artifact=seed_approval(p,db,actor,matter)
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        prefs=('SYNTHETIC preference',)
        next_policy=PolicySnapshot(client_ref=matter.client_ref,version=2,sha256=api('rules.storage','policy_sha256')(matter.client_ref,2,prefs),preferences=prefs,approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(next_policy,actor,matter_id=matter.id,db=db)
        assert p.read_matter(matter.id,actor,db).active_policy_version==2
        assert p.read_approval(matter.id,approval.id,actor,db).status=='stale'
        assert p.read_export(matter.id,artifact.id,actor,db).superseded
        approved=api('rules.loader','approve_policy')(2,actor,evidence(actor,next_policy.sha256),matter_id=matter.id,db=db)
        assert approved.approved_by==actor.user_id
        assert api('rules.loader','read_policy')(1,actor,matter_id=matter.id,db=db).preferences==()


def test_default_cards_four_types_and_18_dimensions():
    cards=api('rules.loader','load_default_cards')()
    assert len(cards)==14 and len({r.id for _,r,_ in cards})==14
    assert {str(c) for _,r,_ in cards for c in r.coverage_ids}=={f'C{i:02}' for i in range(1,19)}
    assert {str(t) for _,r,_ in cards for t in r.contract_types}=={'sales','service','lease','nda'}
    assert next(meta for slug,_,meta in cards if slug=='CN-TECH-TRAINING')['enabled'] is False


def test_rule_and_policy_savepoint_and_immutable(tmp_path,monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    module=importlib.import_module('cn_contract.rules.loader')
    def fail(*args,**kwargs): raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(module,'audit_change',fail)
    with database.session() as db:
        with pytest.raises(RuntimeError): module.register_rule(rule(),actor,matter_id=matter.id,db=db)
        assert db.execute(text('SELECT count(*) FROM rule_snapshots')).scalar()==0
    monkeypatch.undo()
    with database.session() as db: module.register_rule(rule(),actor,matter_id=matter.id,db=db)
    for table in ('rule_snapshots','policy_snapshots'):
        for op in (f"UPDATE {table} SET payload='{{}}'",f'DELETE FROM {table}'):
            with database.session() as db,pytest.raises(IntegrityError): db.execute(text(op))


def test_client_rule_binds_registered_policy_version(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        api('rules.loader','approve_policy')(1,actor,evidence(actor,policy.sha256),matter_id=matter.id,db=db)
        item=rule(basis_kind='client_policy')
        api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db)
        next_policy=PolicySnapshot(client_ref=matter.client_ref,version=2,
            sha256=api('rules.storage','policy_sha256')(matter.client_ref,2,()),preferences=(),approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(next_policy,actor,matter_id=matter.id,db=db)
        api('rules.loader','approve_policy')(2,actor,evidence(actor,next_policy.sha256),matter_id=matter.id,db=db)
        with pytest.raises(s.ServiceError):
            api('rules.loader','approve_rule')(str(item.id),'1',actor,evidence(actor,api('rules.storage','rule_sha256')(item)),matter_id=matter.id,db=db)


@pytest.mark.parametrize('state',['absent','unconfirmed','rejected','duplicate','date_wrong_kind','date_wrong_unit','bool_false'])
def test_date_and_trigger_preconditions(tmp_path,state):
    rows=[]
    if state not in ('absent',): rows=[('event_date',date(2026,1,1),'date')]
    if state=='duplicate': rows*=2
    if state=='date_wrong_kind': rows=[('event_date','2026-01-01','text')]
    if state=='date_wrong_unit': rows=[('event_date',date(2026,1,1),'date','working_hour')]
    if state=='bool_false': rows=[('trigger',False,'bool'),('event_date',date(2026,1,1),'date')]
    p,s,database,actor,matter,fs,policy=prepare(tmp_path,rows)
    with database.session() as db:
        if state in ('unconfirmed','rejected'):
            new=tuple(f.model_copy(update={'version':2,'confirmation_status':ConfirmationStatus(state),'confirmed_by':None,'confirmed_at':None}) for f in fs.facts)
            fs=FactSnapshot(version=2,facts=new,sha256=p.fact_snapshot_sha256(new)); p.save_fact_snapshot(matter.id,fs,actor,db)
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        item=rule(trigger_facts=['trigger'] if state=='bool_false' else [])
        api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db,metadata={'event_field':'event_date'})
        api('rules.loader','approve_rule')(str(item.id),'1',actor,evidence(actor,api('rules.storage','rule_sha256')(item)),matter_id=matter.id,db=db)
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db)
        assert not selected.applied


@pytest.mark.parametrize('attack',['unknown_date','future_date_override','wrong_uuid','datetime','same'])
def test_event_dates_only_corroborate_confirmed_dates(tmp_path,attack):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path,[('signed_at',date(2026,1,1),'date')])
    with database.session() as db:
        item=rule(); api('security','provision_rule_manager_grant')(actor.user_id,db)
        api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db,metadata={'event_field':'signed_at'})
        api('rules.loader','approve_rule')(str(item.id),'1',actor,evidence(actor,api('rules.storage','rule_sha256')(item)),matter_id=matter.id,db=db)
        snap=snapshot(db,actor,matter)
        mapping={str(item.id):date(2026,1,1)}
        if attack=='unknown_date': mapping={str(item.id):date(2026,1,2)}
        if attack=='future_date_override': mapping={str(item.id):date(2100,1,1)}
        if attack=='wrong_uuid': mapping={str(uuid4()):date(2026,1,1)}
        if attack=='datetime': mapping={str(item.id):datetime.now(timezone.utc)}
        call=lambda:api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db,event_dates=mapping)
        if attack=='same': assert call().applied
        else:
            with pytest.raises((s.ServiceError,ValueError)): call()


def test_approved_policy_and_rules_are_case_scoped(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        other=matter.model_copy(update={'id':uuid4()})
        p.provision_matter(other,db)
        api('rules.loader','save_policy')(policy,actor,matter_id=other.id,db=db)
        other_approved=api('rules.loader','approve_policy')(1,actor,evidence(actor,policy.sha256),matter_id=other.id,db=db)
        item=approve(db,actor,matter,rule())
        snap=snapshot(db,actor,matter)
        with pytest.raises(s.ServiceError): api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,other_approved,snap.rules),snap,actor=actor,db=db)
        assert api('rules.loader','read_policy')(1,actor,matter_id=matter.id,db=db).approved_by is None


def test_policy_runtime_hash_binds_exact_approval(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        before=api('rules.loader','policy_runtime_sha256')(policy,actor,matter_id=matter.id,db=db)
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        approved=api('rules.loader','approve_policy')(1,actor,evidence(actor,policy.sha256),matter_id=matter.id,db=db)
        after=api('rules.loader','policy_runtime_sha256')(approved,actor,matter_id=matter.id,db=db)
        assert before!=after


@pytest.mark.parametrize('kind',['logic','practice','client_policy'])
def test_nonlaw_source_cannot_skip_verification(tmp_path,kind):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        authority=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        item=rule(basis_kind=kind,authority_ids=[authority.id])
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        api('rules.loader','register_rule')(item,actor,matter_id=matter.id,db=db)
        with pytest.raises(s.ServiceError):
            api('rules.loader','approve_rule')(str(item.id),'1',actor,evidence(actor,api('rules.storage','rule_sha256')(item)),matter_id=matter.id,db=db)


def test_selection_reconstructs_t04_original_trust(tmp_path):
    from test_facts import store
    from cn_contract.domain import FactDecision,ParseResult
    p,s,database,actor,matter,parsed,initial=store(tmp_path)
    api('authorities.storage','initialize_storage')(database);api('rules.storage','initialize_storage')(database)
    with database.session() as db:
        fs=api('facts.confirm','confirm_facts')(matter.id,1,[FactDecision(fact_id=initial.facts[0].id,
            decision='confirmed',confirmed_value=initial.facts[0].typed_value,reason='SYNTHETIC confirmation')],actor,db=db)
        policy=PolicySnapshot(client_ref=matter.client_ref,version=1,sha256=api('rules.storage','policy_sha256')(matter.client_ref,1,()),preferences=(),approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(policy,actor,matter_id=matter.id,db=db)
        p.set_position(matter.id,'buyer',actor,db)
        approve(db,actor,matter,rule(trigger_facts=['annual_fee']))
        document=p.read_version(matter.id,parsed.version_id,actor,db)
        quote='X'*len(parsed.anchors[0].quote)
        forged_anchor=parsed.anchors[0].model_copy(update={'quote':quote,'quote_sha256':__import__('hashlib').sha256(quote.encode()).hexdigest()})
        p.save_parse_result(matter.id,parsed.model_copy(update={'anchors':(forged_anchor,)}),actor,db)
        snap=snapshot(db,actor,matter)
        with pytest.raises(s.ServiceError) as exc:
            api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules,document_versions=[document]),snap,actor=actor,db=db)
        assert exc.value.code=='VERSION_CONFLICT'


def test_policy_save_and_approve_failures_leave_no_half_write(tmp_path,monkeypatch):
    from sqlalchemy import text
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    module=importlib.import_module('cn_contract.rules.loader')
    def fail(*args,**kwargs): raise RuntimeError('synthetic audit fault')
    monkeypatch.setattr(module,'audit_change',fail)
    with database.session() as db:
        next_policy=PolicySnapshot(client_ref=matter.client_ref,version=2,sha256=api('rules.storage','policy_sha256')(matter.client_ref,2,()),preferences=(),approved_by=None,approved_at=None)
        with pytest.raises(RuntimeError): module.save_policy(next_policy,actor,matter_id=matter.id,db=db)
        assert p.read_matter(matter.id,actor,db).active_policy_version==1
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        with pytest.raises(RuntimeError): module.approve_policy(1,actor,evidence(actor,policy.sha256),matter_id=matter.id,db=db)
        assert db.execute(text('SELECT count(*) FROM policy_approvals')).scalar()==0
    with database.session() as db: assert db.execute(text('SELECT count(*) FROM policy_snapshots')).scalar()==1


@pytest.mark.parametrize('table',['rule_approvals','rule_invalidations','policy_approvals','source_evidence','source_attestations','authority_verifications','rule_manager_grants'])
def test_all_t05_technical_records_have_sql_immutability(tmp_path,table):
    from sqlalchemy import text
    p,s,database,actor,matter=setup(tmp_path)
    with database.session() as db:
        triggers=db.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=:table"),{'table':table}).scalars().all()
        assert f'immutable_{table}_update' in triggers and f'immutable_{table}_delete' in triggers


def test_old_policy_approval_is_historical_not_current(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        old=api('rules.loader','approve_policy')(1,actor,evidence(actor,policy.sha256),matter_id=matter.id,db=db)
        next_policy=PolicySnapshot(client_ref=matter.client_ref,version=2,sha256=api('rules.storage','policy_sha256')(matter.client_ref,2,()),preferences=(),approved_by=None,approved_at=None)
        api('rules.loader','save_policy')(next_policy,actor,matter_id=matter.id,db=db)
        assert not api('rules.loader','policy_is_approved')(old,matter.id,db)
        assert api('rules.loader','read_policy')(1,actor,matter_id=matter.id,db=db)==old


def test_overlapping_approved_versions_need_explicit_resolution(tmp_path):
    p,s,database,actor,matter,fs,policy=prepare(tmp_path)
    with database.session() as db:
        original=rule()
        approve(db,actor,matter,original)
        approve(db,actor,matter,original.model_copy(update={'version':2,'finding_template':'SYNTHETIC revised observation'}))
        snap=snapshot(db,actor,matter)
        selected=api('rules.evaluator','select_rules')(context(p,db,actor,matter,fs,policy,snap.rules),snap,actor=actor,db=db)
        assert not selected.applied
        assert len(selected.excluded)==2 and all(e.reason=='missing_facts' for e in selected.excluded)
        assert all('版本' in e.rationale for e in selected.excluded)
