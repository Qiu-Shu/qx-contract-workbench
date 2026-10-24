"""Actual synthetic poll services retain every outcome without dispatch or raw secrets."""
import hashlib
import importlib
import importlib.util
import json
import socket
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.config import canonical_json
from cn_contract.security import ServiceError
from cn_contract.task_drafts import service as tasks
from test_assistant_storage import workspace


def api():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.ingress') is not None, 'D2b atomic ingress required'
    return importlib.import_module('cn_contract.weixin_inbox.ingress')


def setup(workspace):
    from cn_contract.storage_bootstrap import initialize_storage
    from cn_contract.weixin_inbox import accounts
    database, actors, _, _ = workspace
    initialize_storage(database)
    actor = actors['lawyer']
    account = accounts.create_synthetic_account(actor, d.WeixinAccountCreateInput(
        bot_account_id='synthetic-ingress-bot', initial_cursor='SYNTHETIC:start'), database=database)
    views, bindings, mappings = [], [], []
    for peer in ('synthetic-peer-a', 'synthetic-peer-b'):
        with database.session() as db:
            view = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
                request_id=uuid4(), display_title='独立虚构收件测试'), db)
            binding = tasks.create_binding(actor, view.scope.conversation_id, db)
        mapping = accounts.bind_synthetic_peer(actor, account.id, d.WeixinPeerBindInput(
            sender_peer_id=peer, task_binding_id=binding.id, expected_scope=view.scope), database=database)
        views.append(view)
        bindings.append(binding)
        mappings.append(mapping)
    return database, actors, account, tuple(mappings), tuple(views), tuple(bindings)


def message(identifier='1', peer='synthetic-peer-a', content='独立虚构待审文字'):
    return {'message_id':identifier, 'from_user_id':peer, 'to_user_id':'synthetic-ingress-bot',
        'message_type':1, 'message_state':2, 'item_list':[{'type':1, 'text_item':{'text':content}}],
        'context_token':'SYNTHETIC_CONTEXT_SECRET'}


def raw(*messages, cursor='SYNTHETIC:next'):
    return json.dumps({'ret':0, 'errcode':0, 'get_updates_buf':cursor, 'msgs':list(messages)},
        ensure_ascii=False).encode('utf-8')


def request(revision=0, cursor='SYNTHETIC:start', **changes):
    return d.WeixinPollInput(request_id=uuid4(), expected_revision=revision,
        expected_cursor=cursor, **changes)


def snapshot(database):
    names = ('weixin_accounts', 'weixin_peer_bindings', 'weixin_poll_receipts',
        'weixin_inbox_descriptors', 'task_channel_bindings', 'task_inbox_events', 'task_drafts',
        'task_executions', 'assistant_messages', 'assistant_runs', 'audit_events')
    with database.session() as db:
        return {name:[tuple(row) for row in db.execute(text('SELECT * FROM '+name+' ORDER BY rowid'))]
            for name in names}


def assert_code(code, callback):
    with pytest.raises(ServiceError) as error:
        callback()
    assert error.value.code == code


def test_atomic_mixed_peer_service_roundtrip_has_only_safe_pending_payload(workspace, monkeypatch):
    service = api()
    database, actors, account, mappings, _, _ = setup(workspace)
    def never(*args, **kwargs):
        raise AssertionError('ingress cannot use network or dispatch')
    monkeypatch.setattr(socket, 'create_connection', never)
    monkeypatch.setattr(socket.socket, 'connect', never)
    monkeypatch.setattr(tasks, 'receive_batch', never)
    file = message('18446744073709551615', 'synthetic-peer-b')
    file['item_list'] = [{'type':4, 'file_item':{'file_name':'独立虚构.pdf', 'len':'512',
        'media':{'aes_key':'SYNTHETIC_AES_SECRET', 'encrypt_query_param':'SYNTHETIC_QUERY_SECRET',
            'full_url':'https://example.invalid/no-download'}}}]
    unknown = message('3', 'synthetic-unbound')
    original = message(1)
    inputs = (original, file, unknown, {'not':'a message'})
    req, response = request(), raw(*inputs)
    before = snapshot(database)
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, req, response, database=database)
    assert [item.status for item in receipt.descriptors] == [
        'accepted_pending_dispatch', 'accepted_pending_dispatch', 'blocked', 'blocked']
    assert [item.reason for item in receipt.descriptors] == [None, None, 'sender_unbound', 'message_invalid']
    assert [item.mapping_id for item in receipt.descriptors[:2]] == [item.id for item in mappings]
    assert receipt.descriptors[0].upstream_message_id == '1'
    assert receipt.descriptors[1].upstream_message_id == '18446744073709551615'
    assert receipt.descriptors[1].payload.media[0].status == 'pending'
    assert receipt.request_sha256 == hashlib.sha256(canonical_json(req.model_dump(mode='json')).encode()).hexdigest()
    assert receipt.response_sha256 == hashlib.sha256(response).hexdigest()
    assert [item.source_sha256 for item in receipt.descriptors] == [
        hashlib.sha256(canonical_json(item).encode()).hexdigest() for item in inputs]
    assert receipt.next_revision == 1 and receipt.next_cursor == 'SYNTHETIC:next'
    assert service.find_poll_receipt(actors['lawyer'], account.id, req.request_id, database=database) == receipt
    after = snapshot(database)
    for name in ('task_channel_bindings', 'task_inbox_events', 'task_drafts', 'task_executions',
            'assistant_messages', 'assistant_runs', 'audit_events'):
        assert after[name] == before[name]
    stored = repr(after)
    assert all(secret not in stored for secret in ('SYNTHETIC_CONTEXT_SECRET', 'SYNTHETIC_AES_SECRET',
        'SYNTHETIC_QUERY_SECRET', 'example.invalid', "'not': 'a message'"))
    with database.session() as db:
        from cn_contract.weixin_inbox.integrity import validate_weixin_records
        assert validate_weixin_records(db, allow_inbox=True) == []


def test_original_source_controls_same_poll_and_later_repeats(workspace):
    service = api()
    database, actors, account, mappings, views, _ = setup(workspace)
    first = message('7')
    changed = message('7', content='changed fictional content')
    blocked = message('8', 'synthetic-unbound')
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, request(),
        raw(first, first, changed, blocked, blocked), database=database)
    assert [item.reason for item in receipt.descriptors] == [None, 'replayed', 'event_conflict',
        'sender_unbound', 'previously_blocked']
    assert receipt.descriptors[1].prior_descriptor_id == receipt.descriptors[0].id
    assert receipt.descriptors[2].prior_descriptor_id == receipt.descriptors[0].id
    assert receipt.descriptors[4].prior_descriptor_id == receipt.descriptors[3].id
    from cn_contract.weixin_inbox import accounts
    with database.session() as db:
        view = conversations.create_conversation(actors['lawyer'], d.AssistantConversationCreateInput(
            request_id=uuid4(), display_title='独立虚构后来授权'), db)
        binding = tasks.create_binding(actors['lawyer'], view.scope.conversation_id, db)
    accounts.bind_synthetic_peer(actors['lawyer'], account.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-unbound', task_binding_id=binding.id,
        expected_scope=view.scope), database=database)
    repeat = service.record_synthetic_poll(actors['lawyer'], account.id,
        request(1, receipt.next_cursor), raw(first, blocked, changed), database=database)
    assert [item.reason for item in repeat.descriptors] == ['replayed', 'previously_blocked', 'event_conflict']
    assert repeat.descriptors[1].prior_descriptor_id == receipt.descriptors[3].id
    assert all(item.payload is None for item in repeat.descriptors)
    with database.session() as db:
        from cn_contract.weixin_inbox.integrity import validate_weixin_records
        assert validate_weixin_records(db, allow_inbox=True) == []


def test_replay_ignores_advanced_checkpoint_but_conflicts_on_request_or_raw_bytes(workspace):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    req, response = request(), raw(message())
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, req, response, database=database)
    empty = service.record_synthetic_poll(actors['lawyer'], account.id,
        request(1, receipt.next_cursor), b'{"ret":0}', database=database)
    assert empty.descriptors == () and empty.descriptor_count == 0
    assert empty.next_revision == 2 and empty.next_cursor == receipt.next_cursor
    before = snapshot(database)
    assert service.record_synthetic_poll(actors['lawyer'], account.id, req, response, database=database) == receipt
    assert_code('VERSION_CONFLICT', lambda: service.record_synthetic_poll(actors['lawyer'], account.id,
        req.model_copy(update={'expected_revision':1}), response, database=database))
    assert_code('VERSION_CONFLICT', lambda: service.record_synthetic_poll(actors['lawyer'], account.id,
        req, response+b' ', database=database))
    assert service.find_poll_receipt(actors['lawyer'], account.id, uuid4(), database=database) is None
    assert snapshot(database) == before


@pytest.mark.parametrize('response', [b'{}', b'{"ret":1}', b'{"errcode":1}', b'{"ret":false}',
    b'{"ret":0,"ret":0}', b'{"ret":0,"msgs":{}}', b'{"ret":0,"get_updates_buf":5}',
    b'{"ret":0,"extra":"blocked"}', b'{"ret":0,"msgs":null}', b'\xff',
    b'{"ret":0,"longpolling_timeout_ms":-1}', raw(*[{}]*101),
    raw(cursor='x'*262145), b' '*262145], ids=[
        'empty-object', 'ret-error', 'errcode-error', 'bool-ret', 'duplicate-key', 'object-msgs',
        'numeric-cursor', 'extra-field', 'null-msgs', 'bad-utf8', 'negative-timeout',
        'over-100', 'over-cursor', 'over-bytes'])
def test_bad_envelope_refuses_whole_batch_without_checkpoint(workspace, response):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    before = snapshot(database)
    with pytest.raises(ServiceError):
        service.record_synthetic_poll(actors['lawyer'], account.id, request(), response, database=database)
    assert snapshot(database) == before


@pytest.mark.parametrize(('changes', 'reason'), [
    ({'to_user_id':'another-bot'}, 'recipient_mismatch'),
    ({'message_type':2}, 'message_unsupported'),
    ({'group_id':'synthetic-group'}, 'message_unsupported'),
    ({'extra':'ignored? never'}, 'message_unsupported'),
    ({'item_list':[]}, 'message_invalid'),
    ({'message_id':'01'}, 'message_invalid'),
    ({'message_id':True}, 'message_invalid'),
    ({'message_id':'18446744073709551616'}, 'message_invalid'),
    ({'from_user_id':'bad peer'}, 'message_invalid'),
    ({'to_user_id':5}, 'message_invalid'),
    ({'item_list':[{'type':4, 'file_item':{'file_name':'../private.pdf'}}]}, 'message_invalid'),
])
def test_bad_message_is_recorded_and_does_not_discard_valid_neighbor(workspace, changes, reason):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    bad = {**message('10'), **changes}
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, request(),
        raw(bad, message('11')), database=database)
    assert receipt.descriptors[0].status == 'blocked' and receipt.descriptors[0].reason == reason
    assert receipt.descriptors[0].payload is None
    if reason == 'message_invalid' and ('message_id' in changes or 'from_user_id' in changes):
        assert receipt.descriptors[0].source_event_id is None
        assert receipt.descriptors[0].sender_peer_id is receipt.descriptors[0].upstream_message_id is None
    assert receipt.descriptors[1].status == 'accepted_pending_dispatch'
    assert receipt.next_revision == 1


@pytest.mark.parametrize('change', ['stale', 'archived', 'revoked'])
def test_current_mapping_failure_is_pure_classification_and_preserves_other_peer(workspace, monkeypatch, change):
    service = api()
    database, actors, account, mappings, views, _ = setup(workspace)
    from cn_contract import security
    from cn_contract.weixin_inbox import accounts
    def never(*args, **kwargs):
        raise AssertionError('classification cannot audit or change transaction boundary')
    monkeypatch.setattr(security, 'deny', never)
    if change == 'revoked':
        accounts.revoke_synthetic_peer(actors['lawyer'], mappings[0].id,
            d.WeixinRevokeInput(reason='独立虚构撤权'), database=database)
    else:
        with database.session() as db:
            column = "archived_at='2026-10-24T00:00:00+00:00'" if change == 'archived' else 'materials_revision=materials_revision+1'
            db.execute(text('UPDATE assistant_conversations SET '+column+' WHERE id=:id'),
                {'id':str(views[0].scope.conversation_id)})
    before = snapshot(database)
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, request(),
        raw(message('1'), message('2', 'synthetic-peer-b')), database=database)
    assert receipt.descriptors[0].reason == ('binding_revoked' if change == 'revoked' else 'scope_stale')
    assert receipt.descriptors[1].status == 'accepted_pending_dispatch'
    assert snapshot(database)['audit_events'] == before['audit_events']


@pytest.mark.parametrize('change', ['peer_revoke', 'scope', 'session', 'forged_role', 'other_owner'])
def test_find_and_replay_recheck_current_access_before_returning_old_text(workspace, change):
    service = api()
    database, actors, account, mappings, views, _ = setup(workspace)
    actor, req, response = actors['lawyer'], request(), raw(message())
    service.record_synthetic_poll(actor, account.id, req, response, database=database)
    if change == 'peer_revoke':
        from cn_contract.weixin_inbox import accounts
        accounts.revoke_synthetic_peer(actor, mappings[0].id,
            d.WeixinRevokeInput(reason='独立虚构撤销'), database=database)
    elif change in ('scope', 'session'):
        with database.session() as db:
            if change == 'scope':
                db.execute(text('UPDATE assistant_conversations SET input_revision=input_revision+1 WHERE id=:id'),
                    {'id':str(views[0].scope.conversation_id)})
            else:
                db.execute(text('UPDATE sessions SET revoked=1 WHERE id=:id'), {'id':str(actor.session_id)})
    elif change == 'forged_role':
        actor = actors['assistant'].model_copy(update={'roles':frozenset({d.Role.HANDLING_LAWYER})})
    else:
        actor = actors['reviewer']
    before = snapshot(database)
    with pytest.raises(ServiceError):
        service.find_poll_receipt(actor, account.id, req.request_id, database=database)
    with pytest.raises(ServiceError):
        service.record_synthetic_poll(actor, account.id, req, response, database=database)
    assert snapshot(database) == before


def test_restore_fence_allows_history_lookup_and_refuses_even_identical_record_replay(workspace):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    req, response = request(), raw(message())
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, req, response, database=database)
    from cn_contract.ops.storage import RestoreFenceRow
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='1'*64,
            manifest_sha256='2'*64, payload='{}'))
    before = snapshot(database)
    assert service.find_poll_receipt(actors['lawyer'], account.id, req.request_id, database=database) == receipt
    assert_code('BLOCKED_LIVE', lambda: service.record_synthetic_poll(actors['lawyer'],
        account.id, req, response, database=database))
    assert snapshot(database) == before


def test_invalid_message_unicode_is_only_a_blocked_digest_and_neighbor_survives(workspace):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    bad = message('20', content='\ud800')
    response = json.dumps({'ret':0, 'msgs':[bad, message('21')]}).encode('utf-8')
    receipt = service.record_synthetic_poll(actors['lawyer'], account.id, request(), response, database=database)
    assert receipt.descriptors[0].reason == 'message_invalid'
    assert receipt.descriptors[0].payload is None
    assert receipt.descriptors[1].status == 'accepted_pending_dispatch'
    assert receipt.next_cursor == account.initial_cursor
    assert service.find_poll_receipt(actors['lawyer'], account.id,
        receipt.request_id, database=database) == receipt


@pytest.mark.parametrize('change', ['revision', 'cursor', 'invalid_copy'])
def test_checkpoint_and_input_revalidation_fail_without_any_poll_write(workspace, change):
    service = api()
    database, actors, account, _, _, _ = setup(workspace)
    req = request()
    if change == 'revision':
        req = req.model_copy(update={'expected_revision':1})
    elif change == 'cursor':
        req = req.model_copy(update={'expected_cursor':'incorrect'})
    else:
        req = req.model_copy(update={'expected_revision':True})
    before = snapshot(database)
    with pytest.raises((ServiceError, ValueError)):
        service.record_synthetic_poll(actors['lawyer'], account.id, req, raw(message()), database=database)
    assert snapshot(database) == before
