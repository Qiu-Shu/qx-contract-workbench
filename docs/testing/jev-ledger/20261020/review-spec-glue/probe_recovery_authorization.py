"""Independent recovery accounting and model/session authorization isolation."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.judge_integrity import validate_judge_records
from cn_contract.assistant.providers import judge_attempts as attempts, jev_codec
from cn_contract.assistant.providers.judge_policy import JudgeRuntime, encoded, sha
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import world


def prepare(world,count=1):
    database,actor,conversation,message,_=world
    config=d.JevConfig(enabled=True)
    requests=[];runs=[]
    with database.session() as db:
        for index in range(count):
            conv=conversation if index==0 else service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
            run=service.save_message(actor,conv.scope.conversation_id,d.AssistantMessageInput(request_id=uuid4(),
                expected_scope=conv.scope,expected_composer_revision=0,content='独立合成恢复场景'+str(index)),db)
            runs.append(run)
            requests.append(attempts.request_for_run(actor,run.id,db,config))
    provider=JevProvider.for_synthetic_loopback(config,lambda:'SYNTHETIC_NEVER_READ_KEY',
        'http://127.0.0.1:1/v1/systemone')
    runtime=JudgeRuntime(provider)
    runtime.grant(d.JudgePolicy(policy_id=uuid4(),workspace_id=conversation.scope.workspace_id,
        actor_id=actor.user_id,session_id=actor.session_id,config_sha256=sha(encoded(config)),
        permissions=tuple(d.JudgePermission(local_request_id=r.local_request_id,purpose=r.purpose,
            input_hash=jev_codec.input_hash(r,config)) for r in requests),reserved_usd='.02',max_total_usd='.04',max_calls=2,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=2)))
    return database,actor,runs,requests,runtime


def main_snapshot(db):
    return {table:[tuple(r) for r in db.execute(text('SELECT * FROM '+table+' ORDER BY 1'))]
        for table in ('assistant_runs','assistant_messages','assistant_run_events')}


def test_recovery_releases_only_unsent_budget_and_keeps_main_rows_exact(world):
    database,actor,runs,_,runtime=prepare(world,3)
    with database.session() as db:
        first=attempts.reserve(actor,runs[0].id,db,runtime)
        second=attempts.reserve(actor,runs[1].id,db,runtime)
        attempts.claim(actor,second.id,db,runtime)
        before=main_snapshot(db)
    with database.session() as db:
        assert attempts.recover_attempts(db)==2
        assert main_snapshot(db)==before
        a=attempts.read_attempt(actor,first.id,db)
        b=attempts.read_attempt(actor,second.id,db)
        assert (a.state,a.receipt.occupied_usd)==('not_sent',Decimal(0))
        assert (b.state,b.receipt.occupied_usd)==('sent_unknown',Decimal('.02'))
        assert b.receipt.result.usage is None and a.decision is b.decision is None
        assert attempts._budget(runtime.policy,db)==(Decimal('.02'),1)
        third=attempts.reserve(actor,runs[2].id,db,runtime)
        assert third.state=='reserved'
        assert attempts._budget(runtime.policy,db)==(Decimal('.04'),2)
        validate_judge_records(db)
        assert main_snapshot(db)==before


def test_existing_main_model_runtime_is_not_jev_authorization(world):
    database,actor,runs,_,_=prepare(world)
    main_runtime=world[-1]
    with pytest.raises(ServiceError):JudgeRuntime(main_runtime.provider,main_runtime.policy)
    with database.session() as db:
        with pytest.raises(ServiceError):attempts.reserve(actor,runs[0].id,db,main_runtime)
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts'))==0


def test_same_user_new_login_cannot_inherit_old_session_judge_permission(world):
    database,actor,runs,requests,runtime=prepare(world)
    with database.session() as db:
        token,_=login('lawyer','fixture123',db)
        another=authenticate(token,db)
    assert actor.user_id==another.user_id and actor.session_id!=another.session_id
    with pytest.raises(ServiceError):runtime.snapshot_for(another,requests[0])
    with database.session() as db:
        with pytest.raises(ServiceError):attempts.reserve(another,runs[0].id,db,runtime)
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts'))==0
