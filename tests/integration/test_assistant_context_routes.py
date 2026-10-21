"""Context generation route: fixed server format, 202 lifecycle, no client format choice."""
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from cn_contract.web import local_server
from tests.integration.test_assistant_context_send import context_world
from tests.integration.test_assistant_generation_routes import signin
from tests.integration.test_assistant_library_adapter import library


def read_attempt(client, identifier):
    response = client.get('/api/assistant/attempts/'+identifier)
    assert response.status_code == 200, response.text
    return response.json()


def test_context_generation_route_executes_replays_and_rejects_changes(context_world, tmp_path):
    database, actor, view, submission, basis, runtime = context_world
    root = Path(database.engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path,
                                       assistant_model_runtime=runtime)
    with TestClient(app) as client:
        headers = signin(client)
        url = '/api/assistant/conversations/'+str(view.scope.conversation_id)
        body = submission.model_dump(mode='json')
        response = client.post(url+'/context-generations', headers=headers, json=body)
        assert response.status_code == 202, response.text
        first = response.json()
        assert first['input_format'] == 'library-context-v1' and 'input_format' not in body
        deadline = time.monotonic() + 10
        current = read_attempt(client, first['id'])
        while current['state'] in ('reserved', 'sending') and time.monotonic() < deadline:
            time.sleep(0.05)
            current = read_attempt(client, first['id'])
        assert current['state'] == 'received' and current['output'] is not None
        # Idempotent replay returns the same attempt; any change conflicts.
        replay = client.post(url+'/context-generations', headers=headers, json=body)
        assert replay.status_code == 202 and replay.json()['id'] == first['id']
        changed = client.post(url+'/context-generations', headers=headers,
                              json={**body, 'content': '换一个合成问题'})
        assert changed.status_code == 409 and changed.json()['code'] == 'VERSION_CONFLICT'
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_judge_attempts')) == 0
        assert len(runtime.provider.context_calls) == 1 and runtime.provider.calls == []


def test_context_generation_route_requires_signin_and_existing_conversation(context_world, tmp_path):
    database, _, view, submission, _, runtime = context_world
    root = Path(database.engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path,
                                       assistant_model_runtime=runtime)
    with TestClient(app) as client:
        url = '/api/assistant/conversations/'+str(view.scope.conversation_id)
        body = submission.model_dump(mode='json')
        assert client.post(url+'/context-generations', json=body).status_code == 401
        from uuid import uuid4
        other = '/api/assistant/conversations/'+str(uuid4())+'/context-generations'
        response = client.post(other, headers=signin(client), json=body)
        assert response.status_code in (403, 404)
        assert runtime.provider.context_calls == []
