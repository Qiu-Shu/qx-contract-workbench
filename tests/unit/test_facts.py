"""T04 synthetic service tests: candidates are evidence, never conclusions."""
import importlib
import hashlib
import json
from io import BytesIO
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from cn_contract.domain import Anchor, ParseResult, Fact, FactDecision, FactSnapshot, Role
from test_versions import world, meta
from test_state import seed_approval
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'helpers'))
from synthetic_documents import docx, DOCX_MIME
from cn_contract.documents import parse_document


def api(module, name):
    try:
        target = importlib.import_module('cn_contract.facts.' + module)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith('cn_contract.facts'):
            pytest.fail('T04 missing service: ' + name)
        raise
    function = getattr(target, name, None)
    assert callable(function), 'T04 missing service: ' + name
    return function


def setup(tmp_path, position=None):
    p, s, a, database, actor, matter = world(tmp_path)
    with database.session() as db:
        row = db.get(p.MatterRow, str(matter.id))
        payload = json.loads(row.payload)
        payload['position'] = position
        row.payload = type(matter).model_validate(payload).model_dump_json()
        doc = p.create_version(meta(matter.id,original_name='虚构T04.docx',mime=DOCX_MIME),actor,db,
            content=BytesIO(docx('<w:p><w:r><w:t>虚构年费1200元，与客户陈述冲突</w:t></w:r></w:p>')))
        parsed = parse_document(doc,database.settings,actor=actor,db=db)
    return p, s, database, actor, matter, parsed


def candidate(parsed, field='annual_fee', value='1200', **changes):
    item = dict(field=field, typed_value={'kind':'decimal','value':value}, unit='CNY',
        provenance_type='document', anchor_ids=[str(parsed.anchors[0].id)], receipt_ids=[])
    item.update(changes)
    return item


def store(tmp_path, items=None):
    build = api('extract', 'build_fact_candidates')
    initialize = api('storage', 'initialize_storage')
    p, s, database, actor, matter, parsed = setup(tmp_path)
    initialize(database)
    with database.session() as db:
        facts = build(parsed, {'facts': items or [candidate(parsed)]}, matter_id=matter.id,
            version=1, actor=actor, db=db)
        snap = FactSnapshot(version=1, facts=tuple(facts), sha256=p.fact_snapshot_sha256(facts))
        p.save_fact_snapshot(matter.id, snap, actor, db)
    return p, s, database, actor, matter, parsed, snap


def test_position_required(tmp_path):
    build = api('extract','build_fact_candidates')
    require = api('extract','require_position')
    p, s, database, actor, matter, parsed = setup(tmp_path)
    with database.session() as db:
        facts = build(parsed, {'facts':[candidate(parsed)]}, matter_id=matter.id, version=1, actor=actor, db=db)
        assert facts[0].confirmation_status == 'unconfirmed'
        assert p.read_matter(matter.id,actor,db).position is None
        with pytest.raises(s.ServiceError) as e:
            require(matter.id, actor=actor, db=db)
        assert e.value.code == 'FACTS_UNCONFIRMED'
        assert db.query(p.FactSnapshotRow).count() == 0


@pytest.mark.parametrize('typed,unit', [({'kind':'text','value':'甲方'},None),({'kind':'bool','value':False},None),
    ({'kind':'integer','value':0},'day'),({'kind':'decimal','value':'0.25'},'ratio'),
    ({'kind':'date','value':'2026-09-01'},None),({'kind':'datetime','value':'2026-09-01T00:00:00Z'},None),
    ({'kind':'null','value':None},None)])
def test_tagged_values_and_conflicts_preserved(tmp_path,typed,unit):
    build=api('extract','build_fact_candidates')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    with database.session() as db:
        items=[candidate(parsed,typed_value=typed,unit=unit),candidate(parsed,value='999')]
        facts=build(parsed,{'facts':items},matter_id=matter.id,version=1,actor=actor,db=db)
        assert len(facts)==2 and facts[0].id != facts[1].id
        assert facts[0].typed_value.kind == typed['kind']
        assert all(f.confirmed_by is None and f.confirmation_status=='unconfirmed' for f in facts)


@pytest.mark.parametrize('changes',[{'typed_value':12},{'typed_value':{'kind':'decimal','value':1.2}},
    {'typed_value':{'kind':'decimal','value':'NaN'}},{'unit':None},{'anchor_ids':[]},
    {'anchor_ids':[str(uuid4())]},{'receipt_ids':[str(uuid4())]}, {'confirmation_status':'confirmed'}])
def test_invalid_candidates_blocked(tmp_path,changes):
    build=api('extract','build_fact_candidates')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    with database.session() as db:
        with pytest.raises((s.ServiceError,ValueError)):
            build(parsed,{'facts':[candidate(parsed,**changes)]},matter_id=matter.id,version=1,actor=actor,db=db)


def test_parse_equal_and_duplicate_anchor_required(tmp_path):
    build=api('extract','build_fact_candidates')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    with database.session() as db:
        for result,item in [(parsed.model_copy(update={'quality_issues':('forged',)}),candidate(parsed)),
            (parsed,candidate(parsed,anchor_ids=[str(parsed.anchors[0].id)]*2))]:
            with pytest.raises(s.ServiceError):
                build(result,{'facts':[item]},matter_id=matter.id,version=1,actor=actor,db=db)


def test_confirm_correct_reject_and_invalidation(tmp_path):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    first=snap.facts[0]
    with database.session() as db:
        approval,artifact=seed_approval(p,db,actor,matter)
        changed=confirm(matter.id,1,[FactDecision(fact_id=first.id,decision='corrected',
            confirmed_value={'kind':'decimal','value':'1100'},reason='虚构人工核对')],actor,db=db)
        assert changed.version==2 and changed.facts[0].typed_value.value == 1100
        assert changed.facts[0].unit=='CNY' and changed.facts[0].anchor_ids==first.anchor_ids
        assert changed.facts[0].confirmed_by==actor.user_id
        assert changed.facts[0].confirmed_at.tzinfo is timezone.utc
        assert p.get_fact_snapshot(matter.id,1,actor,db).facts[0].typed_value.value==1200
        assert p.read_approval(matter.id,approval.id,actor,db).status=='stale'
        assert p.read_export(matter.id,artifact.id,actor,db).superseded
        assert '虚构人工核对' not in ''.join(r.payload for r in db.query(p.AuditRow))


@pytest.mark.parametrize('case',['empty','duplicate','unknown','change_confirmed','change_rejected','kind_change','old'])
def test_decisions_preflight_without_partial_version(tmp_path,case):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    fact=snap.facts[0]
    d=FactDecision(fact_id=fact.id,decision='confirmed',confirmed_value=fact.typed_value,reason='synthetic')
    decisions=[d]
    if case=='empty': decisions=[]
    if case=='duplicate': decisions=[d,d]
    if case=='unknown': decisions=[d.model_copy(update={'fact_id':uuid4()})]
    if case.startswith('change_'): decisions=[FactDecision(fact_id=fact.id,decision=case[7:],confirmed_value={'kind':'decimal','value':'99'},reason='synthetic')]
    if case=='kind_change': decisions=[FactDecision(fact_id=fact.id,decision='corrected',confirmed_value={'kind':'text','value':'99'},reason='synthetic')]
    with database.session() as db:
        with pytest.raises((s.ServiceError,ValueError)):
            confirm(matter.id,0 if case=='old' else 1,decisions,actor,db=db)
        assert db.query(p.FactSnapshotRow).count()==1


def test_fact_decision_rollback_and_sql_immutable(tmp_path):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    d=FactDecision(fact_id=snap.facts[0].id,decision='confirmed',confirmed_value=snap.facts[0].typed_value,reason='private')
    with pytest.raises(RuntimeError):
        with database.session() as db:
            confirm(matter.id,1,[d],actor,db=db)
            raise RuntimeError('synthetic rollback')
    with database.session() as db:
        assert db.query(p.FactSnapshotRow).count()==1
        assert db.execute(text('SELECT count(*) FROM fact_decisions')).scalar()==0
        confirm(matter.id,1,[d],actor,db=db)
    for op in ('UPDATE fact_decisions SET payload=\'{}\'','DELETE FROM fact_decisions'):
        with database.session() as db, pytest.raises(IntegrityError): db.execute(text(op))


def test_real_roles_and_revoked_session_block_confirmation(tmp_path):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    d=FactDecision(fact_id=snap.facts[0].id,decision='confirmed',confirmed_value=snap.facts[0].typed_value,reason='synthetic')
    with database.session() as db:
        db.get(p.UserRow,str(actor.user_id)).roles=json.dumps(['assistant'])
    with database.session() as db, pytest.raises(s.ServiceError):
        confirm(matter.id,1,[d],actor.model_copy(update={'roles':frozenset({Role.HANDLING_LAWYER})}),db=db)
    with database.session() as db:
        db.get(p.UserRow,str(actor.user_id)).roles=json.dumps(['handling_lawyer'])
        s.revoke_session(actor.session_id,db)
    with database.session() as db, pytest.raises(s.ServiceError): confirm(matter.id,1,[d],actor,db=db)


@pytest.mark.parametrize('case',['fake_anchor','external','missing_anchor','receipt'])
def test_confirmation_rechecks_sources_saved_directly(tmp_path,case):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    f=Fact(id=uuid4(),matter_id=matter.id,version=1,field='direct_candidate',typed_value={'kind':'decimal','value':'10'},unit='CNY',
        provenance_type='external' if case=='external' else 'document',anchor_ids=() if case=='missing_anchor' else (uuid4(),),
        receipt_ids=(uuid4(),) if case=='receipt' else (),confirmation_status='unconfirmed',confirmed_by=None,confirmed_at=None)
    with database.session() as db:
        p.save_fact_snapshot(matter.id,FactSnapshot(version=1,facts=(f,),sha256=p.fact_snapshot_sha256((f,))),actor,db)
    with database.session() as db:
        with pytest.raises(s.ServiceError):
            confirm(matter.id,1,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,reason='synthetic')],actor,db=db)
        assert db.query(p.FactSnapshotRow).count()==1


def test_confirm_caught_internal_failure_is_atomic(tmp_path):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    from sqlalchemy import event, text
    from cn_contract.facts.storage import FactDecisionRow
    d=FactDecision(fact_id=snap.facts[0].id,decision='confirmed',confirmed_value=snap.facts[0].typed_value,reason='synthetic')
    with database.session() as db:
        approval,artifact=seed_approval(p,db,actor,matter)
    def failure(mapper,connection,target): raise RuntimeError('synthetic decision write fault')
    event.listen(FactDecisionRow,'before_insert',failure)
    try:
        with database.session() as db:
            with pytest.raises(RuntimeError): confirm(matter.id,1,[d],actor,db=db)
            assert p.read_matter(matter.id,actor,db).active_fact_version==1
            assert p.read_approval(matter.id,approval.id,actor,db).status=='valid'
            assert not p.read_export(matter.id,artifact.id,actor,db).superseded
            assert db.execute(text('SELECT count(*) FROM fact_decisions')).scalar()==0
    finally: event.remove(FactDecisionRow,'before_insert',failure)
    with database.session() as db: assert db.query(p.FactSnapshotRow).count()==1


def test_concurrent_old_version_only_advances_once(tmp_path):
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    from concurrent.futures import ThreadPoolExecutor
    d=FactDecision(fact_id=snap.facts[0].id,decision='confirmed',confirmed_value=snap.facts[0].typed_value,reason='synthetic')
    def run():
        try:
            with database.session() as db: confirm(matter.id,1,[d],actor,db=db)
            return 'advanced'
        except s.ServiceError as e: return e.code
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:run(),range(2)))
    assert sorted(results)==['VERSION_CONFLICT','advanced']


def test_order_and_historical_confirmer_preserved(tmp_path):
    confirm=api('confirm','confirm_facts')
    build=api('extract','build_fact_candidates')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    with database.session() as db:
        facts=build(parsed,{'facts':[candidate(parsed,field='b'),candidate(parsed,field='a')]},matter_id=matter.id,version=1,actor=actor,db=db)
        p.save_fact_snapshot(matter.id,FactSnapshot(version=1,facts=tuple(facts),sha256=p.fact_snapshot_sha256(facts)),actor,db)
        assert p.fact_snapshot_sha256(facts)!=p.fact_snapshot_sha256(list(reversed(facts)))
        second=confirm(matter.id,1,[FactDecision(fact_id=facts[0].id,decision='confirmed',confirmed_value=facts[0].typed_value,reason='synthetic')],actor,db=db)
        user=s.provision_user('second-synthetic','local-test-password',{Role.REVIEWING_LAWYER},db)
        s.set_membership(matter.id,user,db)
        token,_=s.login('second-synthetic','local-test-password',db)
        other=s.authenticate(token,db)
    with database.session() as db:
        third=confirm(matter.id,2,[FactDecision(fact_id=facts[1].id,decision='rejected',confirmed_value=facts[1].typed_value,reason='synthetic')],other,db=db)
        assert [f.field for f in third.facts]==['b','a']
        assert third.facts[0].confirmed_by==actor.user_id
        assert third.facts[0].confirmed_at==second.facts[0].confirmed_at
        assert third.facts[1].typed_value==facts[1].typed_value


def test_cross_matter_parse_and_removed_member_denied(tmp_path):
    build=api('extract','build_fact_candidates')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    with database.session() as db:
        other=matter.model_copy(update={'id':uuid4()})
        p.provision_matter(other,db)
    with database.session() as db,pytest.raises(s.ServiceError):
        build(parsed,{'facts':[candidate(parsed)]},matter_id=other.id,version=1,actor=actor,db=db)
    with database.session() as db: s.remove_membership(matter.id,actor.user_id,db)
    with database.session() as db,pytest.raises(s.ServiceError):
        build(parsed,{'facts':[candidate(parsed)]},matter_id=matter.id,version=1,actor=actor,db=db)


@pytest.mark.parametrize('operation',['build','confirm'])
@pytest.mark.parametrize('poison_kind',['quote','completeness'])
def test_saved_parse_poison_does_not_replace_original_evidence(tmp_path,operation,poison_kind):
    build=api('extract','build_fact_candidates')
    confirm=api('confirm','confirm_facts')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    if poison_kind=='completeness':
        with database.session() as db:
            doc=p.create_version(meta(matter.id,original_name='虚构不完整.docx',mime=DOCX_MIME),actor,db,
                content=BytesIO(docx(extras={'docProps/thumbnail.jpeg':b'SYNTHETIC-IMAGE'})))
            parsed=parse_document(doc,database.settings,actor=actor,db=db)
        assert parsed.unsupported_parts
    forged_quote='虚构999'
    poisoned_anchor=Anchor.model_validate({**parsed.anchors[0].model_dump(mode='python'),'quote':forged_quote,
        'quote_sha256':hashlib.sha256(forged_quote.encode()).hexdigest(),'end':len(forged_quote)})
    poisoned=parsed.model_copy(update={'anchors':(poisoned_anchor,)} if poison_kind=='quote' else {'unsupported_parts':(),'quality_issues':()})
    with database.session() as db:
        p.save_parse_result(matter.id,poisoned,actor,db)
        if operation=='confirm':
            f=Fact(id=uuid4(),matter_id=matter.id,version=1,field='forged',typed_value={'kind':'decimal','value':'999'},unit='CNY',
                provenance_type='document',anchor_ids=(poisoned.anchors[0].id,),receipt_ids=(),confirmation_status='unconfirmed',confirmed_by=None,confirmed_at=None)
            p.save_fact_snapshot(matter.id,FactSnapshot(version=1,facts=(f,),sha256=p.fact_snapshot_sha256((f,))),actor,db)
    with database.session() as db,pytest.raises(s.ServiceError):
        if operation=='build': build(poisoned,{'facts':[candidate(poisoned,value='999')]},matter_id=matter.id,version=1,actor=actor,db=db)
        else: confirm(matter.id,1,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,reason='synthetic')],actor,db=db)
