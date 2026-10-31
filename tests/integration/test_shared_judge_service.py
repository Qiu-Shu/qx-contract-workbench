"""Real Jev transport, synthetic loopback only; one independent durable claim."""
import asyncio
from sqlalchemy import text
from cn_contract import domain as d
from cn_contract.assistant.shared_judge import SharedJudgeService,validate_records
from cn_contract.assistant.providers.judge_policy import JudgeRuntime
from cn_contract.assistant.providers.jev import JevProvider
from tests.integration.test_assistant_generation import world
from tests.integration.test_jev_provider import server,raw,envelope,request,KEY


def test_shared_configured_provider_transport_reuse_and_material_path(world):
    async def scenario():
        database,actor,conversation,*_=world
        runtime=JudgeRuntime()
        for purpose in ('primary_intent','material_kind'):
            with server(raw(envelope(request(purpose)))) as (url,received,_):
                runtime.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
                shared=SharedJudgeService(database,runtime)
                value=d.SharedJudgeInput(expected_scope=conversation.scope,purpose=purpose,text='独立虚构合同咨询')
                first=await shared.assist(actor,value)
                assert first and first.status=='ok'
                second=await shared.assist(actor,value)
                assert second==first and len(received)==1
        with database.session() as db:validate_records(db)
    asyncio.run(scenario())


def test_shared_timeout_fallback_unknown_claim_never_retries(world):
    async def scenario():
        database,actor,conversation,*_=world
        runtime=JudgeRuntime()
        with server(raw(envelope(request())),header_pause=.3) as (url,received,_):
            runtime.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True,timeout_ms=50),lambda:KEY,url))
            shared=SharedJudgeService(database,runtime)
            value=d.SharedJudgeInput(expected_scope=conversation.scope,purpose='primary_intent',text='独立虚构咨询')
            first=await shared.assist(actor,value)
            assert first is None or first.status!='ok'
            await shared.assist(actor,value)
            assert len(received)<=1
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_shared_judgments'))==1
            validate_records(db)
    asyncio.run(scenario())


def test_shared_discards_stale_response_and_does_not_repeat(world):
    async def scenario():
        database,actor,conversation,*_=world
        runtime=JudgeRuntime();current=[True]
        with server(raw(envelope(request())),pause=.1) as (url,received,seen):
            runtime.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
            shared=SharedJudgeService(database,runtime)
            value=d.SharedJudgeInput(expected_scope=conversation.scope,purpose='primary_intent',text='独立虚构旧输入')
            pending=asyncio.create_task(shared.assist(actor,value,current=lambda:current[0]))
            async with asyncio.timeout(2):
                while not seen.is_set():await asyncio.sleep(.005)
            current[0]=False
            assert await pending is None
            current[0]=True
            assert await shared.assist(actor,value) is None
            assert len(received)==1
    asyncio.run(scenario())


def service_envelope(choices,candidates=()):
    from uuid import uuid4
    from cn_contract.assistant.providers.jev_codec import service_questions
    scope=d.ServiceJudgeScope(workspace_id=uuid4(),owner_id=uuid4(),session_id=uuid4(),connection_id=uuid4(),batch_id=uuid4(),revision=1)
    request=d.ServiceJudgeRequest(local_request_id=uuid4(),scope=scope,text='虚构',candidates=candidates)
    questions=service_questions(request)
    return {'model':'jev-1.13.0','usage':{'input_tokens':8,'output_tokens':4},'answers':{
        key:{'type':'choice','choice':choices[key],'confidence':.95,
             'probabilities':{option:float(option==choices[key]) for option in value['criteria']}}
        for key,value in questions.items()}}


def test_service_four_questions_actual_transport_routes_court_without_throwaway_chat(world):
    from tests.integration.test_weixin_service_runtime import setup,later
    from tests.integration.test_weixin_personal_runtime import close,packet,command,file_message
    async def scenario():
        runtime,wire,manager,main,actor=await setup(world)
        try:
            with server(raw(service_envelope({'readiness':'start','relation':'new','workflow':'court','material_kind':'contract'}))) as (url,received,_):
                judge=JudgeRuntime()
                judge.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
                runtime.judge=SharedJudgeService(world[0],judge)
                await runtime.ingest(runtime._epoch,packet(command(1,'请站在法官视角帮我准备发言'),file_message(wire,2)))
                await runtime.advance(runtime._epoch,now=later())
                assert len(main.calls)==1
                import json
                first=json.loads(received[0]['body'])
                assert set(first['questions'])=={'readiness','relation','workflow','material_kind'}
                assert 'court' in first['questions']['workflow']['criteria']
                assert 'scope' not in first['state']
                with world[0].session() as db:
                    assert db.scalar(text('SELECT workflow FROM weixin_service_batches'))=='court'
                    assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_runs'))==1
                    validate_records(db)
                assert len(received)==2  # pre-business four-way and locally parsed material, no duplicate intent call
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_service_jev_wait_keeps_batch_pending_and_same_input_is_reused(world):
    from tests.integration.test_weixin_service_runtime import setup,later
    from tests.integration.test_weixin_personal_runtime import close,packet,command,file_message
    async def scenario():
        runtime,wire,manager,main,actor=await setup(world)
        try:
            with server(raw(service_envelope({'readiness':'wait','relation':'new','workflow':'contract','material_kind':'contract'}))) as (url,received,_):
                judge=JudgeRuntime();judge.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
                runtime.judge=SharedJudgeService(world[0],judge)
                await runtime.ingest(runtime._epoch,packet(command(1,'请审查合同，我随后再说明情况'),file_message(wire,2)))
                await runtime.advance(runtime._epoch,now=later())
                await runtime.advance(runtime._epoch,now=later())
                assert not main.calls and len(received)==1
                with world[0].session() as db:
                    assert db.scalar(text('SELECT state FROM weixin_service_batches'))=='waiting'
                    assert db.scalar(text('SELECT COUNT(*) FROM weixin_service_runs'))==0
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_service_intake_during_slow_judgment_invalidates_old_batch(world):
    from tests.integration.test_weixin_service_runtime import setup,later
    from tests.integration.test_weixin_personal_runtime import close,packet,command,file_message
    async def scenario():
        runtime,wire,manager,main,actor=await setup(world)
        try:
            with server(raw(service_envelope({'readiness':'start','relation':'new','workflow':'contract','material_kind':'contract'})),pause=.2) as (url,received,seen):
                judge=JudgeRuntime();judge.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
                runtime.judge=SharedJudgeService(world[0],judge)
                await runtime.ingest(runtime._epoch,packet(command(1,'请审查合同'),file_message(wire,2)))
                pending=asyncio.create_task(runtime.advance(runtime._epoch,now=later()))
                async with asyncio.timeout(2):
                    while not seen.is_set():await asyncio.sleep(.005)
                await runtime.ingest(runtime._epoch,packet(command(3,'还有附件，稍等'),cursor='late'))
                await pending
                assert not main.calls
                with world[0].session() as db:
                    assert db.scalar(text('SELECT state FROM weixin_service_batches'))=='held'
                    assert db.scalar(text('SELECT state FROM assistant_shared_judgments'))=='discarded'
                    validate_records(db)
        finally:await close(runtime,manager)
    asyncio.run(scenario())


def test_desktop_can_reuse_all_four_questions_with_existing_conversation_scope(world):
    async def scenario():
        database,actor,conversation,*_=world
        with server(raw(service_envelope({'readiness':'start','relation':'new','workflow':'court','material_kind':'judgment'}))) as (url,received,_):
            runtime=JudgeRuntime();runtime.configure(JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:KEY,url))
            shared=SharedJudgeService(database,runtime)
            value=d.SharedJudgeInput(expected_scope=conversation.scope,purpose='service_intake',text='虚构庭审准备')
            result=await shared.assist(actor,value)
            assert result.status=='ok' and result.answers['workflow'].choice=='court'
            assert len(received)==1
            with database.session() as db:validate_records(db)
    asyncio.run(scenario())
