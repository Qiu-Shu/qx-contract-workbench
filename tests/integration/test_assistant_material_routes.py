"""Authenticated material preview and single-send routes over fictional DOCX data."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.security import authenticate, provision_user
from cn_contract.web import local_server
from test_assistant_generation import world
from test_assistant_generation_routes import signin, wait_attempt
from test_assistant_main_provider import config
from test_assistant_material_generation import material_world, selection_for
from test_contract_c4_material_flow import MaterialProvider, SECRET


@contextmanager
def boot(material_world, tmp_path, runtime=None):
    database, _, cid, _ = material_world
    root = Path(database.engine.url.database).parent
    app = local_server.build_local_app(root, data_parent=tmp_path, assistant_model_runtime=runtime)
    with TestClient(app) as client:
        headers = signin(client)
        yield SimpleNamespace(client=client, database=database, headers=headers, runtime=runtime,
            url='/api/assistant/conversations/'+str(cid))


def body_for(material_world):
    return selection_for(material_world, 'contract').model_dump(mode='json')


def test_preview_submit_replay_and_original_request_lookup(material_world, tmp_path):
    provider = MaterialProvider(config())
    registry = MainModelRegistry(); registry.configure(provider)
    with boot(material_world, tmp_path, registry) as http:
        body = body_for(material_world)
        preview = http.client.post(http.url+'/material-preview', headers=http.headers, json=body)
        assert preview.status_code == 200, preview.text
        basis = d.MainMaterialSendBasis.model_validate(preview.json())
        assert str(basis.request_id) == body['request_id']
        assert basis.manifest.workflow == 'contract'
        with http.database.session() as db:
            actor = authenticate(http.client.cookies.get('qx_session'), db)
        policy = d.MainModelPolicy(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
            actor_id=actor.user_id, config_sha256=sha(encoded(config())),
            allowed_content_sha256s=(basis.manifest_sha256,), max_total_usd='1', max_calls=1,
            expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
        registry.grant(policy, actor.session_id, basis=basis)
        submitted = http.client.post(http.url+'/material-generations', headers=http.headers, json=body)
        assert submitted.status_code == 202, submitted.text
        attempt = submitted.json()
        replay = http.client.post(http.url+'/material-generations', headers=http.headers, json=body)
        assert replay.status_code == 202 and replay.json()['id'] == attempt['id']
        completed = wait_attempt(http, attempt['id'])
        assert completed['state'] == 'received'
        assert completed['output']['manifest'] == preview.json()['manifest']
        found = http.client.get(http.url+'/generations/by-request/'+body['request_id'])
        assert found.status_code == 200 and found.json()['id'] == attempt['id']
        assert len(provider.calls) == 1
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1


def test_unauthorized_preview_and_submit_reject_before_body_read(material_world, tmp_path, monkeypatch):
    database = material_world[0]
    with database.session() as db:
        provision_user('other', 'fixture123', {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True)
    with boot(material_world, tmp_path) as http:
        from cn_contract.web import assistant_material_generation
        async def unread(*args):
            pytest.fail('unauthorized material body was read')
        monkeypatch.setattr(assistant_material_generation, 'body_input', unread)
        other = signin(http.client, 'other')
        for suffix in ('/material-preview', '/material-generations'):
            assert http.client.post(http.url+suffix, headers=other, content='bad').status_code == 403
            assert http.client.post(http.url+suffix, content='bad').status_code == 403
        http.client.cookies.clear()
        assert http.client.post(http.url+'/material-preview', content='bad').status_code == 401
        with database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_path_scope_mismatch_and_unconfigured_runtime_fail_closed(material_world, tmp_path):
    with boot(material_world, tmp_path) as http:
        body = body_for(material_world)
        other = d.AssistantConversationCreateInput(request_id=uuid4())
        from cn_contract.assistant import service
        with http.database.session() as db:
            actor = authenticate(http.client.cookies.get('qx_session'), db)
            changed = service.create_conversation(actor, other, db)
        mismatched = {**body, 'expected_scope': changed.scope.model_dump(mode='json')}
        for suffix in ('/material-preview', '/material-generations'):
            response = http.client.post(http.url+suffix, headers=http.headers, json=mismatched)
            assert response.status_code in {403, 409}
            assert http.client.post(http.url+suffix, headers=http.headers, json=body).status_code == 403
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0


def test_restored_copy_allows_neither_preview_nor_submit(material_world, tmp_path):
    with boot(material_world, tmp_path, MainModelRegistry()) as http:
        body = body_for(material_world)
        from cn_contract.ops import storage
        with http.database.session() as db:
            db.add(storage.RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64,
                manifest_sha256='b'*64, payload='{}'))
        for suffix in ('/material-preview', '/material-generations'):
            response = http.client.post(http.url+suffix, headers=http.headers, json=body)
            assert response.status_code == 409, response.text
        with http.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
