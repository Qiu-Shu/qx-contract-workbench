"""Desktop projections and QR are local and use independent fictional identities."""
import asyncio
import httpx
from uuid import uuid4
from fastapi import FastAPI
from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.security import login
from cn_contract.task_drafts import service as drafts
from cn_contract.weixin_inbox.personal_runtime import attach_runtime
from tests.integration.test_weixin_personal_runtime import setup_runtime, close, packet, command, world


def test_personal_source_projection_is_explicit_before_freeze(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world,automatic=False)
        await runtime.ingest(runtime._epoch,packet(command(content='请起草客户回复')))
        with world[0].session() as db:
            draft=drafts.list_drafts(actor,world[2].scope.conversation_id,db).items[0]
            assert draft.synthetic is False
            assert draft.events[0].channel=='weixin_personal'
        assert not provider.calls
        await close(runtime,manager)
    asyncio.run(scenario())


def test_qr_is_local_svg_same_session_same_cid_no_store_and_no_url_input(world):
    async def scenario():
        runtime,wire,manager,provider,actor=await setup_runtime(world,automatic=False)
        cid=world[2].scope.conversation_id
        runtime._status=runtime._status.model_copy(update={'state':'waiting_scan','qr_url':'https://ilinkai.weixin.qq.com/qr/fiction'})
        with world[0].session() as db:
            another_token,_=login('lawyer','fixture123',db)
            other=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        app=FastAPI();attach_runtime(app,runtime)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',
                cookies={'qx_session':runtime._value.session_token}) as client:
            path=f'/api/assistant/conversations/{cid}/personal-weixin/qr.svg'
            result=await client.get(path)
            assert result.status_code==200
            assert result.headers['content-type'].startswith('image/svg+xml')
            assert result.headers['cache-control']=='no-store'
            assert result.headers['x-content-type-options']=='nosniff'
            assert '<svg' in result.text and '<path' in result.text
            assert 'ilinkai' not in result.text and 'script' not in result.text
            assert (await client.get(path+'?url=https://external.invalid')).status_code==400
            assert (await client.get(f'/api/assistant/conversations/{other.scope.conversation_id}/personal-weixin/qr.svg')).status_code==404
            client.cookies.set('qx_session',another_token)
            assert (await client.get(path)).status_code==404
            client.cookies.set('qx_session',runtime._value.session_token)
            runtime.disable()
            assert (await client.get(path)).status_code==404
        assert not provider.calls
        await close(runtime,manager)
    asyncio.run(scenario())


def test_legacy_synthetic_views_keep_their_serialized_shape(world):
    database,actor,conversation,_,_=world
    with database.session() as db:
        binding=drafts.create_binding(actor,conversation.scope.conversation_id,db)
        receipt=drafts.receive_batch(actor,binding.id,d.TaskInboxBatchInput(expected_cursor=0,next_cursor=1,
            events=(d.TaskInboxEventInput(event_id='fictional-legacy',text='合成审查指令',start_new=True,media=()),)),db)
        draft=receipt.drafts[0]
        assert draft.synthetic is True and 'synthetic' not in draft.model_dump(mode='json')
        assert draft.events[0].channel=='synthetic' and 'channel' not in draft.events[0].model_dump(mode='json')
        assert drafts.read_draft(actor,draft.id,db).manifest_sha256==draft.manifest_sha256
