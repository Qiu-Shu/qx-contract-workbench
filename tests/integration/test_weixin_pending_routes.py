"""CID-rooted metadata listing never delivers a message or inherits latest access."""
from cn_contract import domain as d
import hashlib
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.weixin_inbox import accounts
from test_assistant_routes import chat, native, sign_in
from test_weixin_authorization_routes import endpoint, module, advance
from test_weixin_generation_routes import target, payload
from test_weixin_generation_ingress_atomic import deny_projected_case
from test_weixin_generation_dispatch_routes import setup, receive, state, write, find


def listing(h, **query):
    return h['client'].get(h['base']+'/pending',params={
        'target_conversation_id':h['destination']['scope']['conversation_id'],**query})


def test_http_lists_fixed_pending_metadata_without_any_business_write(chat):
    h=setup(chat);descriptors=receive(h).descriptors;before=state(h['database'])
    response=listing(h)
    assert response.status_code==200,response.text
    value=response.json()
    assert set(value)=={'mode','read_only','conversation_id','items','next_cursor'}
    assert value['mode']=='synthetic' and value['read_only'] is True
    assert value['conversation_id']==h['destination']['scope']['conversation_id']
    assert value['next_cursor'] is None
    assert [item['descriptor_id'] for item in value['items']]==[str(item.id) for item in descriptors]
    for item in value['items']:
        assert set(item)=={'descriptor_id','conversation_id','received_at','has_text','media_count'}
        assert item['conversation_id']==value['conversation_id']
        assert item['has_text'] is True and item['media_count']==0
    assert state(h['database'])==before


@pytest.mark.parametrize('query', [[], [('target_conversation_id','bad')],
    [('target_conversation_id','')], [('cursor','bad')], [('cursor','')],
    [('limit','0')], [('limit','21')], [('limit','-1')], [('limit','1.0')],
    [('limit','true')], [('limit','1e1')], [('limit',' 1')], [('limit','01')],
    [('limit','+1')], [('limit','')], [('limit','1'),('limit','2')],
    [('cursor',str(uuid4())),('cursor',str(uuid4()))],
    [('target_conversation_id','duplicate'),('target_conversation_id','duplicate')],
    [('mapping_id',str(uuid4()))]], ids=[
    'missing-target','bad-target','empty-target','bad-cursor','empty-cursor',
    'zero','too-large','negative','decimal','boolean','exponent','space','leading-zero',
    'sign','empty-limit','duplicate-limit','duplicate-cursor','duplicate-target','unknown-key'])
def test_query_is_explicit_unique_and_bounded(chat, query):
    h = setup(chat); before = state(h['database'])
    params = list(query)
    if query and not any(key == 'target_conversation_id' for key, _ in query):
        params.insert(0, ('target_conversation_id', h['destination']['scope']['conversation_id']))
    response = h['client'].get(h['base']+'/pending', params=params)
    assert response.status_code == 422, response.text
    assert state(h['database']) == before


def test_unauthenticated_request_precedes_invalid_query_and_unknown_root(chat):
    client, _, _ = chat
    response = client.get(endpoint(uuid4())+'/pending?limit=bad')
    assert response.status_code == 401, response.text


@pytest.mark.parametrize('damage', ['origin','fetch_site','owner','unknown','workspace'])
def test_current_root_guard_precedes_invalid_query(chat, damage):
    h = setup(chat); headers = {}
    if damage == 'origin': headers = {'Origin':'https://evil.invalid'}
    elif damage == 'fetch_site': headers = {'Sec-Fetch-Site':'same-site'}
    elif damage == 'owner': sign_in(h['client'], '另一合成律师')
    elif damage == 'unknown': h['base'] = endpoint(uuid4())
    else: advance(h['database'], h['view']['scope']['conversation_id'], workspace_id=str(uuid4()))
    before = state(h['database'])
    response = h['client'].get(h['base']+'/pending?limit=bad', headers=headers)
    assert response.status_code == 403, response.text
    assert state(h['database']) == before


def test_http_keyset_survives_dispatched_anchor_and_observes_new_poll(chat):
    h = setup(chat); first = receive(h, (91,92,93)).descriptors
    one = listing(h, limit=1)
    assert one.status_code == 200, one.text
    assert [item['descriptor_id'] for item in one.json()['items']] == [str(first[0].id)]
    assert one.json()['next_cursor'] == str(first[0].id)
    assert write(h, first[0].id).status_code == 200
    newest = receive(h, (94,)).descriptors[0]
    before = state(h['database'])
    two = listing(h, cursor=one.json()['next_cursor'], limit=20)
    assert two.status_code == 200, two.text
    assert [item['descriptor_id'] for item in two.json()['items']] == [
        str(first[1].id), str(first[2].id), str(newest.id)]
    assert two.json()['next_cursor'] is None
    assert state(h['database']) == before


@pytest.mark.parametrize('position', ['root','fixed_target','later_target'])
def test_http_checks_explicit_historical_target_acl(chat, position):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    later, binding = target(h['client'], h['headers'])
    request = payload(h['mapping'], later, binding, h['generation'])
    request['expected_checkpoint_revision'] = 1
    response = h['client'].post(h['base']+'/generations',headers=h['headers'],json=request)
    assert response.status_code == 200, response.text
    cid = {'root':h['view'],'fixed_target':h['destination'],'later_target':later}[position]['scope']['conversation_id']
    deny_projected_case(h, cid)
    before = state(h['database'])
    result = listing(h)
    assert result.status_code == (200 if position == 'later_target' else 403), result.text
    if position == 'later_target':
        assert [item['descriptor_id'] for item in result.json()['items']] == [str(descriptor.id)]
    after = state(h['database'])
    if position != 'later_target':
        # Existing case authorization denial intentionally appends one security audit.
        assert len(after['audit_events']) == len(before['audit_events'])+1
        audit = json.loads(after['audit_events'][-1][-1])
        assert audit['action'] == 'authorization_denied'
        assert audit['actor_id'] == str(h['actor'].user_id)
        assert audit['correlation_id'] == result.json()['correlation_id']
        assert audit['reason_sha256'] == hashlib.sha256(b'CROSS_MATTER_DENIED').hexdigest()
        assert 'reason' not in audit
        assert after.pop('audit_events')[:-1] == before.pop('audit_events')
    assert after == before


@pytest.mark.parametrize('change', ['account','mapping','archive'])
def test_metadata_read_does_not_grant_dispatch_authority(chat, change):
    h = setup(chat); descriptor = receive(h, (91,)).descriptors[0]
    if change == 'archive':
        advance(h['database'], h['destination']['scope']['conversation_id'], archived_at='2099-01-01T00:00:00Z')
    else:
        operation = accounts.revoke_synthetic_account if change == 'account' else accounts.revoke_synthetic_peer
        identifier = h['account'].id if change == 'account' else h['mapping'].id
        operation(h['actor'], identifier, d.WeixinRevokeInput(reason='synthetic pending read'), database=h['database'])
    before = state(h['database'])
    result = listing(h)
    assert result.status_code == 200, result.text
    assert [item['descriptor_id'] for item in result.json()['items']] == [str(descriptor.id)]
    assert write(h, descriptor.id).status_code == 409
    assert state(h['database']) == before


def test_foreign_peer_cursor_and_target_cannot_resolve_root(chat):
    h = setup(chat, other_peer=True)
    descriptor = receive(h, (99,), mapping=h['other_mapping']).descriptors[0]
    before = state(h['database'])
    assert listing(h, cursor=str(descriptor.id)).status_code == 403
    assert listing(h, target_conversation_id=str(uuid4())).status_code == 403
    # A valid destination has no mapping of its own: never reverse-resolve its root.
    h['base'] = endpoint(h['destination']['scope']['conversation_id'])
    result = listing(h)
    assert result.status_code == 200 and result.json()['items'] == []
    assert state(h['database']) == before


@pytest.mark.parametrize('foreign', ['peer', 'unbound'])
def test_http_rejects_owned_but_unrelated_target(chat, foreign):
    h = setup(chat, other_peer=True)
    if foreign == 'peer':
        cid = str(h['other_mapping'].scope.conversation_id)
    else:
        view, _ = target(h['client'], h['headers'])
        cid = view['scope']['conversation_id']
    before = state(h['database'])
    response = listing(h, target_conversation_id=cid)
    assert response.status_code == 403, response.text
    assert state(h['database']) == before


def test_transaction_rechecks_session_after_http_authorization(chat, monkeypatch):
    from cn_contract.weixin_inbox import pending
    h = setup(chat); receive(h)
    original = pending.list_pending_descriptors
    def revoked(*args, **kwargs):
        with h['database'].session() as db:
            db.execute(text('UPDATE sessions SET revoked=1'))
        return original(*args, **kwargs)
    monkeypatch.setattr(pending, 'list_pending_descriptors', revoked)
    response = listing(h)
    assert response.status_code == 401, response.text
    with h['database'].session() as db:
        for table in ('weixin_dispatch_receipts','task_inbox_events','assistant_model_attempts'):
            assert db.scalar(text('SELECT count(*) FROM '+table)) == 0


def test_recovery_blocks_pending_but_keeps_exact_receipt_get(native):
    from cn_contract.web import local_server
    original, root = native
    with TestClient(original) as client:
        h = setup((client, original.state.database, root))
        descriptors = receive(h).descriptors
        receipt = write(h, descriptors[0].id)
        assert receipt.status_code == 200, receipt.text
        assert not module().is_weixin_authorization_read_path(h['base']+'/pending')
        with h['database'].session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()),archive_sha256='a'*64,manifest_sha256='b'*64,payload='{}'))
        assert listing(h).status_code == 409
    app = local_server.build_local_app(root, data_parent=root.parent.parent)
    try:
        with TestClient(app) as restored:
            sign_in(restored); h['client'] = restored
            before = state(app.state.database)
            assert listing(h).status_code == 409
            assert find(h, descriptors[0].id).json() == receipt.json()
            assert state(app.state.database) == before
    finally:
        app.state.database.engine.dispose()
