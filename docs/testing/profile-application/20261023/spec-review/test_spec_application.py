"""Independent synthetic application Spec probes; no external providers or data."""
import asyncio
import copy
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import (
    profile_world, authorize, unsent_provider, archive_response,
)
from tests.integration.test_assistant_profile_application import native_http, grant, submit, selection
from tests.integration.test_assistant_generation_routes import wait_attempt, count
from tests.integration.test_assistant_main_provider import server, config, KEY


@pytest.mark.parametrize('change_purpose', [False, True])
def test_existing_after_new_control_lifecycle_is_only_lookup_not_a_fresh_grant(
        world, tmp_path, monkeypatch, change_purpose):
    with server(archive_response()) as (endpoint, received, _):
        with native_http(world, tmp_path, endpoint=endpoint) as http:
            grant(http)
            started = submit(http)
            assert started.status_code == 202
            identifier = started.json()['id']
            original = wait_attempt(http, identifier)
            assert original['output'] is not None and len(received) == 1
            # A replaced controller has no in-memory intent tombstone; persistent
            # basis equality must still protect the registered local save purpose.
            replacement = NativeModelControl(http.database, http.registry,
                provider_factory=lambda cfg, resolver:
                    DeepSeekProvider.for_synthetic_loopback(cfg, resolver, endpoint))
            configured = http.client.portal.call(replacement.configure,
                {'config':config().model_dump(mode='json'), 'secret':KEY})
            payload = copy.deepcopy(http.authorization)
            payload['expected_config_version'] = configured['config_version']
            payload['basis']['project_intake'] = change_purpose
            def no_grant(*args, **kwargs):
                pytest.fail('existing registration must not re-grant')
            monkeypatch.setattr(http.registry, 'grant', no_grant)
            if change_purpose:
                with pytest.raises(ServiceError) as failure:
                    http.client.portal.call(replacement.authorize_profile, payload)
                assert failure.value.code == 'VERSION_CONFLICT'
            else:
                assert http.client.portal.call(replacement.authorize_profile, payload) == {'status':'existing'}
            # Configuration invalidated the prior lease. POST must reject; GETs
            # remain current-authorized reads and must not dispatch or authorize.
            assert submit(http).status_code in (403, 409)
            tasks = http.app.state.assistant_generation_tasks
            def no_dispatch(*args, **kwargs):
                pytest.fail('history read must not dispatch')
            monkeypatch.setattr(tasks, '_dispatch', no_dispatch)
            with http.database.session() as db:
                prepared = attempts._input(attempts._row(UUID(identifier), db))
            found = http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
            exact = http.client.get('/api/assistant/attempts/'+identifier)
            history = http.client.get(http.url+'/generation-history',
                params={'message_id':str(prepared.request.message_id)})
            assert found.status_code == exact.status_code == history.status_code == 200
            assert found.json() == exact.json() == original
            assert history.json()['items'][0]['attempt'] == original
            assert count(http.database) == 1 and len(received) == 1


@pytest.mark.parametrize('route', ['profile-preview', 'profile-generations'])
@pytest.mark.parametrize('change', ['archived', 'restored', 'draft'])
def test_current_storage_and_scope_are_rechecked_after_the_body(
        world, tmp_path, monkeypatch, route, change):
    from cn_contract.web import assistant_profile_generation as routes
    with native_http(world, tmp_path) as http:
        grant(http)
        parse = routes.body_input
        async def changed(request, model):
            value = await parse(request, model)
            with http.database.session() as db:
                if change == 'archived':
                    db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                        {'at':service._at(), 'id':str(http.conversation.scope.conversation_id)})
                elif change == 'restored':
                    db.execute(text('''INSERT INTO ops_restore_fences(ref,archive_sha256,manifest_sha256,payload)
                        VALUES(:id,:hash,:hash,'{}')'''), {'id':str(uuid4()), 'hash':'0'*64})
                else:
                    current = service.read_conversation(http.actor, http.conversation.scope.conversation_id, db)
                    service.save_draft(http.actor, current.scope.conversation_id, d.AssistantDraftInput(
                        expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                        content='请求正文读取期间保存的新合成文字'), db)
            return value
        monkeypatch.setattr(routes, 'body_input', changed)
        body = selection(http) if route == 'profile-preview' else http.body
        result = http.client.post(http.url+'/'+route, headers=http.headers, json=body)
        assert result.status_code == 409, result.text
        assert count(http.database) == count(http.database, 'assistant_messages') == 0


def test_dispatch_observes_an_already_committed_attempt_from_a_separate_connection(
        profile_world, monkeypatch):
    database, actor, conversation, message = profile_world
    async def scenario():
        registry, _, _, _ = authorize(profile_world, unsent_provider())
        tasks = GenerationTasks(database, registry)
        tasks.start()
        observed = []
        def inspect_committed(identifier, run_id, coroutine, **kwargs):
            coroutine.close()
            with database.engine.connect() as connection:
                row = connection.execute(text('SELECT state,input_format FROM assistant_model_attempts WHERE id=:id'),
                    {'id':str(identifier)}).one()
                assert tuple(row) == ('reserved','profile-text-v1')
                assert connection.scalar(text('SELECT count(*) FROM assistant_runs WHERE id=:id'),
                    {'id':str(run_id)}) == 1
            observed.append(identifier)
        monkeypatch.setattr(tasks, '_dispatch', inspect_committed)
        try:
            request = d.MainProfileSubmission(**message.model_dump(mode='python'))
            first = tasks.submit_profile(actor, conversation.scope.conversation_id, request)
            assert tasks.submit_profile(actor, conversation.scope.conversation_id, request).id == first.id
            assert observed == [first.id]
            with database.session() as db:
                assert attempts.recover_attempts(db) == 1
        finally:
            await tasks.close()
    asyncio.run(scenario())
