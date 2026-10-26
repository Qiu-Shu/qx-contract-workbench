"""Versioned synthetic archive delivery; fixtures are not runtime dispatch proof."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.ops import backup
from cn_contract.record_codec import sha
from cn_contract.storage_schema import identify_schema
from cn_contract.security import provision_user
from cn_contract.task_drafts import service as tasks
from cn_contract.weixin_inbox import accounts, ingress
from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
from cn_contract.weixin_inbox.generation_integrity import validate_peer_generations
from cn_contract.weixin_inbox.provenance_integrity import validate_descriptor_generations
from tests.helpers.synthetic_weixin_provenance import chain, insert, poll_sample, snapshot
from tests.integration.test_weixin_dispatch_integrity import corrupt, rehash_receipt
from tests.integration.test_weixin_generation_integrity import rehash_generation
from tests.integration.test_weixin_ingress_atomic import world
from tests.integration.test_weixin_provenance import rewrite


def deliver(h, descriptor, generation=None):
    """Build an independent receipt after a real TaskInbox receive; no dispatcher call."""
    binding_id = generation.task_binding_id if generation else h['mapping'].task_binding_id
    with h['database'].session() as db:
        binding = tasks.read_binding(h['actor'], binding_id, db)
        received = tasks.receive_batch(h['actor'], binding_id, d.TaskInboxBatchInput(
            expected_cursor=binding.cursor, next_cursor=binding.cursor+1, events=(descriptor.payload,)), db)
        created = db.scalar(text('SELECT created_at FROM task_inbox_events WHERE id=:id'),
                            {'id': str(received.events[0].id)})
        at = accounts._activity_time(h['account'].id, db, now=ingress._at(), after=True, floor=(created,))
        fields = dict(id=str(uuid4()), descriptor_id=str(descriptor.id), account_id=str(h['account'].id),
            mapping_id=str(descriptor.mapping_id), actor_id=str(h['actor'].user_id),
            task_binding_id=str(binding_id), task_event_id=str(received.events[0].id),
            source_event_id=descriptor.source_event_id, payload_sha256=sha(descriptor.payload.model_dump(mode='json')),
            expected_task_cursor=binding.cursor, next_task_cursor=binding.cursor+1, created_at=at)
        receipt = d.WeixinDispatchReceipt(**fields, receipt_sha256=sha(fields))
        insert(db, 'weixin_dispatch_receipts', receipt.model_dump(mode='json'))
    return receipt


def validate(h):
    with h['database'].session() as db:
        assert validate_dispatch_records(db, allow_dispatch=True) == []
        assert validate_peer_generations(db, allow_generations=True) == []
        assert validate_descriptor_generations(db, allow_provenance=True) == []
        backup._file_references(db)


def freeze_v18(h):
    with h['database'].session() as db:
        db.execute(text('DROP TABLE assistant_evidence_revisions'))
        db.execute(text('DROP INDEX IF EXISTS weixin_dispatch_binding_cursor'))
        rows = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        assert identify_schema(rows, native=True) == 'weixin-target-provenance-v1'


def test_late_generation_one_delivery_keeps_its_target_and_independent_stream_cursor(world):
    h=chain(world)
    first=deliver(h,h['one'][1],h['first'])
    second=deliver(h,h['two'][1],h['second'])
    assert first.created_at > h['second'].created_at
    assert first.expected_task_cursor == second.expected_task_cursor == 0
    before=snapshot(h['database']);validate(h)
    assert snapshot(h['database']) == before
    with h['database'].session() as db:
        assert db.scalar(text('SELECT count(*) FROM task_drafts WHERE conversation_id=:id'),
            {'id':str(h['first'].scope.conversation_id)}) == 1
        assert db.scalar(text('SELECT 1 FROM weixin_dispatch_receipts WHERE descriptor_id=:id'),
            {'id':str(h['received'].descriptors[1].id)}) is None


def test_frozen_v18_still_rejects_the_same_nonzero_delivery(world):
    h=chain(world);deliver(h,h['one'][1],h['first']);freeze_v18(h)
    before=snapshot(h['database'])
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_DISPATCH_INTEGRITY'):
        validate_dispatch_records(db,allow_dispatch=True)
    assert snapshot(h['database']) == before


def test_zero_stream_may_continue_after_generations_only_under_v19(world):
    h=chain(world);receipt=deliver(h,h['received'].descriptors[1]);validate(h)
    assert receipt.task_binding_id==h['binding'].id
    freeze_v18(h)
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_GENERATION_INTEGRITY'):
        validate_peer_generations(db,allow_generations=True)


def test_public_dispatch_validator_checks_rehashed_generation_parents(world):
    h=chain(world);deliver(h,h['two'][1],h['second'])
    with h['database'].session() as db:
        corrupt(db,'UPDATE weixin_peer_generations SET previous_scope_sha256=:sha WHERE id=:id',
            {'id':str(h['second'].id),'sha':'f'*64})
        rehash_generation(db,h['second'].id)
        changed=db.scalar(text('SELECT generation_sha256 FROM weixin_peer_generations WHERE id=:id'),
            {'id':str(h['second'].id)})
        rewrite(db,h['two'][1].id,generation_sha256=changed)
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_DISPATCH_INTEGRITY'):
        validate_dispatch_records(db,allow_dispatch=True)


@pytest.mark.parametrize('damage',['wrong_target','before_generation','before_poll','payload','event','actor'])
def test_recomputed_receipt_cannot_move_or_change_fixed_delivery(world,damage):
    h=chain(world);receipt=deliver(h,h['one'][1],h['first'])
    changes={'wrong_target':('task_binding_id',str(h['second'].task_binding_id)),
        'before_generation':('created_at',(h['first'].created_at-timedelta(microseconds=1)).isoformat()),
        'before_poll':('created_at',h['first'].created_at.isoformat()),
        'payload':('payload_sha256','f'*64),'event':('source_event_id','synthetic:wrong'),
        'actor':('actor_id',str(uuid4()))}
    field,value=changes[damage]
    with h['database'].session() as db:
        if damage=='actor':
            value=str(provision_user('synthetic-other-delivery','independent-password',{d.Role.HANDLING_LAWYER},db))
        corrupt(db,'UPDATE weixin_dispatch_receipts SET '+field+'=:value WHERE id=:id',
            {'id':str(receipt.id),'value':value})
        rehash_receipt(db,receipt.id)
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_DISPATCH_INTEGRITY'):
        validate_dispatch_records(db,allow_dispatch=True)


def test_prefix_cannot_skip_an_earlier_descriptor_in_the_same_generation(world):
    h=chain(world);_,later=poll_sample(h,h['second'],93)
    deliver(h,later,h['second'])
    with h['database'].session() as db,pytest.raises(ValueError,match='WEIXIN_DISPATCH_INTEGRITY'):
        validate_dispatch_records(db,allow_dispatch=True)
