"""Only accepted synthetic descriptors enter the existing shared TaskInbox."""
import importlib
import importlib.util
from io import BytesIO
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.security import ServiceError, provision_user
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, ingress
from tests.integration.test_weixin_ingress_atomic import world


def api():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.dispatch'), 'D2c needs durable TaskInbox dispatch'
    return importlib.import_module('cn_contract.weixin_inbox.dispatch')


def message(identifier, *, content='请审查独立虚构合同', file=False, peer='synthetic-peer', reply=None):
    item={'type':4,'file_item':{'file_name':'独立虚构合同.docx'}} if file else {'type':1,'text_item':{'text':content}}
    if reply is not None: item['ref_msg']={'svr_id':str(reply)}
    return {'message_id':identifier,'from_user_id':peer,'to_user_id':'synthetic-dispatch-bot',
        'message_type':1,'message_state':2,'item_list':[item]}


def seed(world, messages):
    _,database,actor,view,binding=world
    with database.session() as db:
        current=conversations.read_conversation(actor,view.scope.conversation_id,db)
    account=accounts.create_synthetic_account(actor,d.WeixinAccountCreateInput(bot_account_id='synthetic-dispatch-bot'),database=database)
    mapping=accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='synthetic-peer',
        task_binding_id=binding.id,expected_scope=current.scope),database=database)
    return account,mapping,poll(world,account,messages)


def poll(world, account, messages):
    _,database,actor,*_=world
    current=accounts.read_synthetic_account(actor,account.id,database=database)
    request=d.WeixinPollInput(request_id=uuid4(),expected_revision=current.checkpoint_revision,expected_cursor=current.upstream_cursor)
    raw=json.dumps({'ret':0,'msgs':messages,'get_updates_buf':'opaque:'+str(current.checkpoint_revision+1)},ensure_ascii=False).encode()
    return ingress.record_synthetic_poll(actor,account.id,request,raw,database=database)


def state(database):
    tables=('task_inbox_events','task_drafts','task_draft_events','task_channel_bindings','weixin_dispatch_receipts')
    with database.session() as db:
        return {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))] for table in tables}


@pytest.mark.parametrize('file_first',[False,True])
def test_both_message_orders_aggregate_without_freeze_or_model(world,file_first):
    module=api()
    root,database,actor,view,binding=world
    incoming=[message(1,file=file_first),message(2,file=not file_first)]
    account,mapping,received=seed(world,incoming)
    receipts=[module.dispatch_synthetic_descriptor(actor,item.id,database=database) for item in received.descriptors]
    with database.session() as db:
        drafts=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert len(drafts.items)==1 and len(drafts.items[0].events)==2
        draft=drafts.items[0]
        assert draft.state=='collecting' and draft.instruction=='请审查独立虚构合同'
        assert 'media_pending' in draft.blockers
        assert drafts.binding.cursor==2 and not drafts.unassigned_events
        with pytest.raises(ServiceError):
            tasks.freeze_draft(actor,draft.id,d.TaskFreezeInput(expected_revision=draft.revision,manifest_sha256=draft.manifest_sha256),db)
        for table in ('assistant_runs','task_executions','review_runs'):
            assert db.scalar(text('SELECT count(*) FROM '+table))==0
    before=state(database)
    for original in receipts:
        assert module.find_dispatch_receipt(actor,original.descriptor_id,database=database)==original
        assert module.dispatch_synthetic_descriptor(actor,original.descriptor_id,database=database)==original
    assert state(database)==before
    assert receipts[0].expected_task_cursor==0 and receipts[1].next_task_cursor==2


def test_accepted_order_is_per_mapping_and_blocked_or_duplicate_never_dispatch(world):
    module=api();_,database,actor,*_=world
    first=message(1)
    account,mapping,received=seed(world,[first,message(2),first,message(3,peer='unbound-peer')])
    initial=state(database)
    for item in received.descriptors[2:]:
        with pytest.raises(ServiceError): module.dispatch_synthetic_descriptor(actor,item.id,database=database)
    with pytest.raises(ServiceError) as late:
        module.dispatch_synthetic_descriptor(actor,received.descriptors[1].id,database=database)
    assert late.value.code=='VERSION_CONFLICT' and state(database)==initial
    for item in received.descriptors[:2]: module.dispatch_synthetic_descriptor(actor,item.id,database=database)
    assert module.find_dispatch_receipt(actor,received.descriptors[3].id,database=database) is None


@pytest.mark.parametrize('change',['session','role','owner','mapping','account','scope','archived'])
def test_current_guards_apply_to_new_dispatch_and_fixed_receipt_replay(world,change):
    module=api();_,database,actor,view,*_=world
    account,mapping,received=seed(world,[message(1),message(2)])
    receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    before=state(database)
    with database.session() as db:
        if change=='session': db.execute(text('UPDATE sessions SET revoked=1'))
        elif change=='role': db.execute(text("UPDATE users SET roles='[\"assistant\"]'"))
        elif change=='owner':
            other=provision_user('fictional-other','fictional-long-password',{d.Role.HANDLING_LAWYER},db)
            db.execute(text('UPDATE assistant_conversations SET owner_id=:id'),{'id':str(other)})
        elif change=='scope': db.execute(text('UPDATE assistant_conversations SET input_revision=input_revision+1'))
        elif change=='archived': db.execute(text("UPDATE assistant_conversations SET archived_at='2026-10-24T00:00:00Z'"))
    if change=='mapping': accounts.revoke_synthetic_peer(actor,mapping.id,d.WeixinRevokeInput(reason='独立虚构撤权'),database=database)
    if change=='account': accounts.revoke_synthetic_account(actor,account.id,d.WeixinRevokeInput(reason='独立虚构撤权'),database=database)
    for operation in (lambda:module.dispatch_synthetic_descriptor(actor,received.descriptors[1].id,database=database),
                      lambda:module.dispatch_synthetic_descriptor(actor,receipt.descriptor_id,database=database),
                      lambda:module.find_dispatch_receipt(actor,receipt.descriptor_id,database=database)):
        with pytest.raises(ServiceError):operation()
    # Only the explicit auth changes above differ; no task/dispatch row changed.
    after=state(database)
    assert after==before


def test_unknown_reference_remains_unassigned_and_local_event_collision_is_not_adopted(world):
    module=api();_,database,actor,view,binding=world
    account,mapping,received=seed(world,[message(1,reply=999),message(2)])
    module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    with database.session() as db:
        listing=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert not listing.items and len(listing.unassigned_events)==1
        tasks.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=1,next_cursor=2,
            events=(received.descriptors[1].payload,)),db)
    before=state(database)
    with pytest.raises(ServiceError) as collision:
        module.dispatch_synthetic_descriptor(actor,received.descriptors[1].id,database=database)
    assert collision.value.code=='VERSION_CONFLICT' and state(database)==before


def test_peer_isolation_and_task_cursor_gaps_are_preserved(world):
    module=api();_,database,actor,view,binding=world
    account,mapping,received=seed(world,[message(1),message(2,peer='peer-2')])
    with database.session() as db:
        other=conversations.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        other_binding=tasks.create_binding(actor,other.scope.conversation_id,db)
        tasks.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='desktop-gap',text='桌面独立虚构说明'),)),db)
    # The originally blocked peer remains blocked after mapping; use a genuinely new event.
    accounts.bind_synthetic_peer(actor,account.id,d.WeixinPeerBindInput(sender_peer_id='peer-2',
        task_binding_id=other_binding.id,expected_scope=other.scope),database=database)
    second=poll(world,account,[message(3,peer='peer-2')])
    peer_receipt=module.dispatch_synthetic_descriptor(actor,second.descriptors[0].id,database=database)
    first_receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    assert peer_receipt.expected_task_cursor==0 and first_receipt.expected_task_cursor==1
    with database.session() as db:
        assert len(tasks.list_drafts(actor,other.scope.conversation_id,db).items[0].events)==1
        assert len(tasks.list_drafts(actor,view.scope.conversation_id,db).items[0].events)==2


@pytest.mark.parametrize('control,expected',[('暂停','paused'),('取消','cancelled')])
def test_explicit_lawyer_controls_pause_or_cancel_then_resume_without_model(world,control,expected):
    module=api();_,database,actor,view,*_=world
    _,_,received=seed(world,[message(1),message(2,content=control),message(3,content='继续')])
    for item in received.descriptors[:2]:module.dispatch_synthetic_descriptor(actor,item.id,database=database)
    with database.session() as db:
        draft=tasks.list_drafts(actor,view.scope.conversation_id,db).items[0]
        assert draft.state==expected and draft.instruction=='请审查独立虚构合同'
    module.dispatch_synthetic_descriptor(actor,received.descriptors[2].id,database=database)
    with database.session() as db:
        draft=tasks.list_drafts(actor,view.scope.conversation_id,db).items[0]
        assert draft.state=='collecting' and len(draft.events)==3
        assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==0


def test_ambiguous_desktop_drafts_keep_dispatched_event_durably_unassigned(world):
    module=api();_,database,actor,view,binding=world
    _,_,received=seed(world,[message(1)])
    with database.session() as db:
        tasks.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='desktop-one',text='独立虚构一',start_new=True),
                    d.TaskInboxEventInput(event_id='desktop-two',text='独立虚构二',start_new=True))),db)
    receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    with database.session() as db:
        listing=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert len(listing.items)==2 and len(listing.unassigned_events)==1
        assert listing.unassigned_events[0].id==receipt.task_event_id
        assert receipt.next_task_cursor==2


def test_frozen_known_reply_creates_supplement_after_controlled_local_material_resolution(world):
    module=api();_,database,actor,view,binding=world
    from cn_contract.assistant import attachments
    from cn_contract.documents.ingest import DOCX_MIME
    from cn_contract.review.synthetic import select_fixture
    _,_,path,raw=select_fixture('sales')
    upload=attachments.ingest_attachment(actor,view.scope.conversation_id,d.AssistantAttachmentInput(
        request_id=uuid4(),expected_scope=view.scope,original_name=path.name,mime=DOCX_MIME,
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)),BytesIO(raw),database=database)
    current=attachments.read_materials(actor,view.scope.conversation_id,database=database)
    parsed=attachments.parse_attachment(actor,view.scope.conversation_id,upload.attachment.id,
        d.AssistantAttachmentParseInput(request_id=uuid4(),expected_scope=current.scope),database=database)
    incoming=message(1,file=True);incoming['item_list'][0]['file_item']['file_name']=path.name
    incoming['item_list'].append({'type':1,'text_item':{'text':'审查独立虚构样本'}})
    account,mapping,received=seed(world,[incoming])
    receipt=module.dispatch_synthetic_descriptor(actor,received.descriptors[0].id,database=database)
    with database.session() as db:
        draft=tasks.list_drafts(actor,view.scope.conversation_id,db).items[0]
        media=received.descriptors[0].payload.media[0]
        updated=tasks.update_draft(actor,draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,
            media_resolutions=(d.TaskMediaResolutionInput(event_id=receipt.task_event_id,media_id=media.media_id,
                action='resolve',replacement=d.TaskMediaInput(media_id=media.media_id,name=path.name,
                    mime=DOCX_MIME,status='ready',attachment_id=upload.attachment.id,
                    sha256=upload.attachment.sha256,parse_revision=parsed.parse.revision)),)),db)
        frozen=tasks.freeze_draft(actor,draft.id,d.TaskFreezeInput(expected_revision=updated.revision,
            manifest_sha256=updated.manifest_sha256),db)
    later=poll(world,account,[message(2,content='后到独立虚构补充',reply=1)])
    module.dispatch_synthetic_descriptor(actor,later.descriptors[0].id,database=database)
    with database.session() as db:
        listing=tasks.list_drafts(actor,view.scope.conversation_id,db)
        assert len(listing.items)==2
        child=next(item for item in listing.items if item.parent_draft_id==draft.id)
        assert child.state=='collecting' and child.instruction=='审查独立虚构样本\n后到独立虚构补充'
        assert tasks.read_execution(actor,frozen.id,db).manifest==frozen.manifest
        assert db.scalar(text('SELECT count(*) FROM assistant_runs'))==0
