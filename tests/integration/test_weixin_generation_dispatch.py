"""Dedicated synthetic delivery keeps each accepted source on its historical target."""
import importlib
import importlib.util
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, dispatch, generation_ingress
from tests.helpers.synthetic_weixin_generation_service import append, request as generation_request
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_dispatch_integrity import corrupt, rehash_receipt
from tests.integration.test_weixin_generation_ingress import poll_input, raw
from tests.integration.test_weixin_generation_ingress_atomic import deny_projected_case
from tests.integration.test_weixin_ingress_atomic import world


def api():
    name = 'cn_contract.weixin_inbox.generation_dispatch'
    assert importlib.util.find_spec(name) is not None, 'D2g5d needs an explicit fixed-target dispatch service'
    return importlib.import_module(name)


def receive(history, messages):
    return generation_ingress.record_generation_poll(history['actor'], history['account'].id,
        poll_input(history), raw(messages), database=history['database'])


def state(database):
    with database.session() as db:
        names = db.scalars(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        return {name: [tuple(row) for row in db.execute(text('SELECT * FROM "'+name+'" ORDER BY rowid'))]
                for name in names}


def validate(history):
    with history['database'].session() as db:
        backup._file_references(db)


def saved(service, history, descriptor):
    return service.dispatch_generation_descriptor(history['actor'], descriptor.id, database=history['database'])


@pytest.mark.parametrize('file_first', [False, True])
def test_two_message_orders_enter_one_fixed_generation_draft_without_execution(world, file_first):
    service = api(); history = setup_history(world); generation = append(history)
    received = receive(history, [message(91, file=file_first), message(92, file=not file_first)])
    saved = [service.dispatch_generation_descriptor(history['actor'], descriptor.id,
        database=history['database']) for descriptor in received.descriptors]
    assert [value.task_binding_id for value in saved] == [generation.task_binding_id]*2
    assert [value.expected_task_cursor for value in saved] == [0, 1]
    with history['database'].session() as db:
        listing = tasks.list_drafts(history['actor'], generation.scope.conversation_id, db)
        assert len(listing.items) == 1 and len(listing.items[0].events) == 2
        assert listing.items[0].state == 'collecting' and 'media_pending' in listing.items[0].blockers
        assert listing.binding.cursor == 2
        for name in ('assistant_runs', 'assistant_model_attempts', 'task_executions', 'review_runs'):
            assert db.scalar(text('SELECT count(*) FROM '+name)) == 0
    assert service.find_generation_dispatch_receipt(history['actor'], received.descriptors[0].id,
        database=history['database']) == saved[0]
    validate(history)


def test_generations_and_zero_target_pending_have_independent_prefixes_and_cursors(world):
    service = api(); h = setup_history(world); first = append(h)
    one = receive(h, [message(91), message(92)])
    second = append(h, generation_request(h, first))
    two = receive(h, [message(93), message(94, peer=h['peer'].sender_peer_id)])
    # Older accepted root/first-generation work must not be redirected or block generation two.
    newer = saved(service, h, two.descriptors[0])
    original = saved(service, h, one.descriptors[0])
    following = saved(service, h, one.descriptors[1])
    old_root = saved(service, h, h['received'].descriptors[1])
    other_peer = saved(service, h, two.descriptors[1])
    assert (newer.task_binding_id, newer.expected_task_cursor) == (second.task_binding_id, 0)
    assert (original.task_binding_id, original.expected_task_cursor, following.next_task_cursor) == (first.task_binding_id, 0, 2)
    assert (old_root.task_binding_id, old_root.expected_task_cursor) == (h['mapping'].task_binding_id, 1)
    assert (other_peer.task_binding_id, other_peer.expected_task_cursor) == (h['peer'].task_binding_id, 1)
    assert newer.mapping_id == original.mapping_id == h['mapping'].id
    validate(h)


def test_same_target_order_and_nonaccepted_sources_never_create_a_receipt(world):
    service = api(); h = setup_history(world); append(h)
    received = receive(h, [message(91), message(92), message(91), message(93, peer='synthetic-unbound')])
    before = state(h['database'])
    with pytest.raises(ServiceError) as error:
        saved(service, h, received.descriptors[1])
    assert error.value.code == 'VERSION_CONFLICT'
    for descriptor in received.descriptors[2:]:
        with pytest.raises(ServiceError) as error:
            saved(service, h, descriptor)
        assert error.value.code == 'STATE_CONFLICT'
        assert service.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=h['database']) is None
    assert service.find_generation_dispatch_receipt(h['actor'], received.descriptors[0].id, database=h['database']) is None
    assert state(h['database']) == before
    saved(service, h, received.descriptors[0]); saved(service, h, received.descriptors[1])
    validate(h)


@pytest.mark.parametrize('change', ['session', 'role', 'account', 'peer', 'root_archive', 'target_archive', 'scope', 'restore'])
def test_new_delivery_rechecks_authority_but_fixed_find_only_requires_current_acl(world, change):
    service = api(); h = setup_history(world); generation = append(h)
    received = receive(h, [message(91), message(92)])
    fixed = saved(service, h, received.descriptors[0])
    if change in ('account', 'peer'):
        call = accounts.revoke_synthetic_account if change == 'account' else accounts.revoke_synthetic_peer
        call(h['actor'], h['account'].id if change == 'account' else h['mapping'].id,
            d.WeixinRevokeInput(reason='independent synthetic delivery revocation'), database=h['database'])
    else:
        with h['database'].session() as db:
            if change == 'session': db.get(SessionRow, str(h['actor'].session_id)).revoked = True
            elif change == 'role': db.get(UserRow, str(h['actor'].user_id)).roles = '["assistant"]'
            elif change == 'restore': db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
            elif change == 'scope': db.execute(text('UPDATE assistant_conversations SET input_revision=1 WHERE id=:id'), {'id':str(generation.scope.conversation_id)})
            else:
                cid = h['mapping'].scope.conversation_id if change == 'root_archive' else generation.scope.conversation_id
                db.execute(text("UPDATE assistant_conversations SET archived_at='2099-01-01T00:00:00Z' WHERE id=:id"), {'id':str(cid)})
    before = state(h['database'])
    with pytest.raises(ServiceError) as error:
        saved(service, h, received.descriptors[1])
    expected = {'session':'AUTHORIZATION_REQUIRED', 'role':'CROSS_MATTER_DENIED', 'account':'STATE_CONFLICT',
                'peer':'STATE_CONFLICT', 'restore':'BLOCKED_LIVE'}.get(change, 'VERSION_CONFLICT')
    assert error.value.code == expected
    if change in ('session', 'role'):
        with pytest.raises(ServiceError):
            service.find_generation_dispatch_receipt(h['actor'], fixed.descriptor_id, database=h['database'])
    else:
        assert service.find_generation_dispatch_receipt(h['actor'], fixed.descriptor_id, database=h['database']) == fixed
    assert state(h['database']) == before


@pytest.mark.parametrize('position', ['root', 'fixed_target'])
def test_root_and_recorded_target_current_case_acl_are_pure_preconditions(world, position):
    service = api(); h = setup_history(world); generation = append(h)
    received = receive(h, [message(91), message(92)])
    fixed = saved(service, h, received.descriptors[0])
    deny_projected_case(h, h['mapping'].scope.conversation_id if position == 'root' else generation.scope.conversation_id)
    before = state(h['database'])
    for operation in (lambda:saved(service, h, received.descriptors[1]),
            lambda:service.find_generation_dispatch_receipt(h['actor'], fixed.descriptor_id, database=h['database'])):
        with pytest.raises(ServiceError) as error: operation()
        assert error.value.code == 'CROSS_MATTER_DENIED'
        assert state(h['database']) == before


def test_later_target_acl_does_not_replace_the_receipts_original_target(world):
    service = api(); h = setup_history(world); first = append(h)
    descriptor = receive(h, [message(91)]).descriptors[0]
    fixed = saved(service, h, descriptor)
    second = append(h, generation_request(h, first))
    deny_projected_case(h, second.scope.conversation_id)
    before = state(h['database'])
    assert service.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=h['database']) == fixed
    assert saved(service, h, descriptor) == fixed
    assert state(h['database']) == before


def test_local_inbox_collision_is_not_adopted_as_generation_delivery(world):
    service = api(); h = setup_history(world); generation = append(h)
    descriptor = receive(h, [message(91)]).descriptors[0]
    with h['database'].session() as db:
        tasks.receive_batch(h['actor'], generation.task_binding_id,
            d.TaskInboxBatchInput(expected_cursor=0, next_cursor=1, events=(descriptor.payload,)), db)
    before = state(h['database'])
    with pytest.raises(ServiceError) as error: saved(service, h, descriptor)
    assert error.value.code == 'VERSION_CONFLICT' and state(h['database']) == before


@pytest.mark.parametrize('point', ['task_cursor', 'receipt', 'commit'])
def test_sql_and_commit_failure_keeps_task_and_dispatch_atomic(world, monkeypatch, point):
    service = api(); h = setup_history(world); append(h)
    descriptor = receive(h, [message(91)]).descriptors[0]
    database = h['database']; before = state(database); triggered = []
    if point == 'commit':
        def fail(session):
            triggered.append(point)
            raise OSError('independent synthetic delivery commit failure')
        with monkeypatch.context() as patch:
            patch.setattr(database.session_factory.class_, 'commit', fail)
            with pytest.raises(OSError): saved(service, h, descriptor)
    else:
        def fail(connection, cursor, statement, parameters, context, executemany):
            sql = ' '.join(statement.lower().split())
            if (point == 'task_cursor' and sql.startswith('update task_channel_bindings')
                    or point == 'receipt' and sql.startswith('insert into weixin_dispatch_receipts')):
                triggered.append(point)
                raise OSError('independent synthetic delivery SQL failure')
        event.listen(database.engine, 'before_cursor_execute', fail)
        try:
            with pytest.raises(OSError): saved(service, h, descriptor)
        finally:
            event.remove(database.engine, 'before_cursor_execute', fail)
    assert triggered == [point] and state(database) == before
    assert service.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=database) is None
    assert saved(service, h, descriptor).next_task_cursor == 1
    validate(h)


def test_actual_commit_with_lost_ack_is_only_reconciled_as_a_fixed_receipt(world, monkeypatch):
    service = api(); h = setup_history(world); append(h)
    descriptor = receive(h, [message(91)]).descriptors[0]
    database = h['database']; commit = database.session_factory.class_.commit; committed = []
    def lose_ack(session):
        commit(session); committed.append(True)
        raise OSError('independent synthetic delivery acknowledgement lost')
    with monkeypatch.context() as patch:
        patch.setattr(database.session_factory.class_, 'commit', lose_ack)
        with pytest.raises(OSError): saved(service, h, descriptor)
    assert committed == [True]
    fixed = service.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=database)
    assert fixed is not None and fixed.next_task_cursor == 1
    before = state(database)
    assert saved(service, h, descriptor) == fixed and state(database) == before
    validate(h)


@pytest.mark.parametrize('clock', ['same', 'backwards'])
def test_delivery_time_orders_poll_generation_and_event_without_rewriting_wall_time(world, monkeypatch, clock):
    service = api(); h = setup_history(world); generation = append(h)
    poll = receive(h, [message(91)]); descriptor = poll.descriptors[0]
    stamp = poll.created_at.isoformat() if clock == 'same' else '2000-01-01T00:00:00Z'
    monkeypatch.setattr(dispatch, '_at', lambda:stamp)
    monkeypatch.setattr(tasks, '_at', lambda:stamp)
    receipt = saved(service, h, descriptor)
    assert receipt.created_at > poll.created_at > generation.created_at
    with h['database'].session() as db:
        event_at = db.scalar(text('SELECT created_at FROM task_inbox_events WHERE id=:id'), {'id':str(receipt.task_event_id)})
        assert event_at == stamp
    validate(h)


@pytest.mark.parametrize('change', ['schema18', 'no_generation'])
def test_only_native_v19_generation_accounts_can_use_new_delivery(world, change):
    service = api(); h = setup_history(world)
    if change == 'schema18':
        append(h); descriptor = receive(h, [message(91)]).descriptors[0]
        with h['database'].session() as db: db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
    else: descriptor = h['received'].descriptors[1]
    before = state(h['database'])
    with pytest.raises(ServiceError) as error: saved(service, h, descriptor)
    assert error.value.code == ('VERSION_CONFLICT' if change == 'schema18' else 'STATE_CONFLICT')
    assert state(h['database']) == before


@pytest.mark.parametrize('damage', ['generation', 'sidecar'])
def test_corrupt_complete_history_is_rejected_before_delivery_or_fixed_lookup(world, damage):
    service = api(); h = setup_history(world); generation = append(h)
    descriptor = receive(h, [message(91)]).descriptors[0]
    with h['database'].session() as db:
        if damage == 'generation':
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha WHERE id=:id', {'sha':'f'*64, 'id':str(generation.id)})
        else:
            corrupt(db, 'UPDATE weixin_descriptor_generations SET payload_sha256=:sha WHERE descriptor_id=:id', {'sha':'f'*64, 'id':str(descriptor.id)})
    before = state(h['database'])
    for operation in (lambda:saved(service, h, descriptor),
            lambda:service.find_generation_dispatch_receipt(h['actor'], descriptor.id, database=h['database'])):
        with pytest.raises(ServiceError) as error: operation()
        assert error.value.code == 'VERSION_CONFLICT' and state(h['database']) == before


def test_no_generation_query_keeps_valid_legacy_receipt_readable(world):
    service = api(); h = setup_history(world)
    before = state(h['database'])
    assert service.find_generation_dispatch_receipt(h['actor'], h['dispatched'].descriptor_id,
        database=h['database']) == h['dispatched']
    assert state(h['database']) == before


@pytest.mark.parametrize('damage', ['receipt_time', 'checkpoint'])
def test_no_generation_query_still_validates_complete_legacy_parents(world, damage):
    service = api(); h = setup_history(world)
    with h['database'].session() as db:
        if damage == 'receipt_time':
            corrupt(db, "UPDATE weixin_dispatch_receipts SET created_at='2000-01-01T00:00:00Z' WHERE id=:id",
                {'id':str(h['dispatched'].id)})
            rehash_receipt(db, h['dispatched'].id)
        else:
            db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=checkpoint_revision+1 WHERE id=:id'),
                {'id':str(h['account'].id)})
    before = state(h['database'])
    with pytest.raises(ServiceError) as error:
        service.find_generation_dispatch_receipt(h['actor'], h['dispatched'].descriptor_id, database=h['database'])
    assert error.value.code == 'VERSION_CONFLICT' and state(h['database']) == before
