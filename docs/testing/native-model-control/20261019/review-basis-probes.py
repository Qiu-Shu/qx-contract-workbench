"""Independent synthetic basis probes; no real model and no product mutation."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.policy import sha
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.assistant_generation import _capability
from tests.integration.test_assistant_generation import world
from tests.integration.test_native_model_control import native, configure, enqueue


@pytest.mark.parametrize('change', ['other-conversation', 'same-text-new-composer'])
def test_capability_cannot_advertise_ready_for_a_draft_outside_the_approved_basis(native, change):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        with n.database.session() as db:
            draft = n.draft
            if change == 'other-conversation':
                draft = service.create_conversation(n.actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            draft = service.save_draft(n.actor, draft.scope.conversation_id,
                d.AssistantDraftInput(expected_scope=draft.scope,
                    expected_composer_revision=draft.composer_revision, content=n.request.content), db)
            row = service._owned(n.actor, draft.scope.conversation_id, db)
            capability = _capability(n.actor, row, db, n.registry, SimpleNamespace(accepting=True))
            request = n.request.model_copy(update={'expected_scope': draft.scope,
                'expected_composer_revision': draft.composer_revision})
            with pytest.raises(ServiceError):
                attempts.enqueue_generation(n.actor, draft.scope.conversation_id, request, db,
                    n.registry.resolve(n.actor, draft.scope))
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert capability.state == 'unapproved', f'capability falsely advertised {capability.state}'
        assert n.providers[0].calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['configure', 'revoke'])
def test_inflight_control_change_retains_receipt_without_rebinding_provider_or_result(native, change):
    n = native
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        lease = n.registry.resolve(n.actor, n.draft.scope)
        attempt = enqueue(n, lease)
        entered, release = asyncio.Event(), asyncio.Event()
        original = n.providers[0].generate
        async def waiting(request, **kwargs):
            entered.set()
            await release.wait()
            return await original(request, **kwargs)
        n.providers[0].generate = waiting
        task = asyncio.create_task(execute_attempt(n.actor, attempt.id, n.database, lease))
        await asyncio.wait_for(entered.wait(), 2)
        if change == 'configure': configure(n)
        else: n.control.revoke({'session_token': n.token})
        release.set()
        completed = await asyncio.wait_for(task, 2)
        assert completed.receipt.cost_status == 'estimated'
        assert completed.output is None
        assert len(n.providers[0].calls) == 1
        assert all(provider.calls == [] for provider in n.providers[1:])
        with n.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
    asyncio.run(scenario())


def test_revoke_one_session_keeps_second_session_independent(native):
    n = native
    with n.database.session() as db:
        other_token, _ = login('lawyer', 'fixture123', db)
        other_actor = authenticate(other_token, db)
        other = service.create_conversation(other_actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        other = service.save_draft(other_actor, other.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=other.scope, expected_composer_revision=0,
                content=n.request.content), db)
    async def scenario():
        payload = configure(n)
        n.control.authorize(payload)
        first_lease = n.registry.resolve(n.actor, n.draft.scope)
        other_request = n.request.model_copy(update={'request_id': uuid4(), 'expected_scope': other.scope,
            'expected_composer_revision': other.composer_revision})
        second_payload = {**payload, 'session_token': other_token, 'basis': {
            'request_id': str(other_request.request_id), 'expected_scope': other.scope.model_dump(mode='json'),
            'expected_composer_revision': other.composer_revision, 'content_sha256': sha(other_request.content)}}
        n.control.authorize(second_payload)
        second_lease = n.registry.resolve(other_actor, other.scope)
        assert second_lease.snapshot()[1].policy_id != first_lease.snapshot()[1].policy_id
        n.control.revoke({'session_token': n.token})
        with pytest.raises(ServiceError): first_lease.snapshot()
        with n.database.session() as db:
            second = attempts.enqueue_generation(other_actor, other.scope.conversation_id, other_request, db, second_lease)
        completed = await execute_attempt(other_actor, second.id, n.database, second_lease)
        assert completed.output is not None and len(n.providers[0].calls) == 1
    asyncio.run(scenario())
