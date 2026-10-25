"""Actual CID HTTP generation appends retain history, authority and privacy fences."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts, ingress
from test_assistant_routes import chat, native, create, sign_in
from test_weixin_authorization_routes import bind, endpoint, module, advance
from tests.helpers.synthetic_weixin_generations import state


def target(client, headers, **fields):
    view = create(client, headers, **fields)
    result = client.post('/api/assistant/conversations/'+view['scope']['conversation_id']+'/task-bindings', headers=headers)
    assert result.status_code == 200, result.text
    return view, result.json()


def payload(mapping, view, binding, previous=None, **changes):
    return {**dict(request_id=str(uuid4()), expected_generation=previous['generation'] if previous else 0,
        expected_previous_generation_sha256=previous['generation_sha256'] if previous else None,
        expected_previous_scope_sha256=previous['scope_sha256'] if previous else mapping.scope_sha256,
        expected_checkpoint_revision=previous['checkpoint_revision'] if previous else 0,
        task_binding_id=binding['id'], expected_scope=view['scope'], reason='独立合成：显式增加历史目标记录'), **changes}


def setup(chat):
    client, database, root, headers, view, actor, account, mapping = bind(chat)
    destination, binding = target(client, headers)
    return client, database, headers, view, actor, account, mapping, destination, binding


def receipt(response, request):
    assert response.status_code == 200, response.text
    value = response.json()
    assert set(value) == {'mode','state','generation','request_id','scope','scope_sha256',
        'previous_generation_sha256','previous_scope_sha256','checkpoint_revision','created_at','generation_sha256'}
    assert value['mode'] == 'synthetic' and value['state'] == 'history_only'
    assert value['request_id'] == request['request_id'] and value['scope'] == request['expected_scope']
    assert value['scope_sha256'] == sha(value['scope'])
    return value


def test_http_two_generations_replay_old_request_and_fixed_query_preserve_history(chat):
    client, database, headers, view, actor, account, mapping, dest, binding = setup(chat)
    base = endpoint(view['scope']['conversation_id']); before = state(database, generations=False)
    first_request = payload(mapping, dest, binding)
    first = receipt(client.post(base+'/generations', headers=headers, json=first_request), first_request)
    dest2, binding2 = target(client, headers)
    before = state(database, generations=False)
    second_request = payload(mapping, dest2, binding2, first)
    second = receipt(client.post(base+'/generations', headers=headers, json=second_request), second_request)
    assert first['generation'] == 1 and second['generation'] == 2
    assert client.post(base+'/generations', headers=headers, json=first_request).json() == first
    for value in (first, second):
        found = client.get(base+'/generations/by-request/'+value['request_id'])
        assert found.status_code == 200 and found.json() == value
    assert client.get(base+'/generations/by-request/'+str(uuid4())).json() is None
    assert state(database, generations=False) == before
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations')) == 2
        assert db.scalar(text('SELECT count(*) FROM assistant_model_attempts')) == 0
    with pytest.raises(ServiceError) as blocked:
        ingress.record_synthetic_poll(actor, account.id, d.WeixinPollInput(request_id=uuid4(),
            expected_revision=0, expected_cursor=account.upstream_cursor),
            b'{"ret":0,"msgs":[],"get_updates_buf":"synthetic-later"}', database=database)
    assert blocked.value.code == 'STATE_CONFLICT'


def test_unbound_get_is_null_and_post_cannot_reverse_resolve_new_target(chat):
    client, database, headers, view, _, _, mapping, dest, binding = setup(chat)
    value = payload(mapping, dest, binding)
    root = endpoint(view['scope']['conversation_id'])
    first = client.post(root+'/generations', headers=headers, json=value)
    assert first.status_code == 200, first.text
    before = state(database)
    destination = endpoint(dest['scope']['conversation_id'])
    found = client.get(destination+'/generations/by-request/'+value['request_id'])
    assert found.status_code == 200 and found.json() is None
    assert client.post(destination+'/generations', headers=headers, json=value).status_code == 409
    assert state(database) == before


def test_authentication_precedes_unknown_root_and_json(chat):
    client, _, _ = chat
    base = endpoint(uuid4())
    assert client.post(base+'/generations', content='not-json').status_code == 401
    assert client.get(base+'/generations/by-request/'+str(uuid4())).status_code == 401


@pytest.mark.parametrize('damage', ['csrf','origin','fetch_site','owner','unknown','workspace','archived','account_revoked','mapping_revoked'])
def test_current_root_authority_is_checked_before_parsing(chat, monkeypatch, damage):
    client, database, headers, view, actor, account, mapping, _, _ = setup(chat)
    cid = view['scope']['conversation_id']; base = endpoint(cid)
    async def unread(*args):
        raise AssertionError('current root authority must precede parsing')
    monkeypatch.setattr(module(), 'body_input', unread)
    if damage == 'csrf': headers = {}
    elif damage == 'origin': headers = {**headers, 'Origin':'https://evil.invalid'}
    elif damage == 'fetch_site': headers = {**headers, 'Sec-Fetch-Site':'same-site'}
    elif damage == 'owner': headers = sign_in(client, '另一合成律师')
    elif damage == 'unknown': base = endpoint(uuid4())
    elif damage == 'workspace': advance(database, cid, workspace_id=str(uuid4()))
    elif damage == 'archived': advance(database, cid, archived_at='2026-10-25T06:50:00Z')
    elif damage == 'account_revoked': accounts.revoke_synthetic_account(actor, account.id, d.WeixinRevokeInput(reason='独立合成撤权'), database=database)
    else: accounts.revoke_synthetic_peer(actor, mapping.id, d.WeixinRevokeInput(reason='独立合成撤权'), database=database)
    response = client.post(base+'/generations', headers=headers, content='not-json')
    assert response.status_code == (409 if damage in ('archived','account_revoked','mapping_revoked') else 403)


@pytest.mark.parametrize('raw,expected', [('not-json',422), ('{"request_id":"a","request_id":"b"}',422), ('x'*(256*1024+1),413)], ids=['json','duplicate','size'])
def test_generation_body_is_strict_and_bounded(chat, raw, expected):
    client, database, headers, view, *_ = setup(chat)
    before = state(database)
    response = client.post(endpoint(view['scope']['conversation_id'])+'/generations', headers=headers, content=raw)
    assert response.status_code == expected, response.text
    assert state(database) == before


@pytest.mark.parametrize('extra', ['root_mapping_id','mapping_id','account_id','actor_id','created_at','mode'])
def test_body_cannot_choose_root_or_server_authority(chat, extra):
    client, database, headers, view, _, _, mapping, dest, binding = setup(chat)
    before = state(database)
    response = client.post(endpoint(view['scope']['conversation_id'])+'/generations', headers=headers,
        json=payload(mapping,dest,binding,**{extra:str(uuid4())}))
    assert response.status_code == 422, response.text
    assert state(database) == before


@pytest.mark.parametrize('change', ['scope','hash','checkpoint','binding','reason'])
def test_committed_request_changes_and_old_cas_are_conflicts(chat, change):
    client, database, headers, view, _, _, mapping, dest, binding = setup(chat)
    base = endpoint(view['scope']['conversation_id']); value = payload(mapping,dest,binding)
    first = receipt(client.post(base+'/generations', headers=headers, json=value), value)
    changed = dict(value)
    if change == 'scope': changed['expected_scope'] = {**value['expected_scope'],'input_revision':1}
    elif change == 'hash': changed['expected_previous_scope_sha256'] = 'c'*64
    elif change == 'checkpoint': changed['expected_checkpoint_revision'] = 1
    elif change == 'binding': changed['task_binding_id'] = str(uuid4())
    else: changed['reason'] = '不同的明确理由'
    before = state(database)
    assert client.post(base+'/generations', headers=headers, json=changed).status_code == 409
    assert client.post(base+'/generations', headers=headers, json={**value,'request_id':str(uuid4())}).status_code == 409
    assert client.get(base+'/generations/by-request/'+value['request_id']).json() == first
    assert state(database) == before


def test_receipt_does_not_disclose_private_identity_or_reason(chat):
    client, database, headers, view, actor, account, mapping, dest, binding = setup(chat)
    value = payload(mapping,dest,binding); base = endpoint(view['scope']['conversation_id'])
    response = client.post(base+'/generations', headers=headers, json=value)
    first = receipt(response,value)
    for hidden in (str(mapping.id),str(actor.user_id),str(account.id),account.bot_account_id,
                   mapping.sender_peer_id,value['reason'],binding['id']):
        assert hidden not in response.text
    before = state(database)
    assert client.get(base+'/generations/by-request/'+value['request_id']).json() == first
    assert state(database) == before


def test_get_is_same_origin_and_exact_recovery_predicate(chat):
    client, _, headers, view, *_ = setup(chat)
    base = endpoint(view['scope']['conversation_id']); path = base+'/generations/by-request/'+str(uuid4())
    predicate = module().is_weixin_authorization_read_path
    assert predicate(path)
    for near in (base+'/generations', path+'/', path+'/extra',base+'/generations/by-request/bad',
                 base+'/generations/latest',base+'/generations/polls'):
        assert not predicate(near)
    for extra in ({'Origin':'https://evil.invalid'}, {'Sec-Fetch-Site':'same-site'}):
        assert client.get(path,headers=extra).status_code == 403
