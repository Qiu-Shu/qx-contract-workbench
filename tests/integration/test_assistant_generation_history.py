"""Bounded synthetic generation history; reads never dispatch providers."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.runner import execute_attempt
from cn_contract.ops import workspace_backup
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import provision_user
from tests.helpers.legacy_assistant_backup import PASSPHRASE
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import boot, signin
from tests.integration.test_assistant_history_routes import seed_history
from tests.integration.test_assistant_storage import add_intake, add_matter


def recorded(world, *, execute=True):
    database, actor, conversation, original, runtime = world
    with database.session() as db:
        current = service.read_conversation(actor, conversation.scope.conversation_id, db)
        request = original.model_copy(update={'request_id':uuid4(), 'expected_scope':current.scope,
            'expected_composer_revision':current.composer_revision})
        attempt = attempts.enqueue_generation(actor, current.scope.conversation_id, request, db, runtime)
        run = service.find_run(actor, current.scope.conversation_id, request.request_id, db)
    if execute:
        attempt = asyncio.run(execute_attempt(actor, attempt.id, database, runtime))
    return run.message_id, attempt


def history(http, *identifiers):
    return http.client.get(http.url+'/generation-history',
        params=[('message_id', str(identifier)) for identifier in identifiers])


def test_history_keeps_two_outputs_in_request_order_without_runtime_or_provider_calls(world, tmp_path):
    first_id, first = recorded(world)
    second_id, second = recorded(world)
    runtime = world[-1]
    assert len(runtime.provider.calls) == 2
    with boot(world, tmp_path, runtime=None) as http:
        response = history(http, second_id, first_id)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['scope'] == http.client.get(http.url).json()['scope']
        assert result['scope']['input_revision'] == 2
        assert [item['message_id'] for item in result['items']] == [str(second_id), str(first_id)]
        assert [item['attempt']['id'] for item in result['items']] == [str(second.id), str(first.id)]
        for item in result['items']:
            output = item['attempt']['output']
            assert output['candidate']['citations'][0]['message_id'] == item['message_id']
            assert output['audience'] == 'internal' and output['review_status'] == 'unverified'
        assert len(runtime.provider.calls) == 2
        assert http.app.state.assistant_generation_tasks.runtime is None
        assert http.app.state.assistant_generation_tasks.active_count == 0


def test_legacy_queued_message_is_omitted_without_dispatch(world, tmp_path):
    with boot(world, tmp_path, runtime=None) as http:
        response = http.client.post(http.url+'/messages', headers=http.headers, json=http.body)
        assert response.status_code == 202, response.text
        run = response.json()
        result = history(http, run['message_id'])
        assert result.status_code == 200 and result.json()['items'] == []
        assert http.client.get('/api/assistant/runs/'+run['id']).json()['state'] == 'queued'
        assert world[-1].provider.calls == []


def test_reserved_attempt_is_returned_without_output_or_runtime_lookup(world, tmp_path, monkeypatch):
    with boot(world, tmp_path) as http:
        message_id, attempt = recorded(world, execute=False)
        def unavailable():
            pytest.fail('history must not read runtime configuration')
        monkeypatch.setattr(world[-1], 'snapshot', unavailable)
        for _ in range(2):
            response = history(http, message_id)
            assert response.status_code == 200, response.text
            result = response.json()['items'][0]
            assert result['message_id'] == str(message_id)
            assert result['attempt']['id'] == str(attempt.id)
            assert result['attempt']['state'] == 'reserved'
            assert result['attempt']['output'] is result['attempt']['receipt'] is None
        assert world[-1].provider.calls == []


@pytest.mark.parametrize('query', [
    [], [('message_id', '')], [('message_id', 'bad')], [('unknown', 'x')],
    [('message_id', str(uuid4())) for _ in range(51)],
    [('message_id', '00000000-0000-0000-0000-000000000001')]*2,
    [('message_id', 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'),
     ('message_id', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa')],
])
def test_history_rejects_empty_malformed_duplicate_or_over_limit_queries(world, tmp_path, query):
    with boot(world, tmp_path, runtime=None) as http:
        response = http.client.get(http.url+'/generation-history', params=query)
        assert response.status_code == 422, response.text
        assert response.json()['code'] == 'STATE_CONFLICT'
        assert world[-1].provider.calls == []


def test_history_accepts_fifty_owned_messages_and_bounds_response_dto(world, tmp_path):
    with boot(world, tmp_path, runtime=None) as http:
        identifiers = seed_history(world[0], str(world[2].scope.conversation_id), 50)
        response = history(http, *identifiers)
        assert response.status_code == 200 and response.json()['items'] == []
        assert world[-1].provider.calls == []
    message_id, attempt = recorded(world)
    item = d.MainGenerationHistoryItem(message_id=message_id, attempt=attempt)
    with pytest.raises(ValidationError):
        d.MainGenerationHistoryView(scope=attempt.scope, items=(item,)*51)


@pytest.mark.parametrize('foreign', ['other_conversation', 'missing'])
def test_history_rejects_entire_batch_with_foreign_or_missing_message(world, tmp_path, foreign):
    first_id, _ = recorded(world)
    database, actor, _, original, _ = world
    other_id = uuid4()
    if foreign == 'other_conversation':
        with database.session() as db:
            other = service.create_conversation(actor, d.AssistantConversationCreateInput(request_id=uuid4()), db)
            run = service.save_message(actor, other.scope.conversation_id,
                original.model_copy(update={'request_id':uuid4(), 'expected_scope':other.scope}), db)
            other_id = run.message_id
    with boot(world, tmp_path, runtime=None) as http:
        response = history(http, first_id, other_id)
        assert response.status_code == 403, response.text
        assert response.json()['code'] == 'CROSS_MATTER_DENIED' and 'items' not in response.json()
        assert len(world[-1].provider.calls) == 1


def test_history_checks_authentication_and_owner_before_query_validation(world, tmp_path):
    database = world[0]
    with database.session() as db:
        provision_user('other', 'fixture123', {d.Role.HANDLING_LAWYER}, db, local_workbench_password=True)
    with boot(world, tmp_path, runtime=None) as http:
        signin(http.client, 'other')
        assert history(http, 'bad').status_code == 403
        assert history(http).status_code == 403
        http.client.cookies.clear()
        assert history(http, 'bad').status_code == 401
        assert history(http).status_code == 401
        assert world[-1].provider.calls == []


@pytest.mark.parametrize('change,status', [
    ('session', 401), ('expired', 401), ('disabled', 401), ('role', 403), ('workspace', 403),
])
def test_history_rechecks_current_session_role_and_workspace(world, tmp_path, change, status):
    message_id, _ = recorded(world)
    database, actor, _, _, _ = world
    with boot(world, tmp_path, runtime=None) as http:
        assert history(http, message_id).status_code == 200
        with database.session() as db:
            if change == 'session':
                db.execute(text('UPDATE sessions SET revoked=1'))
            elif change == 'expired':
                for session in db.query(SessionRow).all():
                    session.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
            elif change == 'disabled':
                db.get(UserRow, str(actor.user_id)).disabled = True
            elif change == 'role':
                db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
            else:
                db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
        response = history(http, message_id)
        assert response.status_code == status and 'items' not in response.json()
        assert history(http, 'bad').status_code == status


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
def test_history_rechecks_current_case_and_intake_access(world, tmp_path, scope_kind):
    database, actor, _, original, runtime = world
    matter_id = add_matter(database, actor)
    intake_id = add_intake(database, actor, matter_id)
    options = {} if scope_kind == 'projection' else {
        'scope_kind':scope_kind, 'scope_ref':matter_id if scope_kind == 'matter' else intake_id}
    with database.session() as db:
        conversation = service.create_conversation(actor, d.AssistantConversationCreateInput(
            request_id=uuid4(), **options), db)
        if scope_kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id), 'id':str(conversation.scope.conversation_id)})
    bound = database, actor, conversation, original, runtime
    message_id, _ = recorded(bound)
    with boot(bound, tmp_path, runtime=None) as http:
        assert history(http, message_id).status_code == 200
        with database.session() as db:
            db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
        assert history(http, message_id).status_code == 403
        assert history(http, 'bad').status_code == 403


@pytest.mark.parametrize('change', ['binding_revision', 'scope_reference'])
def test_old_binding_cannot_flow_into_current_conversation_history(world, tmp_path, change):
    message_id, _ = recorded(world)
    database, actor, conversation, _, _ = world
    matter_id = add_matter(database, actor)
    with boot(world, tmp_path, runtime=None) as http:
        with database.session() as db:
            if change == 'binding_revision':
                db.execute(text('UPDATE assistant_conversations SET binding_revision=binding_revision+1 WHERE id=:id'),
                    {'id':str(conversation.scope.conversation_id)})
            else:
                db.execute(text("UPDATE assistant_conversations SET scope_kind='matter',scope_ref=:ref WHERE id=:id"),
                    {'id':str(conversation.scope.conversation_id), 'ref':str(matter_id)})
        assert http.client.get(http.url).status_code == 200
        response = history(http, message_id)
        assert response.status_code == 403 and 'items' not in response.json()


def test_restored_copy_allows_exact_history_read_and_blocks_writes(world, tmp_path):
    message_id, attempt = recorded(world)
    root = Path(world[0].engine.url.database).parent
    archive = tmp_path/'history.qxbak'
    workspace_backup.create_workspace_backup(root, archive, PASSPHRASE, data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    with boot(world, tmp_path, runtime=None, root=Path(restored['restored_root'])) as http:
        response = history(http, message_id)
        assert response.status_code == 200, response.text
        assert response.json()['items'][0]['attempt']['id'] == str(attempt.id)
        for suffix in ('/extra', '/', '-extra'):
            assert http.client.get(http.url+'/generation-history'+suffix).status_code == 409
        assert http.client.get(http.url.replace(str(world[2].scope.conversation_id), 'x'*36)
            +'/generation-history').status_code == 409
        assert http.client.post(http.url+'/generation-history', headers=http.headers).status_code == 409
        assert http.client.post(http.url+'/generations', headers=http.headers, json=http.body).status_code == 409
        assert len(world[-1].provider.calls) == 1
