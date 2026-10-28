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
    doc=Document();doc.add_paragraph('独立虚构合同：甲乙双方约定2026年1月3日交货，价款30000元。')
    stream=BytesIO();doc.save(stream);data=stream.getvalue()
    pad=padding.PKCS7(128).padder();padded=pad.update(data)+pad.finalize()
    encrypt=Cipher(algorithms.AES(KEY),modes.ECB()).encryptor()
    wire.download=encrypt.update(padded)+encrypt.finalize()
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


def count(database,table):
    with database.session() as db:
        return db.scalar(text('SELECT COUNT(*) FROM '+table))


def test_runtime_has_exact_successor_schema():
    assert storage_schema.CURRENT_VERSION == 'weixin-personal-runtime-v1'
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
        assert len(routes)==1 and routes[0].methods=={'GET'}
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
        assert schema_migrations.upgrade_database(db)=='weixin-personal-runtime-v1'
        after=schema_migrations.database_rows(db)
        assert [row for row in after if row[2] not in ('weixin_personal_runs','weixin_personal_outbox')]==before
        assert schema_migrations.upgrade_database(db)=='weixin-personal-runtime-v1'
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
