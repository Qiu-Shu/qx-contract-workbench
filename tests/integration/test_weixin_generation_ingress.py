"""Synthetic generation polls retain immutable targets without delivering tasks."""
import importlib
import importlib.util
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.persistence import SessionRow,UserRow
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError
from cn_contract.storage_schema import identify_schema
from cn_contract.weixin_inbox import accounts,dispatch,ingress
from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
from tests.helpers.synthetic_weixin_generation_service import append,request as generation_request
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.helpers.synthetic_weixin_provenance import snapshot
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_ingress_atomic import world


def api():
    name='cn_contract.weixin_inbox.generation_ingress'
    assert importlib.util.find_spec(name) is not None,'D2g5c needs explicit generation-aware poll services'
    return importlib.import_module(name)


def poll_input(h,**changes):
    with h['database'].session() as db:
        account=accounts._account(h['actor'],h['account'].id,db,active=False)[0]
    return d.WeixinPollInput(**{**dict(request_id=uuid4(),expected_revision=account.checkpoint_revision,
        expected_cursor=account.upstream_cursor),**changes})


def raw(messages,cursor='synthetic:new'):
    return json.dumps(dict(ret=0,msgs=messages,get_updates_buf=cursor),ensure_ascii=False).encode('utf-8')


def receive(h,messages,*,value=None,cursor='synthetic:new'):
    return api().record_generation_poll(h['actor'],h['account'].id,value or poll_input(h),raw(messages,cursor),database=h['database'])


def validate(h):
    with h['database'].session() as db:
        assert validate_descriptor_generations(db,allow_provenance=True)==[]
        backup._file_references(db)


def test_two_service_polls_keep_historical_target_and_do_not_dispatch(world):
    service=api();h=setup_history(world);first=append(h);before=snapshot(h['database'])
    value=poll_input(h);wire=raw([message(91)]);one=service.record_generation_poll(h['actor'],h['account'].id,value,wire,database=h['database'])
    second=append(h,generation_request(h,first));two=receive(h,[message(92)],cursor='synthetic:two')
    with h['database'].session() as db:
        links=db.execute(text('SELECT * FROM weixin_descriptor_generations ORDER BY rowid')).mappings().all()
        assert [row['generation_id'] for row in links]==[str(first.id),str(second.id)]
        assert [row['task_binding_id'] for row in links]==[str(first.task_binding_id),str(second.task_binding_id)]
    validate(h);after=snapshot(h['database'])
    for table in ('task_channel_bindings','task_inbox_events','task_drafts','task_executions','assistant_runs','review_runs','weixin_dispatch_receipts'):
        assert before[table]==after[table],table
    assert service.find_generation_poll_receipt(h['actor'],h['account'].id,value.request_id,database=h['database'])==one
    assert service.record_generation_poll(h['actor'],h['account'].id,value,wire,database=h['database'])==one
    assert snapshot(h['database'])==after
    for action in (lambda:ingress.record_synthetic_poll(h['actor'],h['account'].id,poll_input(h),b'{}',database=h['database']),
                   lambda:dispatch.dispatch_synthetic_descriptor(h['actor'],two.descriptors[0].id,database=h['database'])):
        with pytest.raises(ServiceError) as error:action()
        assert error.value.code=='STATE_CONFLICT'
    assert snapshot(h['database'])==after


def test_complete_mixed_batch_preserves_global_dedup_and_zero_peer(world):
    api();h=setup_history(world);first=append(h)
    values=[message(91),message(91),message(91,content='different synthetic bytes'),
        message(92,peer='not-bound'),message(93,peer=h['peer'].sender_peer_id),message(94,file=True)]
    poll=receive(h,values)
    assert [item.status for item in poll.descriptors]==['accepted_pending_dispatch','duplicate','blocked','blocked','accepted_pending_dispatch','accepted_pending_dispatch']
    assert [poll.descriptors[i].reason for i in (1,2,3)]==['replayed','event_conflict','sender_unbound']
    assert poll.descriptors[0].id==poll.descriptors[1].prior_descriptor_id==poll.descriptors[2].prior_descriptor_id
    assert poll.descriptors[-1].payload.media[0].status=='pending'
    with h['database'].session() as db:
        links=db.execute(text('SELECT descriptor_id,generation_id FROM weixin_descriptor_generations ORDER BY rowid')).fetchall()
        assert links==[(str(poll.descriptors[0].id),str(first.id)),(str(poll.descriptors[-1].id),str(first.id))]
    validate(h)


@pytest.mark.parametrize('clock',['same','backwards'])
def test_poll_time_is_strictly_after_generation_even_when_clock_does_not_advance(world,monkeypatch,clock):
    api();h=setup_history(world);generation=append(h)
    stamp=generation.created_at.isoformat() if clock=='same' else '2000-01-01T00:00:00Z'
    monkeypatch.setattr(ingress,'_at',lambda:stamp)
    poll=receive(h,[message(91)])
    assert poll.created_at>generation.created_at
    validate(h)


@pytest.mark.parametrize('change',['session','role','account','restore','schema17','no_generation'])
def test_explicit_entry_checks_authority_storage_and_exact_schema_before_writes(world,change):
    api();h=setup_history(world)
    if change!='no_generation':append(h)
    value=poll_input(h)
    if change=='account':accounts.revoke_synthetic_account(h['actor'],h['account'].id,d.WeixinRevokeInput(reason='synthetic revoke'),database=h['database'])
    else:
        with h['database'].session() as db:
            if change=='session':db.get(SessionRow,str(h['actor'].session_id)).revoked=True
            elif change=='role':db.get(UserRow,str(h['actor'].user_id)).roles='["assistant"]'
            elif change=='restore':db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='1'*64,manifest_sha256='2'*64,payload='{}'))
            elif change=='schema17':
                db.execute(text('DROP TABLE assistant_evidence_revisions'))
                db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
                db.execute(text('DROP TABLE weixin_descriptor_generations'))
                rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
                assert identify_schema(rows,native=True)=='weixin-generations-v1'
    before=snapshot(h['database']) if change!='schema17' else None
    with pytest.raises(ServiceError) as error:receive(h,[message(91)],value=value)
    assert error.value.code==('AUTHORIZATION_REQUIRED' if change=='session' else 'CROSS_MATTER_DENIED' if change=='role'
        else 'BLOCKED_LIVE' if change=='restore' else 'VERSION_CONFLICT' if change=='schema17' else 'STATE_CONFLICT')
    if before is not None:assert snapshot(h['database'])==before


@pytest.mark.parametrize('change',['target_scope','target_archived','root_archived','peer'])
def test_per_message_stale_or_revoked_target_is_blocked_without_intermediate_audit(world,change):
    api();h=setup_history(world);generation=append(h)
    if change=='peer':accounts.revoke_synthetic_peer(h['actor'],h['mapping'].id,d.WeixinRevokeInput(reason='synthetic peer revoke'),database=h['database'])
    else:
        with h['database'].session() as db:
            cid=h['mapping'].scope.conversation_id if change=='root_archived' else generation.scope.conversation_id
            if change=='target_scope':db.execute(text('UPDATE assistant_conversations SET input_revision=1 WHERE id=:id'),{'id':str(cid)})
            else:db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),{'at':'2099-01-01T00:00:00Z','id':str(cid)})
    before=snapshot(h['database']);poll=receive(h,[message(91),message(92,peer=h['peer'].sender_peer_id)])
    assert poll.descriptors[0].status=='blocked' and poll.descriptors[0].reason==('binding_revoked' if change=='peer' else 'scope_stale')
    assert poll.descriptors[1].status=='accepted_pending_dispatch'
    after=snapshot(h['database']);assert after['audit_events']==before['audit_events']
    assert after['weixin_descriptor_generations']==before['weixin_descriptor_generations']
    validate(h)


@pytest.mark.parametrize('direction',['to_root','to_previous','from_previous_unknown'])
def test_cross_generation_known_reply_in_either_direction_rolls_back_complete_poll(world,direction):
    api();h=setup_history(world);first=append(h)
    if direction=='to_root':messages=[message(91,reply=1)]
    else:
        receive(h,[message(91,reply=92 if direction=='from_previous_unknown' else None)])
        append(h,generation_request(h,first))
        messages=[message(92,reply=91 if direction=='to_previous' else None)]
    before=snapshot(h['database'])
    with pytest.raises(ServiceError) as error:receive(h,messages,cursor='synthetic:conflict')
    assert error.value.code=='VERSION_CONFLICT' and snapshot(h['database'])==before
    validate(h)


def test_unknown_future_reply_can_become_known_in_same_generation(world):
    api();h=setup_history(world);append(h)
    receive(h,[message(91,reply=92)]);receive(h,[message(92)],cursor='synthetic:future')
    validate(h)


@pytest.mark.parametrize('change',['root_archive','target_archive','scope','account','peer','restore'])
def test_fixed_query_is_readonly_after_scope_archive_revocation_or_restore(world,change):
    service=api();h=setup_history(world);generation=append(h);value=poll_input(h)
    received=receive(h,[message(91)],value=value)
    if change in ('account','peer'):
        call=accounts.revoke_synthetic_account if change=='account' else accounts.revoke_synthetic_peer
        call(h['actor'],h['account'].id if change=='account' else h['mapping'].id,d.WeixinRevokeInput(reason='synthetic historical lookup'),database=h['database'])
    else:
        with h['database'].session() as db:
            if change=='restore':db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='1'*64,manifest_sha256='2'*64,payload='{}'))
            elif change=='scope':db.execute(text('UPDATE assistant_conversations SET input_revision=1 WHERE id=:id'),{'id':str(generation.scope.conversation_id)})
            else:
                cid=h['mapping'].scope.conversation_id if change=='root_archive' else generation.scope.conversation_id
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),{'at':'2099-01-01T00:00:00Z','id':str(cid)})
    before=snapshot(h['database'])
    assert service.find_generation_poll_receipt(h['actor'],h['account'].id,value.request_id,database=h['database'])==received
    assert service.find_generation_poll_receipt(h['actor'],h['account'].id,uuid4(),database=h['database']) is None
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('position',['root','fixed_target'])
@pytest.mark.parametrize('damage',['membership','matter_archived','intake_owner'])
def test_current_projected_acl_denial_never_releases_poll_lock_or_exposes_fixed_body(world,position,damage):
    from cn_contract.matters import create_matter
    from cn_contract.persistence import MatterRow,MembershipRow
    from cn_contract.security import provision_user
    service=api();h=setup_history(world);generation=append(h);value=poll_input(h)
    receive(h,[message(91)],value=value)
    with h['database'].session() as db:
        matter=create_matter(d.MatterCreateInput(title='独立虚构收件当前权限',contract_type='sales',
            review_mode='pre_sign',position='buyer',objectives=('合成权限边界',)),h['actor'],db)
        intake=uuid4()
        db.execute(text("INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id) VALUES(:id,:owner,:request,:sha,1,:matter)"),
            dict(id=str(intake),owner=str(h['actor'].user_id),request=str(uuid4()),sha='a'*64,matter=str(matter.id)))
        cid=h['mapping'].scope.conversation_id if position=='root' else generation.scope.conversation_id
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),{'intake':str(intake),'id':str(cid)})
        if damage=='membership':db.delete(db.get(MembershipRow,(str(matter.id),str(h['actor'].user_id))))
        elif damage=='matter_archived':db.get(MatterRow,str(matter.id)).status='archived'
        else:
            other=provision_user('独立虚构收件他人','synthetic-password',{d.Role.HANDLING_LAWYER},db)
            db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),{'owner':str(other),'id':str(intake)})
    before=snapshot(h['database']);result=receive(h,[message(92),message(93,peer=h['peer'].sender_peer_id)])
    assert result.descriptors[0].status=='blocked' and result.descriptors[0].reason=='scope_denied'
    assert result.descriptors[0].payload is None and result.descriptors[1].status=='accepted_pending_dispatch'
    after=snapshot(h['database']);assert after['audit_events']==before['audit_events']
    with pytest.raises(ServiceError) as error:
        service.find_generation_poll_receipt(h['actor'],h['account'].id,value.request_id,database=h['database'])
    assert error.value.code=='CROSS_MATTER_DENIED' and snapshot(h['database'])==after
    validate(h)


@pytest.mark.parametrize('wire',[b'{}',b'{"ret":0,"ret":0}',b'{"ret":0,"msgs":{}}',b'\xff'])
def test_new_entry_keeps_bounded_strict_envelope_rejection_atomic(world,wire):
    service=api();h=setup_history(world);append(h);before=snapshot(h['database'])
    with pytest.raises(ServiceError):service.record_generation_poll(h['actor'],h['account'].id,poll_input(h),wire,database=h['database'])
    assert snapshot(h['database'])==before


@pytest.mark.parametrize('damage',['request_changed','raw_changed','stale_checkpoint'])
def test_generation_receipt_replay_requires_exact_request_and_response(world,damage):
    service=api();h=setup_history(world);append(h);value=poll_input(h);wire=raw([message(91)])
    service.record_generation_poll(h['actor'],h['account'].id,value,wire,database=h['database'])
    before=snapshot(h['database'])
    bad=value.model_copy(update={'expected_revision':value.expected_revision+1}) if damage=='request_changed' else value
    if damage=='stale_checkpoint':bad=value.model_copy(update={'request_id':uuid4()})
    with pytest.raises(ServiceError) as error:
        service.record_generation_poll(h['actor'],h['account'].id,bad,wire+b' ' if damage=='raw_changed' else wire,database=h['database'])
    assert error.value.code=='VERSION_CONFLICT' and snapshot(h['database'])==before
