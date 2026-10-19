"""Independent synthetic Standards probes; no real provider or network."""
import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI
import pytest
from sqlalchemy import text

from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError
from cn_contract.storage_bootstrap import initialize_storage
from cn_contract.web.assistant_generation import attach_generation
from cn_contract.web.demo_server import attach_job_worker
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import boot, save_draft


def add_fence(database):
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64,
            manifest_sha256='b'*64, payload='{"synthetic":true}'))


def test_previous_startup_failure_stops_worker_and_disposes(world, monkeypatch):
    database, _, _, _, runtime = world
    initialize_storage(database)
    app = FastAPI()
    disposed = []
    dispose = database.engine.dispose
    def observed_dispose():
        disposed.append(True)
        assert not app.state.worker_thread.is_alive()
        dispose()
    monkeypatch.setattr(database.engine, 'dispose', observed_dispose)
    @asynccontextmanager
    async def failed_start(application):
        raise RuntimeError('SYNTHETIC_START_FAILURE')
        yield
    app.router.lifespan_context = failed_start
    attach_generation(app, database, runtime)
    attach_job_worker(app, database)
    async def scenario():
        with pytest.raises(RuntimeError, match='SYNTHETIC_START_FAILURE'):
            async with app.router.lifespan_context(app):
                pytest.fail('startup failure admitted application')
        assert not app.state.assistant_generation_tasks.accepting
        assert app.state.assistant_generation_tasks.active_count == 0
        assert not runtime.provider.calls
    asyncio.run(scenario())
    assert disposed


def test_previous_teardown_failure_cannot_skip_generation_and_worker_close(world):
    database, actor, conversation, message, runtime = world
    initialize_storage(database)
    app = FastAPI()
    @asynccontextmanager
    async def failed_exit(application):
        try:
            yield
        finally:
            raise RuntimeError('SYNTHETIC_EXIT_FAILURE')
    app.router.lifespan_context = failed_exit
    attach_generation(app, database, runtime)
    attach_job_worker(app, database)
    async def scenario():
        entered = asyncio.Event()
        async def waiting(request, **kwargs):
            runtime.provider.calls.append(request)
            entered.set()
            await asyncio.Event().wait()
        runtime.provider.generate = waiting
        with pytest.raises(RuntimeError, match='SYNTHETIC_EXIT_FAILURE'):
            async with app.router.lifespan_context(app):
                manager = app.state.assistant_generation_tasks
                attempt = manager.submit(actor, conversation.scope.conversation_id, message)
                await asyncio.wait_for(entered.wait(), 3)
        assert not manager.accepting and manager.active_count == 0
        assert not app.state.worker_thread.is_alive()
        with database.session() as db:
            assert db.scalar(text('SELECT state FROM assistant_model_attempts WHERE id=:id'),
                {'id':str(attempt.id)}) == 'sent_unknown'
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
        assert len(runtime.provider.calls) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('phase', ['before_submit', 'before_runner', 'inflight'])
def test_late_restore_fence_blocks_new_registration_or_background_writes(world, phase):
    database, actor, conversation, message, runtime = world
    manager = GenerationTasks(database, runtime)
    async def scenario():
        manager.start()
        if phase == 'before_submit':
            add_fence(database)
            with pytest.raises(ServiceError) as rejected:
                manager.submit(actor, conversation.scope.conversation_id, message)
            assert rejected.value.code == 'BLOCKED_LIVE'
            await manager.close()
            with database.session() as db:
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert not runtime.provider.calls
            return
        entered = asyncio.Event()
        async def waiting(request, **kwargs):
            runtime.provider.calls.append(request)
            entered.set()
            await asyncio.Event().wait()
        runtime.provider.generate = waiting
        attempt = manager.submit(actor, conversation.scope.conversation_id, message)
        if phase == 'inflight':
            await asyncio.wait_for(entered.wait(), 3)
        add_fence(database)
        await manager.close()
        with database.session() as db:
            state = db.scalar(text('SELECT state FROM assistant_model_attempts WHERE id=:id'),
                {'id':str(attempt.id)})
            assert state == ('sending' if phase == 'inflight' else 'reserved')
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
        assert manager.last_error == 'GENERATION_TASK_FAILED'
        assert not manager.accepting and manager.active_count == 0
        assert len(runtime.provider.calls) == int(phase == 'inflight')
    asyncio.run(scenario())


def test_capability_with_real_transport_class_never_resolves_credential(world, tmp_path):
    runtime = world[-1]
    calls = []
    def forbidden_resolver():
        calls.append(True)
        raise AssertionError('capability cannot read credentials')
    runtime.provider = DeepSeekProvider(runtime.provider.config, forbidden_resolver)
    with boot(world, tmp_path) as http:
        save_draft(http)
        for _ in range(3):
            response = http.client.get(http.url+'/generation-capability')
            assert response.status_code == 200
            assert response.json()['state'] == 'ready'
        assert not calls
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
