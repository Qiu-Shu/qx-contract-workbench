"""Synthetic persistent profile attempts; only explicit local HTTP is exercised."""
import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import profile_preparation_service, profile_store, service
from cn_contract.assistant.providers import attempts, history, profile_preparation
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.policy import MainModelRuntime, encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.runner import execute_attempt
from cn_contract.intake import service as intake
from cn_contract.security import ServiceError, authenticate, login
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.unit.test_assistant_profile_codec import candidate, fixture, response
from tests.integration.test_assistant_profile_sources import state
from tests.integration.test_assistant_storage import add_matter


@pytest.fixture
def profile_world(world):
    database, actor, conversation, request, _ = world
    with database.session() as db:
        conversation = service.save_draft(actor, conversation.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=conversation.scope, expected_composer_revision=conversation.composer_revision,
            content='甲称借款35000元。'), db)
    request = request.model_copy(update={'content':conversation.draft_input,
        'expected_scope':conversation.scope, 'expected_composer_revision':conversation.composer_revision})
    return database, actor, conversation, request


def authorize(world, provider, *, project_intake=False, max_total_usd='1'):
    database, actor, conversation, request = world
    with database.session() as db:
        basis = profile_preparation_service.build_profile_basis(actor, conversation.scope.conversation_id,
            request, db, config=provider.config, project_intake=project_intake)
    registry = MainModelRegistry()
    registry.configure(provider)
    policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=conversation.scope.workspace_id,
        actor_id=actor.user_id, config_sha256=sha(encoded(provider.config)),
        allowed_content_sha256s=(profile_preparation.basis_digest(basis),), max_total_usd=max_total_usd,
        max_calls=1, expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    registry.grant(policy, actor.session_id, basis=basis)
    return registry, registry.resolve(actor, basis.expected_scope), basis, policy


def enqueue(world, runtime, *, project_intake=False):
    database, actor, conversation, request = world
    assert hasattr(attempts, 'enqueue_profile'), 'profile ledger entry is not implemented'
    with database.session() as db:
        return attempts.enqueue_profile(actor, conversation.scope.conversation_id, request, db, runtime,
                                        project_intake=project_intake)


def unsent_provider():
    return DeepSeekProvider.for_synthetic_loopback(config(),
        lambda: pytest.fail('unexpected provider call'), 'http://127.0.0.1:1/chat/completions')


def archive_response():
    request = fixture()[1]
    value = candidate()
    value['profile_changes'].append({'field':'consultation',
        'value':{'kind':'text', 'value':request.content}, 'origin':'user_statement',
        'quotes':[{'start':0, 'end':len(request.content), 'quote':request.content}]})
    return response(request, value)


@contextmanager
def denied(code):
    with pytest.raises(ServiceError) as failure:
        yield
    assert failure.value.code == code


def no_archive(database):
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_handlers')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0
        assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0


def test_profile_attempt_sends_once_and_atomically_saves_unverified_profile_and_history(profile_world):
    database, actor, conversation, request = profile_world
    with server(archive_response()) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, basis, _ = authorize(profile_world, provider, project_intake=True)
            first = enqueue(profile_world, runtime, project_intake=True)
            assert first.state == 'reserved' and first.output is None
            assert enqueue(profile_world, runtime, project_intake=True) == first
            result = await execute_attempt(actor, first.id, database, runtime)
            assert type(result) is d.MainProfileAttemptView and result.input_format == 'profile-text-v1'
            assert result.state == 'received' and result.receipt.usage.total_tokens == 42
            assert result.output.candidate.profile_patch.changes[0].verification == 'unverified'
            assert await execute_attempt(actor, first.id, database, runtime) == result
            assert enqueue(profile_world, runtime, project_intake=True) == result
            with database.session() as db:
                saved_input = attempts._input(attempts._row(first.id, db))
                current = service._owned(actor, conversation.scope.conversation_id, db)
                views = history.read_history(actor, current, d.MainGenerationHistoryQuery(
                    message_ids=(saved_input.request.message_id,)), db)
                assert type(views.items[0].attempt) is d.MainProfileAttemptView
                assert views.model_dump(mode='json')['items'][0]['attempt']['output']['candidate']['profile_patch']
                handler = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().one()
                assert handler['outcome'] == 'applied' and handler['profile_receipt_sequence'] == 1
                assert handler['basis_sha256'] == profile_preparation.basis_digest(basis)
                assert db.scalar(text('SELECT count(*) FROM assistant_model_receipts')) == 1
                assert db.scalar(text('SELECT count(*) FROM assistant_model_outputs')) == 1
                assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 1
                assert service.get_run(actor, first.run_id, db).state == 'completed'
                assert saved_input.wire_payload_json.encode() == received[0]['body']
            profile = profile_store.read_profile(actor, conversation.scope.conversation_id, database=database)
            assert profile.revision == 1 and profile.fields[0].verification == 'unverified'
        asyncio.run(scenario())
        assert len(received) == 1


def test_history_roundtrip_preserves_legacy_plain_and_new_profile_shapes():
    scope = fixture()[1].scope
    values = dict(id=uuid4(), run_id=uuid4(), scope=scope, state='reserved', reserved_usd='0.1',
                  receipt=None, output=None)
    for kind in (d.MainAttemptView, d.MainContextAttemptView, d.MainProfileAttemptView):
        attempt = kind(**values)
        history_item = d.MainGenerationHistoryItem(message_id=uuid4(), attempt=attempt)
        raw = history_item.model_dump_json()
        roundtrip = d.MainGenerationHistoryItem.model_validate_json(raw)
        assert type(roundtrip.attempt) is kind
        assert roundtrip.attempt.model_dump(mode='json') == attempt.model_dump(mode='json')


def test_budget_rejection_preserves_current_draft_without_partial_message(profile_world):
    database, _, _, _ = profile_world
    async def scenario():
        _, runtime, _, _ = authorize(profile_world, unsent_provider(), max_total_usd='0.000001')
        before = state(database)
        with denied('BUDGET_EXCEEDED'):
            enqueue(profile_world, runtime)
        assert state(database) == before
    asyncio.run(scenario())


@pytest.mark.parametrize('upgrade', ['plain_message', 'plain_attempt'])
def test_existing_plain_message_or_attempt_cannot_be_upgraded_to_profile(profile_world, upgrade):
    database, actor, conversation, request = profile_world
    async def scenario():
        provider = unsent_provider()
        _, runtime, _, policy = authorize(profile_world, provider)
        with database.session() as db:
            if upgrade == 'plain_message':
                service.save_message(actor, conversation.scope.conversation_id, request, db)
            else:
                plain_policy = policy.model_copy(update={'allowed_content_sha256s':(sha(request.content),)})
                attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db,
                                            MainModelRuntime(provider, plain_policy))
        before = state(database)
        with denied('STATE_CONFLICT' if upgrade == 'plain_message' else 'VERSION_CONFLICT'):
            enqueue(profile_world, runtime)
        assert state(database) == before
    asyncio.run(scenario())


def test_plain_replay_cannot_retrieve_profile_attempt_even_with_matching_policy(profile_world):
    database, actor, conversation, request = profile_world
    async def scenario():
        provider = unsent_provider()
        _, runtime, _, policy = authorize(profile_world, provider)
        first = enqueue(profile_world, runtime)
        with database.session() as db:
            with denied('VERSION_CONFLICT'):
                attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db,
                                            MainModelRuntime(provider, policy))
            assert attempts.read_attempt(actor, first.id, db) == first
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['project_intake', 'content', 'new_policy'])
def test_profile_replay_cannot_change_save_plan_content_or_policy(profile_world, change):
    database, actor, conversation, request = profile_world
    async def scenario():
        provider = unsent_provider()
        registry, runtime, basis, policy = authorize(profile_world, provider)
        first = enqueue(profile_world, runtime)
        changed_request = request.model_copy(update={'content':'完全不同的合成内容'}) if change == 'content' else request
        if change == 'new_policy':
            registry.grant(policy.model_copy(update={'policy_id':uuid4()}), actor.session_id, basis=basis)
            runtime = registry.resolve(actor, basis.expected_scope)
        with database.session() as db:
            with denied('VERSION_CONFLICT'):
                attempts.enqueue_profile(actor, conversation.scope.conversation_id, changed_request, db, runtime,
                                         project_intake=change == 'project_intake')
            assert attempts.read_attempt(actor, first.id, db) == first
    asyncio.run(scenario())


@pytest.mark.parametrize('mode', ['cancel', 'revoke', 'recover_reserved', 'recover_sending'])
def test_cancel_revoke_and_recovery_seal_attempt_without_resend(profile_world, mode):
    database, actor, _, _ = profile_world
    async def scenario():
        registry, runtime, _, policy = authorize(profile_world, unsent_provider())
        first = enqueue(profile_world, runtime)
        with database.session() as db:
            if mode == 'cancel':
                service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
            elif mode.startswith('recover'):
                if mode == 'recover_sending':
                    assert attempts.claim(actor, first.id, db, runtime)
                assert attempts.recover_attempts(db) == 1
                assert attempts.recover_attempts(db) == 0
        if mode == 'revoke':
            registry.revoke(actor.session_id)
        result = await execute_attempt(actor, first.id, database, runtime)
        unknown = mode == 'recover_sending'
        assert result.state == ('sent_unknown' if unknown else 'failed_before_send')
        assert result.receipt.cost_status == ('unknown' if unknown else 'not_sent')
        assert result.output is None
        assert await execute_attempt(actor, first.id, database, runtime) == result
        with database.session() as db:
            used, calls = attempts._budget(policy, db)
            assert calls == (1 if unknown else 0)
            assert (used > 0) is unknown
        no_archive(database)
    asyncio.run(scenario())


def test_concurrent_execute_claims_once_while_another_connection_can_write(profile_world):
    database, actor, conversation, _ = profile_world
    with server(response(fixture()[1]), pause=.2) as (url, received, seen):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            task = asyncio.create_task(execute_attempt(actor, first.id, database, runtime))
            for _ in range(100):
                if seen.is_set():
                    break
                await asyncio.sleep(.005)
            assert seen.is_set()
            second = await execute_attempt(actor, first.id, database, runtime)
            assert second.state == 'sending' and second.receipt is None
            def type_next_draft():
                with database.session() as db:
                    current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                    service.save_draft(actor, conversation.scope.conversation_id, d.AssistantDraftInput(
                        expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                        content='网络等待中另记草稿，不属于已发送正文。'), db)
            await asyncio.wait_for(asyncio.to_thread(type_next_draft), 2)
            result = await task
            assert result.output is not None
            with database.session() as db:
                current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                assert current.draft_input == '网络等待中另记草稿，不属于已发送正文。'
        asyncio.run(scenario())
        assert len(received) == 1


@pytest.mark.parametrize('change', ['scope', 'source', 'cancel', 'profile', 'session', 'intake', 'registry'])
def test_inflight_changes_keep_fees_but_discard_profile_and_handler(profile_world, change):
    database, actor, conversation, request = profile_world
    if change == 'intake':
        with database.session() as db:
            target = intake.create(d.IntakeCreateInput(request_id=uuid4(), draft=d.IntakeDraft(title='合成接待')), actor, db)
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:target WHERE id=:id'),
                       {'target':str(target.id), 'id':str(conversation.scope.conversation_id)})
    with server(response(fixture()[1]), pause=.2) as (url, received, seen):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            registry, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            task = asyncio.create_task(execute_attempt(actor, first.id, database, runtime))
            for _ in range(100):
                if seen.is_set():
                    break
                await asyncio.sleep(.005)
            assert seen.is_set()
            if change == 'registry':
                registry.revoke(actor.session_id)
            else:
                with database.session() as db:
                    if change == 'scope':
                        db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),
                                   {'id':str(conversation.scope.conversation_id)})
                    elif change == 'source':
                        db.execute(text('DROP TRIGGER immutable_assistant_messages_update'))
                        db.execute(text("UPDATE assistant_messages SET content='被替换的合成原话' WHERE conversation_id=:id"),
                                   {'id':str(conversation.scope.conversation_id)})
                    elif change == 'cancel':
                        service.cancel_run(actor, first.run_id, d.AssistantCancelInput(request_id=uuid4()), db)
                    elif change == 'session':
                        db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
                    elif change == 'intake':
                        intake.save(target.id, d.IntakeUpdateInput(expected_revision=1,
                            draft=d.IntakeDraft(title='在途人工修改接待')), actor, db)
                    else:
                        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
                        profile_store._commit(actor, d.ProfileCommitInput(request_id=uuid4(),
                            patch=d.ProfilePatch(scope=current.scope, base_profile_revision=0),
                            manual_edits=(d.ProfileEdit(field='title', value={'kind':'text','value':'在途人工档案'}),)),
                            d.ProfileSourceSnapshot(scope=current.scope), db)
            if change == 'session':
                with denied('AUTHORIZATION_REQUIRED'):
                    await task
                with database.session() as db:
                    token, _ = login('lawyer', 'fixture123', db)
                    fresh = authenticate(token, db)
                    result = attempts.read_attempt(fresh, first.id, db)
            else:
                result = await task
            assert result.receipt.cost_status == 'estimated' and result.receipt.usage.total_tokens == 42
            assert result.output is None
            with database.session() as db:
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_handlers')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == (1 if change == 'profile' else 0)
        asyncio.run(scenario())
        assert len(received) == 1


@pytest.mark.parametrize('mode', ['cancel_task', 'timeout'])
def test_runner_interruption_preserves_unknown_cost_without_retry(profile_world, mode):
    database, actor, _, _ = profile_world
    with server(response(fixture()[1]), pause=2) as (url, received, seen):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(timeout_seconds=1), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            task = asyncio.create_task(execute_attempt(actor, first.id, database, runtime))
            if mode == 'cancel_task':
                for _ in range(100):
                    if seen.is_set():
                        break
                    await asyncio.sleep(.005)
                assert seen.is_set()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
            with database.session() as db:
                result = attempts.read_attempt(actor, first.id, db)
            assert result.state == 'sent_unknown' and result.output is None
            assert result.receipt.cost_status == 'unknown' and result.receipt.estimated_cost_usd is None
            assert await execute_attempt(actor, first.id, database, runtime) == result
            no_archive(database)
        asyncio.run(scenario())
        assert len(received) == 1


def test_valid_empty_patch_records_unchanged_handler_once_without_inventing_profile(profile_world):
    database, actor, _, _ = profile_world
    with server(response(fixture()[1], {'text':'未增加事实，请继续核对。', 'citations':[], 'profile_changes':[]})) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            result = await execute_attempt(actor, first.id, database, runtime)
            assert result.output.candidate.profile_patch.changes == ()
            with database.session() as db:
                handler = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().one()
                assert handler['outcome'] == 'unchanged' and handler['profile_receipt_sequence'] == 1
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 1
                assert service.get_run(actor, first.run_id, db).state == 'completed'
        asyncio.run(scenario())
        assert len(received) == 1


@pytest.mark.parametrize('failure', ['version_conflict', 'save_failed', 'denial_audit'])
def test_save_failure_preserves_answer_fees_and_one_blocked_handler(profile_world, monkeypatch, failure):
    from cn_contract.security import deny
    database, actor, _, _ = profile_world
    matter = add_matter(database, actor) if failure == 'denial_audit' else None
    with database.session() as db:
        previous_audits = db.scalar(text('SELECT count(*) FROM audit_events'))
    calls = []
    def fail_save(caller, request, sources, db):
        calls.append(request.request_id)
        if failure == 'denial_audit':
            deny(caller, matter, 'authorization_denied', db)
        if failure == 'version_conflict':
            raise ServiceError('VERSION_CONFLICT', 409)
        raise ValueError('synthetic private save failure')
    monkeypatch.setattr(profile_store, '_commit', fail_save)
    with server(response(fixture()[1])) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider, project_intake=True)
            first = enqueue(profile_world, runtime, project_intake=True)
            result = await execute_attempt(actor, first.id, database, runtime)
            assert result.output is not None and result.receipt.usage.total_tokens == 42
            assert 'synthetic private save failure' not in result.model_dump_json()
            assert enqueue(profile_world, runtime, project_intake=True) == result
            assert await execute_attempt(actor, first.id, database, runtime) == result
            with database.session() as db:
                handler = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().one()
                assert handler['outcome'] == 'blocked' and handler['profile_receipt_sequence'] is None
                assert handler['reason_code'] == ('version_conflict' if failure == 'version_conflict' else 'save_failed')
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_receipts')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_profile_revisions')) == 0
                assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_model_receipts')) == 1
                assert db.scalar(text('SELECT count(*) FROM assistant_model_outputs')) == 1
                assert db.scalar(text('SELECT count(*) FROM audit_events')) == previous_audits+(failure == 'denial_audit')
        asyncio.run(scenario())
        assert len(received) == len(calls) == 1


@pytest.mark.parametrize('table', ['assistant_model_receipts', 'assistant_model_outputs', 'assistant_profile_handlers'])
def test_final_ledger_failure_rolls_back_saved_profile_intake_and_all_receipts(profile_world, table):
    from sqlalchemy.exc import IntegrityError
    database, actor, _, _ = profile_world
    with database.session() as db:
        db.execute(text('CREATE TRIGGER synthetic_reject_ledger BEFORE INSERT ON '+table+
                        " BEGIN SELECT RAISE(ABORT,'synthetic ledger failure'); END"))
    with server(archive_response()) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider, project_intake=True)
            first = enqueue(profile_world, runtime, project_intake=True)
            with database.session() as db:
                token, saved_input, configured = attempts.claim(actor, first.id, db, runtime)
            reply = await runtime.provider.generate_profile(saved_input, expected_config=configured)
            with database.session() as db:
                # The caller catches the error and commits its outer transaction.
                with pytest.raises(IntegrityError):
                    attempts.settle(actor, first.id, token, reply, db, runtime)
            no_archive(database)
            with database.session() as db:
                assert db.scalar(text('SELECT count(*) FROM intake_cases')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_model_receipts')) == 0
                assert db.scalar(text('SELECT count(*) FROM assistant_model_outputs')) == 0
                assert db.scalar(text("SELECT count(*) FROM assistant_run_events WHERE event_type='response.ready'")) == 0
                assert attempts.read_attempt(actor, first.id, db).state == 'sending'
        asyncio.run(scenario())
        assert len(received) == 1


@pytest.mark.parametrize('invalid', ['message_source', 'answer_citation', 'usage_envelope'])
def test_invalid_provider_candidate_keeps_received_cost_without_profile_handler(profile_world, invalid):
    from cn_contract.assistant.providers.profile_codec import decode_response
    database, actor, _, _ = profile_world
    async def scenario():
        provider = unsent_provider()
        calls = []
        async def generate_profile(request, *, expected_config, preflight):
            calls.append(request.run_id)
            assert preflight() is True
            reply = decode_response(response(request), request, expected_config, KEY)
            if invalid == 'usage_envelope':
                return reply.model_copy(update={'usage':d.MainUsage(prompt_tokens=1000000,
                    completion_tokens=0, total_tokens=1000000)})
            output = reply.output
            if invalid == 'answer_citation':
                output = output.model_copy(update={'citations':(d.MainCitation(message_id=request.message_id,
                    quote_sha256=request.source_sha256),)})
            else:
                proposal = output.profile_patch.changes[0]
                proposal = proposal.model_copy(update={'source_refs':(proposal.source_refs[0].model_copy(
                    update={'message_id':uuid4()}),)})
                output = output.model_copy(update={'profile_patch':output.profile_patch.model_copy(
                    update={'changes':(proposal,)})})
            return reply.model_copy(update={'output':output})
        provider.generate_profile = generate_profile
        _, runtime, _, _ = authorize(profile_world, provider)
        first = enqueue(profile_world, runtime)
        result = await execute_attempt(actor, first.id, database, runtime)
        assert result.receipt.cost_status == 'estimated' and result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
        assert result.receipt.usage.total_tokens == (1000000 if invalid == 'usage_envelope' else 42)
        assert result.output is None
        assert await execute_attempt(actor, first.id, database, runtime) == result
        no_archive(database)
        assert len(calls) == 1
    asyncio.run(scenario())


def test_permission_change_after_save_rollback_keeps_audit_and_fees_without_adoption(profile_world, monkeypatch):
    from cn_contract.security import deny
    database, actor, _, _ = profile_world
    matter = add_matter(database, actor)
    with database.session() as db:
        previous_audits = db.scalar(text('SELECT count(*) FROM audit_events'))
    def reject_after_durable_revocation(caller, request, sources, db):
        # Model the transaction-ending denial seam plus a committed revocation.
        db.rollback()
        db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
        db.commit()
        deny(caller, matter, 'authorization_denied', db)
    monkeypatch.setattr(profile_store, '_commit', reject_after_durable_revocation)
    with server(response(fixture()[1])) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            with denied('AUTHORIZATION_REQUIRED'):
                await execute_attempt(actor, first.id, database, runtime)
            with database.session() as db:
                token, _ = login('lawyer', 'fixture123', db)
                fresh = authenticate(token, db)
                result = attempts.read_attempt(fresh, first.id, db)
                assert result.output is None and result.receipt.usage.total_tokens == 42
                assert result.receipt.cost_status == 'estimated'
                assert db.scalar(text('SELECT count(*) FROM audit_events')) == previous_audits+1
            no_archive(database)
        asyncio.run(scenario())
        assert len(received) == 1
