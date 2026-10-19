"""Independent CH-04B probes. Synthetic workspaces only; no external endpoints."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import remove_membership
from cn_contract.web.assistant_generation import is_generation_read_path
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import boot, DelayedProvider, wait_attempt
from tests.integration.test_assistant_storage import add_matter


def fence(database):
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64,
            manifest_sha256='b'*64, payload='{"independent_synthetic_probe":true}'))


def states(database):
    with database.session() as db:
        return (db.scalar(text('SELECT state FROM assistant_model_attempts')),
            db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')),
            db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')))


def test_two_event_loops_simultaneous_key_registers_one_dispatch(world):
    database, actor, conversation, request, runtime = world
    gate = Barrier(2)

    def submit_on_private_loop():
        async def scenario():
            manager = GenerationTasks(database, runtime)
            manager.start()
            gate.wait(timeout=5)
            attempt = manager.submit(actor, conversation.scope.conversation_id, request)
            async with asyncio.timeout(5):
                while manager.active_count:
                    await asyncio.sleep(0)
            await manager.close()
            return attempt.id
        return asyncio.run(scenario())

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit_on_private_loop) for _ in range(2)]
        identifiers = [future.result(timeout=10) for future in futures]
    assert identifiers[0] == identifiers[1]
    assert len(runtime.provider.calls) == 1
    assert states(database) == ('received', 1, 1)


@pytest.mark.parametrize('started', [False, True])
def test_new_fence_during_manager_shutdown_never_overrides_quarantine(world, started):
    database, actor, conversation, request, runtime = world

    async def scenario():
        entered = asyncio.Event()
        async def waiting(value, **kwargs):
            runtime.provider.calls.append(value)
            entered.set()
            await asyncio.Event().wait()
        runtime.provider.generate = waiting
        manager = GenerationTasks(database, runtime)
        manager.start()
        manager.submit(actor, conversation.scope.conversation_id, request)
        if started:
            await asyncio.wait_for(entered.wait(), 3)
        fence(database)
        await manager.close()
        assert manager.active_count == 0 and not manager.accepting
        assert manager.last_error == 'GENERATION_TASK_FAILED'

    asyncio.run(scenario())
    assert states(database) == ('sending' if started else 'reserved', 0, 0)
    assert len(runtime.provider.calls) == int(started)


def scoped_world(world):
    database, actor, _, request, runtime = world
    matter = add_matter(database, actor)
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), scope_kind='matter', scope_ref=matter), db)
    return (database, actor, conversation,
            request.model_copy(update={'expected_scope':conversation.scope}), runtime), matter


def test_matter_revocation_while_http_body_arrives_stops_registration(world, tmp_path, monkeypatch):
    current, matter = scoped_world(world)
    with boot(current, tmp_path) as http:
        from cn_contract.web import assistant_generation
        async def revoke(request, model):
            with http.database.session() as db:
                remove_membership(matter, current[1].user_id, db)
            return model.model_validate(http.body)
        monkeypatch.setattr(assistant_generation, 'body_input', revoke)
        response = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
        assert response.status_code == 403
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert not current[-1].provider.calls


def test_matter_revocation_after_send_denies_all_new_reads_and_candidate(world, tmp_path):
    current, matter = scoped_world(world)
    runtime = current[-1]
    runtime.provider = DelayedProvider(runtime.provider.config)
    with boot(current, tmp_path) as http:
        response = http.client.post(http.url+'/generations', headers=http.headers, json=http.body)
        assert response.status_code == 202
        attempt = response.json()['id']
        assert runtime.provider.started.wait(2)
        with http.database.session() as db:
            remove_membership(matter, current[1].user_id, db)
        for path in (http.url+'/generation-capability',
                     http.url+'/generations/by-request/'+http.body['request_id'],
                     '/api/assistant/attempts/'+attempt):
            response = http.client.get(path)
            assert response.status_code == 403
            assert '独立合成待核候选' not in response.text
        runtime.provider.release.set()
        # Shutdown drains the owned task without adopting a now-unauthorized result.
    state, receipts, outputs = states(current[0])
    assert state in {'received', 'sent_unknown'} and receipts == 1 and outputs == 0
    assert len(runtime.provider.calls) == 1


def test_restore_whitelist_matches_only_three_exact_canonical_shapes():
    identifier = str(uuid4())
    allowed = ['/api/assistant/attempts/'+identifier,
        '/api/assistant/conversations/'+identifier+'/generation-capability',
        '/api/assistant/conversations/'+identifier+'/generations/by-request/'+identifier]
    for path in allowed:
        assert is_generation_read_path(path)
        for candidate in (path+'/', path+'/extra', path+'?x=1', path+'\n',
                path.replace(identifier, identifier.upper()), path.replace(identifier, 'a'*36),
                path.replace('/api/', '/api//'), path.replace(identifier, '%2f'+identifier),
                path.replace('/assistant/', '/assistant/%2e%2e/')):
            assert not is_generation_read_path(candidate), candidate
    assert not is_generation_read_path('/api/assistant/conversations/'+identifier+'/generations')


def test_failed_generation_start_releases_native_worker_and_workspace_lock(world, tmp_path, monkeypatch):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from cn_contract.web import local_server
    database, _, _, _, runtime = world
    root = Path(database.engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path, assistant_model_runtime=runtime)
    def fail_start(manager):
        raise RuntimeError('SYNTHETIC_START_FAILURE')
    monkeypatch.setattr(GenerationTasks, 'start', fail_start)
    with pytest.raises(RuntimeError, match='SYNTHETIC_START_FAILURE'):
        with TestClient(app):
            pytest.fail('failed startup must not serve requests')
    assert not app.state.worker_thread.is_alive()
    with local_server._worker_lock(root):
        pass
    assert runtime.provider.calls == []


def test_approved_text_over_wire_byte_cap_returns_fixed_client_error(world, tmp_path):
    from pathlib import Path
    from fastapi.testclient import TestClient
    from cn_contract.assistant.providers.policy import sha
    from cn_contract.web import local_server
    from tests.integration.test_assistant_generation_routes import signin
    database, actor, conversation, request, runtime = world
    content = '🦊' * 20000
    request = d.AssistantMessageInput.model_validate({**request.model_dump(mode='python'), 'content':content})
    runtime.policy = d.MainModelPolicy.model_validate({**runtime.policy.model_dump(mode='python'),
        'allowed_content_sha256s':(sha(content),)})
    root = Path(database.engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path, assistant_model_runtime=runtime)
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = signin(client)
        base = '/api/assistant/conversations/'+str(conversation.scope.conversation_id)
        response = client.post(base+'/generations', headers=headers, json=request.model_dump(mode='json'))
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_messages')) == 0
        assert runtime.provider.calls == []
        assert response.status_code in {403, 413, 422}, (response.status_code, response.text)
        assert response.json()['code']
