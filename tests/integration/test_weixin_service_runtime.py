"""Synthetic service runtime through actual attachment/business/model ledgers."""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.weixin_inbox.service_runtime import ServiceWeixinRuntime
from cn_contract.weixin_transport import PersonalWeixinTransport
from tests.integration.test_weixin_personal_runtime import setup_runtime,close,packet,command,file_message,count
from tests.integration.test_assistant_generation import world


async def setup(world,automatic=True):
    old,wire,manager,provider,actor=await setup_runtime(world,automatic=automatic)
    token=old._value.session_token;policy=old._value.automatic_policy
    client=old._transport._client
    old.disable()
    client.close()
    import httpx
    from tests.unit.test_weixin_transport import Wire
    wire=Wire();client=httpx.Client(transport=httpx.MockTransport(wire.handle))
    runtime=ServiceWeixinRuntime(world[0],old.native_model,manager,client_factory=lambda:client)
    runtime.start({'session_token':token,'workspace_id':str(world[2].scope.workspace_id),
        'automatic_policy':policy.model_dump(mode='json') if policy else None})
    runtime._task.cancel();await asyncio.gather(runtime._task,return_exceptions=True);runtime._task=None
    runtime._transport=PersonalWeixinTransport(client=client)
    runtime._transport.start_qr();runtime._transport.poll_login();runtime._bind(runtime._epoch)
    return runtime,wire,manager,provider,actor


def later():return datetime.now(timezone.utc)+timedelta(seconds=6)


def test_service_two_texts_two_files_wait_dedup_and_actual_execution(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            await runtime.ingest(epoch,packet(command(1,'新事项：甲租赁事项，请审查合同'),command(2,'我是甲方'),
                file_message(wire,3,'虚构主合同.docx'),file_message(wire,4,'虚构补充.docx')))
            await runtime.advance(epoch)
            assert provider.calls==[]
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==1
            assert count(world[0],'weixin_service_runs')==1
            assert count(world[0],'weixin_service_outbox')==1
            await runtime.ingest(epoch,packet(command(1,'新事项：甲租赁事项，请审查合同'),command(2,'我是甲方'),
                file_message(wire,3,'虚构主合同.docx'),file_message(wire,4,'虚构补充.docx')))
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==1
            from cn_contract.weixin_inbox.service_records import validate_records
            with world[0].session() as db:
                validate_records(db)
                from cn_contract.ops.backup import _file_references
                _file_references(db)
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_service_global_connection_hold_files_and_archive_other_chat(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            await runtime.ingest(epoch,packet(command(1,'新事项：甲合同审查'),command(2,'还有附件，稍等'),file_message(wire,3)))
            await runtime.advance(epoch,now=later())
            assert not provider.calls
            with world[0].session() as db:
                view=service.read_conversation(actor,world[2].scope.conversation_id,db)
                service.archive_conversation(actor,view.scope.conversation_id,d.AssistantArchiveInput(expected_scope=view.scope,
                    expected_composer_revision=view.composer_revision),db,require_disconnected=runtime.require_disconnected)
            assert runtime.status(actor).state=='connected'
            await runtime.ingest(epoch,packet(command(4,'继续'),cursor='two'))
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==1
        finally:await close(runtime,manager)
    asyncio.run(scenario())



def test_two_matters_clarification_routes_original_batch_and_capability_change(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            for i,title in enumerate(('甲事项','乙事项')):
                await runtime.ingest(epoch,packet(command(i*2+1,'新事项：'+title+'，请整理案件'),file_message(wire,i*2+2),cursor=title))
                await runtime.advance(epoch,now=later())
            assert len(provider.calls)==2
            with world[0].session() as db:
                destinations=list(db.execute(text('SELECT conversation_id FROM weixin_service_batches ORDER BY rowid')).scalars())
            assert len(set(destinations))==2
            await runtime.ingest(epoch,packet(command(5,'继续整理这个案件'),file_message(wire,6,'虚构补件.docx'),cursor='ambiguous'))
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==2
            with world[0].session() as db:
                pending=dict(db.execute(text("SELECT * FROM weixin_service_batches WHERE state='clarify'")).mappings().one())
            await runtime.ingest(epoch,packet(command(7,destinations[0]+'，庭审准备'),cursor='answer'))
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==3
            with world[0].session() as db:
                row=db.execute(text('SELECT * FROM weixin_service_batches WHERE id=:id'),{'id':pending['id']}).mappings().one()
                assert row['conversation_id']==destinations[0]
                assert row['workflow']=='court'
                assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_batch_events WHERE batch_id=:id'),{'id':pending['id']})==3
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_files_first_then_instruction_and_main_role_answer_preserve_originals(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            await runtime.ingest(epoch,packet(file_message(wire,1,'虚构一.docx'),file_message(wire,2,'虚构二.docx')))
            await runtime.advance(epoch,now=later())
            assert not provider.calls
            assert count(world[0],'weixin_service_batches')==1
            await runtime.ingest(epoch,packet(command(3,'新事项：请审查合同'),cursor='instruction'))
            await runtime.advance(epoch,now=later())
            assert not provider.calls
            await runtime.ingest(epoch,packet(command(4,'虚构一.docx是主合同'),cursor='answer'))
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==1
            assert count(world[0],'weixin_service_batches')==1
            assert count(world[0],'weixin_service_media')==2
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_inflight_late_material_keeps_old_scope_and_reply_source(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            await runtime.ingest(epoch,packet(command(1,'新事项：请整理案件'),file_message(wire,2)))
            provider.hold=asyncio.Event()
            running=asyncio.create_task(runtime.advance(epoch,now=later()))
            async with asyncio.timeout(10):
                while not provider.calls:await asyncio.sleep(.01)
            first=provider.calls[0]
            await runtime.ingest(epoch,packet(command(3,'继续补充材料'),file_message(wire,4,'虚构补件.docx'),cursor='late'))
            assert provider.calls[0]==first
            provider.hold.set();await running
            await runtime.advance(epoch,now=later())
            assert len(provider.calls)==2
            with world[0].session() as db:
                runs=list(db.execute(text('SELECT * FROM weixin_service_runs ORDER BY rowid')).mappings())
                replies=list(db.execute(text("SELECT * FROM weixin_service_outbox WHERE result_key LIKE 'model:%' ORDER BY rowid")).mappings())
                assert len(runs)==len(replies)==2
                assert replies[0]['source_event_id']==runs[0]['source_event_id']
                assert replies[1]['source_event_id']==runs[1]['source_event_id']
                assert runs[0]['source_event_id']!=runs[1]['source_event_id']
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_greeting_and_logout_never_run_and_epoch_blocks_send(world):
    from cn_contract.security import ServiceError
    import pytest
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            await runtime.ingest(epoch,packet(command(1,'测试')))
            await runtime.advance(epoch,now=later())
            assert not provider.calls
            assert count(world[0],'weixin_service_runs')==0
            assert count(world[0],'weixin_service_outbox')==1
            runtime.disable()
            called=[]
            with pytest.raises(ServiceError):await runtime._io(epoch,lambda:called.append(True))
            assert called==[]
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_service_restart_unassigned_and_unknown_outbox_survive_backup(world,tmp_path):
    from pathlib import Path
    from cn_contract.ops import backup,workspace_backup
    from cn_contract.persistence import Database
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    from cn_contract.security import login
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        await runtime.ingest(runtime._epoch,packet(file_message(wire,1)))
        await runtime.advance(runtime._epoch,now=later())
        assert not provider.calls
        with world[0].session() as db:
            before={name:tuple(db.execute(text('SELECT * FROM '+name))) for name in
                ('weixin_service_connections','weixin_service_polls','weixin_service_events','weixin_service_media','weixin_service_batches',
                 'weixin_service_batch_events','weixin_service_outbox')}
        await close(runtime,manager)
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            with world[0].session() as db:
                assert db.scalar(text("SELECT COUNT(*) FROM weixin_service_batches WHERE state='waiting'"))==1
            await runtime.ingest(runtime._epoch,packet(command(2,'新事项：请审查合同'),cursor='two'))
            await runtime.advance(runtime._epoch,now=later())
            assert len(provider.calls)==1
            with world[0].session() as db:
                before={name:tuple(db.execute(text('SELECT * FROM '+name))) for name in
                    ('weixin_service_connections','weixin_service_polls','weixin_service_events','weixin_service_media','weixin_service_batches',
                     'weixin_service_batch_events','weixin_service_outbox','weixin_service_runs')}
        finally:await close(runtime,manager)
        return before
    before=asyncio.run(scenario());database=world[0]
    root=Path(database.engine.url.database).parent;archive=tmp_path/'service.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored-service',PASSPHRASE)
    target=Path(restored['restored_root']);db2=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',database.settings,initialize_schema=False)
    try:
        with db2.session() as db:
            backup._file_references(db)
            for name,rows in before.items():assert tuple(db.execute(text('SELECT * FROM '+name)))==rows
            token,_=login('lawyer','fixture123',db)
        async def blocked():
            from cn_contract.assistant.native_model_control import NativeModelControl
            from cn_contract.assistant.providers.registry import MainModelRegistry
            from cn_contract.assistant.task_manager import GenerationTasks
            from cn_contract.security import ServiceError
            import pytest
            registry=MainModelRegistry();native=NativeModelControl(db2,registry)
            runtime=ServiceWeixinRuntime(db2,native,GenerationTasks(db2,registry),client_factory=lambda:pytest.fail('no restored network'))
            with pytest.raises(ServiceError):runtime.start({'session_token':token,'workspace_id':str(world[2].scope.workspace_id)})
        asyncio.run(blocked())
    finally:db2.engine.dispose()


def test_service_new_schema_preserves_all_81_old_tables_and_objects(tmp_path):
    from tests.integration.test_assistant_judge_schema import old_db
    from cn_contract import storage_schema,schema_migrations
    db=old_db(tmp_path/'old81.db','weixin-personal-runtime-v1',True)
    try:
        before=schema_migrations.database_rows(db)
        assert len([r for r in before if r[0]=='table'])==81
        assert schema_migrations.upgrade_database(db)=='weixin-service-v1'
        after=schema_migrations.database_rows(db)
        assert len([r for r in after if r[0]=='table'])==90
        old_names={r[1] for r in before}
        assert [r for r in after if r[1] in old_names]==before
        assert schema_migrations.upgrade_database(db)=='weixin-service-v1'
    finally:db.close()


def test_three_large_unassigned_originals_survive_desktop_backup(world,tmp_path):
    import hashlib
    from pathlib import Path
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
    from cn_contract.ops import backup,workspace_backup
    from cn_contract.persistence import Database
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    from tests.unit.test_weixin_transport import KEY
    data=b'F'*(20*1024**2)
    pad=padding.PKCS7(128).padder();padded=pad.update(data)+pad.finalize()
    encrypt=Cipher(algorithms.AES(KEY),modes.ECB()).encryptor()
    encrypted=encrypt.update(padded)+encrypt.finalize()
    async def receive():
        runtime,wire,manager,provider,actor=await setup(world,automatic=False)
        try:
            wire.fixture_file=(data,encrypted)
            await runtime.ingest(runtime._epoch,packet(*(file_message(wire,i,'fictional-'+str(i)+'.pdf') for i in range(1,4))))
            assert not provider.calls
            with world[0].session() as db:
                assert db.scalar(text('SELECT SUM(length(data)) FROM weixin_service_media'))==3*len(data)
                import pytest
                with pytest.raises(ValueError,match='SERVICE_RECORDS_NOT_ALLOWED'):
                    from cn_contract.weixin_inbox.service_records import validate_records
                    validate_records(db,allowed=False)
        finally:await close(runtime,manager)
    asyncio.run(receive())
    root=Path(world[0].engine.url.database).parent
    assert (root/'workbench.db').stat().st_size>backup.FILE_LIMIT
    archive=tmp_path/'large-service.qxbak'
    workspace_backup.create_workspace_backup(root,archive,PASSPHRASE,data_parent=tmp_path)
    restored=workspace_backup.restore_workspace_backup(archive,tmp_path/'restored-large-service',PASSPHRASE)
    target=Path(restored['restored_root'])
    db2=Database('sqlite:///'+str(target/'workbench.db'),target/'protected',world[0].settings,initialize_schema=False)
    try:
        with db2.session() as db:
            backup._file_references(db)
            rows=list(db.execute(text('SELECT data,sha256 FROM weixin_service_media')))
            assert len(rows)==3
            assert all(raw==data and digest==hashlib.sha256(data).hexdigest() for raw,digest in rows)
    finally:db2.engine.dispose()


def test_global_http_routes_qr_csrf_and_session_revocation(world):
    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from cn_contract.security import ServiceError,login,revoke_session
    from cn_contract.weixin_inbox.personal_runtime import PersonalWeixinRuntime,attach_runtime
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        facade=PersonalWeixinRuntime(world[0],runtime.native_model,manager)
        facade._service=runtime
        app=FastAPI();attach_runtime(app,facade)
        async def failure(request,error):return JSONResponse({'code':error.code},status_code=error.status_code)
        app.add_exception_handler(ServiceError,failure)
        token=runtime._value.session_token
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',cookies={'qx_session':token}) as client:
                status=await client.get('/api/assistant/personal-weixin/status')
                assert status.status_code==200 and status.json()['state']=='connected'
                assert status.json()['capabilities']==['contract','case','court','sales']
                runtime._status=runtime._status.model_copy(update={'state':'waiting_scan','qr_url':'https://ilinkai.weixin.qq.com/qr/fiction'})
                assert (await client.get('/api/assistant/personal-weixin/qr.svg')).status_code==200
                denied=await client.post('/api/assistant/judge/assist',json={'expected_scope':world[2].scope.model_dump(mode='json'),
                    'purpose':'primary_intent','text':'虚构'})
                assert denied.status_code==403
                with world[0].session() as db:another,csrf=login('lawyer','fixture123',db)
                client.cookies.set('qx_session',another)
                assert (await client.get('/api/assistant/personal-weixin/status')).json()['state']=='disconnected'
                allowed=await client.post('/api/assistant/judge/assist',headers={'X-CSRF-Token':csrf},json={
                    'expected_scope':world[2].scope.model_dump(mode='json'),'purpose':'primary_intent','text':'虚构'})
                assert allowed.status_code==200 and allowed.json()['result'] is None
                with world[0].session() as db:revoke_session(actor.session_id,db)
                called=[]
                import pytest
                with pytest.raises(ServiceError):await runtime._io(runtime._epoch,lambda:called.append(True))
                assert called==[]
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_five_second_collector_not_delayed_by_long_poll(world):
    import httpx
    from threading import Event
    from tests.unit.test_weixin_transport import Wire
    async def scenario():
        runtime,oldwire,manager,provider,actor=await setup(world)
        value=runtime._value.model_dump(mode='json');oldclient=runtime._transport._client
        runtime.disable();oldclient.close()
        wire=Wire();wire.updates=packet(command(1,'新事项：请审查合同'),file_message(wire,2))
        release=Event();polls=[0]
        def handle(request):
            if request.url.path.endswith('/getupdates'):
                polls[0]+=1
                if polls[0]>1:release.wait(10)
            return wire.handle(request)
        client=httpx.Client(transport=httpx.MockTransport(handle))
        runtime.client_factory=lambda:client
        try:
            runtime.start(value)
            async with asyncio.timeout(9):
                while not provider.calls:await asyncio.sleep(.05)
            assert polls[0]>=2 and not release.is_set()
            assert len(provider.calls)==1
        finally:
            release.set();await close(runtime,manager);client.close()
    asyncio.run(scenario())


def test_test_message_does_not_consume_waiting_files_and_concurrent_duplicate_is_once(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup(world)
        try:
            epoch=runtime._epoch
            raw=packet(file_message(wire,1))
            await asyncio.gather(runtime.ingest(epoch,raw),runtime.ingest(epoch,raw))
            assert count(world[0],'weixin_service_events')==1
            assert count(world[0],'weixin_service_media')==1
            await runtime.advance(epoch,now=later())
            await runtime.ingest(epoch,packet(command(2,'测试'),cursor='ack'))
            await runtime.advance(epoch,now=later())
            assert not provider.calls
            with world[0].session() as db:
                assert db.scalar(text("SELECT COUNT(*) FROM weixin_service_batches WHERE state='waiting'"))==1
                assert db.scalar(text("SELECT COUNT(*) FROM weixin_service_batches WHERE state='completed'"))==1
        finally:await close(runtime,manager)
    asyncio.run(scenario())
