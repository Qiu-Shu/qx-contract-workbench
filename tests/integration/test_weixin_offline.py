"""Synthetic protocol previews prove current desktop ACL and no consumption."""
import importlib
import importlib.util
import json
import socket
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.security import ServiceError, login, authenticate
from cn_contract.task_drafts import service
from test_assistant_storage import workspace, conversation


def adapter():
    assert importlib.util.find_spec('cn_contract.weixin_offline') is not None, 'D1 offline protocol adapter required'
    return importlib.import_module('cn_contract.weixin_offline')


def message(identifier='18446744073709551615', content='帮我审查独立虚构合同'):
    return {'message_id':identifier,'from_user_id':'synthetic-lawyer-peer',
        'to_user_id':'synthetic-bot-account','message_type':1,'message_state':2,
        'item_list':[{'type':1,'text_item':{'text':content}}],
        'context_token':'SYNTHETIC_CONTEXT_SECRET'}


def raw(*messages, cursor='SYNTHETIC_NEXT_OPAQUE_CURSOR'):
    return json.dumps({'ret':0,'errcode':0,'get_updates_buf':cursor,'msgs':list(messages)},
        ensure_ascii=False).encode('utf-8')


@pytest.fixture
def offline(workspace):
    from cn_contract.storage_bootstrap import initialize_storage
    database,actors,_,_=workspace
    initialize_storage(database)
    view=conversation(workspace)
    with database.session() as db:
        binding=service.create_binding(actors['lawyer'],view.scope.conversation_id,db)
        scope=adapter().create_offline_scope(actors['lawyer'],binding.id,
            bot_account_id='synthetic-bot-account',sender_peer_id='synthetic-lawyer-peer',
            upstream_cursor='SYNTHETIC_BEFORE_OPAQUE_CURSOR',db=db)
    return database,actors,view,binding,scope


def snapshot(db):
    names=('task_channel_bindings','task_inbox_events','task_drafts','task_draft_events',
        'task_media_resolutions','task_executions','assistant_messages','assistant_runs','document_versions')
    return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
        for name in names}


def test_preview_has_no_network_or_persistence_and_preserves_distinct_cursors(offline,monkeypatch):
    database,actors,_,binding,scope=offline
    def never(*args,**kwargs):
        raise AssertionError('offline preview must not access network')
    monkeypatch.setattr(socket,'create_connection',never)
    monkeypatch.setattr(socket.socket,'connect',never)
    with database.session() as db:
        before=snapshot(db)
        plan=adapter().preview_response(actors['lawyer'],scope,raw(message()),db=db)
        assert plan.scope==scope and plan.batch.expected_cursor==binding.cursor
        assert plan.batch.next_cursor==binding.cursor+1
        assert plan.next_upstream_cursor=='SYNTHETIC_NEXT_OPAQUE_CURSOR'
        assert plan.scope.upstream_cursor=='SYNTHETIC_BEFORE_OPAQUE_CURSOR'
        assert snapshot(db)==before
        assert 'SYNTHETIC_CONTEXT_SECRET' not in plan.model_dump_json()


@pytest.mark.parametrize('file_first',[False,True])
def test_fixture_preview_can_be_explicitly_replayed_to_synthetic_inbox_but_pending_never_freezes(offline,file_first):
    database,actors,_,binding,scope=offline
    file_message=message('100','')
    file_message['item_list']=[{'type':4,'file_item':{'file_name':'独立虚构主合同.pdf','len':'4157',
        'media':{'aes_key':'SYNTHETIC_AES_SECRET','encrypt_query_param':'SYNTHETIC_CDN_SECRET',
                 'full_url':'https://example.invalid/no-download'}}}]
    items=[message('99'),file_message]
    if file_first:items.reverse()
    with database.session() as db:
        plan=adapter().preview_response(actors['lawyer'],scope,raw(*items),db=db)
        assert snapshot(db)['task_inbox_events']==[]
        payload=plan.model_dump_json()
        assert all(secret not in payload for secret in ('SYNTHETIC_AES_SECRET','SYNTHETIC_CDN_SECRET','SYNTHETIC_CONTEXT_SECRET','example.invalid'))
        # Explicit test-only replay into the existing synthetic core; the adapter never calls it.
        receipt=service.receive_batch(actors['lawyer'],binding.id,plan.batch,db)
        replay=service.receive_batch(actors['lawyer'],binding.id,plan.batch,db)
        assert replay==receipt and len(receipt.drafts)==1 and len(receipt.events)==2
        draft=receipt.drafts[0]
        assert draft.blockers and any('pending' in item for item in draft.blockers)
        with pytest.raises(ServiceError):
            service.freeze_draft(actors['lawyer'],draft.id,d.TaskFreezeInput(
                expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        assert db.scalar(text('SELECT count(*) FROM task_executions'))==0
        assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==0


def test_other_owner_or_session_cannot_reuse_preview_scope(offline):
    database,actors,_,_,scope=offline
    with database.session() as db:
        before=snapshot(db)
        with pytest.raises(ServiceError):adapter().preview_response(actors['reviewer'],scope,raw(message()),db=db)
        token,_=login('lawyer','only-fictional-password',db)
        other_session=authenticate(token,db)
        assert other_session.session_id!=actors['lawyer'].session_id
        with pytest.raises(ServiceError):adapter().preview_response(other_session,scope,raw(message()),db=db)
        assert snapshot(db)==before


@pytest.mark.parametrize('change',['session','binding_revision','materials_revision','task_cursor','archived','restore'])
def test_current_revocation_or_changed_scope_rejects_before_consumption(offline,change):
    database,actors,view,binding,scope=offline
    with database.session() as db:
        if change=='session':db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'),{'id':str(actors['lawyer'].session_id)})
        elif change in ('binding_revision','materials_revision'):
            db.execute(text('UPDATE assistant_conversations SET '+change+'='+change+'+1 WHERE id=:id'),{'id':str(view.scope.conversation_id)})
        elif change=='task_cursor':db.execute(text('UPDATE task_channel_bindings SET cursor=1 WHERE id=:id'),{'id':str(binding.id)})
        elif change=='archived':db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-24T00:00:00+00:00' WHERE id=:id"),{'id':str(view.scope.conversation_id)})
        else:
            from cn_contract.ops.storage import RestoreFenceRow
            db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='1'*64,
                manifest_sha256='2'*64,payload='{}'))
            db.flush()
        before=snapshot(db)
        with pytest.raises(ServiceError):adapter().preview_response(actors['lawyer'],scope,raw(message()),db=db)
        assert snapshot(db)==before


def test_forged_actor_roles_are_rejected_before_source_binding_lookup(offline,monkeypatch):
    database,actors,_,binding,_=offline
    def never(*args,**kwargs):
        raise AssertionError('untrusted Actor roles must be checked before binding lookup')
    monkeypatch.setattr(service,'read_binding',never)
    with database.session() as db:
        forged=actors['assistant'].model_copy(update={'roles':frozenset({d.Role.HANDLING_LAWYER})})
        with pytest.raises(ServiceError):
            adapter().create_offline_scope(forged,binding.id,bot_account_id='synthetic-bot-account',
                sender_peer_id='synthetic-lawyer-peer',upstream_cursor='',db=db)


def test_matter_membership_is_rechecked_after_scope_was_prepared(offline):
    from cn_contract.matters import create_matter
    from cn_contract.security import remove_membership
    database,actors,_,_,_=offline
    with database.session() as db:
        matter=create_matter(d.MatterCreateInput(title='独立虚构微信预览权限案',contract_type='sales',
            review_mode='pre_sign',position='buyer',objectives=('仅合成身份隔离验收',)),actors['lawyer'],db)
        view=conversations.create_conversation(actors['lawyer'],d.AssistantConversationCreateInput(
            request_id=uuid4(),scope_kind='matter',scope_ref=matter.id),db)
        binding=service.create_binding(actors['lawyer'],view.scope.conversation_id,db)
        scope=adapter().create_offline_scope(actors['lawyer'],binding.id,
            bot_account_id='synthetic-bot-account',sender_peer_id='synthetic-lawyer-peer',upstream_cursor='',db=db)
    with database.session() as db:
        remove_membership(matter.id,actors['lawyer'].user_id,db)
    with database.session() as db:
        before=snapshot(db)
        with pytest.raises(ServiceError) as denied:
            adapter().preview_response(actors['lawyer'],scope,raw(message()),db=db)
        assert denied.value.code=='CROSS_MATTER_DENIED'
        # Existing authorization may append a denial audit; business rows/cursors remain unchanged.
        assert snapshot(db)==before
