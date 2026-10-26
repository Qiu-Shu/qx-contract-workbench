"""Only metadata for one explicit historical target; real synthetic services."""
import importlib
import importlib.util
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts, generation_dispatch
from tests.helpers.synthetic_weixin_generation_service import append, request as generation_request
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.integration.test_weixin_dispatch import message, poll
from tests.integration.test_weixin_dispatch_integrity import corrupt
from tests.integration.test_weixin_generation_dispatch import receive, state
from tests.integration.test_weixin_generation_ingress_atomic import deny_projected_case
from tests.integration.test_weixin_ingress_atomic import world


def api():
    name = 'cn_contract.weixin_inbox.pending'
    module = importlib.import_module(name) if importlib.util.find_spec(name) is not None else None
    assert callable(getattr(module, 'list_pending_descriptors', None)), (
        'D2g5g requires the public fixed-target list_pending_descriptors service')
    for model in ('WeixinPendingQuery', 'WeixinPendingDescriptorView', 'WeixinPendingPage'):
        assert hasattr(d, model), 'D2g5g requires centralized ' + model
    return module


def page(history, target, *, cursor=None, limit=20):
    return api().list_pending_descriptors(history['actor'], history['view'].scope.conversation_id,
        d.WeixinPendingQuery(target_conversation_id=target, cursor=cursor, limit=limit),
        database=history['database'])


def test_public_service_lists_fixed_target_metadata_without_writes(world):
    api()
    history = setup_history(world); generation = append(history)
    incoming = receive(history, [message(91), message(92, file=True)])
    before = state(history['database'])
    result = page(history, generation.scope.conversation_id)
    assert result.mode == 'synthetic' and result.read_only is True
    assert result.conversation_id == generation.scope.conversation_id and result.next_cursor is None
    assert [item.descriptor_id for item in result.items] == [item.id for item in incoming.descriptors]
    assert [(item.has_text, item.media_count) for item in result.items] == [(True, 0), (False, 1)]
    for item in result.items:
        assert item.received_at == incoming.created_at
        assert item.conversation_id == generation.scope.conversation_id
        assert set(item.model_dump(mode='json')) == {
            'descriptor_id', 'conversation_id', 'received_at', 'has_text', 'media_count'}
    assert state(history['database']) == before


def ids(value):
    return [item.descriptor_id for item in value.items]


def rejected(history, target, *, code='CROSS_MATTER_DENIED', cursor=None, cid=None, denial_audit=False):
    before = state(history['database'])
    with pytest.raises(ServiceError) as caught:
        api().list_pending_descriptors(history['actor'], cid or history['view'].scope.conversation_id,
            d.WeixinPendingQuery(target_conversation_id=target, cursor=cursor), database=history['database'])
    assert caught.value.code == code
    after = state(history['database'])
    if denial_audit:
        # Existing security.deny intentionally commits one separate refusal audit.
        # Read-only means no business write; it must not suppress that policy.
        original, amended = before.pop('audit_events'), after.pop('audit_events')
        assert amended[:-1] == original and len(amended) == len(original) + 1
        recorded = json.loads(amended[-1][-1])
        assert recorded['action'] == 'authorization_denied'
        assert recorded['actor_id'] == str(history['actor'].user_id)
        assert recorded['entity_type'] == 'matter' and 'reason' not in recorded
    assert after == before


@pytest.mark.parametrize('limit', [0, 21, -1, True, '2', 1.0, None])
def test_query_rejects_non_strict_or_out_of_bounds_limit(limit):
    api()
    with pytest.raises(ValidationError):
        d.WeixinPendingQuery(target_conversation_id=uuid4(), limit=limit)


@pytest.mark.parametrize('values', [{}, {'target_conversation_id':'not-a-uuid'},
    {'target_conversation_id':str(uuid4()), 'cursor':'1'},
    {'target_conversation_id':str(uuid4()), 'extra':'private'}])
def test_query_requires_explicit_target_uuid_and_forbids_extra_fields(values):
    api()
    with pytest.raises(ValidationError):
        d.WeixinPendingQuery(**values)


def test_keyset_continues_after_dispatched_anchor_and_new_poll_without_writes(world):
    h = setup_history(world); generation = append(h)
    first = receive(h, [message(91), message(92), message(91), message(93, peer='synthetic-unbound'), message(94)])
    second = receive(h, [message(95), message(96)])
    assert [item.status for item in first.descriptors] == [
        'accepted_pending_dispatch', 'accepted_pending_dispatch', 'duplicate', 'blocked', 'accepted_pending_dispatch']
    before = state(h['database'])
    one = page(h, generation.scope.conversation_id, limit=2)
    assert ids(one) == [item.id for item in first.descriptors[:2]]
    assert one.next_cursor == first.descriptors[1].id and state(h['database']) == before
    for descriptor in first.descriptors[:2]:
        generation_dispatch.dispatch_generation_descriptor(h['actor'], descriptor.id, database=h['database'])
    # Anchor remains the same immutable source even though it is no longer pending.
    before = state(h['database'])
    two = page(h, generation.scope.conversation_id, cursor=one.next_cursor, limit=2)
    assert ids(two) == [first.descriptors[4].id, second.descriptors[0].id]
    assert two.next_cursor == second.descriptors[0].id and state(h['database']) == before
    latest = receive(h, [message(97)])
    before = state(h['database'])
    three = page(h, generation.scope.conversation_id, cursor=two.next_cursor, limit=2)
    assert ids(three) == [second.descriptors[1].id, latest.descriptors[0].id]
    assert three.next_cursor is None and state(h['database']) == before
    assert page(h, generation.scope.conversation_id, cursor=latest.descriptors[0].id).items == ()


def test_maximum_twenty_has_only_one_lookahead_and_query_bypass_is_revalidated(world, monkeypatch):
    h = setup_history(world); generation = append(h)
    incoming = receive(h, [message(index) for index in range(100, 122)])
    checked = []; original = generation_dispatch._source
    def observed(*args, **kwargs):
        checked.append(args[1])
        return original(*args, **kwargs)
    monkeypatch.setattr(generation_dispatch, '_source', observed)
    before = state(h['database'])
    result = page(h, generation.scope.conversation_id)
    assert ids(result) == [item.id for item in incoming.descriptors[:20]]
    assert result.next_cursor == incoming.descriptors[19].id
    assert len(checked) == 21 and state(h['database']) == before
    malformed = d.WeixinPendingQuery.model_construct(target_conversation_id=generation.scope.conversation_id, limit=21)
    with pytest.raises(ValidationError):
        api().list_pending_descriptors(h['actor'], h['view'].scope.conversation_id, malformed, database=h['database'])


def test_old_root_and_two_generations_and_peer_have_independent_pending_lists(world):
    h = setup_history(world); first = append(h)
    old = receive(h, [message(91), message(92)])
    second = append(h, generation_request(h, first))
    new = receive(h, [message(93), message(94, peer=h['peer'].sender_peer_id)])
    before = state(h['database'])
    assert ids(page(h, h['view'].scope.conversation_id)) == [h['received'].descriptors[1].id]
    assert ids(page(h, first.scope.conversation_id)) == [item.id for item in old.descriptors]
    assert ids(page(h, second.scope.conversation_id)) == [new.descriptors[0].id]
    peer_page = api().list_pending_descriptors(h['actor'], h['peer_view'].scope.conversation_id,
        d.WeixinPendingQuery(target_conversation_id=h['peer_view'].scope.conversation_id), database=h['database'])
    assert ids(peer_page) == [new.descriptors[1].id]
    # A target CID is not a way to discover the original root mapping.
    target_page = api().list_pending_descriptors(h['actor'], first.scope.conversation_id,
        d.WeixinPendingQuery(target_conversation_id=first.scope.conversation_id), database=h['database'])
    assert target_page.items == () and target_page.next_cursor is None
    assert state(h['database']) == before


@pytest.mark.parametrize('kind', ['unknown', 'root', 'peer', 'other_target', 'blocked', 'duplicate'])
def test_cursor_must_be_an_accepted_source_of_exact_root_and_target(world, kind):
    h = setup_history(world); first = append(h)
    incoming = receive(h, [message(91), message(91), message(92, peer='synthetic-unbound')])
    second = append(h, generation_request(h, first))
    other = receive(h, [message(93), message(94, peer=h['peer'].sender_peer_id)])
    cursor = dict(unknown=uuid4(), root=h['received'].descriptors[1].id,
        peer=other.descriptors[1].id, other_target=other.descriptors[0].id,
        blocked=incoming.descriptors[2].id, duplicate=incoming.descriptors[1].id)[kind]
    rejected(h, first.scope.conversation_id, cursor=cursor)


def test_no_mapping_empty_page_and_unknown_target_or_cursor_do_not_create_records(world):
    h = setup_history(world)
    unbound = h['targets'][0][0].scope.conversation_id
    before = state(h['database'])
    result = api().list_pending_descriptors(h['actor'], unbound,
        d.WeixinPendingQuery(target_conversation_id=unbound), database=h['database'])
    assert result.items == () and result.next_cursor is None
    assert state(h['database']) == before
    rejected(h, unbound, cid=unbound, cursor=uuid4())
    rejected(h, uuid4())


@pytest.mark.parametrize('foreign', ['peer', 'unbound'])
def test_existing_root_rejects_owned_but_unrelated_target(world, foreign):
    h = setup_history(world); append(h)
    target = h['peer_view'] if foreign == 'peer' else h['targets'][1][0]
    rejected(h, target.scope.conversation_id)


def test_related_generation_without_descriptors_has_empty_page(world):
    h = setup_history(world); generation = append(h)
    before = state(h['database'])
    result = page(h, generation.scope.conversation_id)
    assert result.items == () and result.next_cursor is None
    assert state(h['database']) == before


def test_other_account_cursor_is_not_adopted_even_for_same_owner_and_peer(world):
    h = setup_history(world); generation = append(h)
    local = receive(h, [message(91)])
    target, binding = h['targets'][1]
    other = accounts.create_synthetic_account(h['actor'], d.WeixinAccountCreateInput(
        bot_account_id='synthetic-pending-other-bot'), database=h['database'])
    accounts.bind_synthetic_peer(h['actor'], other.id, d.WeixinPeerBindInput(
        sender_peer_id='synthetic-peer', task_binding_id=binding.id,
        expected_scope=target.scope), database=h['database'])
    wire = message(91)
    wire['to_user_id'] = other.bot_account_id
    foreign = poll(world, other, [wire])
    before = state(h['database'])
    assert ids(page(h, generation.scope.conversation_id)) == [local.descriptors[0].id]
    assert state(h['database']) == before
    rejected(h, generation.scope.conversation_id, cursor=foreign.descriptors[0].id)


def test_bare_unbound_root_is_empty_but_still_validates_unrelated_complete_history(world):
    _, database, actor, view, _ = world
    before = state(database)
    query = d.WeixinPendingQuery(target_conversation_id=view.scope.conversation_id)
    assert api().list_pending_descriptors(actor, view.scope.conversation_id, query, database=database).items == ()
    assert state(database) == before
    h = setup_history(world)
    unbound = h['targets'][0][0].scope.conversation_id
    with database.session() as db:
        corrupt(db, "UPDATE weixin_dispatch_receipts SET created_at='2000-01-01T00:00:00Z' WHERE id=:id", {'id':str(h['dispatched'].id)})
    rejected(h, unbound, cid=unbound, code='VERSION_CONFLICT')


@pytest.mark.parametrize('change', ['account', 'peer', 'root_archive', 'target_archive', 'scope'])
def test_readable_history_does_not_restore_write_authority(world, change):
    h = setup_history(world); generation = append(h)
    incoming = receive(h, [message(91)])
    if change in ('account', 'peer'):
        call = accounts.revoke_synthetic_account if change == 'account' else accounts.revoke_synthetic_peer
        call(h['actor'], h['account'].id if change == 'account' else h['mapping'].id,
            d.WeixinRevokeInput(reason='独立合成列表读取撤销'), database=h['database'])
    else:
        with h['database'].session() as db:
            if change == 'scope':
                db.execute(text('UPDATE assistant_conversations SET input_revision=input_revision+1 WHERE id=:id'),
                    {'id':str(generation.scope.conversation_id)})
            else:
                cid = h['view'].scope.conversation_id if change == 'root_archive' else generation.scope.conversation_id
                db.execute(text("UPDATE assistant_conversations SET archived_at='2099-01-01T00:00:00Z' WHERE id=:id"), {'id':str(cid)})
    before = state(h['database'])
    assert ids(page(h, generation.scope.conversation_id)) == [incoming.descriptors[0].id]
    with pytest.raises(ServiceError):
        generation_dispatch.dispatch_generation_descriptor(h['actor'], incoming.descriptors[0].id, database=h['database'])
    assert state(h['database']) == before


@pytest.mark.parametrize('change', ['session', 'role', 'restore', 'root_owner', 'target_owner', 'target_workspace'])
def test_current_principal_fence_and_object_ownership_are_not_cached(world, change):
    h = setup_history(world); generation = append(h)
    receive(h, [message(91)])
    with h['database'].session() as db:
        if change == 'session': db.get(SessionRow, str(h['actor'].session_id)).revoked = True
        elif change == 'role': db.get(UserRow, str(h['actor'].user_id)).roles = '["assistant"]'
        elif change == 'restore': db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
        else:
            cid = h['view'].scope.conversation_id if change == 'root_owner' else generation.scope.conversation_id
            column = 'workspace_id' if change == 'target_workspace' else 'owner_id'
            replacement = db.get(UserRow, str(h['actor'].user_id)).id if column == 'owner_id' else str(uuid4())
            if column == 'owner_id':
                from cn_contract.security import provision_user
                replacement = str(provision_user('synthetic-pending-other', 'Independent-other-52!', {d.Role.HANDLING_LAWYER}, db))
            db.execute(text('UPDATE assistant_conversations SET '+column+'=:value WHERE id=:id'), {'id':str(cid), 'value':replacement})
    code = {'session':'AUTHORIZATION_REQUIRED', 'restore':'BLOCKED_LIVE'}.get(change, 'CROSS_MATTER_DENIED')
    rejected(h, generation.scope.conversation_id, code=code)


@pytest.mark.parametrize('position', ['root', 'target'])
def test_current_case_membership_is_required_even_for_empty_page(world, position):
    h = setup_history(world); generation = append(h)
    cid = h['view'].scope.conversation_id if position == 'root' else generation.scope.conversation_id
    deny_projected_case(h, cid)
    rejected(h, generation.scope.conversation_id, denial_audit=True)


@pytest.mark.parametrize('denied_target', ['old', 'latest'])
def test_other_generations_lost_case_access_does_not_replace_selected_target_acl(world, denied_target):
    h = setup_history(world); first = append(h)
    old = receive(h, [message(91)])
    second = append(h, generation_request(h, first))
    new = receive(h, [message(92)])
    denied, permitted, incoming = (first, second, new) if denied_target == 'old' else (second, first, old)
    deny_projected_case(h, denied.scope.conversation_id)
    before = state(h['database'])
    assert ids(page(h, permitted.scope.conversation_id)) == [incoming.descriptors[0].id]
    assert state(h['database']) == before
    rejected(h, denied.scope.conversation_id, denial_audit=True)


@pytest.mark.parametrize('damage', ['schema', 'generation', 'sidecar', 'checkpoint', 'legacy_receipt'])
def test_full_history_damage_is_rejected_including_empty_filtered_target(world, damage):
    h = setup_history(world); generation = append(h)
    incoming = receive(h, [message(91)])
    with h['database'].session() as db:
        if damage == 'schema': db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
        elif damage == 'generation':
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha WHERE id=:id', {'sha':'f'*64, 'id':str(generation.id)})
        elif damage == 'sidecar':
            corrupt(db, 'UPDATE weixin_descriptor_generations SET payload_sha256=:sha WHERE descriptor_id=:id', {'sha':'f'*64, 'id':str(incoming.descriptors[0].id)})
        elif damage == 'checkpoint':
            db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=checkpoint_revision+1 WHERE id=:id'), {'id':str(h['account'].id)})
        else:
            corrupt(db, "UPDATE weixin_dispatch_receipts SET created_at='2000-01-01T00:00:00Z' WHERE id=:id", {'id':str(h['dispatched'].id)})
    for target in (generation.scope.conversation_id, h['targets'][1][0].scope.conversation_id):
        rejected(h, target, code='VERSION_CONFLICT')


def test_list_executes_no_dml_and_projects_only_five_metadata_fields(world):
    h = setup_history(world); generation = append(h)
    incoming = receive(h, [message(91, content='合成私密正文-不得回传'), message(92, file=True)])
    writes = []
    def observe(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith(('insert ', 'update ', 'delete ', 'replace ')):
            writes.append(statement)
    event.listen(h['database'].engine, 'before_cursor_execute', observe)
    try:
        result = page(h, generation.scope.conversation_id)
    finally:
        event.remove(h['database'].engine, 'before_cursor_execute', observe)
    assert writes == [] and ids(result) == [item.id for item in incoming.descriptors]
    assert set(result.model_dump()) == {'mode','read_only','conversation_id','items','next_cursor'}
    raw = result.model_dump_json()
    for secret in ('合成私密正文', '独立虚构合同', 'synthetic-dispatch-bot', 'synthetic-peer', 'opaque:',
            str(h['account'].id), str(h['mapping'].id), str(generation.task_binding_id), str(incoming.id)):
        assert secret not in raw
    for item in result.items:
        assert item.received_at.utcoffset().total_seconds() == 0
