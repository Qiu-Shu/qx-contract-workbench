"""Native lifespan seals synthetic model attempts before the ordinary worker starts."""
import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import workspace_backup
from cn_contract.ops.storage import quarantined
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web import demo_server, local_server
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world


def enqueue(world, *, another=False):
    database, actor, conversation, request, runtime = world
    with database.session() as db:
        if another:
            conversation = service.create_conversation(actor,
                d.AssistantConversationCreateInput(request_id=uuid4()), db)
            request = request.model_copy(update={'request_id':uuid4(), 'expected_scope':conversation.scope})
        return attempts.enqueue_generation(actor, conversation.scope.conversation_id, request, db, runtime)


def read(world, identifier):
    database, actor, *_ = world
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)


def history(database):
    with database.session() as db:
        return {table: db.execute(text(f'SELECT * FROM {table} ORDER BY rowid')).all() for table in (
            'assistant_model_attempts', 'assistant_model_receipts', 'assistant_model_outputs',
            'assistant_runs', 'assistant_run_events')}


@pytest.mark.parametrize('claimed', [False, True])
def test_native_startup_seals_pending_before_worker_and_never_resends(world, tmp_path, monkeypatch, claimed):
    database, actor, _, _, runtime = world
    pending = enqueue(world)
    if claimed:
        with database.session() as db:
            assert attempts.claim(actor, pending.id, db, runtime) is not None
    done = enqueue(world, another=True)
    completed = asyncio.run(execute_attempt(actor, done.id, database, runtime))
    assert len(runtime.provider.calls) == 1
    completed_before = read(world, done.id)
    root = Path(database.engine.url.database).parent
    expected = 'sent_unknown' if claimed else 'failed_before_send'
    expected_cost = 'unknown' if claimed else 'not_sent'
    worker_starts = []
    original_recover_jobs = demo_server.recover_jobs

    async def unexpected_network(*args, **kwargs):
        pytest.fail('native recovery must not call the live model provider')

    def before_old_worker(worker_database):
        with pytest.raises(ValueError, match='WORKSPACE_IN_USE'):
            with local_server._worker_lock(root):
                pass
        # A separate session must already observe the committed recovery.
        result = read(world, pending.id)
        assert result.state == expected
        assert result.receipt.cost_status == expected_cost
        assert read(world, done.id) == completed_before
        worker_starts.append(True)
        return original_recover_jobs(worker_database)

    monkeypatch.setattr(DeepSeekProvider, 'generate', unexpected_network)
    monkeypatch.setattr(demo_server, 'recover_jobs', before_old_worker)
    with TestClient(local_server.build_local_app(root, data_parent=tmp_path)) as client:
        assert client.get('/login').status_code == 200
        result = read(world, pending.id)
        assert result.output is None
        with database.session() as db:
            assert service.get_run(actor, pending.run_id, db).state == 'interrupted'
        assert asyncio.run(execute_attempt(actor, pending.id, database, runtime)) == result
        assert asyncio.run(execute_attempt(actor, done.id, database, runtime)) == completed
    after_first = history(database)
    with TestClient(local_server.build_local_app(root, data_parent=tmp_path)) as client:
        assert client.get('/login').status_code == 200
    assert history(database) == after_first
    assert worker_starts == [True, True]
    assert len(runtime.provider.calls) == 1


@pytest.mark.parametrize('claimed', [False, True])
def test_restored_native_startup_keeps_model_history_quarantined(world, tmp_path, monkeypatch, claimed):
    database, actor, _, _, runtime = world
    pending = enqueue(world)
    if claimed:
        with database.session() as db:
            attempts.claim(actor, pending.id, db, runtime)
    root = Path(database.engine.url.database).parent
    archive = tmp_path/'synthetic-startup.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    result = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    restored_root = Path(result['restored_root'])
    restored = local_server._database(restored_root)
    before = history(restored)

    def forbidden_recovery(db):
        pytest.fail('native startup must not activate or rewrite a quarantined restored workspace')

    async def unexpected_network(*args, **kwargs):
        pytest.fail('restored startup must not call the live model provider')

    # Restore has already sealed old attempts; ordinary startup must leave it alone.
    monkeypatch.setattr(attempts, 'recover_attempts', forbidden_recovery)
    monkeypatch.setattr(DeepSeekProvider, 'generate', unexpected_network)
    try:
        with TestClient(local_server.build_local_app(restored_root, data_parent=tmp_path)) as client:
            assert client.post('/api/login', json={'username':'lawyer','password':'fixture123'}).status_code == 200
            blocked = client.post('/api/assistant/conversations', json={'request_id':str(uuid4())})
            assert blocked.status_code == 409
            with restored.session() as db:
                assert quarantined(db)
                token, _ = login('lawyer', 'fixture123', db)
                restored_actor = authenticate(token, db)
            with pytest.raises(ServiceError) as denied:
                asyncio.run(execute_attempt(restored_actor, pending.id, restored, runtime))
            assert denied.value.code == 'BLOCKED_LIVE'
        assert history(restored) == before
        assert not runtime.provider.calls
    finally:
        restored.engine.dispose()


def test_native_recovery_failure_rolls_back_and_does_not_start_worker(world, tmp_path, monkeypatch):
    database, *_ = world
    pending = enqueue(world)
    root = Path(database.engine.url.database).parent
    before = history(database)
    recover = attempts.recover_attempts
    worker_starts = []

    def fail_after_recovery(db):
        assert recover(db) == 1
        raise RuntimeError('synthetic recovery failure')

    def forbidden_worker(db):
        worker_starts.append(True)
        pytest.fail('worker must not start after recovery failure')

    monkeypatch.setattr(attempts, 'recover_attempts', fail_after_recovery)
    monkeypatch.setattr(demo_server, 'recover_jobs', forbidden_worker)
    with pytest.raises(RuntimeError, match='synthetic recovery failure'):
        with TestClient(local_server.build_local_app(root, data_parent=tmp_path)):
            pass
    assert not worker_starts
    assert read(world, pending.id).state == 'reserved'
    assert history(database) == before
    # Failure must release the OS lock for a later explicit restart.
    with local_server._worker_lock(root):
        pass
