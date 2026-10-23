"""Independent synthetic Spec probes; no sockets or real storage."""
import asyncio
import copy
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service, profile_store
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.assistant.providers import attempts, profile_codec
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import (
    profile_world, authorize, enqueue, unsent_provider,
)
from tests.integration.test_assistant_main_provider import KEY
from tests.unit.test_assistant_profile_codec import candidate, response
from tests.integration.test_assistant_attachment_backup import corrupt


def next_draft(current_world):
    database, actor, old, _ = current_world
    with database.session() as db:
        view = service.read_conversation(actor, old.scope.conversation_id, db)
        view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content='甲称借款35000元。'), db)
    request = d.AssistantMessageInput(request_id=uuid4(), expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, content=view.draft_input)
    return database, actor, view, request


def claim_and_reply(current_world, runtime, first):
    database, actor, _, _ = current_world
    with database.session() as db:
        token, prepared, config = attempts.claim(actor, first.id, db, runtime)
    reply = profile_codec.decode_response(response(prepared.request), prepared.request, config, KEY)
    assert reply.output is not None
    return token, prepared, reply


def assert_integrity(database):
    with database.session() as db:
        validate_model_records(db)


def test_valid_wire_candidate_cannot_persist_an_unreadable_expanded_output(profile_world):
    database, actor, _, _ = profile_world
    async def scenario():
        provider = unsent_provider()
        _, runtime, _, _ = authorize(profile_world, provider)
        first = enqueue(profile_world, runtime)
        with database.session() as db:
            token, prepared, config = attempts.claim(actor, first.id, db, runtime)
        value = candidate()
        change = value['profile_changes'][0]
        change['quotes'] = [copy.deepcopy(change['quotes'][0]) for _ in range(40)]
        value['profile_changes'] = [copy.deepcopy(change) for _ in range(30)]
        raw = response(prepared.request, value)
        assert len(raw) < config.max_response_bytes
        reply = profile_codec.decode_response(raw, prepared.request, config, KEY)
        assert reply.output is not None and reply.usage.total_tokens == 42
        with database.session() as db:
            attempts.settle(actor, first.id, token, reply, db, runtime)
        with database.session() as db:
            # Valid provider output must remain readable or be rejected before
            # storing candidate/profile; received usage must survive either way.
            result = attempts.read_attempt(actor, first.id, db)
            assert result.receipt.usage.total_tokens == 42

    asyncio.run(scenario())


def test_two_rounds_are_two_explicit_approved_messages_and_preserve_both_histories(profile_world):
    database, actor, _, _ = profile_world
    async def scenario():
        current = profile_world
        refs = []
        for _ in range(2):
            _, runtime, basis, _ = authorize(current, unsent_provider(), project_intake=True)
            first = enqueue(current, runtime, project_intake=True)
            token, prepared, reply = claim_and_reply(current, runtime, first)
            with database.session() as db:
                attempts.settle(actor, first.id, token, reply, db, runtime)
            assert_integrity(database)
            refs.append((first, basis, prepared))
            current = next_draft(current)
        assert refs[0][1].base_profile_revision == 0
        assert refs[1][1].base_profile_revision == 1
        assert refs[0][2].request.message_id != refs[1][2].request.message_id
        with database.session() as db:
            assert db.scalar(text('SELECT count(*) FROM assistant_profile_handlers')) == 2
            assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 2
            for first, _, _ in refs:
                assert attempts.read_attempt(actor, first.id, db).output is not None
        assert_integrity(database)
    asyncio.run(scenario())


def test_persisted_policy_identity_cannot_be_reused_after_registry_restart(profile_world):
    database, actor, _, _ = profile_world
    async def scenario():
        provider = unsent_provider()
        _, runtime, _, policy = authorize(profile_world, provider)
        first = enqueue(profile_world, runtime)
        token, _, reply = claim_and_reply(profile_world, runtime, first)
        with database.session() as db:
            attempts.settle(actor, first.id, token, reply, db, runtime)
        newer = next_draft(profile_world)
        _, _, new_basis, new_policy = authorize(newer, provider)
        registry = MainModelRegistry()
        registry.configure(provider)
        reused = new_policy.model_copy(update={'policy_id': policy.policy_id})
        registry.grant(reused, actor.session_id, basis=new_basis)
        runtime = registry.resolve(actor, new_basis.expected_scope)
        with pytest.raises((ValueError, ServiceError)):
            enqueue(newer, runtime)
        with database.session() as db:
            assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT count(*) FROM assistant_messages')) == 1
            assert service.read_conversation(actor, newer[2].scope.conversation_id, db).draft_input == newer[3].content
        assert_integrity(database)
    asyncio.run(scenario())


def test_another_live_login_cannot_adopt_a_claimed_sessions_profile_reply(profile_world):
    database, actor, _, _ = profile_world
    async def scenario():
        _, runtime, _, _ = authorize(profile_world, unsent_provider())
        first = enqueue(profile_world, runtime)
        token, _, reply = claim_and_reply(profile_world, runtime, first)
        with database.session() as db:
            secret, _ = login('lawyer', 'fixture123', db)
            fresh = authenticate(secret, db)
            assert fresh.session_id != actor.session_id
            attempts.settle(fresh, first.id, token, reply, db, runtime)
        with database.session() as db:
            result = attempts.read_attempt(actor, first.id, db)
            assert result.receipt.usage.total_tokens == 42 and result.output is None
            assert db.scalar(text('SELECT count(*) FROM assistant_profile_handlers')) == 0
        assert_integrity(database)
    asyncio.run(scenario())


@pytest.mark.parametrize('tamper', ['wrong_ready_case', 'unknown_profile_event',
                                  'handler_created_before_output'])
def test_fixed_handler_history_rejects_extra_or_misordered_events(profile_world, tamper):
    database, actor, _, _ = profile_world
    async def scenario():
        _, runtime, _, _ = authorize(profile_world, unsent_provider())
        first = enqueue(profile_world, runtime)
        token, _, reply = claim_and_reply(profile_world, runtime, first)
        with database.session() as db:
            attempts.settle(actor, first.id, token, reply, db, runtime)
    asyncio.run(scenario())
    assert_integrity(database)
    if tamper == 'handler_created_before_output':
        corrupt(database, 'assistant_profile_handlers',
            "UPDATE assistant_profile_handlers SET created_at='2000-01-01T00:00:00+00:00'")
    elif tamper == 'wrong_ready_case':
        corrupt(database, 'assistant_run_events',
            "UPDATE assistant_run_events SET event_type='RESPONSE.READY' WHERE event_type='response.ready'")
    else:
        with database.session() as db:
            last = db.execute(text('SELECT * FROM assistant_run_events ORDER BY seq DESC LIMIT 1')).mappings().one()
            event = 'profile.unexpected' if tamper == 'unknown_profile_event' else 'response.unexpected'
            db.execute(text('''INSERT INTO assistant_run_events VALUES(:run,:seq,:event,'internal','{}',:at)'''),
                {'run':last['run_id'], 'seq':last['seq']+1, 'event':event, 'at':last['created_at']})
    with pytest.raises(ValueError, match='ASSISTANT_MODEL_INTEGRITY'):
        assert_integrity(database)
