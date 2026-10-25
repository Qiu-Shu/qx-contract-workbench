"""Real CID HTTP dispatch exposes only the fixed acknowledgement, never transport data."""
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.weixin_inbox import accounts, generation_ingress, generation_dispatch
from test_assistant_routes import chat, native, create, sign_in
from test_weixin_authorization_routes import bind, endpoint, module, advance
from test_weixin_generation_routes import target, payload
from test_weixin_generation_dispatch import state
from test_weixin_generation_ingress import raw
from test_weixin_generation_ingress_atomic import deny_projected_case
from test_weixin_dispatch import message


def setup(chat, *, other_peer=False):
    client, database, root, headers, view, actor, account, mapping = bind(chat)
    other_mapping = None
    if other_peer:
        peer_view, peer_binding = target(client, headers)
        other_mapping = accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
            sender_peer_id='synthetic-http-other-peer', task_binding_id=peer_binding['id'],
            expected_scope=d.ScopeSnapshot(**peer_view['scope'])), database=database)
    destination, binding = target(client, headers)
    value = payload(mapping, destination, binding)
    response = client.post(endpoint(view['scope']['conversation_id'])+'/generations', headers=headers, json=value)
    assert response.status_code == 200, response.text
    return dict(client=client, database=database, root=root, headers=headers, view=view,
        actor=actor, account=account, mapping=mapping, destination=destination, binding=binding,
        generation=response.json(), base=endpoint(view['scope']['conversation_id']), other_mapping=other_mapping)


def receive(h, identifiers=(91,92), *, mapping=None, account=None):
    account = account or h['account']; mapping = mapping or h['mapping']
    current = accounts.read_synthetic_account(h['actor'], account.id, database=h['database'])
    values = [{**message(identifier, peer=mapping.sender_peer_id), 'to_user_id':account.bot_account_id}
              for identifier in identifiers]
    return generation_ingress.record_generation_poll(h['actor'], account.id,
        d.WeixinPollInput(request_id=uuid4(), expected_revision=current.checkpoint_revision,
            expected_cursor=current.upstream_cursor), raw(values, 'synthetic-http:'+str(uuid4())), database=h['database'])


def write(h, identifier, **kwargs):
    return h['client'].post(h['base']+'/dispatches', headers=h['headers'],
        json={'descriptor_id':str(identifier)}, **kwargs)


def find(h, identifier, **kwargs):
    return h['client'].get(h['base']+'/dispatches/by-descriptor/'+str(identifier), **kwargs)


def receipt(response, h, descriptor, *, expected=0):
    assert response.status_code == 200, response.text
    value = response.json()
    assert set(value) == {'mode','state','descriptor_id','conversation_id','task_event_id',
        'expected_task_cursor','next_task_cursor','created_at','receipt_sha256'}
    assert value['mode'] == 'synthetic' and value['state'] == 'recorded'
    assert value['descriptor_id'] == str(descriptor.id)
    assert value['conversation_id'] == h['destination']['scope']['conversation_id']
    assert (value['expected_task_cursor'],value['next_task_cursor']) == (expected,expected+1)
    saved = generation_dispatch.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=h['database'])
    assert value['receipt_sha256'] == saved.receipt_sha256 and value['task_event_id'] == str(saved.task_event_id)
    return value


def test_http_fixed_historical_generation_survives_later_target_and_replays_once(chat):
    h = setup(chat); descriptors = receive(h).descriptors
    assert find(h, descriptors[0].id).status_code == 200
    assert find(h, descriptors[0].id).json() is None
    dest2, binding2 = target(h['client'], h['headers'])
    second_request = payload(h['mapping'], dest2, binding2, h['generation'])
    # A later generation CAS includes the actual account checkpoint after the poll.
    second_request['expected_checkpoint_revision'] = 1
    second = h['client'].post(h['base']+'/generations', headers=h['headers'], json=second_request)
    assert second.status_code == 200, second.text
    newer = receive(h, (93,)).descriptors[0]
    newer_receipt = write(h, newer.id)
    assert newer_receipt.status_code == 200, newer_receipt.text
    assert newer_receipt.json()['conversation_id'] == dest2['scope']['conversation_id']
    first = receipt(write(h, descriptors[0].id), h, descriptors[0])
    receipt(write(h, descriptors[1].id), h, descriptors[1], expected=1)
    before = state(h['database'])
    assert write(h, descriptors[0].id).json() == first
    assert find(h, descriptors[0].id).json() == first
    assert state(h['database']) == before
    with h['database'].session() as db:
        for name in ('assistant_runs','assistant_model_attempts','task_executions','review_runs'):
            assert db.scalar(text('SELECT count(*) FROM '+name)) == 0


def test_http_preserves_per_target_prefix_and_unknown_query_is_pure(chat):
    h = setup(chat); descriptors = receive(h).descriptors
    before = state(h['database'])
    assert write(h, descriptors[1].id).status_code == 409
    assert find(h, uuid4()).status_code == 403
    assert find(h, descriptors[1].id).json() is None
    assert state(h['database']) == before
    receipt(write(h, descriptors[0].id), h, descriptors[0])
    receipt(write(h, descriptors[1].id), h, descriptors[1], expected=1)


def test_target_cid_cannot_reverse_resolve_the_authorizing_root(chat):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    first = receipt(write(h, descriptor.id), h, descriptor)
    root = h['base']; h['base'] = endpoint(h['destination']['scope']['conversation_id'])
    before = state(h['database'])
    assert find(h, descriptor.id).json() is None
    assert write(h, descriptor.id).status_code == 409
    assert state(h['database']) == before
    h['base'] = root
    assert find(h, descriptor.id).json() == first


@pytest.mark.parametrize('foreign', ['peer','account'])
def test_cid_cannot_choose_another_peer_or_account_descriptor(chat, foreign):
    h = setup(chat, other_peer=foreign == 'peer')
    account, mapping = h['account'], h['other_mapping']
    if foreign == 'account':
        view, binding = target(h['client'], h['headers'])
        account = accounts.create_synthetic_account(h['actor'],
            d.WeixinAccountCreateInput(bot_account_id='synthetic-http-other-bot'), database=h['database'])
        mapping = accounts.bind_synthetic_peer(h['actor'], account.id, d.WeixinPeerBindInput(
            sender_peer_id='synthetic-http-other-peer', task_binding_id=binding['id'],
            expected_scope=d.ScopeSnapshot(**view['scope'])), database=h['database'])
        dest, destination_binding = target(h['client'], h['headers'])
        response = h['client'].post(endpoint(view['scope']['conversation_id'])+'/generations',
            headers=h['headers'], json=payload(mapping, dest, destination_binding))
        assert response.status_code == 200, response.text
    descriptor = receive(h, (99,), mapping=mapping, account=account).descriptors[0]
    before = state(h['database'])
    assert write(h, descriptor.id).status_code == 403
    assert find(h, descriptor.id).status_code == 403
    assert state(h['database']) == before


def test_unauthenticated_dispatch_and_query_precede_unknown_root_and_body(chat):
    client, _, _ = chat; base = endpoint(uuid4())
    assert client.post(base+'/dispatches', content='not-json').status_code == 401
    assert client.get(base+'/dispatches/by-descriptor/'+str(uuid4())).status_code == 401


@pytest.mark.parametrize('damage', ['csrf','origin','fetch_site','owner','unknown','workspace',
    'archived','account_revoked','mapping_revoked','restore'])
def test_current_root_guard_precedes_any_dispatch_body_parse(chat, monkeypatch, damage):
    h = setup(chat); cid = h['view']['scope']['conversation_id']
    async def unread(*args):
        raise AssertionError('root authority and restored fence must precede JSON')
    monkeypatch.setattr(module(), 'body_input', unread)
    if damage == 'csrf': h['headers'] = {}
    elif damage == 'origin': h['headers'] = {**h['headers'],'Origin':'https://evil.invalid'}
    elif damage == 'fetch_site': h['headers'] = {**h['headers'],'Sec-Fetch-Site':'same-site'}
    elif damage == 'owner': h['headers'] = sign_in(h['client'], '另一合成律师')
    elif damage == 'unknown': h['base'] = endpoint(uuid4())
    elif damage == 'workspace': advance(h['database'], cid, workspace_id=str(uuid4()))
    elif damage == 'archived': advance(h['database'], cid, archived_at='2099-01-01T00:00:00Z')
    elif damage in ('account_revoked','mapping_revoked'):
        operation = accounts.revoke_synthetic_account if damage == 'account_revoked' else accounts.revoke_synthetic_peer
        identifier = h['account'].id if damage == 'account_revoked' else h['mapping'].id
        operation(h['actor'], identifier, d.WeixinRevokeInput(reason='independent synthetic HTTP revoke'), database=h['database'])
    else:
        with h['database'].session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    response = h['client'].post(h['base']+'/dispatches', headers=h['headers'], content='not-json')
    assert response.status_code == (409 if damage in ('archived','account_revoked','mapping_revoked','restore') else 403)


@pytest.mark.parametrize('raw_body,expected', [('not-json',422),
    ('{"descriptor_id":"a","descriptor_id":"b"}',422),('x'*(256*1024+1),413),
    ('[]',422),('{"descriptor_id":7}',422),('{"descriptor_id":"bad"}',422),('{}',422)],
    ids=['json','duplicate','size','array','integer','bad-uuid','missing'])
def test_dispatch_body_is_strict_and_bounded(chat, raw_body, expected):
    h = setup(chat); before = state(h['database'])
    response = h['client'].post(h['base']+'/dispatches', headers=h['headers'], content=raw_body)
    assert response.status_code == expected, response.text
    assert state(h['database']) == before


@pytest.mark.parametrize('extra', ['mapping_id','account_id','actor_id','task_binding_id','scope',
    'generation','expected_task_cursor','mode','state','receipt_sha256','reason'])
def test_body_has_no_caller_authority_target_cursor_or_receipt_override(chat, extra):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    before = state(h['database'])
    response = h['client'].post(h['base']+'/dispatches', headers=h['headers'],
        json={'descriptor_id':str(descriptor.id),extra:str(uuid4())})
    assert response.status_code == 422, response.text
    assert state(h['database']) == before


@pytest.mark.parametrize('change', ['session','account','mapping','archive'])
def test_body_read_race_rechecks_current_authority(chat, monkeypatch, change):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    original = module().body_input
    async def changed(request, model):
        value = await original(request, model)
        if change == 'session':
            with h['database'].session() as db: db.execute(text('UPDATE sessions SET revoked=1'))
        elif change == 'archive':
            advance(h['database'], h['view']['scope']['conversation_id'], archived_at='2099-01-01T00:00:00Z')
        else:
            operation = accounts.revoke_synthetic_account if change == 'account' else accounts.revoke_synthetic_peer
            identifier = h['account'].id if change == 'account' else h['mapping'].id
            operation(h['actor'], identifier, d.WeixinRevokeInput(reason='independent synthetic parse race'), database=h['database'])
        return value
    monkeypatch.setattr(module(), 'body_input', changed)
    response = write(h, descriptor.id)
    assert response.status_code == (401 if change == 'session' else 409), response.text
    with h['database'].session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_dispatch_receipts')) == 0
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events')) == 0


def test_fixed_receipt_does_not_expose_transport_identity_payload_or_reason(chat):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    response = write(h, descriptor.id); value = receipt(response, h, descriptor)
    for hidden in (str(h['account'].id),str(h['mapping'].id),str(h['actor'].user_id),
        str(h['actor'].session_id),h['account'].bot_account_id,h['mapping'].sender_peer_id,
        h['binding']['id'],'请审查独立虚构合同','独立合成：显式增加历史目标记录'):
        assert hidden not in response.text
    before = state(h['database'])
    assert find(h, descriptor.id).json() == value
    assert state(h['database']) == before


@pytest.mark.parametrize('position', ['root','fixed_target','later_target'])
def test_get_uses_current_root_and_fixed_target_acl_without_latest_substitution(chat, position):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    value = receipt(write(h, descriptor.id), h, descriptor)
    dest2, binding2 = target(h['client'], h['headers'])
    request = payload(h['mapping'], dest2, binding2, h['generation'])
    request['expected_checkpoint_revision'] = 1
    response = h['client'].post(h['base']+'/generations',headers=h['headers'],json=request)
    assert response.status_code == 200, response.text
    cid = {'root':h['view'],'fixed_target':h['destination'],'later_target':dest2}[position]['scope']['conversation_id']
    deny_projected_case(h, cid)
    before = state(h['database'])
    found = find(h, descriptor.id)
    if position == 'later_target':
        assert found.status_code == 200 and found.json() == value
    else:
        assert found.status_code == 403, found.text
    after = state(h['database'])
    if position == 'root':
        assert set(after) == set(before)
        for table, rows in before.items():
            if table != 'audit_events':
                assert after[table] == rows, table
        old, recorded = before['audit_events'], after['audit_events']
        assert len(recorded) == len(old)+1 and recorded[:-1] == old
        payload = json.loads(recorded[-1][-1])
        assert payload.pop('reason_sha256') == hashlib.sha256(b'CROSS_MATTER_DENIED').hexdigest()
        assert 'reason' not in payload
        audit = d.AuditEvent.model_validate({**payload,'reason':'CROSS_MATTER_DENIED'})
        assert audit.action == 'authorization_denied' and audit.reason == 'CROSS_MATTER_DENIED'
        assert audit.actor_id == h['actor'].user_id
        assert str(audit.correlation_id) == found.json()['correlation_id']
        assert audit.before_hash is None and audit.after_hash is None
        assert audit.entity_type == 'matter' and audit.entity_id == audit.matter_id
        assert recorded[-1][:4] == (str(audit.id),str(audit.matter_id),str(audit.actor_id),audit.action)
        with h['database'].session() as db:
            denied_matter = db.scalar(text('''SELECT intake.matter_id FROM intake_cases intake
                JOIN assistant_conversations conversation ON conversation.projection_intake_id=intake.id
                WHERE conversation.id=:id'''),{'id':cid})
        assert str(audit.matter_id) == denied_matter
    else:
        assert after == before


def test_revocation_preserves_fixed_read_but_blocks_replay(chat):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    value = receipt(write(h, descriptor.id), h, descriptor)
    accounts.revoke_synthetic_account(h['actor'],h['account'].id,
        d.WeixinRevokeInput(reason='independent synthetic fixed read'),database=h['database'])
    before = state(h['database'])
    assert find(h,descriptor.id).json() == value
    assert write(h,descriptor.id).status_code == 409
    assert state(h['database']) == before


def test_lost_http_ack_is_reconciled_by_get_without_another_delivery(chat, monkeypatch):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    call = module().conversation.dispatch_descriptor
    def lost(*args, **kwargs):
        call(*args, **kwargs)
        raise OSError('independent synthetic HTTP acknowledgement lost')
    monkeypatch.setattr(module().conversation, 'dispatch_descriptor', lost)
    with pytest.raises(OSError, match='acknowledgement lost'):
        write(h, descriptor.id)
    before = state(h['database'])
    value = receipt(find(h, descriptor.id), h, descriptor)
    assert value['next_task_cursor'] == 1 and state(h['database']) == before
    with h['database'].session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_inbox_events')) == 1
        assert db.scalar(text('SELECT count(*) FROM weixin_dispatch_receipts')) == 1


def test_get_same_origin_and_exact_lower_uuid_recovery_predicate(chat):
    h = setup(chat); path = h['base']+'/dispatches/by-descriptor/'+str(uuid4())
    predicate = module().is_weixin_authorization_read_path
    assert predicate(path)
    upper = h['base']+'/dispatches/by-descriptor/ABCDEF12-3456-4789-ABCD-EF1234567890'
    for near in (h['base']+'/dispatches',path+'/',path+'/x',h['base']+'/dispatches/by-descriptor/bad',
        upper,h['base']+'/dispatches/latest',h['base']+'/dispatches/by-descriptor/'+uuid4().hex):
        assert not predicate(near), near
    for headers in ({'Origin':'https://evil.invalid'}, {'Sec-Fetch-Site':'same-site'}):
        assert h['client'].get(path,headers=headers).status_code == 403


def test_recovery_allows_only_exact_fixed_dispatch_reads_and_never_posts(native):
    from cn_contract.web import local_server
    original, root = native
    with TestClient(original) as client:
        h = setup((client, original.state.database, root))
        descriptor = receive(h, (91,)).descriptors[0]
        value = receipt(write(h, descriptor.id), h, descriptor)
        with h['database'].session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
    app = local_server.build_local_app(root, data_parent=root.parent.parent)
    try:
        with TestClient(app) as restored:
            headers = sign_in(restored)
            path = h['base']+'/dispatches/by-descriptor/'+str(descriptor.id)
            assert restored.get(path).json() == value
            assert restored.post(h['base']+'/dispatches',headers=headers,json={'descriptor_id':str(descriptor.id)}).status_code == 409
            upper = h['base']+'/dispatches/by-descriptor/ABCDEF12-3456-4789-ABCD-EF1234567890'
            for near in (path+'/',path+'/x',h['base']+'/dispatches',upper):
                assert restored.get(near).status_code == 409
    finally:
        app.state.database.engine.dispose()
