"""Nonempty generation accounts pause old runtime paths without rewriting history."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts, conversation, dispatch, ingress
from tests.helpers.synthetic_weixin_generations import append_generation, setup_history, state
from tests.integration.test_weixin_dispatch import message, poll
from tests.integration.test_weixin_ingress_atomic import world


def denied(code, operation):
    with pytest.raises(ServiceError) as failure:
        operation()
    assert failure.value.code == code


@pytest.mark.parametrize('operation',['poll','dispatch_pending','dispatch_replay','refresh'])
def test_generation_account_pauses_all_active_legacy_operations(world,operation):
    h=setup_history(world);append_generation(h)
    before=state(h['database'])
    actions=dict(poll=lambda:poll(world,h['account'],[message(9)]),
        dispatch_pending=lambda:dispatch.dispatch_synthetic_descriptor(h['actor'],h['received'].descriptors[1].id,database=h['database']),
        dispatch_replay=lambda:dispatch.dispatch_synthetic_descriptor(h['actor'],h['dispatched'].descriptor_id,database=h['database']),
        refresh=lambda:accounts.refresh_synthetic_peer(h['actor'],h['mapping'].id,h['grant_request'],database=h['database']))
    denied('STATE_CONFLICT',actions[operation])
    assert state(h['database'])==before


@pytest.mark.parametrize('kind',['poll','dispatch','grant'])
def test_old_fixed_receipt_finds_do_not_reauthorize_old_targets(world,kind):
    h=setup_history(world);append_generation(h)
    before=state(h['database'])
    actions=dict(poll=lambda:ingress.find_poll_receipt(h['actor'],h['account'].id,h['received'].request_id,database=h['database']),
        dispatch=lambda:dispatch.find_dispatch_receipt(h['actor'],h['dispatched'].descriptor_id,database=h['database']),
        grant=lambda:accounts.find_peer_scope_grant(h['actor'],h['mapping'].id,h['grant'].request_id,database=h['database']))
    denied('VERSION_CONFLICT',actions[kind])
    assert state(h['database'])==before


def test_other_peer_in_the_same_account_is_also_paused(world):
    h=setup_history(world);append_generation(h);before=state(h['database'])
    denied('STATE_CONFLICT',lambda:dispatch.dispatch_synthetic_descriptor(h['actor'],h['peer_dispatch'].descriptor_id,database=h['database']))
    denied('VERSION_CONFLICT',lambda:dispatch.find_dispatch_receipt(h['actor'],h['peer_dispatch'].descriptor_id,database=h['database']))
    denied('VERSION_CONFLICT',lambda:ingress.find_poll_receipt(h['actor'],h['account'].id,h['peer_poll'].request_id,database=h['database']))
    assert conversation.read_authorization(h['actor'],h['peer_view'].scope.conversation_id,database=h['database']).state=='target_changed'
    assert state(h['database'])==before


def test_zero_generations_keep_existing_current_reads_and_poll_dispatch_behavior(world):
    h=setup_history(world);database=h['database'];actor=h['actor']
    assert conversation.read_authorization(actor,h['view'].scope.conversation_id,database=database).state=='current'
    assert accounts.find_peer_scope_grant(actor,h['mapping'].id,h['grant'].request_id,database=database)==h['grant']
    assert dispatch.find_dispatch_receipt(actor,h['dispatched'].descriptor_id,database=database)==h['dispatched']
    assert ingress.find_poll_receipt(actor,h['account'].id,h['received'].request_id,database=database)==h['received']
    dispatch.dispatch_synthetic_descriptor(actor,h['received'].descriptors[1].id,database=database)
    later=poll(world,h['account'],[message(9)])
    assert later.descriptors[0].status=='accepted_pending_dispatch'
    dispatch.dispatch_synthetic_descriptor(actor,later.descriptors[0].id,database=database)
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations'))==0
        for table in ('assistant_runs','review_runs','task_executions'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0


@pytest.mark.parametrize('kind',['peer','account'])
def test_permanent_revocation_is_still_possible_after_generation(world,monkeypatch,kind):
    h=setup_history(world);generation=append_generation(h)
    function=accounts.revoke_synthetic_peer if kind=='peer' else accounts.revoke_synthetic_account
    identifier=h['mapping'].id if kind=='peer' else h['account'].id
    monkeypatch.setattr(accounts,'_at',lambda:(generation.created_at-timedelta(days=1)).isoformat())
    result=function(h['actor'],identifier,d.WeixinRevokeInput(reason='独立合成代际后永久撤权'),database=h['database'])
    assert result.revoked_at>generation.created_at
    assert conversation.read_authorization(h['actor'],h['view'].scope.conversation_id,database=h['database']).state=='revoked'


@pytest.mark.parametrize('blocking',['generation','archive','archived_revoked','peer','account','restore'])
def test_projection_priorities_show_blocking_state_without_creating_runs(world,blocking):
    h=setup_history(world);append_generation(h);database=h['database'];actor=h['actor']
    if blocking in ('peer','account','archived_revoked'):
        fn=accounts.revoke_synthetic_peer if blocking=='peer' else accounts.revoke_synthetic_account
        fn(actor,h['mapping'].id if blocking=='peer' else h['account'].id,d.WeixinRevokeInput(reason='独立合成状态优先级'),database=database)
    if blocking in ('archive','archived_revoked','restore'):
        with database.session() as db:
            db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-24T23:00:00Z' WHERE id=:id"),{'id':str(h['view'].scope.conversation_id)})
            if blocking=='restore':
                db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='1'*64,manifest_sha256='2'*64,payload='{}'))
    before=state(database)
    projection=conversation.read_authorization(actor,h['view'].scope.conversation_id,database=database)
    assert projection.state==dict(generation='target_changed',archive='archived',archived_revoked='archived',peer='revoked',account='revoked',restore='restored_blocked')[blocking]
    assert projection.authorized_scope==h['grant'].scope
    assert state(database)==before
    with database.session() as db:
        for table in ('assistant_runs','review_runs','task_executions'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0


def test_generation_pause_is_limited_to_its_account(world):
    from cn_contract.assistant import service
    from cn_contract.task_drafts import service as tasks
    h=setup_history(world);append_generation(h);database=h['database'];actor=h['actor']
    with database.session() as db:
        view=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        binding=tasks.create_binding(actor,view.scope.conversation_id,db)
    account=accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(bot_account_id='synthetic-unpaused-account'),database=database)
    accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='synthetic-peer',
        task_binding_id=binding.id,expected_scope=view.scope),database=database)
    item=message(91);item['to_user_id']=account.bot_account_id
    received=poll(world,account,[item])
    assert received.descriptors[0].status=='accepted_pending_dispatch'
    receipt=dispatch.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    assert receipt.next_task_cursor==1
    assert conversation.read_authorization(actor,view.scope.conversation_id,database=database).state=='current'


def test_generation_pause_preserves_ordinary_task_draft_read_and_manual_update(world):
    from cn_contract.task_drafts import service as tasks
    h=setup_history(world);append_generation(h);database=h['database'];actor=h['actor']
    before={name:rows for name,rows in state(database).items() if name.startswith('weixin_')}
    with database.session() as db:
        listing=tasks.list_drafts(actor,h['view'].scope.conversation_id,db)
        assert len(listing.items)==1
        original=tasks.read_draft(actor,listing.items[0].id,db)
        changed=tasks.update_draft(actor,original.id,d.TaskDraftUpdateInput(expected_revision=original.revision,
            instruction='律师明确补充的独立合成审查指令'),db)
        assert changed.id==original.id and changed.revision==original.revision+1
        assert changed.instruction=='律师明确补充的独立合成审查指令'
    with database.session() as db:
        assert tasks.read_draft(actor,original.id,db).instruction==changed.instruction
        for table in ('assistant_runs','review_runs','task_executions'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0
    assert {name:rows for name,rows in state(database).items() if name.startswith('weixin_')}==before
