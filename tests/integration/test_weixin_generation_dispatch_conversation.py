"""CID-bound synthetic delivery uses the final transaction and a redacted receipt."""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.security import ServiceError
from cn_contract.weixin_inbox import accounts, conversation, generation_dispatch
from tests.helpers.synthetic_weixin_generation_service import append, request
from tests.helpers.synthetic_weixin_generations import setup_history
from tests.integration.test_weixin_dispatch import message
from tests.integration.test_weixin_generation_dispatch import receive, state, validate
from tests.integration.test_weixin_ingress_atomic import world


KEYS = {'mode', 'state', 'descriptor_id', 'conversation_id', 'task_event_id',
        'expected_task_cursor', 'next_task_cursor', 'created_at', 'receipt_sha256'}


def api():
    assert hasattr(conversation, 'dispatch_descriptor'), 'D2g5e needs a CID-owned final transaction'
    assert hasattr(conversation, 'find_dispatch'), 'D2g5e needs exact CID-owned receipt recovery'
    assert hasattr(d, 'WeixinGenerationDispatchInput'), 'dispatch body has only the descriptor UUID'
    return conversation


def setup(world):
    h = setup_history(world)
    first = append(h)
    received = receive(h, [message(91), message(92)])
    return h, first, received.descriptors


def send(h, cid, descriptor):
    return api().dispatch_descriptor(h['actor'], cid,
        d.WeixinGenerationDispatchInput(descriptor_id=descriptor.id), database=h['database'])


def find(h, cid, descriptor_id):
    return api().find_dispatch(h['actor'], cid, descriptor_id, database=h['database'])


def test_fixed_receipt_projection_and_public_python_service_share_one_acknowledgement(world):
    h, first, descriptors = setup(world)
    second = append(h, request(h, first))
    cid = h['view'].scope.conversation_id
    before = state(h['database'])
    assert find(h, cid, descriptors[0].id) is None
    assert state(h['database']) == before
    result = send(h, cid, descriptors[0])
    value = result.model_dump(mode='json')
    assert set(value) == KEYS and value['mode'] == 'synthetic' and value['state'] == 'recorded'
    assert result.conversation_id == first.scope.conversation_id != second.scope.conversation_id
    private = generation_dispatch.find_generation_dispatch_receipt(h['actor'], descriptors[0].id,
        database=h['database'])
    assert (result.task_event_id, result.receipt_sha256) == (private.task_event_id, private.receipt_sha256)
    assert (result.expected_task_cursor, result.next_task_cursor) == (0, 1)
    for hidden in (str(h['account'].id), str(h['mapping'].id), str(h['actor'].user_id),
                   str(first.task_binding_id), h['account'].bot_account_id, h['mapping'].sender_peer_id,
                   private.source_event_id, descriptors[0].payload.text):
        assert hidden not in result.model_dump_json()
    before = state(h['database'])
    assert send(h, cid, descriptors[0]) == result == find(h, cid, descriptors[0].id)
    assert state(h['database']) == before
    validate(h)


@pytest.mark.parametrize('operation', ['send', 'find'])
def test_other_owned_peer_cannot_deliver_or_read_the_roots_descriptor(world, operation):
    h, _, descriptors = setup(world)
    if operation == 'find':
        send(h, h['view'].scope.conversation_id, descriptors[0])
    before = state(h['database'])
    with pytest.raises(ServiceError) as error:
        if operation == 'send': send(h, h['peer_view'].scope.conversation_id, descriptors[0])
        else: find(h, h['peer_view'].scope.conversation_id, descriptors[0].id)
    assert error.value.code == 'CROSS_MATTER_DENIED'
    assert state(h['database']) == before


def test_target_cid_does_not_reverse_resolve_a_root_and_unknown_id_does_not_leak(world):
    h, first, descriptors = setup(world)
    before = state(h['database'])
    assert find(h, first.scope.conversation_id, descriptors[0].id) is None
    with pytest.raises(ServiceError) as error: send(h, first.scope.conversation_id, descriptors[0])
    assert error.value.code == 'STATE_CONFLICT'
    with pytest.raises(ServiceError) as error: find(h, h['view'].scope.conversation_id, uuid4())
    assert error.value.code == 'CROSS_MATTER_DENIED'
    assert state(h['database']) == before


@pytest.mark.parametrize('change', ['root_archive', 'target_archive', 'target_revision', 'account', 'peer', 'restore'])
def test_fixed_query_survives_logical_state_changes_without_enabling_a_write(world, change):
    h, first, descriptors = setup(world)
    cid = h['view'].scope.conversation_id
    fixed = send(h, cid, descriptors[0])
    if change in ('account', 'peer'):
        call = accounts.revoke_synthetic_account if change == 'account' else accounts.revoke_synthetic_peer
        identifier = h['account'].id if change == 'account' else h['mapping'].id
        call(h['actor'], identifier, d.WeixinRevokeInput(reason='独立合成CID分发撤权'), database=h['database'])
    else:
        with h['database'].session() as db:
            if change == 'restore':
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
            elif change == 'target_revision':
                db.execute(text('UPDATE assistant_conversations SET input_revision=input_revision+1 WHERE id=:id'),
                           {'id': str(first.scope.conversation_id)})
            else:
                target = cid if change == 'root_archive' else first.scope.conversation_id
                db.execute(text("UPDATE assistant_conversations SET archived_at='2099-01-01T00:00:00Z' WHERE id=:id"), {'id': str(target)})
    before = state(h['database'])
    assert find(h, cid, descriptors[0].id) == fixed
    with pytest.raises(ServiceError): send(h, cid, descriptors[1])
    assert state(h['database']) == before


def test_projection_failure_rolls_back_task_event_cursor_and_receipt_together(world, monkeypatch):
    h, _, descriptors = setup(world)
    api()
    before = state(h['database'])
    triggered = []
    def fail(*args):
        triggered.append(True)
        raise OSError('independent synthetic response construction failure')
    with monkeypatch.context() as patch:
        patch.setattr(conversation, '_dispatch_receipt', fail)
        with pytest.raises(OSError): send(h, h['view'].scope.conversation_id, descriptors[0])
    assert triggered == [True] and state(h['database']) == before
    assert find(h, h['view'].scope.conversation_id, descriptors[0].id) is None


@pytest.mark.parametrize('extra', ['account_id', 'root_mapping_id', 'task_binding_id', 'actor_id', 'mode', 'scope'])
def test_dispatch_input_cannot_supply_server_authority(extra):
    api()
    with pytest.raises(ValidationError):
        d.WeixinGenerationDispatchInput(descriptor_id=uuid4(), **{extra: str(uuid4())})


def test_receipt_projection_requires_exact_one_step_cursor_and_immutable_shape(world):
    h, _, descriptors = setup(world)
    value = send(h, h['view'].scope.conversation_id, descriptors[0])
    with pytest.raises(ValidationError):
        type(value).model_validate({**value.model_dump(mode='python'), 'next_task_cursor': 5})
    with pytest.raises(ValidationError):
        type(value).model_validate({**value.model_dump(mode='python'), 'account_id': uuid4()})
    with pytest.raises(ValidationError): value.state = 'history_only'
