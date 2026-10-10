"""QX05 uses invented sources and local identities, never certifies real law."""
from hashlib import sha256
from datetime import date, datetime, timezone
from cn_contract.domain import AuthorityInput
from cn_contract.authorities.registry import register_authority
from tests.integration.test_decision_exports import world_with_history, decide, report
import pytest
from pydantic import ValidationError
from cn_contract.security import ServiceError
from tests.integration.test_api import api, reviewed_case


def source_input():
    text='SYNTHETIC 仅供工程验证：付款时间由双方书面确定。'
    return AuthorityInput(title='SYNTHETIC 本机来源',issuer='SYNTHETIC',url='https://example.invalid/source',
        article='虚构第1条',text_snapshot=text,snapshot_sha256=sha256(text.encode()).hexdigest(),
        promulgated_at=date(2025,1,1),effective_from=date(2025,1,1),effective_to=None,
        jurisdiction='CN-mainland',legal_rank='law',fetch_status='fetched',fetched_at=datetime.now(timezone.utc),
        verification_status='unverified',verified_by=None,verified_at=None)
def registered(world):
    with world[0].session() as db:
        return register_authority(source_input(),world[1],matter_id=world[3].id,db=db)


def basis(world,source,**changes):
    value=dict(authority_id=str(source.id),source_sha256=source.snapshot_sha256,
        quote='付款时间由双方书面确定。',proposition='付款时间应书面约定',
        support='supported',support_reason='虚构命题与原句核对',
        applicability='applies',applicability_reason='虚构买卖交易范围核对',event_date='2025-06-01',
        policy_sha256=world[6].manifest.policy_sha256)
    return {**value,**changes}


def test_accept_does_not_promote_unverified_source_and_export_is_explicit(tmp_path):
    world=world_with_history(tmp_path); source=registered(world)
    saved=decide(world,'accept',basis_review=basis(world,source))
    assert saved['decision']['basis_review']['source_status']=='unverified'
    assert saved['decision']['basis_review']['position']==world[4].position
    _,client,_=report(world)
    assert '法源真实性未核验' in client
    assert '虚构命题与原句核对' not in client
    _,internal,_=report(world,'internal')
    assert '虚构命题与原句核对' in internal and '付款时间由双方书面确定。' in internal


@pytest.mark.parametrize('changes,code',[
    ({'quote':'并不存在的条文'},'VERSION_CONFLICT'),
    ({'source_sha256':'0'*64},'VERSION_CONFLICT'),
    ({'policy_sha256':'0'*64},'APPROVAL_STALE'),
    ({'event_date':'2024-01-01'},'RULE_UNAPPROVED'),
])
def test_exact_source_policy_and_date_are_required(tmp_path,changes,code):
    world=world_with_history(tmp_path); source=registered(world)
    with pytest.raises(ServiceError) as error:decide(world,'accept',basis_review=basis(world,source,**changes))
    assert error.value.code==code


def test_cross_case_source_denied(tmp_path):
    a=world_with_history(tmp_path/'a');b=world_with_history(tmp_path/'b');source=registered(b)
    with pytest.raises(ServiceError) as error:decide(a,'accept',basis_review=basis(a,source))
    assert error.value.code=='CROSS_MATTER_DENIED'


@pytest.mark.parametrize('support,applies,text',[
    ('not_supported','applies','不支持该命题'),('supported','not_applies','不适用于本案'),
    ('pending','pending','命题支持待核')])
def test_support_and_application_failures_remain_distinct(tmp_path,support,applies,text):
    world=world_with_history(tmp_path); source=registered(world)
    decide(world,'accept',basis_review=basis(world,source,support=support,applicability=applies))
    assert text in report(world)[1]


def test_business_standard_is_case_policy_bound_and_internal_only(tmp_path):
    world=world_with_history(tmp_path)
    value=dict(kind='business_preference',proposition='虚构谈判条件',support='not_applicable',support_reason='商业选择',
        applicability='not_applicable',applicability_reason='不是法律要求',policy_sha256=world[6].manifest.policy_sha256,
        standard_position='PRIVATE 首选付款30日',fallback_position='PRIVATE 退让至60日',escalation_conditions='PRIVATE 超过60日升级')
    saved=decide(world,'accept',basis_review=value)
    assert saved['decision']['basis_review']['source_status']=='not_legal_basis'
    client=report(world)[1]; internal=report(world,'internal')[1]
    assert '商业偏好（非法律命令）' in client and 'PRIVATE' not in client
    assert 'PRIVATE 首选付款30日' in internal and 'PRIVATE 超过60日升级' in internal
    with pytest.raises(ValidationError):decide(world,'accept',basis_review={**value,'support':'supported'})


def test_source_metadata_cannot_be_supplied_by_client(tmp_path):
    world=world_with_history(tmp_path);source=registered(world)
    with pytest.raises(ValidationError):
        decide(world,'accept',basis_review=basis(world,source,source_status='verified'))


def test_later_basis_review_stales_old_export_and_keeps_history(tmp_path):
    from cn_contract.web import services
    from cn_contract.exports.approvals import read_bundle
    world=world_with_history(tmp_path);source=registered(world)
    decide(world,'accept',basis_review=basis(world,source))
    bundle=report(world)[0]
    decide(world,'accept',basis_review=basis(world,source,support='not_supported'))
    with world[0].session() as db:
        with pytest.raises(ServiceError) as error:read_bundle(bundle.id,world[1],db=db)
        assert error.value.code=='APPROVAL_STALE'
        records=services.decisions(world[3].id,world[6].id,world[1],db)
        assert [r['decision']['basis_review']['support'] for r in records]==['supported','not_supported']


def test_http_register_source_and_record_basis_without_source_fetch(api):
    client,_,_,_=api;matter,run,headers,_=reviewed_case(api)
    response=client.post(f'/api/matters/{matter}/authority-sources',headers={**headers,'Idempotency-Key':'qx05-source'},
        json=source_input().model_dump(mode='json'))
    assert response.status_code==201,response.text
    source=response.json()
    listed=client.get(f'/api/matters/{matter}/authority-sources')
    assert listed.status_code==200 and source['id'] in [v['id'] for v in listed.json()['items']]
    payload=dict(authority_id=source['id'],source_sha256=source['snapshot_sha256'],quote='付款时间由双方书面确定。',
        proposition='虚构付款命题',support='pending',support_reason='尚待核验',applicability='pending',
        applicability_reason='尚待核验',event_date='2025-06-01',policy_sha256=run['manifest']['policy_sha256'])
    sent=client.post(f'/api/matters/{matter}/findings/{run["findings"][0]["id"]}/decision',headers=headers,
        json=dict(run_id=run['id'],run_sha256=run['run_sha256'],decision='accept',reason='虚构处置',basis_review=payload))
    assert sent.status_code==201,sent.text
    assert sent.json()['decision']['basis_review']['source_status']=='unverified'


def test_source_index_paginates_all_records_and_separates_live_status(api):
    from cn_contract.security import authenticate
    client,database,_,_=api;matter,_,headers,_=reviewed_case(api)
    from uuid import UUID
    with database.session() as db:
        actor=authenticate(client.cookies.get('qx_session'),db)
        for _ in range(101):register_authority(source_input(),actor,matter_id=UUID(matter),db=db)
    first=client.get(f'/api/matters/{matter}/authority-sources').json()
    assert len(first['items'])==100 and first['next_cursor']
    assert all(item['current_verified'] is False for item in first['items'])
    second=client.get(f'/api/matters/{matter}/authority-sources?after={first["next_cursor"]}').json()
    assert len(second['items'])==1 and second['next_cursor'] is None
    assert len({s['id'] for s in first['items']+second['items']})==101


@pytest.mark.parametrize('change',['source_successor','policy'])
def test_source_successor_and_policy_change_prevent_old_basis_delivery(tmp_path,change):
    from cn_contract.exports.approvals import read_bundle
    from cn_contract.domain import PolicySnapshot
    from cn_contract.rules.loader import save_policy
    from cn_contract.rules.storage import policy_sha256
    world=world_with_history(tmp_path);source=registered(world)
    decide(world,'accept',basis_review=basis(world,source));bundle=report(world)[0]
    with world[0].session() as db:
        if change=='source_successor':
            register_authority(source_input(),world[1],matter_id=world[3].id,db=db,supersedes_id=source.id)
        else:
            policy=PolicySnapshot(client_ref=world[3].client_ref,version=2,
                sha256=policy_sha256(world[3].client_ref,2,()),preferences=(),approved_by=None,approved_at=None)
            save_policy(policy,world[1],matter_id=world[3].id,db=db)
    with world[0].session() as db,pytest.raises(ServiceError):read_bundle(bundle.id,world[1],db=db)


def test_same_contract_basis_records_capture_buyer_and_seller_positions(tmp_path):
    from unittest.mock import patch
    from tests.helpers.synthetic_review import prepare
    captured=[]
    for position in ['buyer','seller']:
        with patch('tests.helpers.synthetic_exports.prepare',lambda p:prepare(p,position=position)):
            world=world_with_history(tmp_path/position)
        source=registered(world)
        result=decide(world,'accept',basis_review=basis(world,source))
        captured.append(result['decision']['basis_review']['position'])
    assert captured==['buyer','seller']


def test_source_endpoints_reject_missing_csrf_and_cross_case_reference(api):
    from tests.integration.test_api import create_case
    client,_,_,_=api;matter,run,headers,_=reviewed_case(api)
    response=client.post(f'/api/matters/{matter}/authority-sources',json=source_input().model_dump(mode='json'))
    assert response.status_code==403
    source=client.post(f'/api/matters/{matter}/authority-sources',headers=headers,
        json=source_input().model_dump(mode='json')).json()
    other=create_case(client,headers)
    assert client.get(f'/api/matters/{other}/authority-sources/{source["id"]}').status_code==403
