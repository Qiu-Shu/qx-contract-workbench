"""One lifecycle owns both explicitly submitted local and model work."""
import asyncio
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_task_manager import finished


class LocalAdapter:
    def __init__(self):
        self.calls = []
        self.entered, self.release = Event(), Event()
        self.release.set()

    def search(self, query):
        self.calls.append(query)
        self.entered.set()
        assert self.release.wait(5), 'synthetic release missing'
        return d.LibraryCitationPage(query=query, state='not_configured')


def setup(world):
    database, actor, conversation, request, runtime = world
    adapter = LocalAdapter()
    tasks = GenerationTasks(database, None, library_adapter=adapter)
    request = request.model_copy(update={'content':'租赁', 'requested_skill':'legal_research'})
    return tasks, adapter, request


def view(world, identifier):
    from cn_contract.assistant.research import read_research
    with world[0].session() as db:
        return read_research(world[1], identifier, db)


def test_local_submit_without_model_and_replay_never_dispatches_twice(world):
    tasks, adapter, request = setup(world)
    database, actor, conversation, _, runtime = world
    async def scenario():
        tasks.start()
        first = tasks.submit_research(actor, conversation.scope.conversation_id, request)
        assert tasks.active_count == 1 and not adapter.calls
        assert tasks.submit_research(actor, conversation.scope.conversation_id, request) == first
        await finished(tasks)
        result = tasks.submit_research(actor, conversation.scope.conversation_id, request)
        assert result.run.state == 'completed' and len(result.receipts) == 1
        assert len(adapter.calls) == 1 and not runtime.provider.calls
        with database.session() as db:
            for table in ('assistant_model_attempts', 'assistant_model_outputs', 'assistant_judge_attempts'):
                assert db.scalar(text('SELECT COUNT(*) FROM '+table)) == 0
        await tasks.close()
        assert tasks.submit_research(actor, conversation.scope.conversation_id, request) == result
    asyncio.run(scenario())


def test_immediate_close_seals_local_before_dispatch(world):
    tasks, adapter, request = setup(world)
    async def scenario():
        tasks.start()
        first = tasks.submit_research(world[1], world[2].scope.conversation_id, request)
        await tasks.close()
        assert view(world, first.run.id).run.state == 'interrupted'
        assert not adapter.calls and tasks.active_count == 0
    asyncio.run(scenario())


def test_close_waits_for_local_thread_and_rejects_late_publication(world):
    tasks, adapter, request = setup(world)
    adapter.release.clear()
    async def scenario():
        tasks.start()
        first = tasks.submit_research(world[1], world[2].scope.conversation_id, request)
        assert await asyncio.to_thread(adapter.entered.wait, 3)
        closing = asyncio.create_task(tasks.close())
        try:
            await asyncio.sleep(.05)
            assert not closing.done() and not tasks.accepting and tasks.active_count == 1
            assert view(world, first.run.id).run.state == 'interrupted'
        finally:
            adapter.release.set()
            await closing
        result = view(world, first.run.id)
        assert not result.receipts and result.run.state == 'interrupted'
        assert tasks.active_count == 0 and len(adapter.calls) == 1
    asyncio.run(scenario())


def test_local_and_model_share_capacity_and_replay_needs_no_new_slot(world):
    tasks, adapter, request = setup(world)
    tasks.runtime = world[-1]
    database, actor, _, model_request, _ = world
    with database.session() as db:
        conversations = [service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db) for _ in range(5)]
    async def scenario():
        tasks.start()
        for conversation in conversations[:4]:
            tasks.submit_research(actor, conversation.scope.conversation_id, request.model_copy(update={
                'request_id':uuid4(), 'expected_scope':conversation.scope}))
        assert tasks.active_count == 4 and not tasks.accepting
        with pytest.raises(ServiceError) as caught:
            tasks.submit(actor, conversations[4].scope.conversation_id, model_request.model_copy(update={
                'request_id':uuid4(), 'expected_scope':conversations[4].scope}))
        assert caught.value.code == 'ASSISTANT_BUSY'
        await tasks.close()
        assert not adapter.calls and not world[-1].provider.calls
    asyncio.run(scenario())


def test_local_factory_failure_seals_registration_without_retry(world, monkeypatch):
    tasks, adapter, request = setup(world)
    async def scenario():
        tasks.start()
        def fail(coro, **kwargs):
            raise RuntimeError('synthetic factory failure')
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, 'create_task', fail)
            with pytest.raises(ServiceError):
                tasks.submit_research(world[1], world[2].scope.conversation_id, request)
        old = tasks.submit_research(world[1], world[2].scope.conversation_id, request)
        assert old.run.state == 'interrupted' and not adapter.calls
        assert tasks.last_error == 'GENERATION_TASK_FAILED'
        await tasks.close()
    asyncio.run(scenario())
