"""Preview requests retain HTTP authority and never authorize a model call."""
import pytest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_generation_routes import count, signin
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_research_routes import boot, submit


def selection(http):
    result = submit(http)
    view = http.client.get(http.url).json()
    response = http.client.put(http.url+'/draft', headers=http.headers, json={
        'expected_scope':view['scope'], 'expected_composer_revision':view['composer_revision'],
        'content':'请结合所选历史片段整理待核问题。'})
    assert response.status_code == 200, response.text
    view = response.json()
    return {'expected_scope':view['scope'], 'expected_composer_revision':view['composer_revision'],
        'citation_ids':result['receipts'][0]['result']['citation_ids']}


def test_preview_route_works_without_model_and_has_no_execution_side_effect(world, tmp_path, library):
    with boot(world, tmp_path, library[0]) as http:
        body = selection(http)
        before = http.client.get(http.url).json()
        response = http.client.post(http.url+'/context-preview', headers=http.headers, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['state'] == 'not_configured' and result['sending_enabled'] is False
        assert result['manifest']['question'] == before['draft_input']
        assert [item['saved_citation_id'] for item in result['manifest']['sources']] == body['citation_ids']
        assert http.client.get(http.url).json() == before
        assert http.client.post(http.url+'/context-preview', headers=http.headers, json=body).json() == result
        assert count(http.database, 'assistant_runs') == 1
        for name in ('assistant_model_attempts', 'assistant_model_outputs', 'assistant_judge_attempts'):
            assert count(http.database, name) == 0
        assert world[-1].provider.calls == []


@pytest.mark.parametrize('change,status', [('csrf',403),('origin',403),('extra_text',422),
    ('duplicate',422),('empty',422),('unknown',403),('stale',409),('scope',409)])
def test_preview_http_rejects_untrusted_selections(world, tmp_path, library, change, status):
    from uuid import uuid4
    with boot(world, tmp_path, library[0]) as http:
        body, headers = selection(http), dict(http.headers)
        if change == 'csrf': headers = {}
        elif change == 'origin': headers['Origin'] = 'https://synthetic.invalid'
        elif change == 'extra_text': body['question'] = '网页伪造的全文'
        elif change == 'duplicate': body['citation_ids'] *= 2
        elif change == 'empty': body['citation_ids'] = []
        elif change == 'unknown': body['citation_ids'] = [str(uuid4())]
        elif change == 'stale': body['expected_composer_revision'] -= 1
        else: body['expected_scope']['conversation_id'] = str(uuid4())
        response = http.client.post(http.url+'/context-preview', headers=headers, json=body)
        assert response.status_code == status, response.text
        assert count(http.database, 'assistant_runs') == 1
        assert count(http.database, 'assistant_model_attempts') == 0


@pytest.mark.parametrize('kind', ['runtime','registry','expired_grant','too_large'])
def test_preview_uses_configuration_without_spending_or_creating_grant(world, tmp_path, library, kind):
    from cn_contract.assistant.providers.registry import MainModelRegistry
    from cn_contract.web.local_server import build_local_app
    database, actor, view, _, runtime = world
    with boot(world, tmp_path, library[0]) as http:
        body = selection(http)
        before = http.client.get(http.url).json()
    if kind == 'too_large':
        runtime.provider.config = runtime.provider.config.model_copy(update={'max_input_bytes':1})
    configured = runtime
    if kind in {'registry','expired_grant'}:
        configured = MainModelRegistry()
        configured.configure(runtime.provider)
    root = Path(database.engine.url.database).parent
    app = build_local_app(root, data_parent=tmp_path, assistant_model_runtime=configured)
    with TestClient(app) as client:
        headers = signin(client)
        if kind == 'expired_grant':
            from cn_contract.security import authenticate
            from unittest.mock import patch
            with app.state.database.session() as db:
                current_actor = authenticate(client.cookies.get('qx_session'), db)
            # Register for this actual HTTP login, then observe it after expiry.
            with patch('cn_contract.assistant.providers.registry.datetime') as clock:
                clock.now.return_value = datetime.now(timezone.utc)-timedelta(hours=2)
                configured.grant(runtime.policy.model_copy(update={
                    'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}), current_actor.session_id)
        response = client.post(http.url+'/context-preview', headers=headers, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['state'] == ('input_too_large' if kind == 'too_large' else 'ready')
        assert result['sending_enabled'] is False
        assert result['wire_bytes'] == len(result['wire_payload_json'].encode('utf-8'))
        assert client.get(http.url).json() == before
        for name in ('assistant_model_attempts','assistant_model_receipts','assistant_model_outputs','assistant_judge_attempts'):
            assert count(app.state.database,name) == 0
    assert runtime.provider.calls == []


def test_preview_stays_blocked_after_backup_restore(world, tmp_path, library):
    from cn_contract.ops import workspace_backup
    from tests.helpers.legacy_assistant_backup import PASSPHRASE
    with boot(world, tmp_path, library[0]) as http:
        body = selection(http)
        with http.database.session() as db:
            before_schema = db.execute(text('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')).all()
        assert http.client.post(http.url+'/context-preview', headers=http.headers, json=body).status_code == 200
        with http.database.session() as db:
            assert db.execute(text('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')).all() == before_schema
        source_root = http.root
    archive = tmp_path/'context-preview.qxbak'
    workspace_backup.create_workspace_backup(source_root, archive, PASSPHRASE, data_parent=tmp_path)
    restored = workspace_backup.restore_workspace_backup(archive, tmp_path/'restored', PASSPHRASE)
    with boot(world, tmp_path, root=Path(restored['restored_root'])) as http:
        response = http.client.post(http.url+'/context-preview', headers=http.headers, json=body)
        assert response.status_code == 409 and response.json()['code'] == 'BLOCKED_LIVE'
        assert http.client.get('/api/assistant/library-citations/'+body['citation_ids'][0]).status_code == 200
        assert count(http.database, 'assistant_model_attempts') == 0
