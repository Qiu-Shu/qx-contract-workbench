"""Offline personal runtime integration; all identities and materials are fiction."""
from cn_contract import storage_schema
import asyncio
import base64
import hashlib
from io import BytesIO
import json
from uuid import uuid4
import httpx
import pytest
from docx import Document
from sqlalchemy import text
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cn_contract import domain as d
from cn_contract.assistant import service, business
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import login, authenticate, ServiceError
from cn_contract.weixin_inbox.personal_runtime import PersonalWeixinRuntime
from cn_contract.weixin_transport import PersonalWeixinTransport
from cn_contract.task_drafts import service as drafts
from tests.integration.test_assistant_generation import world
from tests.unit.test_weixin_transport import Wire, incoming, KEY


class Provider:
    def __init__(self, config, secret):
        self.config, self.calls = config, []
        self.hold = None

    async def generate(self, request, **kwargs):
        raise AssertionError('material pathway required')

    async def generate_material(self, prepared, *, expected_config, preflight):
        assert preflight()
        self.calls.append(prepared)
        if self.hold:
            await self.hold.wait()
        return d.MainMaterialReply(state='received',provider_request_id='fictional-material',
            usage=d.MainUsage(prompt_tokens=20,completion_tokens=10,total_tokens=30),
            output=d.MainMaterialCandidate(text='虚构材料已分析，原文和履行事实仍待律师核对。',
                citations=(prepared.basis.manifest.sources[0].source_id,)))


def packet(*messages, cursor='next'):
    return json.dumps({'msgs':list(messages),'get_updates_buf':cursor},ensure_ascii=False).encode()


def command(number=2, content='请审查合同'):
    return incoming(message_id=number,item_list=[{'type':1,'text_item':{'text':content}}])


def file_message(wire, number=1, name='独立虚构合同.docx'):
    # Wire serves one fictional body; reuse its bytes so every declared digest stays coherent.
    fixture=getattr(wire,'fixture_file',None)
    if fixture is None:
        doc=Document();doc.add_paragraph('独立虚构合同：甲乙双方约定2026年1月3日交货，价款30000元。')
        stream=BytesIO();doc.save(stream);data=stream.getvalue()
        pad=padding.PKCS7(128).padder();padded=pad.update(data)+pad.finalize()
        encrypt=Cipher(algorithms.AES(KEY),modes.ECB()).encryptor()
        fixture=(data,encrypt.update(padded)+encrypt.finalize())
        wire.fixture_file=fixture
    data,wire.download=fixture
    return incoming(message_id=number,item_list=[{'type':4,'file_item':{'file_name':name,
        'len':str(len(data)),'md5':hashlib.md5(data).hexdigest(),
        'media':{'aes_key':base64.b64encode(KEY).decode(),'encrypt_query_param':'fictional-query'}}}])


async def setup_runtime(world, *, automatic=True):
    database, _, conversation, _, _ = world
    database._local_materials_enabled = True
    with database.session() as db:
        token,_=login('lawyer','fixture123',db);actor=authenticate(token,db)
        conversation=service.read_conversation(actor,conversation.scope.conversation_id,db)
    registry=MainModelRegistry()
    native=NativeModelControl(database,registry,provider_factory=Provider)
    config=d.MainModelConfig(enabled=True,model='deepseek-flash',input_usd_per_million='0.3',
        output_usd_per_million='1.2',price_reference='fictional-ceiling')
    configured=native.configure({'config':config.model_dump(mode='json'),'secret':'FICTIONAL_SECRET_0123456789'})
    manager=GenerationTasks(database,registry);manager.start()
    wire=Wire(); client=httpx.Client(transport=httpx.MockTransport(wire.handle))
    runtime=PersonalWeixinRuntime(database,native,manager,client_factory=lambda:client)
    policy={'expected_config_version':configured['config_version'],'max_total_usd':'1'} if automatic else None
    assert runtime.start({'session_token':token,'expected_scope':conversation.scope.model_dump(mode='json'),
        'automatic_policy':policy})=={'status':'started'}
    # Drive the exact ingestion/dispatch executor deterministically, without a clock delay.
    runtime._task.cancel();await asyncio.gather(runtime._task,return_exceptions=True);runtime._task=None
    runtime._transport=PersonalWeixinTransport(client=client)
    runtime._transport.start_qr();runtime._transport.poll_login();runtime._bind(runtime._epoch)
    return runtime,wire,manager,registry._provider,actor


async def close(runtime,manager):
    client=runtime._transport._client if runtime._transport else None
    runtime.disable();await manager.close()
    if client:client.close()


def test_archive_requires_disconnect_and_fences_late_io_and_restart(world):
    async def scenario():
        runtime, wire, manager, _, actor = await setup_runtime(world,automatic=False)
        database = world[0];cid = runtime._value.expected_scope.conversation_id
        token = runtime._value.session_token;epoch = runtime._epoch;client = runtime._transport._client
        try:
            with database.session() as db:
                view = service.read_conversation(actor,cid,db)
                archive = d.AssistantArchiveInput(expected_scope=view.scope,expected_composer_revision=view.composer_revision)
                with pytest.raises(ServiceError) as error:
                    service.archive_conversation(actor,cid,archive,db,require_disconnected=runtime.require_disconnected)
                assert error.value.code == 'PERSONAL_WEIXIN_CONNECTED'
            runtime.disable()
            with database.session() as db:
                assert service.archive_conversation(actor,cid,archive,db,
                    require_disconnected=runtime.require_disconnected).archived_at
            called = []
            with pytest.raises(ServiceError):
                await runtime._io(epoch,lambda:called.append(True))
            assert called == []
            with pytest.raises(ServiceError):
                runtime.start({'session_token':token,'expected_scope':view.scope.model_dump(mode='json'),
                    'automatic_policy':None})
        finally:
            await close(runtime,manager);client.close()
    asyncio.run(scenario())


def count(database,table):
    with database.session() as db:
        return db.scalar(text('SELECT COUNT(*) FROM '+table))


@pytest.mark.parametrize('action',['update','assign'])
def test_synthetic_paused_edits_still_require_explicit_resume(world,action):
    database,actor,conversation,_,_=world
    with database.session() as db:
        binding=drafts.create_binding(actor,conversation.scope.conversation_id,db)
        receipt=drafts.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,events=(
            d.TaskInboxEventInput(event_id='first',text='虚构任务一',start_new=True),
            d.TaskInboxEventInput(event_id='second',text='虚构任务二',start_new=True),
            d.TaskInboxEventInput(event_id='unassigned',text='归属待定的虚构补充'))),db)
        draft=receipt.drafts[0]
        draft=drafts.update_draft(actor,draft.id,d.TaskDraftUpdateInput(expected_revision=draft.revision,action='pause'),db)
        value=d.TaskDraftUpdateInput(expected_revision=draft.revision,action=action,
            **({'instruction':'尝试修改'} if action=='update' else {'event_ids':(receipt.events[-1].id,)}))
        with pytest.raises(ServiceError) as error:
            drafts.update_draft(actor,draft.id,value,db)
        assert error.value.code=='STATE_CONFLICT'
        assert drafts.read_draft(actor,draft.id,db)==draft
        assert len(drafts.list_drafts(actor,conversation.scope.conversation_id,db).unassigned_events)==1


@pytest.mark.parametrize('hold',['还有附件，稍等',' 还有附件 , 请稍等！ ','附件还没发完，请等一下','暂停','先别审'])
def test_explicit_hold_retains_later_material_and_requires_resume_after_reconnect(world,hold):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];cid=world[2].scope.conversation_id;epoch=runtime._epoch
        first=packet(file_message(wire),command(),command(3,hold),cursor='first')
        await runtime.ingest(epoch,first);await runtime.advance(epoch)
        assert not provider.calls
        with database.session() as db:
            draft=drafts.list_drafts(actor,cid,db).items[0]
            assert draft.state=='paused'
            identifier=draft.id
        later=packet(file_message(wire,4,'虚构附件.docx'),cursor='later')
        await runtime.ingest(epoch,later);await runtime.advance(epoch)
        with database.session() as db:
            view=drafts.list_drafts(actor,cid,db)
            assert len(view.items)==1 and not view.unassigned_events
            draft=view.items[0]
            assert draft.id==identifier and draft.state=='paused'
            assert len(draft.media_resolutions)==2
        assert not provider.calls
        await close(runtime,manager)
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch
        await runtime.ingest(epoch,later);await runtime.advance(epoch)
        assert not provider.calls
        with database.session() as db:
            draft=drafts.read_draft(actor,identifier,db)
            main=draft.media_resolutions[0].replacement.attachment_id
            draft=drafts.update_draft(actor,identifier,d.TaskDraftUpdateInput(
                expected_revision=draft.revision,main_attachment_id=main),db)
            assert draft.state=='paused'
        await runtime.advance(epoch)
        assert not provider.calls
        resumed=packet(command(5,' 继续！ '),cursor='resume')
        await runtime.ingest(epoch,resumed);await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert len(provider.calls[0].basis.manifest.materials)==2
        assert count(database,'task_drafts')==1
        await runtime.ingest(epoch,resumed);await runtime.advance(epoch)
        assert len(provider.calls)==1
        await close(runtime,manager)
    asyncio.run(scenario())


def test_personal_desktop_main_selection_completes_in_same_chat_without_mock(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];cid=world[2].scope.conversation_id;epoch=runtime._epoch
        await runtime.ingest(epoch,packet(file_message(wire),file_message(wire,2,'虚构附件.docx'),command(3)))
        await runtime.advance(epoch)
        assert not provider.calls
        with database.session() as db:
            draft=drafts.list_drafts(actor,cid,db).items[0]
            assert 'main_contract_selection_required' in draft.blockers
            main=draft.media_resolutions[0].replacement.attachment_id
            draft=drafts.update_draft(actor,draft.id,d.TaskDraftUpdateInput(
                expected_revision=draft.revision,main_attachment_id=main),db)
            assert not draft.synthetic
        await runtime.advance(epoch)
        assert len(provider.calls)==1 and count(database,'task_executions')==0
        with database.session() as db:
            history=business.history(actor,cid,db)
            assert history[0].contract_draft_id==draft.id
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))==1
        assert any('虚构材料已分析' in request.content.decode() for request in wire.requests
            if request.url.path.endswith('/sendmessage'))
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('other_state',['paused','collecting'])
def test_ambiguous_paused_resume_requires_desktop_assignment_and_keeps_sources(world,other_state):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];cid=world[2].scope.conversation_id;epoch=runtime._epoch
        await runtime.ingest(epoch,packet(file_message(wire),command(),command(3,'暂停'),cursor='first'))
        with database.session() as db:
            first=drafts.list_drafts(actor,cid,db).items[0]
            other=drafts._new_draft(cid,db,parent=drafts._draft(actor,first.id,db))
            other=drafts.read_draft(actor,other,db)
            if other_state=='paused':
                drafts.update_draft(actor,other.id,d.TaskDraftUpdateInput(expected_revision=other.revision,action='pause'),db)
            original=tuple(db.execute(text('SELECT id,payload_json,payload_sha256 FROM task_inbox_events')))
        await runtime.ingest(epoch,packet(command(4,'继续'),file_message(wire,5,'归属待定附件.docx'),cursor='resume'))
        await runtime.advance(epoch);await runtime.advance(epoch)
        assert not provider.calls
        assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==1
        with database.session() as db:
            view=drafts.list_drafts(actor,cid,db)
            assert len(view.unassigned_events)==2
            assert drafts.read_draft(actor,first.id,db).state=='paused'
            assert drafts.read_draft(actor,other.id,db).state==other_state
            first=drafts.read_draft(actor,first.id,db)
            assigned=drafts.update_draft(actor,first.id,d.TaskDraftUpdateInput(expected_revision=first.revision,
                action='assign',event_ids=tuple(event.id for event in view.unassigned_events)),db)
            assert assigned.state=='collecting' and not assigned.synthetic
            drafts.update_draft(actor,first.id,d.TaskDraftUpdateInput(expected_revision=assigned.revision,
                main_attachment_id=first.main_attachment_id),db)
            assert tuple(db.execute(text('SELECT id,payload_json,payload_sha256 FROM task_inbox_events LIMIT 3')))==original
            if other_state=='collecting':
                # Explicitly pause the other task; assigning one event does not select between two runnable tasks.
                drafts.update_draft(actor,other.id,d.TaskDraftUpdateInput(expected_revision=other.revision,action='pause'),db)
        await runtime.advance(epoch)
        assert len(provider.calls)==1 and count(database,'task_drafts')==2
        assert len(provider.calls[0].basis.manifest.materials)==2
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('fence',['logout','expiry','peer-revoke','restore','binding','config','epoch'])
def test_queued_reply_rechecks_authority_before_worker_send(world,fence):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from cn_contract.weixin_transport import ProbeError
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];epoch=runtime._epoch;transport=runtime._transport
        await runtime.ingest(epoch,packet(command(1,'销售接待：客户咨询虚构交货纠纷')))
        loop=asyncio.get_running_loop();loop.set_default_executor(ThreadPoolExecutor(max_workers=1))
        started,release=Event(),Event()
        def occupy():
            started.set();assert release.wait(10)
        occupied=loop.run_in_executor(None,occupy)
        while not started.is_set():await asyncio.sleep(.01)
        reply=asyncio.create_task(runtime._reply(epoch,'queued-fixture','独立虚构回复'))
        replacement=None
        try:
            async with asyncio.timeout(5):
                while count(database,'weixin_personal_outbox')!=1:await asyncio.sleep(.01)
            if fence=='peer-revoke':
                from cn_contract.weixin_inbox.personal import revoke_personal_peer
                revoke_personal_peer(actor,runtime._mapping.id,d.WeixinRevokeInput(reason='虚构撤销'),database=database)
            elif fence=='config':
                runtime.native_model._config_version=uuid4()
            elif fence=='epoch':
                runtime._epoch+=1
                replacement=PersonalWeixinTransport(client=httpx.Client(transport=httpx.MockTransport(Wire().handle)))
                replacement.start_qr();replacement.poll_login()
                runtime._transport=replacement
            else:
                with database.session() as db:
                    if fence=='logout':
                        from cn_contract.security import revoke_session
                        revoke_session(actor.session_id,db)
                    elif fence=='expiry':
                        db.execute(text("UPDATE sessions SET expires_at='2000-01-01 00:00:00.000000' WHERE id=:id"),{'id':str(actor.session_id)})
                    elif fence=='restore':
                        db.execute(text("INSERT INTO ops_restore_fences(ref,archive_sha256,manifest_sha256,payload) VALUES('fiction','a','b','{}')"))
                    else:
                        db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),
                            {'id':str(world[2].scope.conversation_id)})
        finally:
            release.set();await occupied
        with pytest.raises(ServiceError):await reply
        assert not [r for r in wire.requests if r.url.path.endswith('/sendmessage')]
        assert not provider.calls
        with pytest.raises(ProbeError):transport.identity()
        if replacement:assert replacement.identity()
        with database.session() as db:
            assert db.scalar(text('SELECT status FROM weixin_personal_outbox'))=='unknown'
        await close(runtime,manager)
        if replacement:transport._client.close()
        if fence=='logout':
            runtime,wire,manager,provider,actor=await setup_runtime(world)
            await runtime.ingest(runtime._epoch,packet(command(1,'销售接待：客户咨询虚构交货纠纷')))
            await runtime._reply(runtime._epoch,'queued-fixture','独立虚构回复')
            assert not [r for r in wire.requests if r.url.path.endswith('/sendmessage')]
            assert count(database,'weixin_personal_outbox')==1
            await close(runtime,manager)
    asyncio.run(scenario())


def test_runtime_has_exact_successor_schema():
    assert storage_schema.CURRENT_VERSION == 'weixin-service-v1'
    from cn_contract.weixin_inbox.personal_runtime import PersonalWeixinRuntime
    assert PersonalWeixinRuntime


@pytest.mark.parametrize('order',['file-first','instruction-first'])
def test_real_attachment_business_and_model_chain_once(world,order):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        file=file_message(wire)
        first,second=(file,command()) if order=='file-first' else (command(),file)
        await runtime.ingest(epoch,packet(first,cursor='one'));await runtime.advance(epoch)
        assert not provider.calls
        await runtime.ingest(epoch,packet(second,cursor='two'));await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert count(database,'assistant_attachments')==1
        assert count(database,'task_drafts')==1
        assert count(database,'weixin_personal_runs')==1
        assert count(database,'assistant_model_outputs')==1
        with database.session() as db:
            from cn_contract.ops.backup import _file_references
            _file_references(db)
            histories=business.history(actor,world[2].scope.conversation_id,db)
            assert histories[0].task_id!=histories[0].contract_draft_id
            assert db.scalar(text("SELECT COUNT(*) FROM task_channel_bindings WHERE channel='synthetic'"))==0
        await runtime.ingest(epoch,packet(first,second,cursor='three'));await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert len([r for r in wire.requests if r.url.path.endswith('/download')])==1
        assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==2
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('workflow,content',[
    ('case','请整理案件材料和时间线'),('court','请准备模拟法庭'),('sales','销售接待：客户咨询虚构交货纠纷')])
def test_four_capabilities_and_grouped_materials(world,workflow,content):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        files=() if workflow=='sales' else (file_message(wire,1,'虚构主文.docx'),file_message(wire,2,'虚构附件.docx'))
        await runtime.ingest(epoch,packet(*files,command(3,content)))
        assert not provider.calls
        await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert provider.calls[0].basis.manifest.workflow==workflow
        assert len(provider.calls[0].basis.manifest.materials)==len(files)
        assert count(database,'task_drafts')==1
        with database.session() as db:
            from cn_contract.ops.backup import _file_references
            _file_references(db)
        await close(runtime,manager)
    asyncio.run(scenario())


def test_rereview_new_task_and_late_material_keep_history(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        await runtime.advance(epoch)
        first=provider.calls[0]
        await runtime.ingest(epoch,packet(command(3,'请重新审查合同，重点看违约条款'),cursor='second'))
        await runtime.advance(epoch)
        assert len(provider.calls)==2
        assert provider.calls[0]==first
        assert provider.calls[1].basis.manifest.question=='请重新审查合同，重点看违约条款'
        assert provider.calls[1].basis.manifest.stable_task_id!=first.basis.manifest.stable_task_id
        await runtime.ingest(epoch,packet(file_message(wire,4,'虚构补充.docx'),cursor='third'))
        await runtime.advance(epoch)
        assert len(provider.calls)==3
        assert len(provider.calls[0].basis.manifest.materials)==1
        assert len(provider.calls[2].basis.manifest.materials)==2
        assert provider.calls[2].basis.manifest.stable_task_id==provider.calls[1].basis.manifest.stable_task_id
        assert provider.calls[2].basis.manifest.conversation_history
        with database.session() as db:
            from cn_contract.ops.backup import _file_references
            _file_references(db)
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('reason',['collect','dirty','ambiguous','main'])
def test_collection_waits_without_losing_desktop_draft(world,reason):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world,automatic=reason!='collect')
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        messages=[file_message(wire),command(3,'请审查合同并模拟法庭' if reason=='ambiguous' else '请审查合同')]
        if reason=='main':messages.insert(1,file_message(wire,2,'虚构另一份.docx'))
        if reason=='dirty':
            with database.session() as db:
                view=service.read_conversation(actor,cid,db)
                service.save_draft(actor,cid,d.AssistantDraftInput(expected_scope=view.scope,
                    expected_composer_revision=view.composer_revision,content='桌面尚未发送的虚构草稿'),db)
        await runtime.ingest(epoch,packet(*messages));await runtime.advance(epoch);await runtime.advance(epoch)
        assert not provider.calls
        assert count(database,'weixin_personal_runs')==0
        assert count(database,'task_drafts')==1
        assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==(0 if reason=='dirty' else 1)
        if reason=='dirty':
            with database.session() as db:
                assert service.read_conversation(actor,cid,db).draft_input=='桌面尚未发送的虚构草稿'
        await close(runtime,manager)
    asyncio.run(scenario())


def test_mixed_poll_records_blocked_neighbors_and_context_is_not_stored(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        await runtime.ingest(epoch,packet(incoming(message_id=8,from_user_id='other-person'),
            file_message(wire),incoming(message_id=9,item_list=[{'type':2}]),command()))
        await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert count(database,'weixin_inbox_descriptors')==4
        assert len([r for r in wire.requests if r.url.path.endswith('/download')])==1
        with database.session() as db:
            for table in ('weixin_inbox_descriptors','weixin_personal_runs','weixin_personal_outbox',
                    'assistant_runs','assistant_model_attempts','task_inbox_events'):
                serialized=str(tuple(db.execute(text('SELECT * FROM '+table))))
                for secret in ('private-context','private-token','fictional-query','aes_key'):
                    assert secret not in serialized
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('automatic',[False,True])
@pytest.mark.parametrize('item_id',[None,'','fictional:item-id'])
def test_ordinary_message_shape_reaches_same_chat_once_without_reviving_blocked_history(world,monkeypatch,automatic,item_id):
    from cn_contract import weixin_offline as decoder
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world,automatic=automatic)
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        def ordinary(number):
            message=command(number,'销售接待：客户咨询独立虚构交货纠纷')
            message.update(seq=number,client_id='fictional-client',session_id='fictional-session',
                create_time_ms=0,update_time_ms=1,delete_time_ms=0,group_id='',
                root_id=0,parent_id=18446744073709551615)
            message['item_list'][0].update(create_time_ms=0,update_time_ms=1,is_completed=True,
                msg_id=str(number) if item_id is None else item_id,button_item_list=[],at_bot_username_list=[])
            return message
        old=ordinary(101);fresh=ordinary(102)
        try:
            # Recreate the old strict allowlist solely to seed an immutable historical refusal.
            with monkeypatch.context() as historical:
                historical.setattr(decoder,'_MESSAGE',decoder._MESSAGE-{'root_id','parent_id'})
                assert not await runtime.ingest(epoch,packet(old,cursor='historical'))
            with database.session() as db:
                historical_poll=tuple(db.execute(text('SELECT * FROM weixin_poll_receipts')))
                historical_descriptor=tuple(db.execute(text('SELECT * FROM weixin_inbox_descriptors')))
                assert db.scalar(text('SELECT reason FROM weixin_inbox_descriptors'))=='message_unsupported'
                old_id=db.scalar(text('SELECT id FROM weixin_inbox_descriptors'))
            assert count(database,'task_inbox_events')==0
            assert await runtime.ingest(epoch,packet(old,fresh,fresh,cursor='current'))
            with database.session() as db:
                rows=db.execute(text('''SELECT status,reason,prior_descriptor_id,payload_json
                    FROM weixin_inbox_descriptors ORDER BY rowid''')).all()
                assert [(row.status,row.reason) for row in rows]==[
                    ('blocked','message_unsupported'),('blocked','previously_blocked'),
                    ('accepted_pending_dispatch',None),('duplicate','replayed')]
                assert rows[1].prior_descriptor_id==old_id and rows[1].payload_json is None
                payload=d.TaskInboxEventInput.model_validate_json(rows[2].payload_json)
                assert payload.text=='销售接待：客户咨询独立虚构交货纠纷'
                assert payload.reply_to_event_id is None and payload.task_id is None
                assert payload.start_new is False
                draft=drafts.list_drafts(actor,cid,db).items[0]
                assert not draft.synthetic and len(draft.events)==1
                assert draft.events[0].event_id==payload.event_id
            await runtime.advance(epoch)
            assert len(provider.calls)==int(automatic)
            if automatic:
                assert provider.calls[0].basis.manifest.workflow=='sales'
            assert not await runtime.ingest(epoch,packet(old,fresh,cursor='replayed'))
            await runtime.advance(epoch)
            assert len(provider.calls)==int(automatic)
            assert count(database,'task_inbox_events')==count(database,'task_drafts')==1
            assert count(database,'weixin_dispatch_receipts')==1
            assert count(database,'assistant_model_outputs')==count(database,'weixin_personal_runs')==int(automatic)
            with database.session() as db:
                assert tuple(db.execute(text('SELECT * FROM weixin_poll_receipts ORDER BY rowid LIMIT 1')))==historical_poll
                assert tuple(db.execute(text('SELECT * FROM weixin_inbox_descriptors ORDER BY rowid LIMIT 1')))==historical_descriptor
                history=business.history(actor,cid,db)
                assert len(history)==int(automatic)
                if automatic:
                    assert history[0].scope.conversation_id==cid
                    assert db.scalar(text('SELECT business_run_id FROM weixin_personal_runs WHERE draft_id=:id'),
                        {'id':str(draft.id)})==str(history[0].run_id)
                from cn_contract.ops.backup import _file_references
                _file_references(db)
            assert not [r for r in wire.requests if r.url.path.endswith('/download')]
            assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==1
            if not automatic:
                assert '材料和指令已收集' in next(r.content.decode() for r in wire.requests
                    if r.url.path.endswith('/sendmessage'))
        finally:
            await close(runtime,manager)
    asyncio.run(scenario())


def test_late_material_waits_until_running_snapshot_finishes(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        provider.hold=asyncio.Event()
        running=asyncio.create_task(runtime.advance(epoch))
        async with asyncio.timeout(5):
            while not provider.calls:await asyncio.sleep(.01)
        frozen=provider.calls[0]
        arriving=asyncio.create_task(runtime.ingest(epoch,packet(file_message(wire,4,'虚构补充.docx'),cursor='later')))
        await asyncio.sleep(.3)
        assert not arriving.done() and count(database,'assistant_attachments')==1
        provider.hold.set()
        await running;await arriving
        await runtime.advance(epoch)
        assert len(provider.calls)==2 and provider.calls[0]==frozen
        assert len(provider.calls[0].basis.manifest.materials)==1
        assert len(provider.calls[1].basis.manifest.materials)==2
        await close(runtime,manager)
    asyncio.run(scenario())


def test_notice_source_remains_its_draft_when_old_context_is_replayed(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        original=command(2,'销售接待：客户咨询虚构交货纠纷')
        await runtime.ingest(epoch,packet(original));await runtime.advance(epoch)
        await runtime.ingest(epoch,packet(command(3,'新建任务，请审查合同'),cursor='new'))
        await runtime.ingest(epoch,packet(original,cursor='replay'))
        await runtime.advance(epoch)
        with database.session() as db:
            from cn_contract.ops.backup import _file_references
            _file_references(db)
        await close(runtime,manager)
    asyncio.run(scenario())


def test_shared_draft_link_uses_personal_source_even_after_desktop_event(world):
    from cn_contract.task_drafts import service as drafts
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        with database.session() as db:
            binding=drafts.create_binding(actor,cid,db)
            drafts.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
                events=(d.TaskInboxEventInput(event_id='fictional-desktop',text='补充：请重点审查交付条款'),)),db)
        await runtime.advance(epoch)
        assert len(provider.calls)==1
        with database.session() as db:
            from cn_contract.ops.backup import _file_references
            _file_references(db)
            assert db.scalar(text('''SELECT b.channel FROM weixin_personal_runs r JOIN task_inbox_events e
                ON e.id=r.source_event_id JOIN task_channel_bindings b ON b.id=e.binding_id'''))=='weixin_personal'
        await close(runtime,manager)
    asyncio.run(scenario())


def test_unknown_send_is_claimed_before_network_and_never_retried(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];epoch=runtime._epoch
        old=wire.handle
        def handle(request):
            if request.url.path.endswith('/sendmessage'):
                assert count(database,'weixin_personal_outbox')==1
                return httpx.Response(200,json={})
            return old(request)
        runtime._transport._client.close()
        runtime._transport._client=httpx.Client(transport=httpx.MockTransport(handle))
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        await runtime.advance(epoch)
        with database.session() as db:
            assert db.scalar(text('SELECT status FROM weixin_personal_outbox'))=='unknown'
        await runtime.advance(epoch)
        assert count(database,'weixin_personal_outbox')==1
        assert len(provider.calls)==1
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('fence',['stop','config','model-revoke','logout','peer-revoke','restore','binding'])
def test_authority_changes_fence_future_io(world,fence):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0];transport=runtime._transport
        if fence=='stop':runtime.disable()
        elif fence=='config':runtime.native_model.disable()
        elif fence=='model-revoke':runtime.native_model.revoke({'session_token':runtime._value.session_token})
        elif fence=='peer-revoke':
            from cn_contract.weixin_inbox.personal import revoke_personal_peer
            revoke_personal_peer(actor,runtime._mapping.id,d.WeixinRevokeInput(reason='独立虚构撤销'),database=database)
        else:
            with database.session() as db:
                if fence=='logout':
                    from cn_contract.security import revoke_session
                    revoke_session(actor.session_id,db)
                elif fence=='restore':
                    db.execute(text("INSERT INTO ops_restore_fences(ref,archive_sha256,manifest_sha256,payload) VALUES('fiction','a','b','{}')"))
                else:
                    db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),
                        {'id':str(world[2].scope.conversation_id)})
        before=len(wire.requests)
        with pytest.raises(ServiceError):
            await runtime._io(epoch,transport.poll_updates,'')
        assert len(wire.requests)==before
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('operation',['stop','peer-revoke','config'])
def test_late_model_completion_cannot_publish_or_send(world,operation):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        provider.hold=asyncio.Event()
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        running=asyncio.create_task(runtime.advance(epoch))
        async with asyncio.timeout(5):
            while not provider.calls:await asyncio.sleep(.01)
        if operation=='stop':runtime.disable()
        elif operation=='config':runtime.native_model.disable()
        else:
            from cn_contract.weixin_inbox.personal import revoke_personal_peer
            revoke_personal_peer(actor,runtime._mapping.id,d.WeixinRevokeInput(reason='虚构执行中撤销'),database=database)
        provider.hold.set()
        await asyncio.gather(running,return_exceptions=True)
        async with asyncio.timeout(5):
            while manager.active_count:await asyncio.sleep(.01)
        assert count(database,'assistant_model_outputs')==0
        assert not [r for r in wire.requests if r.url.path.endswith('/sendmessage')]
        await close(runtime,manager)
    asyncio.run(scenario())


def test_other_login_session_revoke_does_not_disconnect_fixed_owner(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch
        with world[0].session() as db:
            other_token,_=login('lawyer','fixture123',db)
        assert runtime.native_model.revoke({'session_token':other_token})=={'status':'revoked'}
        assert runtime._epoch==epoch
        assert runtime.status(actor,world[2].scope.conversation_id).state=='connected'
        await runtime.ingest(epoch,packet(command(1,'销售接待：虚构咨询')))
        await runtime.advance(epoch)
        assert len(provider.calls)==1
        await close(runtime,manager)
    asyncio.run(scenario())


def test_live_worker_start_ack_is_immediate_and_bad_document_pauses_once(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        database=world[0];old=runtime._value.model_dump(mode='json')
        runtime.disable()
        wire=Wire();message=file_message(wire)
        wire.download=b'not a valid cipher or document'
        wire.updates=packet(message)
        client=httpx.Client(transport=httpx.MockTransport(wire.handle))
        runtime.client_factory=lambda:client
        start=asyncio.get_running_loop().time()
        assert runtime.start(old)=={'status':'started'}
        assert asyncio.get_running_loop().time()-start<1
        assert not wire.requests
        async with asyncio.timeout(6):
            while runtime._status.state!='paused':await asyncio.sleep(.05)
        status=runtime.status(actor,world[2].scope.conversation_id)
        assert status.state=='paused' and status.qr_url is None
        assert count(database,'assistant_attachments')==0
        assert len([r for r in wire.requests if r.url.path.endswith('/download')])==1
        with database.session() as db:
            assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts'))==0
        assert not provider.calls and runtime._value is None
        await close(runtime,manager)
    asyncio.run(scenario())


def test_status_same_session_and_chat_and_no_http_start(world):
    from fastapi import FastAPI
    from cn_contract.weixin_inbox.personal_runtime import attach_runtime
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        cid=world[2].scope.conversation_id;database=world[0]
        runtime._status=runtime._status.model_copy(update={'state':'waiting_scan','qr_url':'https://ilinkai.weixin.qq.com/qr/fiction'})
        with database.session() as db:
            token,_=login('lawyer','fixture123',db);another=authenticate(token,db)
            other=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        assert runtime.status(actor,cid).qr_url
        assert runtime.status(another,cid).qr_url is None
        assert runtime.status(actor,other.scope.conversation_id).qr_url is None
        app=FastAPI();attach_runtime(app,runtime)
        routes=[r for r in app.routes if 'personal-weixin' in r.path]
        assert len(routes)==4 and all(route.methods=={'GET'} for route in routes)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',
                cookies={'qx_session':runtime._value.session_token}) as client:
            result=await client.get(f'/api/assistant/conversations/{cid}/personal-weixin/status')
            assert result.status_code==200 and result.json()['qr_url']
            assert (await client.post(f'/api/assistant/conversations/{cid}/personal-weixin/start',json={})).status_code==404
        await close(runtime,manager)
    asyncio.run(scenario())


def test_runtime_history_survives_backup_but_restore_has_no_authority(world,tmp_path):
    from pathlib import Path
    from cn_contract.ops import backup,workspace_backup
    from cn_contract.persistence import Database
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        await runtime.ingest(runtime._epoch,packet(file_message(wire),command()))
        await runtime.advance(runtime._epoch)
        with world[0].session() as db:
            before={table:tuple(db.execute(text('SELECT * FROM '+table))) for table in
                ('weixin_personal_runs','weixin_personal_outbox','weixin_inbox_descriptors','assistant_model_outputs')}
        await close(runtime,manager)
        return before
    before=asyncio.run(scenario());database=world[0]
    root=Path(database.engine.url.database).parent;archive=tmp_path/'personal.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored',PASSPHRASE)
    target=Path(restored['restored_root']);db2=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
    try:
        with db2.session() as db:
            backup._file_references(db)
            for table,rows in before.items():assert tuple(db.execute(text('SELECT * FROM '+table)))==rows
            token,_=login('lawyer','fixture123',db)
        async def blocked():
            registry=MainModelRegistry();native=NativeModelControl(db2,registry)
            runtime=PersonalWeixinRuntime(db2,native,GenerationTasks(db2,registry),
                client_factory=lambda:pytest.fail('restored database must not connect'))
            with pytest.raises(ServiceError):
                runtime.start({'session_token':token,'expected_scope':world[2].scope.model_dump(mode='json'),'automatic_policy':None})
        asyncio.run(blocked())
    finally:db2.engine.dispose()


def test_exact_successor_migration_preserves_every_predecessor_object(tmp_path):
    from cn_contract import schema_migrations
    from tests.integration.test_assistant_judge_schema import old_db
    db=old_db(tmp_path/'old.db','weixin-personal-v1',True)
    try:
        before=schema_migrations.database_rows(db)
        assert schema_migrations.upgrade_database(db)=='weixin-service-v1'
        after=schema_migrations.database_rows(db)
        additions={row[2] for row in storage_schema.schema_rows('weixin-service-v1',native=True)}-{row[2] for row in before}
        assert [row for row in after if row[2] not in additions]==before
        assert schema_migrations.upgrade_database(db)=='weixin-service-v1'
    finally:db.close()


def test_pdf_real_parser_and_personal_manifest_never_enters_mock_bridge(world):
    from pathlib import Path
    from cn_contract.task_drafts import service as drafts, mock_policy
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world,automatic=False)
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        raw=(Path(__file__).parents[1]/'fixtures/task-pdf-v1/native-sales.pdf').read_bytes()
        pad=padding.PKCS7(128).padder();data=pad.update(raw)+pad.finalize()
        encrypt=Cipher(algorithms.AES(KEY),modes.ECB()).encryptor();wire.download=encrypt.update(data)+encrypt.finalize()
        msg=incoming(message_id=1,item_list=[{'type':4,'file_item':{'file_name':'独立虚构合同.pdf',
            'len':str(len(raw)),'media':{'aes_key':base64.b64encode(KEY).decode(),'encrypt_query_param':'fictional-pdf'}}}])
        database._assistant_synthetic_hashes=frozenset({hashlib.sha256(raw).hexdigest()})
        await runtime.ingest(epoch,packet(msg,command()))
        with database.session() as db:
            draft=drafts.list_drafts(actor,cid,db).items[0]
            execution=drafts.freeze_draft(actor,draft.id,d.TaskFreezeInput(expected_revision=draft.revision,
                manifest_sha256=draft.manifest_sha256),db)
            assert execution.manifest.synthetic is False
            assert execution.manifest.events[0].media[0].reading_status=='readable'
            with pytest.raises(ServiceError,match='blocked'):
                mock_policy.sources(execution,actor,db)
            from cn_contract.ops.backup import _file_references
            _file_references(db)
        await close(runtime,manager)
    asyncio.run(scenario())


def test_following_case_and_court_reuse_same_source_materials(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        await runtime.advance(epoch)
        for number,content in [(3,'请用已有材料整理案件'),(4,'请用这些材料模拟法庭')]:
            await runtime.ingest(epoch,packet(command(number,content),cursor=str(number)))
            await runtime.advance(epoch)
        assert [request.basis.manifest.workflow for request in provider.calls]==['contract','case','court']
        assert len({request.basis.manifest.materials[0].attachment_id for request in provider.calls})==1
        await close(runtime,manager)
    asyncio.run(scenario())


def test_stop_after_download_starts_does_not_store_late_original(world):
    from threading import Event
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        entered,release=Event(),Event();old=wire.handle
        def handle(request):
            if request.url.path.endswith('/download'):
                entered.set();assert release.wait(5)
            return old(request)
        runtime._transport._client.close()
        runtime._transport._client=httpx.Client(transport=httpx.MockTransport(handle))
        pending=asyncio.create_task(runtime.ingest(epoch,packet(file_message(wire),command())))
        async with asyncio.timeout(5):
            while not entered.is_set():await asyncio.sleep(.01)
        runtime.disable();release.set()
        with pytest.raises(ServiceError):await pending
        assert count(database,'assistant_attachments')==0
        assert count(database,'weixin_poll_receipts')==0
        assert not provider.calls
        await manager.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('boundary',['before-cursor','after-cursor'])
def test_interrupted_intake_recovers_original_and_dispatch_once(world,monkeypatch,boundary):
    from cn_contract.weixin_inbox import personal
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        raw=packet(file_message(wire),command())
        name='record_personal_poll' if boundary=='before-cursor' else 'dispatch_personal_descriptor'
        original=getattr(personal,name)
        def crash(*args,**kwargs):raise ServiceError('STATE_CONFLICT',409)
        monkeypatch.setattr(personal,name,crash)
        with pytest.raises(ServiceError):await runtime.ingest(epoch,raw)
        assert count(database,'assistant_attachments')==1
        assert count(database,'assistant_attachment_parses')==1
        with database.session() as db:
            assert db.scalar(text('SELECT checkpoint_revision FROM weixin_accounts'))==(0 if boundary=='before-cursor' else 1)
        monkeypatch.setattr(personal,name,original)
        await runtime.ingest(epoch,raw);await runtime.advance(epoch)
        assert count(database,'assistant_attachments')==1
        assert count(database,'assistant_attachment_parses')==1
        assert count(database,'task_drafts')==1
        assert len(provider.calls)==1
        assert len([r for r in wire.requests if r.url.path.endswith('/download')])==1
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('table',['weixin_personal_runs','weixin_personal_outbox'])
def test_runtime_integrity_rejects_mutated_association_or_reply_hash(world,table):
    from cn_contract.weixin_inbox.runtime_records import validate_records
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        await runtime.ingest(runtime._epoch,packet(file_message(wire),command()))
        await runtime.advance(runtime._epoch)
        await close(runtime,manager)
        with world[0].session() as db:
            validate_records(db)
            trigger='weixin_personal_runs_no_update' if table.endswith('runs') else 'weixin_personal_outbox_update'
            db.execute(text('DROP TRIGGER '+trigger))
            db.execute(text('UPDATE '+table+(' SET draft_revision=draft_revision+1' if table.endswith('runs') else " SET payload_sha256='"+'f'*64+"'")))
            with pytest.raises(ValueError,match='PERSONAL_RUNTIME_INTEGRITY'):validate_records(db)
    asyncio.run(scenario())


def test_reconnection_replays_existing_outcome_without_unknown_resend(world):
    async def scenario():
        first,wire,manager,provider,actor=await setup_runtime(world)
        raw=packet(file_message(wire),command())
        wire.send={}
        await first.ingest(first._epoch,raw);await first.advance(first._epoch)
        with world[0].session() as db:
            account=db.scalar(text('SELECT id FROM weixin_accounts'))
            claim=tuple(db.execute(text('SELECT * FROM weixin_personal_outbox')).one())
        await close(first,manager)
        second,wire2,manager2,provider2,actor2=await setup_runtime(world)
        assert str(second._account.id)==account
        await second.ingest(second._epoch,raw);await second.advance(second._epoch)
        assert not provider2.calls
        assert not [r for r in wire2.requests if r.url.path.endswith(('/sendmessage','/download'))]
        with world[0].session() as db:
            assert tuple(db.execute(text('SELECT * FROM weixin_personal_outbox')).one())==claim
        await close(second,manager2)
    asyncio.run(scenario())


@pytest.mark.parametrize('reply_state',['submitted','unknown'])
def test_cancelled_replied_history_allows_empty_polls_reconnect_and_new_task(world,reply_state):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0];cid=world[2].scope.conversation_id
        if reply_state=='unknown':wire.send={}
        raw=packet(file_message(wire),command())
        await runtime.ingest(epoch,raw);await runtime.advance(epoch)
        with database.session() as db:
            link=db.execute(text('SELECT * FROM weixin_personal_runs')).mappings().one()
            original_claim=tuple(db.execute(text('SELECT * FROM weixin_personal_outbox')).one())
            assert db.scalar(text('SELECT status FROM weixin_personal_outbox'))==reply_state
            service.cancel_run(actor,link['business_run_id'],d.AssistantCancelInput(request_id=uuid4()),db)
        sends=len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])
        for index in range(3):
            await runtime.ingest(epoch,packet(cursor='idle-'+str(index)))
            await runtime.advance(epoch)
            assert runtime.status(actor,cid).state=='connected'
        assert len(provider.calls)==1
        assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==sends
        await close(runtime,manager)
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch
        await runtime.ingest(epoch,raw)
        for _ in range(3):await runtime.advance(epoch)
        assert runtime.status(actor,cid).state=='connected' and not provider.calls
        assert not [r for r in wire.requests if r.url.path.endswith('/sendmessage')]
        await runtime.ingest(epoch,packet(command(3,'新建任务，请整理案件'),cursor='new-task'))
        await runtime.advance(epoch)
        assert len(provider.calls)==1
        assert len([r for r in wire.requests if r.url.path.endswith('/sendmessage')])==1
        with database.session() as db:
            assert tuple(db.execute(text('SELECT * FROM weixin_personal_outbox WHERE client_id=:id'),
                {'id':original_claim[0]}).one())==original_claim
            from cn_contract.ops.backup import _file_references
            _file_references(db)
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('parent_state',['cancelled','blocked'])
def test_cancelled_business_before_attempt_never_calls_model_or_sends(world,monkeypatch,parent_state):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        execute=runtime._execute
        async def interrupted(*args):raise RuntimeError('fictional crash after durable business receipt')
        monkeypatch.setattr(runtime,'_execute',interrupted)
        with pytest.raises(RuntimeError):await runtime.advance(epoch)
        monkeypatch.setattr(runtime,'_execute',execute)
        with database.session() as db:
            parent=db.scalar(text('SELECT business_run_id FROM weixin_personal_runs'))
            if parent_state=='cancelled':
                service.cancel_run(actor,parent,d.AssistantCancelInput(request_id=uuid4()),db)
            else:
                db.execute(text("UPDATE assistant_runs SET state='blocked' WHERE id=:id"),{'id':parent})
        for _ in range(3):
            if parent_state=='cancelled':await runtime.advance(epoch)
            else:
                with pytest.raises(ServiceError) as caught:await runtime.advance(epoch)
                assert caught.value.code=='VERSION_CONFLICT'
        assert not provider.calls and count(database,'assistant_model_attempts')==0
        assert count(database,'weixin_personal_outbox')==0
        assert runtime.status(actor,world[2].scope.conversation_id).state=='connected'
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('cancel_target',['business','model'])
def test_single_cancel_during_model_stops_output_and_reply_without_disconnect(world,cancel_target):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch;database=world[0]
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        provider.hold=asyncio.Event()
        running=asyncio.create_task(runtime.advance(epoch))
        async with asyncio.timeout(5):
            while not provider.calls:await asyncio.sleep(.01)
        with database.session() as db:
            identifier=(db.scalar(text('SELECT business_run_id FROM weixin_personal_runs'))
                if cancel_target=='business' else runtime._active_run)
            service.cancel_run(actor,identifier,d.AssistantCancelInput(request_id=uuid4()),db)
        provider.hold.set()
        await running
        async with asyncio.timeout(5):
            while manager.active_count:await asyncio.sleep(.01)
        for _ in range(3):await runtime.advance(epoch)
        assert len(provider.calls)==1 and count(database,'assistant_model_outputs')==0
        assert count(database,'weixin_personal_outbox')==0
        assert runtime._active_run is None
        assert runtime.status(actor,world[2].scope.conversation_id).state=='connected'
        await close(runtime,manager)
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',[ServiceError('CROSS_MATTER_DENIED',403),ValueError('fictional corrupt attempt')])
def test_replied_history_does_not_swallow_permission_or_integrity_errors(world,monkeypatch,failure):
    from cn_contract.assistant.providers import attempts
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world)
        epoch=runtime._epoch
        await runtime.ingest(epoch,packet(file_message(wire),command()))
        await runtime.advance(epoch)
        before=len(wire.requests)
        def invalid_attempt(*args):raise failure
        monkeypatch.setattr(attempts,'read_attempt',invalid_attempt)
        with pytest.raises(type(failure)) as caught:await runtime.advance(epoch)
        assert caught.value is failure
        assert len(wire.requests)==before and len(provider.calls)==1
        await close(runtime,manager)
    asyncio.run(scenario())
