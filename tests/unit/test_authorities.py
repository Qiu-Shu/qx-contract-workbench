"""T05 local, explicitly synthetic evidence; no legal verification claimed."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
from uuid import uuid4

import pytest
from cn_contract.domain import AuthorityInput, ApprovalEvidence, Role,VerificationStatus
from test_versions import world


def api(module, name):
    try:
        target = importlib.import_module('cn_contract.' + module)
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith('cn_contract.'):
            pytest.fail('T05 missing service: ' + name)
        raise
    result = getattr(target, name, None)
    assert callable(result), 'T05 missing service: ' + name
    return result


def setup(tmp_path):
    p, s, a, database, actor, matter = world(tmp_path)
    api('authorities.storage', 'initialize_storage')(database)
    api('rules.storage', 'initialize_storage')(database)
    return p, s, database, actor, matter


def source(**changes):
    body = 'SYNTHETIC ONLY: invented source text, no real legal proposition.'
    values = dict(title='SYNTHETIC authority', issuer='SYNTHETIC issuer', url='synthetic://T05',
        article='SYNTHETIC 1', text_snapshot=body, snapshot_sha256=hashlib.sha256(body.encode()).hexdigest(),
        promulgated_at=date(2025,1,1), effective_from=date(2025,2,1), effective_to=date(2026,2,1),
        jurisdiction='CN-mainland', legal_rank='SYNTHETIC', fetch_status='fetched',
        fetched_at=datetime.now(timezone.utc), verification_status='unverified', verified_by=None, verified_at=None)
    values.update(changes)
    return AuthorityInput(**values)


def evidence(actor, sha256, **changes):
    values = dict(reviewer_id=actor.user_id, reviewed_at=datetime.now(timezone.utc),
        text_snapshot_sha256=sha256, applicability='synthetic scope reviewed', exceptions='synthetic exceptions reviewed')
    values.update(changes)
    return ApprovalEvidence(**values)


def test_effective_date():
    applicable = api('authorities.applicability', 'effective_on')
    authority = source()
    assert not applicable(authority, date(2025,1,31))
    assert applicable(authority, date(2025,2,1))
    assert applicable(authority, date(2026,2,1))
    assert not applicable(authority, date(2026,2,2))
    assert not applicable(authority.model_copy(update={'effective_from':None}), date(2025,2,1))


def test_registration_unverified_exact_text_no_fetch(tmp_path):
    p,s,database,actor,matter = setup(tmp_path)
    register = api('authorities.registry','register_authority')
    with database.session() as db:
        item = register(source(), actor, matter_id=matter.id, db=db)
        assert item.verification_status == 'unverified' and item.verified_by is None
        assert item.text_snapshot == source().text_snapshot
        assert api('authorities.registry','read_authority')(item.id,actor,matter_id=matter.id,db=db) == item


@pytest.mark.parametrize('attack',['hash','future_fetch','verified','verified_marker','interval','empty_verified'])
def test_authority_revalidation_blocks_client_claims(tmp_path,attack):
    p,s,database,actor,matter = setup(tmp_path)
    item = source()
    if attack == 'hash': item = item.model_copy(update={'text_snapshot':'changed'})
    if attack == 'future_fetch': item = item.model_copy(update={'fetched_at':datetime.now(timezone.utc)+timedelta(days=1)})
    if attack == 'verified': item = item.model_copy(update={'verification_status':VerificationStatus.VERIFIED,'verified_by':actor.user_id,'verified_at':datetime.now(timezone.utc)})
    if attack == 'verified_marker': item = item.model_copy(update={'verified_by':actor.user_id})
    if attack == 'interval': item = item.model_copy(update={'effective_to':date(2024,1,1)})
    if attack == 'empty_verified': item = item.model_copy(update={'text_snapshot':'','verification_status':VerificationStatus.VERIFIED})
    with database.session() as db, pytest.raises((ValueError,s.ServiceError)):
        api('authorities.registry','register_authority')(item,actor,matter_id=matter.id,db=db)


def test_synthetic_can_never_be_certified_as_law(tmp_path):
    p,s,database,actor,matter = setup(tmp_path)
    grant = api('security','provision_rule_manager_grant')
    with database.session() as db:
        grant(actor.user_id,db)
        item=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        with pytest.raises(s.ServiceError) as exc:
            api('authorities.registry','verify_authority')(item.id,actor,evidence(actor,item.snapshot_sha256),matter_id=matter.id,db=db)
        assert exc.value.code=='RULE_UNAPPROVED'


@pytest.mark.parametrize('attack',['actor_role','revoked_session','no_member','no_grant'])
def test_verification_requires_real_identity_and_grant(tmp_path,attack):
    p,s,database,actor,matter = setup(tmp_path)
    with database.session() as db:
        item=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        if attack!='no_grant': api('security','provision_rule_manager_grant')(actor.user_id,db)
        if attack=='actor_role': db.get(p.UserRow,str(actor.user_id)).roles='["assistant"]'
        if attack=='revoked_session': s.revoke_session(actor.session_id,db)
        if attack=='no_member': s.remove_membership(matter.id,actor.user_id,db)
    with database.session() as db, pytest.raises(s.ServiceError):
        api('authorities.registry','verify_authority')(item.id,actor,evidence(actor,item.snapshot_sha256),matter_id=matter.id,db=db)


def test_authority_predecessor_preserved_and_sql_immutable(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    p,s,database,actor,matter = setup(tmp_path)
    with database.session() as db:
        original=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        body='SYNTHETIC successor'
        successor=api('authorities.registry','register_authority')(source(text_snapshot=body,snapshot_sha256=hashlib.sha256(body.encode()).hexdigest()),actor,matter_id=matter.id,db=db,supersedes_id=original.id)
        assert successor.id != original.id
        assert api('authorities.registry','read_authority')(original.id,actor,matter_id=matter.id,db=db).text_snapshot==original.text_snapshot
    for statement in ('UPDATE authority_snapshots SET payload=\'{}\'','DELETE FROM authority_snapshots'):
        with database.session() as db, pytest.raises(IntegrityError): db.execute(text(statement))


def test_registration_savepoint_no_half_write(tmp_path,monkeypatch):
    p,s,database,actor,matter = setup(tmp_path)
    module=importlib.import_module('cn_contract.authorities.registry')
    def fail(*args,**kwargs): raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(module,'audit_change',fail)
    with database.session() as db:
        with pytest.raises(RuntimeError): module.register_authority(source(),actor,matter_id=matter.id,db=db)
    from sqlalchemy import text
    with database.session() as db:
        assert db.execute(text('SELECT count(*) FROM authority_snapshots')).scalar()==0


@pytest.mark.parametrize('attack',['draft','search_snippet','shell_url','title_only','missing_artifact'])
def test_official_looking_source_cannot_self_attest(tmp_path,attack):
    p,s,database,actor,matter=setup(tmp_path)
    body='独立虚构的待核验来源文字。'*20
    item=source(title='test source',issuer='test issuer',legal_rank='law',url='https://example.gov.cn/source',
        text_snapshot=body,snapshot_sha256=__import__('hashlib').sha256(body.encode()).hexdigest())
    if attack in ('draft','search_snippet'): item=item.model_copy(update={'legal_rank':attack})
    if attack=='shell_url': item=item.model_copy(update={'url':'javascript:alert(1)'})
    if attack=='title_only': item=item.model_copy(update={'text_snapshot':item.title,'snapshot_sha256':hashlib.sha256(item.title.encode()).hexdigest()})
    with database.session() as db:
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        stored=api('authorities.registry','register_authority')(item,actor,matter_id=matter.id,db=db)
        with pytest.raises(s.ServiceError):
            api('authorities.registry','attest_authority_source')(stored.id,actor,evidence(actor,api('authorities.storage','digest')(stored.model_dump(mode='json'))),matter_id=matter.id,db=db,provenance_ref='local-evidence:'+str(uuid4()))


def test_source_successor_invalidates_dependent_case_approval(tmp_path):
    from test_state import seed_approval
    from test_rule_scope import rule
    p,s,database,actor,matter=setup(tmp_path)
    with database.session() as db:
        original=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        api('rules.loader','register_rule')(rule(basis_kind='law',authority_ids=[original.id]),actor,matter_id=matter.id,db=db)
        before=api('rules.loader','read_rule_snapshot')(actor,matter_id=matter.id,db=db)
        approval,artifact=seed_approval(p,db,actor,matter)
        body='SYNTHETIC revised source'
        api('authorities.registry','register_authority')(source(text_snapshot=body,snapshot_sha256=hashlib.sha256(body.encode()).hexdigest()),actor,matter_id=matter.id,db=db,supersedes_id=original.id)
        assert api('rules.loader','read_rule_snapshot')(actor,matter_id=matter.id,db=db).sha256!=before.sha256
        assert p.read_approval(matter.id,approval.id,actor,db).status=='stale'
        assert p.read_export(matter.id,artifact.id,actor,db).superseded
        from sqlalchemy import text
        assert db.execute(text('SELECT count(*) FROM rule_invalidations')).scalar()==1


def test_source_evidence_never_reads_caller_path_or_fetches(tmp_path):
    p,s,database,actor,matter=setup(tmp_path)
    with database.session() as db:
        api('security','provision_rule_manager_grant')(actor.user_id,db)
        authority=api('authorities.registry','register_authority')(source(),actor,matter_id=matter.id,db=db)
        for value in ('C:/private.txt','https://example.gov.cn/source',b'SYNTHETIC local text'):
            with pytest.raises(s.ServiceError): api('authorities.registry','register_source_evidence')(authority.id,actor,matter_id=matter.id,db=db,source_bytes=value)
