"""Actual desktop HTTP projections and explicit local refreshes keep CID ownership."""
import importlib
import importlib.util
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.record_codec import now
from cn_contract.security import authenticate
from cn_contract.weixin_inbox import accounts
from test_assistant_routes import chat, native, sign_in, create
from test_api import create_case


def module():
    assert importlib.util.find_spec('cn_contract.web.weixin_authorization') is not None, 'D2e needs current CID authorization routes'
    return importlib.import_module('cn_contract.web.weixin_authorization')


def state(database):
    names = ('weixin_accounts', 'weixin_peer_bindings', 'weixin_peer_scope_grants',
        'weixin_poll_receipts', 'weixin_inbox_descriptors', 'weixin_dispatch_receipts',
        'task_channel_bindings', 'task_inbox_events', 'task_drafts', 'task_executions', 'assistant_runs', 'audit_events')
    with database.session() as db:
        return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))] for name in names}


def bind(chat, *, matter=False):
    client, database, root = chat
    headers = sign_in(client)
    fields = {'scope_kind':'matter', 'scope_ref':create_case(client, headers)} if matter else {}
    view = create(client, headers, **fields)
    cid = view['scope']['conversation_id']
    binding = client.post('/api/assistant/conversations/'+cid+'/task-bindings', headers=headers)
    assert binding.status_code == 200, binding.text
    with database.session() as db:
        actor = authenticate(client.cookies.get('qx_session'), db)
    account = accounts.create_synthetic_account(actor, d.WeixinAccountCreateInput(
        bot_account_id='synthetic-D2e-private-bot'), database=database)
    mapping = accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-D2e-private-peer', task_binding_id=binding.json()['id'],
        expected_scope=d.ScopeSnapshot(**view['scope'])), database=database)
    return client, database, root, headers, view, actor, account, mapping


def advance(database, cid, **fields):
    assert set(fields) <= {'input_revision', 'materials_revision', 'binding_revision', 'scope_kind', 'scope_ref', 'archived_at', 'workspace_id'}
    with database.session() as db:
        for key,value in fields.items():
            db.execute(text('UPDATE assistant_conversations SET '+key+'=:value WHERE id=:id'), {'id':str(cid), 'value':value})


def endpoint(cid):
    return '/api/assistant/conversations/'+str(cid)+'/weixin-authorization'


def request(view, **changes):
    return {**dict(request_id=str(uuid4()), expected_grant_revision=view['grant_revision'],
        expected_scope_sha256=view['scope_sha256'], expected_scope=view['current_scope'],
        reason='对话页显式更新同目标输入和材料授权'), **changes}


def test_authentication_precedes_body_and_unknown_object_reads(chat):
    client, _, _ = chat
    base = endpoint(uuid4())
    assert client.get(base).status_code == 401
    assert client.post(base+'/refresh', content='not-json').status_code == 401
    assert client.get(base+'/refreshes/by-request/'+str(uuid4())).status_code == 401


def test_unbound_projection_and_unknown_lookup_create_nothing(chat):
    client, database, _ = chat
    headers = sign_in(client)
    conversation = create(client, headers)
    base = endpoint(conversation['scope']['conversation_id'])
    before = state(database)
    response = client.get(base)
    assert response.status_code == 200, response.text
    assert response.json() == dict(mode='synthetic', state='unbound', current_scope=conversation['scope'],
        authorized_scope=None, grant_revision=0, scope_sha256=None)
    assert client.get(base+'/refreshes/by-request/'+str(uuid4())).json() is None
    assert state(database) == before


def test_bound_projection_has_no_account_peer_reason_or_text(chat):
    client, database, _, _, view, _, account, mapping = bind(chat)
    before = state(database)
    response = client.get(endpoint(view['scope']['conversation_id']))
    assert response.status_code == 200, response.text
    assert response.json() == dict(mode='synthetic', state='current', current_scope=view['scope'],
        authorized_scope=view['scope'], grant_revision=0, scope_sha256=mapping.scope_sha256)
    for secret in (str(account.id), str(mapping.id), account.bot_account_id, mapping.sender_peer_id, 'reason', 'text'):
        assert secret not in response.text
    assert state(database) == before


@pytest.mark.parametrize('field', ['input_revision', 'materials_revision'])
def test_explicit_refresh_creates_one_fixed_grant_and_updates_projection(chat, field):
    client, database, _, headers, view, _, _, _ = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    advance(database, cid, **{field:1})
    pending = client.get(base)
    assert pending.status_code == 200 and pending.json()['state'] == 'refresh_required'
    value = request(pending.json())
    first = client.post(base+'/refresh', headers=headers, json=value)
    assert first.status_code == 200, first.text
    grant = first.json()
    assert grant['revision'] == 1 and grant['scope'] == pending.json()['current_scope']
    after = state(database)
    assert len(after['weixin_peer_scope_grants']) == 1
    assert client.post(base+'/refresh', headers=headers, json=value).json() == grant
    assert client.get(base+'/refreshes/by-request/'+value['request_id']).json() == grant
    assert client.get(base+'/refreshes/by-request/'+str(uuid4())).json() is None
    current = client.get(base).json()
    assert current['state'] == 'current' and current['grant_revision'] == 1
    assert current['authorized_scope'] == current['current_scope'] == grant['scope']
    assert state(database) == after


@pytest.mark.parametrize('damage', ['csrf', 'origin', 'fetch_site', 'owner', 'unknown', 'workspace'])
def test_current_authorization_and_same_origin_are_checked_before_json(chat, monkeypatch, damage):
    client, database, _, headers, view, _, _, _ = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    async def unread(*args):
        raise AssertionError('authorization must precede body parsing')
    monkeypatch.setattr(module(), 'body_input', unread)
    if damage == 'csrf':
        headers = {}
    elif damage == 'origin':
        headers = {**headers, 'Origin':'https://evil.invalid'}
    elif damage == 'fetch_site':
        headers = {**headers, 'Sec-Fetch-Site':'same-site'}
    elif damage == 'owner':
        headers = sign_in(client, '另一合成律师')
    elif damage == 'unknown':
        base = endpoint(uuid4())
    else:
        advance(database, cid, workspace_id=str(uuid4()))
    assert client.post(base+'/refresh', headers=headers, content='not-json').status_code == 403


@pytest.mark.parametrize('raw,expected', [('not-json',422), ('{"request_id":"a","request_id":"b"}',422), ('x'*(256*1024+1),413)], ids=['invalid-json', 'duplicate-key', 'oversize'])
def test_refresh_body_is_strict_and_bounded_after_authorization(chat, raw, expected):
    client, database, _, headers, view, _, _, _ = bind(chat)
    base = endpoint(view['scope']['conversation_id'])
    before = state(database)
    response = client.post(base+'/refresh', headers=headers, content=raw)
    assert response.status_code == expected, response.text
    assert state(database) == before


@pytest.mark.parametrize('extra', ['mapping_id', 'account_id', 'actor_id'])
def test_caller_cannot_choose_authority_or_target_mapping(chat, extra):
    client, database, _, headers, view, _, _, _ = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    advance(database, cid, input_revision=1)
    projection = client.get(base)
    assert projection.status_code == 200, projection.text
    assert client.post(base+'/refresh', headers=headers, json=request(projection.json(), **{extra:str(uuid4())})).status_code == 422
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_scope_grants')) == 0


def test_cross_cid_scope_and_cas_drift_never_create_a_grant(chat):
    client, database, _, headers, view, _, _, _ = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    advance(database, cid, input_revision=1)
    projection = client.get(base)
    assert projection.status_code == 200, projection.text
    value = request(projection.json())
    another = create(client, headers)
    wrong = {**value, 'expected_scope':another['scope']}
    assert client.post(base+'/refresh', headers=headers, json=wrong).status_code == 409
    advance(database, cid, input_revision=2)
    assert client.post(base+'/refresh', headers=headers, json=value).status_code == 409
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_scope_grants')) == 0


@pytest.mark.parametrize('change,expected', [('binding_revision','target_changed'), ('input_regression','target_changed'),
    ('archived','archived'), ('account_revoked','revoked'), ('mapping_revoked','revoked'), ('restore','restored_blocked')])
def test_blocked_or_changed_projection_never_refreshes(chat, monkeypatch, change, expected):
    client, database, _, headers, view, actor, account, mapping = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    if change == 'binding_revision':
        advance(database, cid, binding_revision=2)
    elif change == 'input_regression':
        advance(database, cid, input_revision=1)
        accounts.refresh_synthetic_peer(actor, mapping.id, d.WeixinPeerRefreshInput(request_id=uuid4(),
            expected_grant_revision=0, expected_scope_sha256=mapping.scope_sha256,
            expected_scope={**view['scope'], 'input_revision':1}, reason='独立虚构授权'), database=database)
        advance(database, cid, input_revision=0)
    elif change == 'archived':
        advance(database, cid, archived_at=now().isoformat())
    elif change.endswith('_revoked'):
        operation, identifier = (accounts.revoke_synthetic_account, account.id) if change == 'account_revoked' else (accounts.revoke_synthetic_peer, mapping.id)
        operation(actor, identifier, d.WeixinRevokeInput(reason='秘密虚构撤权理由'), database=database)
    else:
        with database.session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    response = client.get(base)
    assert response.status_code == 200 and response.json()['state'] == expected, response.text
    before = state(database)
    result = client.post(base+'/refresh', headers=headers, json=request(response.json()))
    assert result.status_code == 409, result.text
    assert state(database) == before


@pytest.mark.parametrize('change', ['session', 'archived', 'scope'])
def test_current_authority_is_rechecked_after_body_read(chat, monkeypatch, change):
    client, database, _, headers, view, _, _, _ = bind(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    advance(database, cid, input_revision=1)
    projection = client.get(base)
    assert projection.status_code == 200, projection.text
    original = module().body_input
    async def changed(request_object, model):
        result = await original(request_object, model)
        if change == 'session':
            with database.session() as db:
                db.execute(text('UPDATE sessions SET revoked=1'))
        else:
            advance(database, cid, **({'archived_at':now().isoformat()} if change == 'archived' else {'input_revision':2}))
        return result
    monkeypatch.setattr(module(), 'body_input', changed)
    response = client.post(base+'/refresh', headers=headers, json=request(projection.json()))
    assert response.status_code == (401 if change == 'session' else 409), response.text
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_scope_grants')) == 0


@pytest.mark.parametrize('damage', ['membership', 'archived_matter'])
def test_current_matter_permissions_precede_projection_and_body(chat, monkeypatch, damage):
    client, database, _, headers, view, actor, _, _ = bind(chat, matter=True)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    with database.session() as db:
        if damage == 'membership':
            db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id AND user_id=:user'), {'id':view['scope']['scope_ref'], 'user':str(actor.user_id)})
        else:
            db.execute(text("UPDATE matters SET status='archived' WHERE id=:id"), {'id':view['scope']['scope_ref']})
    async def unread(*args):
        raise AssertionError('current matter access must precede parsing')
    monkeypatch.setattr(module(), 'body_input', unread)
    assert client.get(base).status_code == 403
    assert client.get(base+'/refreshes/by-request/'+str(uuid4())).status_code == 403
    assert client.post(base+'/refresh', headers=headers, content='not-json').status_code == 403


def test_recovery_middleware_allows_only_exact_new_read_paths(native):
    from cn_contract.web import local_server
    original_app, root = native
    with TestClient(original_app) as client:
        client, database, _, headers, view, _, _, _ = bind((client, original_app.state.database, root))
        cid = view['scope']['conversation_id']; base = endpoint(cid)
        advance(database, cid, input_revision=1)
        projection = client.get(base)
        assert projection.status_code == 200, projection.text
        value = request(projection.json())
        response = client.post(base+'/refresh', headers=headers, json=value)
        assert response.status_code == 200, response.text
        with database.session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    app = local_server.build_local_app(root, data_parent=root.parent.parent)
    try:
        with TestClient(app) as restored:
            recovered_headers = sign_in(restored)
            assert restored.get(base).json()['state'] == 'restored_blocked'
            assert restored.get(base+'/refreshes/by-request/'+value['request_id']).json() == response.json()
            assert restored.post(base+'/refresh', headers=recovered_headers, json=value).status_code == 409
            assert restored.get(base+'/polls').status_code == 409
            assert restored.get(base+'/refresh/extra').status_code == 409
    finally:
        app.state.database.engine.dispose()


def test_read_predicate_is_exact_and_get_rejects_cross_origin(chat):
    cid, request_id = uuid4(), uuid4()
    predicate = module().is_weixin_authorization_read_path
    base = endpoint(cid)
    assert predicate(base) and predicate(base+'/refreshes/by-request/'+str(request_id))
    for path in (base+'/refresh', base+'/', base+'/polls', base+'/refreshes/by-request/bad', base+'/refreshes/by-request/'+str(request_id)+'/x'):
        assert not predicate(path)
    client, _, _ = chat
    headers = sign_in(client); view = create(client, headers)
    assert client.get(endpoint(view['scope']['conversation_id']), headers={'Origin':'https://evil.invalid'}).status_code == 403
