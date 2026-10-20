"""Synthetic Jev ledger; no remote credential, account or model call."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.providers import jev_codec
from cn_contract.config import canonical_json
from cn_contract.security import ServiceError, authenticate, login
from test_assistant_generation import world
from test_jev_provider import server, envelope, raw


def api():
    return importlib.import_module('cn_contract.assistant.providers.judge_attempts')


def setup(world, *, requested_skill=None):
    database, actor, conversation, message, _ = world
    schema = importlib.import_module('cn_contract.assistant.judge_schema')
    schema.initialize_storage(database)
    with database.session() as db:
        run = service.save_message(actor, conversation.scope.conversation_id,
            message.model_copy(update={'requested_skill': requested_skill}), db)
    cfg = d.JevConfig(enabled=True)
    module = importlib.import_module('cn_contract.assistant.providers.judge_policy')
    provider = JevProvider.for_synthetic_loopback(cfg, lambda: 'SYNTHETIC_JUDGE_KEY',
        'http://127.0.0.1:12345/v1/systemone')
    runtime = module.JudgeRuntime(provider)
    with database.session() as db:
        request = api().request_for_run(actor, run.id, db, cfg)
    policy = d.JudgePolicy(policy_id=uuid4(), workspace_id=request.scope.workspace_id,
        actor_id=actor.user_id, session_id=actor.session_id, config_sha256=module.sha(module.encoded(cfg)),
        permissions=(d.JudgePermission(local_request_id=request.local_request_id, purpose=request.purpose,
                                      input_hash=jev_codec.input_hash(request, cfg)),),
        reserved_usd='0.02', max_total_usd='0.04', max_calls=2,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
    runtime.grant(policy)
    return database, actor, run, request, runtime


def test_reservation_and_replay_never_rewrite_main_run_or_create_second_queue(world):
    database, actor, run, request, runtime = setup(world)
    with database.session() as db:
        before = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(run.id)}).mappings().one())
        first = api().reserve(actor, run.id, db, runtime)
    with database.session() as db:
        replay = api().reserve(actor, run.id, db, runtime)
        after = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(run.id)}).mappings().one())
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 1
    assert replay == first and first.state == 'reserved' and first.receipt is None
    assert first.reserved_usd == Decimal('.02') and first.scope == request.scope
    assert before == after


def test_real_loopback_claim_settle_preserves_unknown_cost_and_main_run(world):
    database, actor, run, request, runtime = setup(world)
    execution = importlib.import_module('cn_contract.assistant.providers.judge_execution')
    with server(raw(envelope(request))) as (url, calls, _):
        policy = runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(),
            lambda: 'SYNTHETIC_JUDGE_KEY', url))
        runtime.grant(policy)
        with database.session() as db:
            attempt = api().reserve(actor, run.id, db, runtime)
        async def exercise():
            result = await execution.execute_attempt(actor, attempt.id, database, runtime)
            replay = await execution.execute_attempt(actor, attempt.id, database, runtime)
            return result, replay
        result, replay = asyncio.run(exercise())
    assert result == replay and len(calls) == 1
    assert result.state == 'received' and result.receipt.result.status == 'ok'
    assert result.receipt.occupied_usd == Decimal('.02') and result.receipt.cost_status == 'unknown'
    assert result.decision.decision.workflow == 'client_reply'
    with database.session() as db:
        current = service.get_run(actor, run.id, db)
    assert current.state == 'queued' and current.selected_provider is None and current.selected_model is None


def test_valid_reserved_history_is_checked_without_live_authorization(world):
    database, actor, run, _, runtime = setup(world)
    with database.session() as db:
        api().reserve(actor, run.id, db, runtime)
    runtime.revoke()
    integrity = importlib.import_module('cn_contract.assistant.judge_integrity')
    with database.session() as db:
        integrity.validate_judge_records(db)


def reserve(values):
    database, actor, run, _, runtime = values
    with database.session() as db:
        return api().reserve(actor, run.id, db, runtime)


def reply(request, config, **changes):
    answer = envelope(request)['answers']['primary_intent']
    fields = dict(status='ok', evidence='received', local_request_id=request.local_request_id,
        scope=request.scope, input_hash=jev_codec.input_hash(request, config), elapsed_ms=1,
        model='jev-1.13.0', usage=d.JudgeUsage(input_tokens=20, output_tokens=None),
        answers={'primary_intent': d.JudgeChoice(**answer)})
    fields.update(changes)
    return d.JudgeResult(**fields)


@pytest.mark.parametrize('change', ['none', 'no-policy', 'expired', 'session', 'actor', 'workspace', 'input', 'purpose'])
def test_no_matching_independent_permission_never_reserves(world, change):
    values = setup(world); database, actor, run, request, runtime = values
    module = importlib.import_module('cn_contract.assistant.providers.judge_policy')
    if change == 'none': runtime = module.JudgeRuntime()
    elif change == 'no-policy': runtime.revoke()
    elif change == 'expired':
        policy = runtime.policy
        runtime.revoke()
        with pytest.raises(ServiceError):
            runtime.grant(policy.model_copy(update={'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}))
        # Expiry is also checked at grant; no policy survives a failed grant.
    else:
        policy = runtime.policy
        patch = {'session': {'session_id': uuid4()}, 'actor': {'actor_id': uuid4()},
            'workspace': {'workspace_id': uuid4()},
            'input': {'permissions': (policy.permissions[0].model_copy(update={'input_hash':'0'*64}),)},
            'purpose': {'permissions': (policy.permissions[0].model_copy(update={'purpose':'material_kind'}),)}}[change]
        runtime.grant(policy.model_copy(update={'policy_id':uuid4(), **patch}))
    with database.session() as db:
        with pytest.raises(ServiceError): api().reserve(actor, run.id, db, runtime)
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts')) == 0


def test_explicit_skill_skips_without_provider_or_policy(world):
    database, actor, run, _, _ = setup(world, requested_skill='contract_review')
    module = importlib.import_module('cn_contract.assistant.providers.judge_policy')
    with database.session() as db:
        assert api().reserve(actor, run.id, db, module.JudgeRuntime()) is None
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts')) == 0


def test_other_session_cannot_claim_or_abandon_original_session_reservation(world):
    values = setup(world); database, actor, _, _, runtime = values
    first = reserve(values)
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db); other = authenticate(token, db)
    with database.session() as db:
        with pytest.raises(ServiceError): api().claim(other, first.id, db, runtime)
        assert api().read_attempt(actor, first.id, db).state == 'reserved'


@pytest.mark.parametrize('change', ['revoke', 'grant-aba', 'config-aba', 'new-runtime'])
def test_authorization_generation_change_closes_reserved_without_resurrection(world, change):
    values = setup(world); database, actor, _, _, runtime = values; first = reserve(values)
    policy, provider = runtime.policy, runtime.provider
    if change == 'revoke': runtime.revoke()
    elif change == 'grant-aba': runtime.revoke(); runtime.grant(policy)
    elif change == 'config-aba': runtime.configure(provider); runtime.grant(policy)
    else:
        module = importlib.import_module('cn_contract.assistant.providers.judge_policy')
        runtime = module.JudgeRuntime(provider, policy)
    with database.session() as db:
        assert api().claim(actor, first.id, db, runtime) is None
        result = api().read_attempt(actor, first.id, db)
        assert api().claim(actor, first.id, db, runtime) is None
    assert result.state == 'not_sent' and result.receipt.occupied_usd == 0 and result.decision is None


@pytest.mark.parametrize('change', ['revoke', 'cancel', 'materials', 'input', 'config'])
def test_received_receipt_survives_invalidation_but_decision_is_not_adopted(world, change):
    values = setup(world); database, actor, run, request, runtime = values; first = reserve(values)
    with database.session() as db:
        token, _, cfg = api().claim(actor, first.id, db, runtime)
    if change == 'revoke': runtime.revoke()
    elif change == 'config': runtime.configure(runtime.provider)
    else:
        with database.session() as db:
            if change == 'cancel':
                service.cancel_run(actor, run.id, d.AssistantCancelInput(request_id=uuid4()), db)
            else:
                field = 'materials_revision' if change == 'materials' else 'input_revision'
                db.execute(text(f'UPDATE assistant_conversations SET {field}={field}+1 WHERE id=:id'),
                           {'id':str(request.scope.conversation_id)})
    with database.session() as db:
        api().settle(actor, first.id, token, reply(request, cfg), db, runtime)
        result = api().read_attempt(actor, first.id, db)
    assert result.state == 'received' and result.decision is None
    assert result.receipt.result.usage.input_tokens == 20 and result.receipt.result.usage.output_tokens is None
    assert result.receipt.occupied_usd == Decimal('.02') and result.receipt.result.status == 'ok'


@pytest.mark.parametrize('state', ['reserved', 'sending'])
def test_recovery_records_evidence_only_and_is_idempotent(world, state):
    values = setup(world); database, actor, run, _, runtime = values; first = reserve(values)
    with database.session() as db:
        if state == 'sending': api().claim(actor, first.id, db, runtime)
        before = dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(run.id)}).mappings().one())
        assert api().recover_attempts(db) == 1
        assert api().recover_attempts(db) == 0
        result = api().read_attempt(actor, first.id, db)
        assert dict(db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(run.id)}).mappings().one()) == before
    assert result.state == ('not_sent' if state == 'reserved' else 'sent_unknown')
    assert result.receipt.occupied_usd == (0 if state == 'reserved' else Decimal('.02'))


def test_claim_fence_is_once_and_wrong_settlement_cannot_modify_it(world):
    values = setup(world); database, actor, _, request, runtime = values; first = reserve(values)
    with database.session() as db:
        token, _, config = api().claim(actor, first.id, db, runtime)
        assert api().claim(actor, first.id, db, runtime) is None
    with database.session() as db:
        with pytest.raises(ServiceError): api().settle(actor, first.id, 'wrong-token', reply(request, config), db, runtime)
        assert api().read_attempt(actor, first.id, db).state == 'sending'
        api().settle(actor, first.id, token, reply(request, config), db, runtime)
        with pytest.raises(ServiceError): api().settle(actor, first.id, token, reply(request, config), db, runtime)
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_receipts')) == 1


@pytest.mark.parametrize('change', ['request', 'scope', 'hash'])
def test_foreign_result_identity_cannot_be_accounted_against_another_claim(world, change):
    values = setup(world); database, actor, _, request, runtime = values; first = reserve(values)
    with database.session() as db:
        token, _, config = api().claim(actor, first.id, db, runtime)
        patch = {'request': {'local_request_id':uuid4()}, 'scope': {'scope':request.scope.model_copy(update={'input_revision':0})},
                 'hash': {'input_hash':'0'*64}}[change]
        with pytest.raises(ServiceError): api().settle(actor, first.id, token, reply(request, config, **patch), db, runtime)
        assert api().read_attempt(actor, first.id, db).state == 'sending'


def test_revoke_during_client_entry_prevents_actual_post_and_releases_only_unsent(world, monkeypatch):
    import httpx2
    values = setup(world); database, actor, run, request, runtime = values
    original = httpx2.AsyncClient.__aenter__
    with server(raw(envelope(request))) as (url, calls, _):
        policy = runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(), lambda:'SYNTHETIC_JUDGE_KEY', url))
        runtime.grant(policy); first = reserve(values)
        async def entered(client):
            result = await original(client)
            runtime.revoke()
            return result
        monkeypatch.setattr(httpx2.AsyncClient, '__aenter__', entered)
        execution = importlib.import_module('cn_contract.assistant.providers.judge_execution')
        result = asyncio.run(execution.execute_attempt(actor, first.id, database, runtime))
    assert calls == [] and result.state == 'not_sent' and result.receipt.occupied_usd == 0
    assert result.decision is None


def test_cancelled_execution_records_unknown_and_never_retries(world):
    values = setup(world); database, actor, _, request, runtime = values
    with server(raw(envelope(request)), pause=.5) as (url, calls, seen):
        policy = runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(), lambda:'SYNTHETIC_JUDGE_KEY', url))
        runtime.grant(policy); first = reserve(values)
        execution = importlib.import_module('cn_contract.assistant.providers.judge_execution')
        async def exercise():
            task = asyncio.create_task(execution.execute_attempt(actor, first.id, database, runtime))
            while not seen.is_set(): await asyncio.sleep(.002)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            return await execution.execute_attempt(actor, first.id, database, runtime)
        result = asyncio.run(exercise())
    assert len(calls) == 1 and result.state == 'sent_unknown' and result.decision is None
    assert result.receipt.occupied_usd == Decimal('.02')


def test_runtime_mutations_after_execution_are_owned_by_the_app_loop(world):
    values = setup(world); _, _, _, _, runtime = values
    async def bind(): runtime.bind_execution()
    asyncio.run(bind())
    with pytest.raises(ServiceError): runtime.revoke()
    with pytest.raises(ServiceError): asyncio.run(bind())


@pytest.mark.parametrize('evidence', ['not_sent', 'sent_unknown', 'received'])
def test_only_definite_unsent_releases_policy_quota_and_regrant_never_resets_it(world, evidence):
    values = setup(world); database, actor, run, request, runtime = values
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        second_run = service.save_message(actor, conversation.scope.conversation_id,
            d.AssistantMessageInput(request_id=uuid4(), expected_scope=conversation.scope,
                expected_composer_revision=0, content='第二份完全合成的独立咨询。'), db)
        second_request = api().request_for_run(actor, second_run.id, db, runtime.configuration())
    permission = d.JudgePermission(local_request_id=second_request.local_request_id, purpose='primary_intent',
        input_hash=jev_codec.input_hash(second_request, runtime.configuration()))
    policy = runtime.policy.model_copy(update={'policy_id':uuid4(), 'max_total_usd':Decimal('.02'), 'max_calls':1,
        'permissions':runtime.policy.permissions+(permission,)})
    runtime.grant(policy); first = reserve(values)
    with database.session() as db:
        token, _, cfg = api().claim(actor, first.id, db, runtime)
        outcome = reply(request, cfg) if evidence == 'received' else d.JudgeResult(status='failed',
            reason_code='provider_error', evidence=evidence, local_request_id=request.local_request_id,
            scope=request.scope, input_hash=jev_codec.input_hash(request,cfg), elapsed_ms=1)
        api().settle(actor, first.id, token, outcome, db, runtime)
    runtime.revoke(); runtime.grant(policy)
    with database.session() as db:
        if evidence == 'not_sent':
            assert api().reserve(actor, second_run.id, db, runtime).state == 'reserved'
        else:
            with pytest.raises(ServiceError) as failure: api().reserve(actor, second_run.id, db, runtime)
            assert failure.value.code == 'BUDGET_EXCEEDED'
        importlib.import_module('cn_contract.assistant.judge_integrity').validate_judge_records(db)


def test_changed_policy_id_content_is_rejected_even_by_fresh_runtime(world):
    values = setup(world); database, actor, run, _, runtime = values; reserve(values)
    changed = runtime.policy.model_copy(update={'max_total_usd':Decimal('.08')})
    with pytest.raises(ServiceError) as failure: runtime.grant(changed)
    assert failure.value.code == 'VERSION_CONFLICT'
    runtime = importlib.import_module('cn_contract.assistant.providers.judge_policy').JudgeRuntime(runtime.provider, changed)
    with database.session() as db:
        with pytest.raises(ServiceError) as failure: api().reserve(actor, run.id, db, runtime)
        assert failure.value.code == 'VERSION_CONFLICT'


@pytest.mark.parametrize('change', ['purpose', 'scope', 'material', 'cancelled', 'short-cap'])
def test_first_slice_refuses_unmapped_or_changed_source_without_truncation(world, change):
    values = setup(world); database, actor, run, request, runtime = values
    if change == 'short-cap':
        runtime.configure(JevProvider(d.JevConfig(enabled=True,max_input_bytes=1),lambda:'SYNTHETIC_JUDGE_KEY'))
    with database.session() as db:
        if change == 'scope':
            db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1'))
        elif change == 'material':
            db.execute(text('UPDATE assistant_conversations SET materials_revision=materials_revision+1'))
        elif change == 'cancelled':
            service.cancel_run(actor,run.id,d.AssistantCancelInput(request_id=uuid4()),db)
        with pytest.raises(ServiceError):
            api().reserve(actor,run.id,db,runtime,purpose='material_kind' if change=='purpose' else 'primary_intent')
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_attempts'))==0
        assert db.scalar(text('SELECT content FROM assistant_messages'))==request.text


@pytest.mark.parametrize('field', ['session_id', 'message_id', 'input_hash', 'request_json', 'reserved_usd', 'claim_sha256'])
def test_history_integrity_rejects_rewritten_identity_or_noncanonical_evidence(world, field):
    from tests.integration.test_assistant_attachment_backup import corrupt
    values=setup(world);database,actor,_,_,runtime=values;first=reserve(values)
    with database.session() as db:
        api().claim(actor,first.id,db,runtime)
    replacements={'session_id':str(uuid4()),'message_id':str(uuid4()),'input_hash':'0'*64,
        'request_json':'{}','reserved_usd':'0.00','claim_sha256':None}
    corrupt(database,'assistant_judge_attempts',f'UPDATE assistant_judge_attempts SET {field}=?',(replacements[field],))
    with database.session() as db,pytest.raises(ValueError,match='ASSISTANT_JUDGE_INTEGRITY'):
        importlib.import_module('cn_contract.assistant.judge_integrity').validate_judge_records(db)


def test_history_requires_native_identity_and_encrypted_workspace_backup(world):
    values=setup(world);database,_,_,_,_=values;reserve(values)
    with database.session() as db,pytest.raises(ValueError,match='REQUIRE_QXBAK'):
        importlib.import_module('cn_contract.assistant.judge_integrity').validate_judge_records(db,allowed=False)


@pytest.mark.parametrize('stage',['decode','cleanup'])
def test_received_usage_survives_single_deadline_without_becoming_a_decision(world,monkeypatch,stage):
    import httpx2
    import time
    values=setup(world);database,actor,run,_,runtime=values
    cfg=d.JevConfig(enabled=True,timeout_ms=200)
    with database.session() as db: request=api().request_for_run(actor,run.id,db,cfg)
    original_decode=jev_codec.decode_response; original_exit=httpx2.AsyncClient.__aexit__
    decoded=[]
    def decode(*args,**kwargs):
        result=original_decode(*args,**kwargs);decoded.append(result)
        if stage=='decode':time.sleep(.25)
        return result
    async def cleanup(client,*args):
        try:await asyncio.sleep(.25)
        finally:await original_exit(client,*args)
    monkeypatch.setattr(jev_codec,'decode_response',decode)
    if stage=='cleanup':monkeypatch.setattr(httpx2.AsyncClient,'__aexit__',cleanup)
    module=importlib.import_module('cn_contract.assistant.providers.judge_policy')
    policy=runtime.policy.model_copy(update={'policy_id':uuid4(),'config_sha256':module.sha(module.encoded(cfg)),
        'permissions':(d.JudgePermission(local_request_id=request.local_request_id,purpose=request.purpose,
            input_hash=jev_codec.input_hash(request,cfg)),)})
    with server(raw(envelope(request)),headers={'x-typesafe-request-id':'synthetic-late-receipt'}) as (url,calls,_):
        runtime.configure(JevProvider.for_synthetic_loopback(cfg,lambda:'SYNTHETIC_JUDGE_KEY',url));runtime.grant(policy)
        first=reserve(values)
        execution=importlib.import_module('cn_contract.assistant.providers.judge_execution')
        result=asyncio.run(execution.execute_attempt(actor,first.id,database,runtime))
    assert len(calls)==1 and len(decoded)==1 and result.state=='received' and result.decision is None
    assert result.receipt.result.status=='timed_out' and result.receipt.result.elapsed_ms>=200
    assert result.receipt.result.usage.input_tokens==20 and result.receipt.result.usage.output_tokens==4
    assert result.receipt.result.provider_request_id=='synthetic-late-receipt'
    assert result.receipt.occupied_usd==Decimal('.02')


def test_parallel_execution_only_one_claim_reaches_real_http(world):
    values=setup(world);database,actor,_,request,runtime=values
    with server(raw(envelope(request)),pause=.08) as (url,calls,seen):
        policy=runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(),lambda:'SYNTHETIC_JUDGE_KEY',url))
        runtime.grant(policy);first=reserve(values)
        execution=importlib.import_module('cn_contract.assistant.providers.judge_execution')
        async def exercise():
            task=asyncio.create_task(execution.execute_attempt(actor,first.id,database,runtime))
            while not seen.is_set():await asyncio.sleep(.002)
            second=await execution.execute_attempt(actor,first.id,database,runtime)
            assert second.state=='sending'
            return await task
        result=asyncio.run(exercise())
    assert len(calls)==1 and result.state=='received'


def test_received_result_keeps_accounting_after_actual_run_cancellation_during_http(world):
    values=setup(world);database,actor,run,request,runtime=values
    with server(raw(envelope(request)),pause=.08) as (url,calls,seen):
        policy=runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(),lambda:'SYNTHETIC_JUDGE_KEY',url))
        runtime.grant(policy);first=reserve(values)
        execution=importlib.import_module('cn_contract.assistant.providers.judge_execution')
        async def exercise():
            task=asyncio.create_task(execution.execute_attempt(actor,first.id,database,runtime))
            while not seen.is_set():await asyncio.sleep(.002)
            with database.session() as db:service.cancel_run(actor,run.id,d.AssistantCancelInput(request_id=uuid4()),db)
            return await task
        result=asyncio.run(exercise())
    assert len(calls)==1 and result.state=='received' and result.decision is None
    assert result.receipt.result.usage.input_tokens==20


def test_failed_configuration_replacement_keeps_prior_valid_grant(world):
    values=setup(world);_,actor,_,request,runtime=values
    prior=runtime.snapshot_for(actor,request)
    malformed=JevProvider(d.JevConfig(enabled=True),lambda:'SYNTHETIC_UNUSED_KEY')
    malformed.config=malformed.config.model_copy(update={'timeout_ms':'PRIVATE-INVALID'})
    with pytest.raises(ServiceError) as failure:runtime.configure(malformed)
    assert failure.value.code=='BLOCKED_LIVE' and runtime.snapshot_for(actor,request)==prior


def test_historical_decision_timestamp_must_precede_approval_expiry(world):
    from tests.integration.test_assistant_attachment_backup import corrupt
    module=importlib.import_module('cn_contract.assistant.providers.judge_policy')
    values=setup(world);database,actor,_,request,runtime=values;first=reserve(values)
    with database.session() as db:
        token,_,cfg=api().claim(actor,first.id,db,runtime)
        api().settle(actor,first.id,token,reply(request,cfg),db,runtime)
        decision=api().read_attempt(actor,first.id,db).decision
    later=runtime.policy.expires_at+timedelta(seconds=1)
    corrupt(database,'assistant_judge_attempts','UPDATE assistant_judge_attempts SET updated_at=?',(later.isoformat(),))
    corrupt(database,'assistant_judge_receipts','UPDATE assistant_judge_receipts SET created_at=?',(later.isoformat(),))
    corrupt(database,'assistant_judge_decisions','UPDATE assistant_judge_decisions SET created_at=?,decision_json=?',
        (later.isoformat(),module.encoded(decision.model_copy(update={'created_at':later}))))
    with database.session() as db,pytest.raises(ValueError,match='ASSISTANT_JUDGE_INTEGRITY'):
        importlib.import_module('cn_contract.assistant.judge_integrity').validate_judge_records(db)


def test_explicit_skill_does_not_need_to_fit_an_unused_judge_wire_budget(world):
    database,actor,conversation,message,_=world
    with database.session() as db:
        run=service.save_message(actor,conversation.scope.conversation_id,
            message.model_copy(update={'content':'😀'*20000,'requested_skill':'contract_review'}),db)
        runtime=importlib.import_module('cn_contract.assistant.providers.judge_policy').JudgeRuntime()
        assert api().reserve(actor,run.id,db,runtime) is None


@pytest.mark.parametrize('response_kind',['valid','invalid-answer','secret-reflection','repeated-cancel'])
def test_external_cancel_after_decode_preserves_safe_receipt_without_adoption(world,monkeypatch,response_kind):
    import httpx2
    values=setup(world);database,actor,run,request,runtime=values
    decoded=asyncio.Event(); original_decode=jev_codec.decode_response
    original_exit=httpx2.AsyncClient.__aexit__
    def decode(*args,**kwargs):
        result=original_decode(*args,**kwargs);decoded.set();return result
    async def cleanup(client,*args):
        try:await asyncio.sleep(.25)
        finally:await original_exit(client,*args)
    monkeypatch.setattr(jev_codec,'decode_response',decode)
    monkeypatch.setattr(httpx2.AsyncClient,'__aexit__',cleanup)
    body=envelope(request)
    if response_kind=='invalid-answer':body['answers']={}
    elif response_kind=='secret-reflection':body['SYNTHETIC_JUDGE_KEY']='SYNTHETIC_PRIVATE_BODY'
    with server(raw(body),headers={'x-typesafe-request-id':'synthetic-cancel-receipt'}) as (url,calls,_):
        policy=runtime.policy
        runtime.configure(JevProvider.for_synthetic_loopback(runtime.configuration(),lambda:'SYNTHETIC_JUDGE_KEY',url))
        runtime.grant(policy);first=reserve(values)
        execution=importlib.import_module('cn_contract.assistant.providers.judge_execution')
        async def exercise():
            task=asyncio.create_task(execution.execute_attempt(actor,first.id,database,runtime))
            await asyncio.wait_for(decoded.wait(),2)
            task.cancel()
            if response_kind=='repeated-cancel':task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            return await execution.execute_attempt(actor,first.id,database,runtime)
        result=asyncio.run(exercise())
    assert len(calls)==1 and result.state=='received' and result.decision is None
    assert result.receipt.result.status!='ok' and result.receipt.result.answers=={}
    assert result.receipt.occupied_usd==Decimal('.02') and result.receipt.cost_status=='unknown'
    if response_kind=='secret-reflection':
        assert result.receipt.result.usage is None and result.receipt.result.provider_request_id is None
    else:
        assert result.receipt.result.usage.input_tokens==20
        assert result.receipt.result.provider_request_id=='synthetic-cancel-receipt'
    assert 'SYNTHETIC_JUDGE_KEY' not in result.model_dump_json() and 'SYNTHETIC_PRIVATE_BODY' not in result.model_dump_json()
    with database.session() as db:
        assert service.get_run(actor,run.id,db).state=='queued'
        assert db.scalar(text('SELECT count(*) FROM assistant_judge_receipts'))==1
        importlib.import_module('cn_contract.assistant.judge_integrity').validate_judge_records(db)


@pytest.mark.parametrize('change',['request-id','scope','input-hash','ok','malformed'])
def test_cancellation_receipt_channel_checks_binding_and_never_adopts(world,monkeypatch,change):
    from cn_contract.assistant.providers.jev import JevCancelledError
    values=setup(world);database,actor,_,request,runtime=values;first=reserve(values)
    result=reply(request,runtime.configuration()).model_copy(update={
        'status':'failed','reason_code':'provider_error','answers':{}})
    if change=='request-id':result=result.model_copy(update={'local_request_id':uuid4()})
    elif change=='scope':result=result.model_copy(update={
        'scope':request.scope.model_copy(update={'conversation_id':uuid4()})})
    elif change=='input-hash':result=result.model_copy(update={'input_hash':'0'*64})
    elif change=='ok':result=reply(request,runtime.configuration())
    else:result={'provider_request_id':'SYNTHETIC_INVALID_RECEIPT'}
    calls=[]
    async def cancelled(*args,**kwargs):
        calls.append(True)
        raise JevCancelledError(result)
    monkeypatch.setattr(runtime.provider,'judge',cancelled)
    execution=importlib.import_module('cn_contract.assistant.providers.judge_execution')
    async def exercise():
        with pytest.raises(asyncio.CancelledError):
            await execution.execute_attempt(actor,first.id,database,runtime)
        return await execution.execute_attempt(actor,first.id,database,runtime)
    outcome=asyncio.run(exercise())
    assert calls==[True] and outcome.state=='sent_unknown' and outcome.decision is None
    assert outcome.receipt.result.usage is None and outcome.receipt.result.provider_request_id is None
    assert outcome.receipt.occupied_usd==Decimal('.02') and outcome.receipt.result.answers=={}
