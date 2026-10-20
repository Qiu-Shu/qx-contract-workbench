"""Independent Jev ledger deadline receipt probes; local synthetic HTTP only."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import time
from uuid import uuid4

import pytest
from sqlalchemy import text
import httpx2

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import judge_attempts as attempts, jev_codec
from cn_contract.assistant.providers.judge_execution import execute_attempt
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, encoded, sha
from cn_contract.assistant.providers.jev import JevProvider
from tests.integration.test_assistant_generation import world
from tests.integration.test_jev_provider import server, envelope, raw


@pytest.mark.parametrize('slow_stage',['decode','cleanup'])
def test_already_received_usage_survives_total_deadline_without_adoption(world,monkeypatch,slow_stage):
    database,actor,conversation,message,_=world
    with database.session() as db:
        run=service.save_message(actor,conversation.scope.conversation_id,message,db)
    config=d.JevConfig(enabled=True,timeout_ms=200)
    with database.session() as db:
        request=attempts.request_for_run(actor,run.id,db,config)
    decoded=[]
    original_decode=jev_codec.decode_response
    def capture_decode(*args,**kwargs):
        result=original_decode(*args,**kwargs)
        decoded.append(result)
        if slow_stage=='decode':time.sleep(.25)
        return result
    monkeypatch.setattr(jev_codec,'decode_response',capture_decode)
    if slow_stage=='cleanup':
        original_exit=httpx2.AsyncClient.__aexit__
        async def slow_exit(self,*args):
            try:await asyncio.sleep(.25)
            finally:await original_exit(self,*args)
        monkeypatch.setattr(httpx2.AsyncClient,'__aexit__',slow_exit)
    with server(raw(envelope(request)),headers={'x-typesafe-request-id':'independent-late-receipt'}) as (url,calls,_):
        runtime=JudgeRuntime(JevProvider.for_synthetic_loopback(config,lambda:'SYNTHETIC_LEDGER_ONLY_KEY',url))
        runtime.grant(d.JudgePolicy(policy_id=uuid4(),workspace_id=request.scope.workspace_id,
            actor_id=actor.user_id,session_id=actor.session_id,config_sha256=sha(encoded(config)),
            permissions=(d.JudgePermission(local_request_id=request.local_request_id,purpose=request.purpose,
                input_hash=jev_codec.input_hash(request,config)),),reserved_usd='.02',max_total_usd='.02',max_calls=1,
            expires_at=datetime.now(timezone.utc)+timedelta(minutes=2)))
        with database.session() as db:
            attempt=attempts.reserve(actor,run.id,db,runtime)
        result=asyncio.run(execute_attempt(actor,attempt.id,database,runtime))
    assert len(calls)==1 and len(decoded)==1
    assert decoded[0]['usage'].input_tokens==20
    assert result.decision is None and result.receipt.cost_status=='unknown'
    assert result.receipt.occupied_usd==Decimal('.02')
    assert result.state=='received'
    assert result.receipt.result.status=='timed_out'
    assert result.receipt.result.usage.input_tokens==20
    assert result.receipt.result.provider_request_id=='independent-late-receipt'
    with database.session() as db:
        assert service.get_run(actor,run.id,db).state=='queued'
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_receipts'))==1


def test_external_cancellation_after_decode_keeps_received_accounting(world,monkeypatch):
    database,actor,conversation,message,_=world
    with database.session() as db:
        run=service.save_message(actor,conversation.scope.conversation_id,message,db)
    config=d.JevConfig(enabled=True)
    with database.session() as db:
        request=attempts.request_for_run(actor,run.id,db,config)
    decoded=asyncio.Event()
    original_decode=jev_codec.decode_response
    def capture(*args,**kwargs):
        value=original_decode(*args,**kwargs)
        assert value['usage'].input_tokens==20
        decoded.set()
        return value
    monkeypatch.setattr(jev_codec,'decode_response',capture)
    original_exit=httpx2.AsyncClient.__aexit__
    async def cleanup(self,*args):
        try:await asyncio.sleep(.25)
        finally:await original_exit(self,*args)
    monkeypatch.setattr(httpx2.AsyncClient,'__aexit__',cleanup)
    with server(raw(envelope(request)),headers={'x-typesafe-request-id':'independent-cancel-receipt'}) as (url,calls,_):
        runtime=JudgeRuntime(JevProvider.for_synthetic_loopback(config,lambda:'SYNTHETIC_LEDGER_ONLY_KEY',url))
        runtime.grant(d.JudgePolicy(policy_id=uuid4(),workspace_id=request.scope.workspace_id,
            actor_id=actor.user_id,session_id=actor.session_id,config_sha256=sha(encoded(config)),
            permissions=(d.JudgePermission(local_request_id=request.local_request_id,purpose=request.purpose,
                input_hash=jev_codec.input_hash(request,config)),),reserved_usd='.02',max_total_usd='.02',max_calls=1,
            expires_at=datetime.now(timezone.utc)+timedelta(minutes=2)))
        with database.session() as db:attempt=attempts.reserve(actor,run.id,db,runtime)
        async def cancel():
            task=asyncio.create_task(execute_attempt(actor,attempt.id,database,runtime))
            await asyncio.wait_for(decoded.wait(),2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
        asyncio.run(cancel())
    assert len(calls)==1
    with database.session() as db:
        result=attempts.read_attempt(actor,attempt.id,db)
        assert result.decision is None and result.receipt.occupied_usd==Decimal('.02')
        assert result.state=='received'
        assert result.receipt.result.usage.input_tokens==20
        assert result.receipt.result.provider_request_id=='independent-cancel-receipt'
