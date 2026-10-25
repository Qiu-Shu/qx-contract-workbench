"""Independent HTTP seam probes; reuse only pre-D2g5e synthetic setup helpers."""
import inspect
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.weixin_inbox import accounts, conversation, generation_dispatch, generation_ingress
from cn_contract.web import weixin_authorization as routes
from test_assistant_routes import chat, native
from test_weixin_authorization_routes import bind, endpoint
from test_weixin_generation_routes import target, payload
from test_weixin_generation_ingress import raw
from test_weixin_generation_ingress_atomic import deny_projected_case
from test_weixin_dispatch import message


def fixture(chat, *, other=False):
    client, database, root, headers, origin, actor, account, mapping = bind(chat)
    second_root = None
    if other:
        other_view, other_binding = target(client, headers)
        accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
            sender_peer_id='synthetic-independent-other-root', task_binding_id=other_binding['id'],
            expected_scope=d.ScopeSnapshot(**other_view['scope'])), database=database)
        second_root = endpoint(other_view['scope']['conversation_id'])
    destination, binding = target(client, headers)
    base = endpoint(origin['scope']['conversation_id'])
    response = client.post(base+'/generations', headers=headers, json=payload(mapping, destination, binding))
    assert response.status_code == 200, response.text
    return dict(client=client, database=database, headers=headers, origin=origin, actor=actor,
        account=account, mapping=mapping, destination=destination, binding=binding,
        generation=response.json(), base=base, second_root=second_root)


def receive(h):
    account = accounts.read_synthetic_account(h['actor'], h['account'].id, database=h['database'])
    value = {**message(8461, peer=h['mapping'].sender_peer_id), 'to_user_id':account.bot_account_id,
        'item_list':[{'type':1, 'text_item':{'text':'synthetic-independent-private-text-canary'}}]}
    receipt = generation_ingress.record_generation_poll(h['actor'], account.id,
        d.WeixinPollInput(request_id=uuid4(), expected_revision=account.checkpoint_revision,
            expected_cursor=account.upstream_cursor), raw([value], 'synthetic-independent-private-cursor'),
        database=h['database'])
    return receipt.descriptors[0]


def task_state(h):
    names = ('task_channel_bindings', 'task_inbox_events', 'task_drafts', 'task_executions',
        'weixin_dispatch_receipts', 'assistant_runs', 'assistant_model_attempts', 'review_runs')
    with h['database'].session() as db:
        return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
            for name in names}


def post(h, descriptor, base=None):
    return h['client'].post((base or h['base'])+'/dispatches', headers=h['headers'],
        json={'descriptor_id':str(descriptor.id)})


def get(h, descriptor, base=None):
    return h['client'].get((base or h['base'])+'/dispatches/by-descriptor/'+str(descriptor.id))


def test_final_transaction_rechecks_root_after_both_http_authorizations(chat, monkeypatch):
    h = fixture(chat); descriptor = receive(h); before = task_state(h)
    original = routes.run_in_threadpool
    async def before_threadpool(operation, *args, **kwargs):
        assert operation is conversation.dispatch_descriptor
        with h['database'].session() as db:
            db.execute(text("UPDATE assistant_conversations SET archived_at='2099-01-01T00:00:00Z' WHERE id=:id"),
                {'id':h['origin']['scope']['conversation_id']})
        return await original(operation, *args, **kwargs)
    monkeypatch.setattr(routes, 'run_in_threadpool', before_threadpool)
    response = post(h, descriptor)
    assert response.status_code == 409 and response.json()['code'] == 'STATE_CONFLICT', response.text
    assert task_state(h) == before
    assert get(h, descriptor).status_code == 200 and get(h, descriptor).json() is None


def test_fixed_old_delivery_ignores_denied_later_target_and_redacts_transport(chat):
    h = fixture(chat); descriptor = receive(h)
    later, later_binding = target(h['client'], h['headers'])
    value = payload(h['mapping'], later, later_binding, h['generation'], expected_checkpoint_revision=1)
    second = h['client'].post(h['base']+'/generations', headers=h['headers'], json=value)
    assert second.status_code == 200, second.text
    deny_projected_case(h, later['scope']['conversation_id'])
    response = post(h, descriptor)
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {'mode','state','descriptor_id','conversation_id','task_event_id',
        'expected_task_cursor','next_task_cursor','created_at','receipt_sha256'}
    assert result['conversation_id'] == h['destination']['scope']['conversation_id']
    for secret in ('synthetic-independent-private-text-canary','synthetic-independent-private-cursor',
            h['account'].bot_account_id, h['mapping'].sender_peer_id, str(h['actor'].user_id),
            str(h['actor'].session_id), str(h['account'].id), str(h['mapping'].id), h['binding']['id']):
        assert secret not in response.text
    before = task_state(h)
    assert get(h, descriptor).json() == result
    assert task_state(h) == before


def test_same_owner_same_account_other_root_cannot_choose_descriptor(chat):
    h = fixture(chat, other=True); descriptor = receive(h); before = task_state(h)
    for response in (get(h, descriptor, h['second_root']), post(h, descriptor, h['second_root'])):
        assert response.status_code == 403 and response.json()['code'] == 'CROSS_MATTER_DENIED', response.text
    assert task_state(h) == before
    assert post(h, descriptor).status_code == 200


def test_lost_http_ack_only_gets_saved_result_without_invoking_write_again(chat, monkeypatch):
    h = fixture(chat); descriptor = receive(h)
    original = conversation.dispatch_descriptor
    def lost_ack(*args, **kwargs):
        original(*args, **kwargs)
        raise ConnectionError('independent synthetic loss after actual commit')
    monkeypatch.setattr(conversation, 'dispatch_descriptor', lost_ack)
    with pytest.raises(ConnectionError, match='after actual commit'):
        post(h, descriptor)
    before = task_state(h)
    def no_resend(*args, **kwargs):
        raise AssertionError('fixed GET must never call the write path')
    monkeypatch.setattr(conversation, 'dispatch_descriptor', no_resend)
    found = get(h, descriptor)
    assert found.status_code == 200 and found.json()['descriptor_id'] == str(descriptor.id), found.text
    assert len(before['task_inbox_events']) == len(before['weixin_dispatch_receipts']) == 1
    assert task_state(h) == before


def test_legacy_public_signatures_and_exact_recovery_predicate_remain_closed():
    for operation in (generation_dispatch.dispatch_generation_descriptor,
            generation_dispatch.find_generation_dispatch_receipt):
        assert str(inspect.signature(operation)) == '(actor, descriptor_id, *, database)'
    root, descriptor = str(uuid4()), str(uuid4())
    base = endpoint(root)
    valid = base+'/dispatches/by-descriptor/'+descriptor
    assert routes.is_weixin_authorization_read_path(valid)
    for invalid in (valid+'/', valid+'/extra', valid.upper(), base+'/dispatches',
            base+'/dispatches/by-descriptor/not-a-uuid', base+'/dispatches/by-request/'+descriptor):
        assert not routes.is_weixin_authorization_read_path(invalid)
