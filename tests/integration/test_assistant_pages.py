"""Synthetic native chat shell, current authorization and recovery entry tests."""
from uuid import uuid4
import re

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract.domain import Role
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import authenticate, provision_user
from cn_contract.web import app as web, local_server
from tests.integration.test_assistant_routes import PASSWORD, chat, create, native, sign_in
from tests.integration.test_assistant_storage import add_intake, add_matter


def test_home_shell_is_authenticated_and_does_not_create_conversations(chat):
    client, database, _ = chat
    assert client.get('/assistant').status_code == 401
    sign_in(client)
    response = client.get('/assistant')
    assert response.status_code == 200
    assert 'data-conversation-id=""' in response.text
    assert 'data-readonly="false"' in response.text
    assert 'data-library-enabled="false"' in response.text
    assert 'id="composer"' in response.text
    assert 'no-store' in response.headers['cache-control']
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert client.get('/api/session').json()['home_url'] == '/assistant'
    assert client.get('/').status_code == client.get('/workspace').status_code == 200
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations')) == 0


def test_existing_shell_checks_ownership_and_never_embeds_draft(chat):
    client, database, _ = chat
    headers = sign_in(client)
    view = create(client, headers, display_title='合成资料不应内嵌标题')
    identifier = view['scope']['conversation_id']
    draft = '独立合成私有草稿<script>不要嵌入页面</script>'
    response = client.put('/api/assistant/conversations/'+identifier+'/draft', headers=headers,
        json={'expected_scope':view['scope'], 'expected_composer_revision':0, 'content':draft})
    assert response.status_code == 200
    page = client.get('/assistant/'+identifier)
    assert page.status_code == 200
    assert 'data-conversation-id="'+identifier+'"' in page.text
    assert draft not in page.text and '合成资料不应内嵌标题' not in page.text
    assert client.get('/assistant/not-a-uuid').status_code == 422
    assert client.get('/assistant/'+str(uuid4())).status_code == 403
    sign_in(client, '另一合成律师')
    assert client.get('/assistant/'+identifier).status_code == 403
    client.cookies.clear()
    assert client.get('/assistant/'+identifier).status_code == 401
    sign_in(client)
    with database.session() as db:
        db.execute(text('UPDATE sessions SET revoked=1'))
    assert client.get('/assistant').status_code == 401
    assert client.get('/assistant/'+identifier).status_code == 401


@pytest.mark.parametrize('role', [Role.ASSISTANT, Role.ADMIN, Role.REVIEWING_LAWYER])
def test_current_role_keeps_existing_entry_and_limits_assistant(chat, role):
    client, database, _ = chat
    with database.session() as db:
        provision_user('合成入口角色', PASSWORD, {role}, db, local_workbench_password=True)
    sign_in(client, '合成入口角色')
    allowed = role == Role.REVIEWING_LAWYER
    assert client.get('/api/session').json()['home_url'] == ('/assistant' if allowed else '/workspace')
    assert client.get('/assistant').status_code == (200 if allowed else 403)
    assert client.get('/workspace').status_code == client.get('/').status_code == 200


def test_default_factory_keeps_workspace_home(native):
    original, _ = native
    database = original.state.database
    app = web.create_app(database.settings, database=database, purpose='assisted_draft',
        assisted_policy=local_server.load_seed_policy(), local_materials_enabled=True)
    assert app.state.assistant_home_enabled is False
    with TestClient(app) as client:
        sign_in(client)
        assert client.get('/api/session').json()['home_url'] == '/workspace'
        assert client.get('/workspace').status_code == 200


@pytest.mark.parametrize('mutation', ['missing', 'empty', 'invalid', 'duplicate'])
def test_invalid_workspace_identity_never_selects_chat_home(chat, mutation):
    client, database, _ = chat
    sign_in(client)
    with database.session() as db:
        if mutation == 'missing':
            db.execute(text('DROP TABLE local_workspace_identity'))
        elif mutation == 'empty':
            db.execute(text('DELETE FROM local_workspace_identity'))
        elif mutation == 'invalid':
            db.execute(text("UPDATE local_workspace_identity SET id='invalid'"))
        else:
            db.execute(text('INSERT INTO local_workspace_identity (id) VALUES (:id)'), {'id':str(uuid4())})
    assert client.get('/api/session').json()['home_url'] == '/workspace'
    assert client.get('/assistant').status_code == 409
    assert client.get('/workspace').status_code == 200


def test_shell_uses_current_workspace_scope(chat):
    client, database, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    with database.session() as db:
        db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
    assert client.get('/assistant/'+view['scope']['conversation_id']).status_code == 403


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
def test_page_rechecks_current_linked_permissions(chat, scope_kind):
    client, database, _ = chat
    headers = sign_in(client)
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
    matter_id = add_matter(database, actor)
    intake_id = add_intake(database, actor, matter_id)
    options = {} if scope_kind == 'projection' else {'scope_kind':scope_kind,
        'scope_ref':str(matter_id if scope_kind == 'matter' else intake_id)}
    view = create(client, headers, **options)
    identifier = view['scope']['conversation_id']
    if scope_kind == 'projection':
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id), 'id':identifier})
    assert client.get('/assistant/'+identifier).status_code == 200
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
    assert client.get('/assistant/'+identifier).status_code == 403


def test_session_and_page_recheck_changed_role(chat):
    client, database, _ = chat
    headers = sign_in(client)
    view = create(client, headers)
    with database.session() as db:
        db.execute(text('UPDATE users SET roles=:roles'), {'roles':'["assistant"]'})
    assert client.get('/api/session').json()['home_url'] == '/workspace'
    assert client.get('/assistant').status_code == 403
    assert client.get('/assistant/'+view['scope']['conversation_id']).status_code == 403


def test_library_availability_is_shell_metadata(native):
    app, _ = native
    app.state.library_root = 'synthetic-configured-library'
    with TestClient(app) as client:
        sign_in(client)
        response = client.get('/assistant')
        assert response.status_code == 200
        assert 'data-library-enabled="true"' in response.text
        assert 'synthetic-configured-library' not in response.text


def test_assistant_static_allowlist_is_exact(chat):
    client, _, _ = chat
    for name in ('assistant.css', 'assistant-api.mjs', 'assistant-state.mjs',
                 'assistant-render.mjs', 'assistant-composer.mjs', 'assistant-generation.mjs', 'assistant.mjs'):
        response = client.get('/static/'+name)
        assert response.status_code == 200, name
        assert response.content, name
        assert response.headers['content-type'].startswith('text/css' if name.endswith('.css') else 'text/javascript')
    for name in ('assistant.html', 'assistant.py', 'assistant-extra.mjs', 'assistant.mjs/extra'):
        assert client.get('/static/'+name).status_code == 404


def test_assistant_entry_serves_every_imported_module(chat):
    client, _, _ = chat
    pending = ['assistant.mjs']
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        response = client.get('/static/'+name)
        assert response.status_code == 200, name
        assert response.headers['content-type'].startswith('text/javascript'), name
        pending.extend(re.findall(r"from\s+['\"]\./([^'\"]+\.mjs)['\"]", response.text))


def test_recovery_default_entry_and_exact_readonly_pages(native):
    original, root = native
    database = original.state.database
    with TestClient(original) as client:
        headers = sign_in(client)
        view = create(client, headers)
        identifier = view['scope']['conversation_id']
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    app = local_server.build_local_app(root, data_parent=root.parent.parent)
    with TestClient(app) as client:
        assert client.get('/assistant').status_code == 401
        headers = sign_in(client)
        assert client.get('/api/session').json()['home_url'] == '/recovery'
        for path in ('/assistant', '/assistant/'+identifier):
            response = client.get(path)
            assert response.status_code == 200
            assert 'data-readonly="true"' in response.text
        for path in ('/assistant/extra', '/assistant/'+identifier+'/extra', '/assistant-extra'):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303 and response.headers['location'] == '/recovery'
        assert client.get('/assistant/'+str(uuid4())).status_code == 403
        assert client.post('/assistant', headers=headers).status_code == 409
        assert client.put('/api/assistant/conversations/'+identifier+'/draft', headers=headers,
            json={'expected_scope':view['scope'], 'expected_composer_revision':0, 'content':'恢复副本不得写入'}).status_code == 409
