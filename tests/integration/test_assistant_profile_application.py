"""Profile-purpose application entry; synthetic local workspaces and providers only."""
import asyncio
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError, provision_user
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import boot, count, save_draft, signin, wait_attempt
from tests.integration.test_assistant_main_provider import KEY, config, server
from tests.integration.test_assistant_profile_execution import (
    archive_response, authorize, profile_world, unsent_provider,
)
from tests.integration.test_assistant_profile_sources import state
from tests.integration.test_assistant_task_manager import finished


def selection(http):
    return {key:http.body[key] for key in ('request_id', 'expected_scope', 'expected_composer_revision')}


@contextmanager
def native_http(world, tmp_path, *, endpoint='http://127.0.0.1:9/chat/completions', project_intake=False):
    registry = MainModelRegistry()
    with boot(world, tmp_path, runtime=registry) as http:
        http.control = NativeModelControl(http.database, registry,
            provider_factory=lambda cfg, resolver: DeepSeekProvider.for_synthetic_loopback(cfg, resolver, endpoint))
        http.registry = registry
        configured = http.client.portal.call(http.control.configure,
            {'config':config().model_dump(mode='json'), 'secret':KEY})
        current = save_draft(http, '甲称借款35000元。')
        http.body.update(content=current['draft_input'], project_intake=project_intake)
        response = http.client.post(http.url+'/profile-preview', headers=http.headers,
                                   json=selection(http) | {'project_intake':project_intake})
        assert response.status_code == 200, response.text
        http.basis = response.json()
        http.authorization = {'session_token':http.client.cookies.get('qx_session'), 'basis':http.basis,
            'expected_config_version':configured['config_version'], 'max_total_usd':'1', 'valid_for_seconds':120}
        yield http


def grant(http):
    assert http.client.portal.call(http.control.authorize_profile, http.authorization) == {'status':'authorized'}


def submit(http):
    return http.client.post(http.url+'/profile-generations', headers=http.headers, json=http.body)


def test_profile_submission_has_explicit_task_entry():
    assert callable(getattr(GenerationTasks, 'submit_profile', None))


def test_profile_preview_describes_current_draft_without_registration(world, tmp_path):
    with boot(world, tmp_path) as http:
        current = save_draft(http)
        before = state(http.database)
        response = http.client.post(http.url+'/profile-preview', headers=http.headers, json={
            'request_id':http.body['request_id'], 'expected_scope':current['scope'],
            'expected_composer_revision':current['composer_revision']})
        assert response.status_code == 200, response.text
        assert response.json()['request_id'] == http.body['request_id']
        assert response.json()['expected_scope'] == current['scope']
        assert http.client.get(http.url).json() == current
        assert state(http.database) == before
        assert world[-1].provider.calls == []


@pytest.mark.parametrize('kind', ['missing', 'disabled'])
def test_profile_preview_requires_enabled_current_configuration(world, tmp_path, kind):
    runtime = world[-1] if kind == 'disabled' else None
    if runtime:
        runtime.provider.config = runtime.provider.config.model_copy(update={'enabled':False})
    with boot(world, tmp_path, runtime=runtime) as http:
        save_draft(http)
        response = http.client.post(http.url+'/profile-preview', headers=http.headers, json=selection(http))
        assert response.status_code == 403 and response.json()['code'] == 'BLOCKED_LIVE'
        assert count(http.database) == 0


def test_profile_preview_rejects_current_stored_material_selection(world, tmp_path):
    from hashlib import sha256
    from io import BytesIO
    from cn_contract.assistant import attachments
    from tests.integration.test_assistant_attachments import sample
    with boot(world, tmp_path) as http:
        current = save_draft(http)
        raw = sample()
        http.database._assistant_synthetic_hashes = frozenset({sha256(raw).hexdigest()})
        attachments.ingest_attachment(http.actor, http.conversation.scope.conversation_id,
            d.AssistantAttachmentInput(request_id=uuid4(), expected_scope=current['scope'],
                original_name='独立合成材料.docx',
                mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=http.database)
        current = http.client.get(http.url).json()
        body = selection(http) | {'expected_scope':current['scope']}
        before = state(http.database)
        response = http.client.post(http.url+'/profile-preview', headers=http.headers, json=body)
        assert response.status_code == 422 and response.json()['code'] == 'NOT_SUPPORTED'
        assert state(http.database) == before


@pytest.mark.parametrize('change,status', [('empty',422), ('stale',409), ('scope',409),
    ('archived',409), ('restored',409), ('content',422), ('skill',422), ('attachment',422),
    ('format',422), ('plan',422)])
def test_profile_preview_rejects_unsupported_or_stale_selections(world, tmp_path, change, status):
    with boot(world, tmp_path) as http:
        if change != 'empty':
            save_draft(http)
        body = selection(http)
        if change == 'stale': body['expected_composer_revision'] += 1
        elif change == 'scope': body['expected_scope'] = {**body['expected_scope'], 'conversation_id':str(uuid4())}
        elif change == 'archived':
            with http.database.session() as db:
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at'), {'at':service._at()})
        elif change == 'restored':
            with http.database.session() as db:
                db.execute(text('INSERT INTO ops_restore_fences(ref,archive_sha256,manifest_sha256,payload) '
                    'VALUES(:id,:digest,:digest,:payload)'), {'id':str(uuid4()), 'digest':'0'*64, 'payload':'{}'})
        elif change == 'content': body['content'] = '网页替换内容'
        elif change == 'skill': body['requested_skill'] = 'contract_review'
        elif change == 'attachment': body['attachment_ids'] = [str(uuid4())]
        elif change == 'format': body['input_format'] = 'plain-text-v1'
        elif change == 'plan': body['project_intake'] = 1
        response = http.client.post(http.url+'/profile-preview', headers=http.headers, json=body)
        assert response.status_code == status, response.text
        assert count(http.database) == 0


@pytest.mark.parametrize('route', ['profile-preview', 'profile-generations'])
def test_profile_routes_check_session_csrf_origin_and_owner_before_body(world, tmp_path, monkeypatch, route):
    with world[0].session() as db:
        provision_user('other', 'fixture123', {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True)
    with boot(world, tmp_path) as http:
        from cn_contract.web import assistant_profile_generation
        async def unread(*args):
            pytest.fail('unauthorized profile body was read')
        monkeypatch.setattr(assistant_profile_generation, 'body_input', unread)
        url = http.url+'/'+route
        assert http.client.post(url, content='bad').status_code == 403
        assert http.client.post(url, headers=http.headers | {'Origin':'https://synthetic.invalid'}, content='bad').status_code == 403
        other = signin(http.client, 'other')
        assert http.client.post(url, headers=other, content='bad').status_code == 403
        http.client.cookies.clear()
        assert http.client.post(url, content='bad').status_code == 401
        assert count(http.database) == 0


@pytest.mark.parametrize('route', ['profile-preview', 'profile-generations'])
def test_profile_routes_recheck_authority_after_body(world, tmp_path, monkeypatch, route):
    with boot(world, tmp_path) as http:
        save_draft(http)
        from cn_contract.web import assistant_profile_generation
        body = selection(http) if route == 'profile-preview' else http.body
        async def revoke(request, model):
            with http.database.session() as db:
                db.execute(text('UPDATE sessions SET revoked=1'))
            return model.model_validate(body)
        monkeypatch.setattr(assistant_profile_generation, 'body_input', revoke)
        response = http.client.post(http.url+'/'+route, headers=http.headers, json=body)
        assert response.status_code == 401
        assert count(http.database) == 0


@pytest.mark.parametrize('extra', [{'policy':{}}, {'basis':{}}, {'profile_patch':{}},
    {'input_format':'profile-text-v1'}, {'project_intake':'true'}, {'requested_skill':'contract_review'},
    {'attachment_ids':[str(uuid4())]}])
def test_profile_generation_rejects_untrusted_controls_and_sources(world, tmp_path, extra):
    with native_http(world, tmp_path) as http:
        grant(http)
        http.body.update(extra)
        response = submit(http)
        assert response.status_code in {409, 422}, response.text
        assert count(http.database) == count(http.database, 'assistant_messages') == 0


@pytest.mark.parametrize('kind', ['missing', 'ordinary', 'revoked', 'changed_plan', 'stale_draft'])
def test_profile_generation_needs_matching_native_purpose_grant(world, tmp_path, kind):
    with native_http(world, tmp_path) as http:
        if kind == 'ordinary':
            plain = d.MainSendApproval(request_id=UUID(http.body['request_id']),
                expected_scope=d.ScopeSnapshot.model_validate(http.body['expected_scope']),
                expected_composer_revision=http.body['expected_composer_revision'],
                content_sha256=http.basis['content_sha256'])
            http.client.portal.call(http.control.authorize, http.authorization | {'basis':plain.model_dump(mode='json')})
        elif kind != 'missing':
            grant(http)
            if kind == 'revoked':
                http.client.portal.call(http.control.revoke, {'session_token':http.authorization['session_token']})
            elif kind == 'changed_plan': http.body['project_intake'] = True
            else: save_draft(http, '授权后修改的合成草稿')
        response = submit(http)
        assert response.status_code in {403,409}, response.text
        assert count(http.database) == count(http.database, 'assistant_messages') == 0


def test_native_profile_http_sends_once_and_reuses_existing_reads(world, tmp_path, monkeypatch):
    def forbidden_judge(*args):
        pytest.fail('profile purpose reserved Jev')
    monkeypatch.setattr(GenerationTasks, '_reserve_judge', forbidden_judge)
    with server(archive_response(), pause=.15) as (endpoint, received, seen):
        with native_http(world, tmp_path, endpoint=endpoint, project_intake=True) as http:
            grant(http)
            response = submit(http)
            assert response.status_code == 202, response.text
            first = response.json()
            assert seen.wait(1)
            assert submit(http).json()['id'] == first['id']
            found = http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
            assert found.status_code == 200 and found.json()['id'] == first['id']
            save_draft(http, '等待期间另记的合成草稿')
            result = wait_attempt(http, first['id'])
            assert result['state'] == 'received' and result['input_format'] == 'profile-text-v1'
            assert result['receipt']['usage']['total_tokens'] == 42
            assert result['output']['candidate']['profile_patch']['changes']
            assert http.client.get(http.url).json()['draft_input'] == '等待期间另记的合成草稿'
            with http.database.session() as db:
                row = attempts._row(UUID(first['id']), db)
                prepared = attempts._input(row)
                assert received[0]['body'] == prepared.wire_payload_json.encode('utf-8')
                handler = db.execute(text('SELECT * FROM assistant_profile_handlers')).mappings().one()
                assert handler['outcome'] == 'applied' and handler['profile_receipt_sequence'] == 1
            history = http.client.get(http.url+'/generation-history', params={'message_id':str(prepared.request.message_id)})
            assert history.status_code == 200 and history.json()['items'][0]['attempt']['id'] == first['id']
            # Replay uses the original submission, independent of the newer draft.
            http.body.update(expected_scope=http.basis['expected_scope'],
                             expected_composer_revision=http.basis['expected_composer_revision'])
            assert submit(http).json()['id'] == first['id']
            assert len(received) == 1
            for table in ('assistant_model_attempts', 'assistant_model_receipts', 'assistant_profile_receipts', 'intake_cases'):
                assert count(http.database, table) == 1
            for table in ('assistant_judge_attempts', 'assistant_handler_receipts'):
                assert count(http.database, table) == 0


@pytest.mark.parametrize('change', ['revoke', 'cancel'])
def test_inflight_profile_revocation_or_cancel_keeps_usage_without_archive(world, tmp_path, change):
    with server(archive_response(), pause=.2) as (endpoint, received, seen):
        with native_http(world, tmp_path, endpoint=endpoint) as http:
            grant(http)
            response = submit(http)
            assert response.status_code == 202, response.text
            first = response.json()
            assert seen.wait(1)
            if change == 'revoke':
                http.client.portal.call(http.control.revoke, {'session_token':http.authorization['session_token']})
            else:
                response = http.client.post('/api/assistant/runs/'+first['run_id']+'/cancel',
                    headers=http.headers, json={'request_id':str(uuid4())})
                assert response.status_code == 200, response.text
            result = wait_attempt(http, first['id'])
            assert result['receipt']['usage']['total_tokens'] == 42 and result['output'] is None
            assert result['receipt']['cost_status'] == 'estimated'
            assert count(http.database, 'assistant_profile_receipts') == 0
            assert count(http.database, 'assistant_profile_handlers') == 0
            assert len(received) == 1
            found = http.client.get(http.url+'/generations/by-request/'+http.body['request_id'])
            assert found.status_code == 200 and found.json()['id'] == first['id']
            if change == 'revoke':
                assert submit(http).status_code in {403,409}
            assert len(received) == 1


@pytest.mark.parametrize('mode', ['busy', 'dispatch_failure', 'close'])
def test_profile_task_admission_failure_and_shutdown_are_durable(profile_world, monkeypatch, mode):
    database, actor, conversation, message = profile_world
    request = d.MainProfileSubmission(**message.model_dump(mode='python'))
    async def scenario():
        registry, _, _, _ = authorize(profile_world, unsent_provider())
        tasks = GenerationTasks(database, registry)
        tasks.start()
        try:
            if mode == 'busy':
                from cn_contract.assistant import task_manager
                monkeypatch.setattr(task_manager, 'MAX_ACTIVE_TASKS', 0)
                before = state(database)
                with pytest.raises(ServiceError) as failure:
                    tasks.submit_profile(actor, conversation.scope.conversation_id, request)
                assert failure.value.code == 'ASSISTANT_BUSY'
                assert state(database) == before
                return
            if mode == 'dispatch_failure':
                def failed(coroutine, **kwargs):
                    raise RuntimeError('synthetic task creation failure')
                with monkeypatch.context() as patch:
                    patch.setattr(asyncio, 'create_task', failed)
                    with pytest.raises(ServiceError) as failure:
                        tasks.submit_profile(actor, conversation.scope.conversation_id, request)
                    assert failure.value.code == 'STATE_CONFLICT'
            else:
                tasks.submit_profile(actor, conversation.scope.conversation_id, request)
                await tasks.close()
            # Historical replay bypasses admission and does not adopt dispatch.
            replay = tasks.submit_profile(actor, conversation.scope.conversation_id, request)
            assert replay.state == 'failed_before_send' and replay.receipt.cost_status == 'not_sent'
            assert tasks.active_count == 0 and count(database) == 1
        finally:
            await tasks.close()
    asyncio.run(scenario())


def test_two_profile_managers_only_dispatch_the_new_registration(profile_world, monkeypatch):
    database, actor, conversation, message = profile_world
    request = d.MainProfileSubmission(**message.model_dump(mode='python'))
    async def scenario():
        registry, _, _, _ = authorize(profile_world, unsent_provider())
        first, second = GenerationTasks(database, registry), GenerationTasks(database, registry)
        first.start(); second.start()
        committed = []
        async def observe(*args):
            committed.append(count(database))
        monkeypatch.setattr(first, '_execute', observe)
        try:
            result = first.submit_profile(actor, conversation.scope.conversation_id, request)
            from cn_contract.assistant import task_manager
            monkeypatch.setattr(task_manager, 'MAX_ACTIVE_TASKS', 0)
            assert second.submit_profile(actor, conversation.scope.conversation_id, request).id == result.id
            assert first.active_count == 1 and second.active_count == 0
            await finished(first)
            assert committed == [1]
        finally:
            await first.close(); await second.close()
    asyncio.run(scenario())
