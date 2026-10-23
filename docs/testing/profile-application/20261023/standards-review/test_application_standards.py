"""Independent profile application probes, using synthetic local workspaces only."""
import asyncio
from functools import wraps
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import profile_preparation_service
from cn_contract.assistant.native_model_control import NativeModelControl
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.security import ServiceError, authenticate, login, revoke_session
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world
from tests.integration.test_assistant_main_provider import config, KEY
from tests.integration.test_assistant_generation_routes import boot, save_draft


def looped(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        async def scenario():
            return await function(*args, **kwargs)
        return asyncio.run(scenario())
    return wrapped


def configured(profile_world):
    database, _, conversation, request = profile_world
    with database.session() as db:
        token, _ = login('lawyer', 'fixture123', db)
        actor = authenticate(token, db)
        basis = profile_preparation_service.build_profile_basis(actor, conversation.scope.conversation_id,
            request, db, config=config(), project_intake=True)
    reads = []
    def provider(configuration, resolver):
        def secret():
            reads.append(True)
            return resolver()
        return DeepSeekProvider.for_synthetic_loopback(configuration, secret,
            'http://127.0.0.1:1/chat/completions')
    registry = MainModelRegistry()
    control = NativeModelControl(database, registry, provider_factory=provider)
    configuration = {'config':config().model_dump(mode='json'), 'secret':KEY}
    result = control.configure(configuration)
    approval = d.NativeProfileAuthorization(session_token=token, basis=basis, max_total_usd='1',
        valid_for_seconds=120, expected_config_version=result['config_version'])
    submission = d.MainProfileSubmission.model_validate(request.model_dump(mode='python') | {'project_intake':True})
    return SimpleNamespace(database=database, actor=actor, conversation=conversation, request=request,
        basis=basis, registry=registry, control=control, configuration=configuration, approval=approval,
        submission=submission, reads=reads)


def ledger(database):
    with database.session() as db:
        return {table:db.scalar(text('SELECT count(*) FROM '+table)) for table in
            ('assistant_messages','assistant_runs','assistant_model_attempts','assistant_model_outputs',
             'assistant_profile_handlers','assistant_profile_receipts')}


@pytest.mark.parametrize('change', ['configure', 'disable', 'revoke', 'session'])
@looped
async def test_queued_profile_loses_old_authority_before_any_secret_resolution(profile_world, change):
    n = configured(profile_world)
    assert n.control.authorize_profile(n.approval) == {'status':'authorized'}
    tasks = GenerationTasks(n.database, n.registry)
    tasks.start()
    first = tasks.submit_profile(n.actor, n.conversation.scope.conversation_id, n.submission)
    # No await has occurred since submission: the network task has not started.
    if change == 'configure':
        n.control.configure(n.configuration)
    elif change == 'disable':
        n.control.disable()
    elif change == 'revoke':
        n.control.revoke({'session_token':n.approval.session_token})
    else:
        with n.database.session() as db:
            revoke_session(n.actor.session_id, db)
    await asyncio.wait_for(asyncio.gather(*tuple(tasks._tasks.values()), return_exceptions=True), 3)
    await asyncio.sleep(0)
    assert n.reads == []
    with n.database.session() as db:
        token, _ = login('lawyer','fixture123',db)
        fresh = authenticate(token,db)
        result = attempts.read_attempt(fresh,first.id,db)
        assert result.state == 'failed_before_send'
        assert result.receipt.cost_status == 'not_sent'
        assert result.receipt.estimated_cost_usd == 0
        assert result.output is None
    assert ledger(n.database) == dict(assistant_messages=1,assistant_runs=1,assistant_model_attempts=1,
        assistant_model_outputs=0,assistant_profile_handlers=0,assistant_profile_receipts=0)
    await tasks.close()


@pytest.mark.parametrize('field', ['project_intake', 'scope_revision', 'duration', 'basis_boolean'])
@looped
async def test_copied_dto_mutation_is_revalidated_before_grant_or_registration(profile_world, field):
    n = configured(profile_world)
    before = ledger(n.database)
    if field in ('duration','basis_boolean'):
        bad = n.approval.model_copy(update={'valid_for_seconds':True}) if field == 'duration' else n.approval.model_copy(
            update={'basis':n.basis.model_copy(update={'project_intake':1})})
        with pytest.raises(ServiceError):
            n.control.authorize_profile(bad)
        assert n.registry.resolve(n.actor,n.conversation.scope).snapshot()[1] is None
    else:
        n.control.authorize_profile(n.approval)
        tasks = GenerationTasks(n.database,n.registry)
        tasks.start()
        bad = n.submission.model_copy(update={'project_intake':1}) if field == 'project_intake' else n.submission.model_copy(
            update={'expected_scope':n.submission.expected_scope.model_copy(update={'input_revision':True})})
        with pytest.raises(ValueError):
            tasks.submit_profile(n.actor,n.conversation.scope.conversation_id,bad)
        assert tasks.active_count == 0
        await tasks.close()
    assert ledger(n.database) == before and n.reads == []


@pytest.mark.parametrize('route', ['profile-preview','profile-generations'])
def test_duplicate_json_plan_keys_are_rejected_without_registration(world,tmp_path,route):
    with boot(world,tmp_path) as http:
        save_draft(http)
        before = ledger(http.database)
        body = {key:http.body[key] for key in ('request_id','expected_scope','expected_composer_revision')}
        if route == 'profile-generations':
            body = dict(http.body)
        body['project_intake'] = False
        raw = json.dumps(body,ensure_ascii=False)[:-1] + ',"project_intake":true}'
        response = http.client.post(http.url+'/'+route,headers=http.headers,
            content=raw)
        assert response.status_code == 422 and response.json()['code'] == 'STATE_CONFLICT'
        assert ledger(http.database) == before and world[-1].provider.calls == []
