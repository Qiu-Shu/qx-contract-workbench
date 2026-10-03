"""Party selection is case-scoped, append-only and never a company lookup."""
from uuid import uuid4
import json
import pytest
from cn_contract.domain import PartyCandidate, PartyDecision, Role
from test_facts import api, setup
from test_state import seed_approval


def candidates(): return [PartyCandidate(candidate_id=uuid4(),name='虚构同名公司',credit_code='SYNTHETIC-A',source='mock'),
    PartyCandidate(candidate_id=uuid4(),name='虚构同名公司',credit_code='SYNTHETIC-B',source='mock')]


def party_world(tmp_path):
    resolve=api('party','resolve_party')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    return resolve,p,s,database,actor,matter


def call(resolve,cs,decision,db,actor,matter,**kwargs):
    return resolve(cs,decision,matter_id=matter.id,role='supplier',name_raw='虚构合同乙方',actor=actor,db=db,**kwargs)


def test_ambiguous_party(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    with database.session() as db:
        party=call(resolve,cs,None,db,actor,matter)
        assert party.resolution_status=='ambiguous' and party.entity_id is None
        assert party.name_confirmed is None and len(party.candidate_evidence)==2
        reverse=call(resolve,list(reversed(cs)),None,db,actor,matter)
        assert reverse.resolution_status=='ambiguous'


@pytest.mark.parametrize('count',[0,1])
def test_unresolved_without_decision(tmp_path,count):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    with database.session() as db: assert call(resolve,candidates()[:count],None,db,actor,matter).resolution_status=='unresolved'


def test_registered_selection_invalidation_and_private_reason(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    with database.session() as db:
        first=call(resolve,cs,None,db,actor,matter)
        approval,artifact=seed_approval(p,db,actor,matter)
    with database.session() as db:
        result=call(resolve,cs,PartyDecision(selected_candidate_id=cs[1].candidate_id,reason='秘密虚构理由',confirmed_by=actor.user_id),db,actor,matter,party_id=first.id)
        assert result.resolution_status=='confirmed' and result.credit_code=='SYNTHETIC-B'
        assert result.entity_id is None and result.id==first.id
        assert p.read_approval(matter.id,approval.id,actor,db).status=='stale'
        assert p.read_export(matter.id,artifact.id,actor,db).superseded
        events=db.query(p.AuditRow).filter_by(action='party_changed').all()
        assert events and all('秘密虚构理由' not in r.payload for r in events)


@pytest.mark.parametrize('case',['fresh','duplicate','unknown','forged','old','changed_context'])
def test_untrusted_selection_blocked(tmp_path,case):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    with database.session() as db: first=call(resolve,cs,None,db,actor,matter)
    decision=PartyDecision(selected_candidate_id=cs[0].candidate_id,reason='synthetic',confirmed_by=actor.user_id)
    identifier=first.id
    if case=='fresh': identifier=None
    if case=='duplicate': cs=[cs[0],cs[0]]
    if case=='unknown': decision=decision.model_copy(update={'selected_candidate_id':uuid4()})
    if case=='forged': decision=decision.model_copy(update={'confirmed_by':uuid4()})
    if case=='old':
        with database.session() as db: call(resolve,candidates(),None,db,actor,matter,party_id=first.id)
    with database.session() as db, pytest.raises((s.ServiceError,ValueError)):
        kwargs={'party_id':identifier,'matter_id':matter.id,'role':'other' if case=='changed_context' else 'supplier', 'name_raw':'虚构合同乙方','actor':actor,'db':db}
        resolve(cs,decision,**kwargs)


def test_party_sql_immutable_and_rollback(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    cs=candidates()
    with pytest.raises(RuntimeError):
        with database.session() as db:
            call(resolve,cs,None,db,actor,matter)
            raise RuntimeError('synthetic rollback')
    with database.session() as db:
        assert db.execute(text('SELECT count(*) FROM party_snapshots')).scalar()==0
        first=call(resolve,cs,None,db,actor,matter)
        call(resolve,cs,PartyDecision(selected_candidate_id=cs[0].candidate_id,reason='synthetic',confirmed_by=actor.user_id),db,actor,matter,party_id=first.id)
    for table in ('party_snapshots','party_decisions'):
        for statement in (f'UPDATE {table} SET payload=\'{{}}\'',f'DELETE FROM {table}'):
            with database.session() as db,pytest.raises(IntegrityError): db.execute(text(statement))


def test_party_ignores_forged_roles(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    with database.session() as db:
        first=call(resolve,cs,None,db,actor,matter)
        db.get(p.UserRow,str(actor.user_id)).roles=json.dumps(['assistant'])
    with database.session() as db,pytest.raises(s.ServiceError):
        call(resolve,cs,PartyDecision(selected_candidate_id=cs[0].candidate_id,reason='synthetic',confirmed_by=actor.user_id),db,actor.model_copy(update={'roles':frozenset({Role.HANDLING_LAWYER})}),matter,party_id=first.id)


def test_party_caught_internal_failure_is_atomic(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    from sqlalchemy import event, text
    from cn_contract.facts.storage import PartyDecisionRow
    cs=candidates()
    with database.session() as db:
        first=call(resolve,cs,None,db,actor,matter)
        approval,artifact=seed_approval(p,db,actor,matter)
    def failure(mapper,connection,target): raise RuntimeError('synthetic decision write fault')
    event.listen(PartyDecisionRow,'before_insert',failure)
    try:
        with database.session() as db:
            with pytest.raises(RuntimeError):
                call(resolve,cs,PartyDecision(selected_candidate_id=cs[0].candidate_id,reason='synthetic',confirmed_by=actor.user_id),db,actor,matter,party_id=first.id)
            assert db.execute(text('SELECT count(*) FROM party_snapshots')).scalar()==1
            assert p.read_approval(matter.id,approval.id,actor,db).status=='valid'
            assert not p.read_export(matter.id,artifact.id,actor,db).superseded
    finally: event.remove(PartyDecisionRow,'before_insert',failure)


def test_candidate_same_code_different_names_not_merged(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    cs[1]=cs[1].model_copy(update={'name':'另一虚构名称','credit_code':cs[0].credit_code})
    with database.session() as db:
        result=call(resolve,cs,None,db,actor,matter)
        assert result.resolution_status=='ambiguous' and len(result.candidate_evidence)==2


def test_party_cross_matter_id_and_removed_member_blocked(tmp_path):
    resolve,p,s,database,actor,matter=party_world(tmp_path)
    cs=candidates()
    with database.session() as db:
        first=call(resolve,cs,None,db,actor,matter)
        other=matter.model_copy(update={'id':uuid4()})
        p.provision_matter(other,db)
    with database.session() as db,pytest.raises(s.ServiceError):
        call(resolve,cs,PartyDecision(selected_candidate_id=cs[0].candidate_id,reason='synthetic',confirmed_by=actor.user_id),db,actor,other,party_id=first.id)
    with database.session() as db: s.remove_membership(matter.id,actor.user_id,db)
    with database.session() as db,pytest.raises(s.ServiceError): call(resolve,cs,None,db,actor,matter)
