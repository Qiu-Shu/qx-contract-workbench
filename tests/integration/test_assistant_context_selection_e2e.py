"""Selection GUI chain, server side: HTTP preview -> native grant -> HTTP send -> history.

One continuous synthetic walk of the exact contract the desktop approval bridge
relies on: the basis comes from the preview response, the grant comes from the
private control channel, and the send goes through the registry-backed routes.
"""
import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import research as research_service
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.config import load_settings
from cn_contract.persistence import Database
from cn_contract.security import ServiceError, authenticate, login
from cn_contract.web.local_server import build_local_app, initialize_workspace
from tests.integration.test_assistant_context_provider import envelope
from tests.integration.test_assistant_generation_routes import signin
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_main_provider import raw, server
from tests.integration.test_assistant_research_service import request

SECRET = 'SYNTHETIC_SELECTION_E2E_NOT_A_REAL_KEY_67890'


def config():
    return d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='synthetic-ceiling')


@pytest.fixture
def selection_world(tmp_path, library):
    """Native full-schema workspace with real saved citations and a saved draft."""
    root = tmp_path / '合成选片工作区'
    initialize_workspace(root, 'lawyer', 'fixture123', data_parent=tmp_path)
    database = Database('sqlite:///' + str(root / 'workbench.db'), root / 'protected',
                        load_settings(), initialize_schema=False)
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        conversation = service.create_conversation(
            actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
        queued = research_service.enqueue_research(actor, conversation.scope.conversation_id,
            request(conversation), db)
    result = research_service.execute_research(actor, queued.run.id, database,
                                               LegalLibraryAdapter(library[0]))
    ids = result.receipts[0].result.citation_ids
    assert ids
    with database.session() as db:
        view = service.read_conversation(actor, conversation.scope.conversation_id, db)
        view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content=' 请按所选历史片段列出需要核对的问题。\n保留不同结论。 '), db)
    endpoint, providers = [], []
    def factory(resolved, resolver):
        provider = DeepSeekProvider.for_synthetic_loopback(resolved, resolver, endpoint[0])
        providers.append(provider)
        return provider
    registry = MainModelRegistry()
    yield SimpleNamespace(database=database, actor=actor, token=token, view=view, ids=ids,
        root=root, registry=registry, endpoint=endpoint, providers=providers,
        control=NativeModelControl(database, registry, provider_factory=factory))
    database.engine.dispose()


def walk(world, tmp_path, tamper=None):
    async def invoke(fn, *args):
        return fn(*args)
    # The loopback response must name the exact manifest before any grant exists,
    # so reconstruct it from the persisted citations the same way the preview does.
    from cn_contract.assistant.context_preview import assemble_context
    with world.database.session() as db:
        row = service._owned(world.actor, world.view.scope.conversation_id, db)
        _, manifest, _ = assemble_context(world.actor, row, world.ids, db,
                                          question=world.view.draft_input)
    with server(raw(envelope(SimpleNamespace(manifest=manifest)))) as (loop_url, received, _):
        world.endpoint.append(loop_url)
        app = build_local_app(world.root, data_parent=tmp_path,
                              assistant_model_runtime=world.registry)
        with TestClient(app) as client:
            # Production runs the control channel and the HTTP app on one loop;
            # portal.call keeps the synthetic grant on the app's portal loop here.
            configured = client.portal.call(invoke, world.control.configure,
                {'config': config().model_dump(mode='json'), 'secret': SECRET})
            assert configured['status'] == 'configured'
            headers = signin(client)
            # The grant is session-bound: authorize with the HTTP session itself,
            # exactly like the desktop channel does for the signed-in lawyer.
            token = client.cookies.get('qx_session')
            assert token
            view = world.view
            url = '/api/assistant/conversations/' + str(view.scope.conversation_id)
            request_id = uuid4()
            selection = d.MainContextSelection(expected_scope=view.scope,
                expected_composer_revision=view.composer_revision, citation_ids=world.ids,
                request_id=request_id)
            response = client.post(url + '/context-preview', headers=headers,
                                   json=selection.model_dump(mode='json'))
            assert response.status_code == 200, response.text
            preview = d.MainContextPreview.model_validate(response.json())
            assert preview.state == 'ready' and preview.sending_enabled is False
            assert preview.manifest == manifest
            basis = preview.send_basis
            assert basis is not None and basis.request_id == request_id
            assert basis.input_format == 'library-context-v1'
            payload = {'session_token': token, 'basis': basis.model_dump(mode='json'),
                'max_total_usd': '1', 'valid_for_seconds': 120, 'max_rounds': 1,
                'expected_config_version': configured['config_version']}
            if tamper is not None:
                with pytest.raises(ServiceError) as denied:
                    client.portal.call(invoke, world.control.authorize_context, tamper(payload))
                assert denied.value.code == 'BLOCKED_LIVE'
                with world.database.session() as db:
                    assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 0
                return received
            assert client.portal.call(invoke, world.control.authorize_context,
                                      payload) == {'status': 'authorized'}
            submission = d.MainContextSubmission(request_id=request_id,
                expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content=view.draft_input, citation_ids=world.ids)
            sent = client.post(url + '/context-generations', headers=headers,
                               json=submission.model_dump(mode='json'))
            assert sent.status_code == 202, sent.text
            first = sent.json()
            assert first['input_format'] == 'library-context-v1'
            deadline = time.monotonic() + 10
            current = client.get('/api/assistant/attempts/' + first['id']).json()
            while current['state'] in ('reserved', 'sending') and time.monotonic() < deadline:
                time.sleep(0.05)
                current = client.get('/api/assistant/attempts/' + first['id']).json()
            assert current['state'] == 'received', current
            assert len(received) == 1
            with world.database.session() as db:
                row = db.execute(text('SELECT * FROM assistant_model_attempts WHERE id=:id'),
                                 {'id': first['id']}).mappings().one()
                prepared = attempts._input(row)
                # The bytes on the wire equal the immutable registered input exactly.
                assert received[0]['body'] == prepared.wire_payload_json.encode('utf-8')
                assert db.scalar(text('SELECT COUNT(*) FROM assistant_judge_attempts')) == 0
            citation = current['output']['candidate']['citations'][0]
            assert citation['saved_citation_id'] == str(world.ids[0])
            # The conversation history persists the exact sent question for rendering.
            history = client.get(url, headers=headers)
            assert history.status_code == 200, history.text
            assert '请按所选历史片段列出需要核对的问题。' in history.text
            # The by-request lookup finds the run, which is how the page reattaches
            # after a network-unknown send.
            found = client.get(url + '/runs/by-request/' + str(request_id), headers=headers)
            assert found.status_code == 200 and found.json()['state'] == 'completed'
            # A replayed authorization is a tombstone; it never regrants.
            assert client.portal.call(invoke, world.control.authorize_context,
                                      payload) == {'status': 'existing'}
            replay = client.post(url + '/context-generations', headers=headers,
                                 json=submission.model_dump(mode='json'))
            assert replay.status_code == 202 and replay.json()['id'] == first['id']
            assert len(received) == 1
        return received


def test_selection_gui_chain_walks_preview_grant_send_and_history(selection_world, tmp_path):
    received = walk(selection_world, tmp_path)
    assert len(received) == 1


def test_selection_gui_chain_denies_a_tampered_basis_before_any_send(selection_world, tmp_path):
    def tamper(payload):
        return {**payload, 'basis': {**payload['basis'], 'wire_sha256': '0' * 64}}
    received = walk(selection_world, tmp_path, tamper=tamper)
    assert received == []
