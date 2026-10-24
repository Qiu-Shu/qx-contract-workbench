"""Independent fictional dispatch history; SQL fixtures do not implement runtime dispatch."""
import importlib
import importlib.util
import json
import sqlite3
from contextlib import closing
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from cn_contract import domain as d
from cn_contract.config import canonical_json, load_settings
from cn_contract.ops import backup
from cn_contract.persistence import Database
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError, authenticate, login, provision_user
from cn_contract.storage_schema import VERSIONS, schema_rows
from cn_contract.web.local_server import initialize_workspace
from cn_contract.weixin_offline import event_id
from tests.helpers.legacy_assistant_backup import PASSWORD, USERNAME
from tests.helpers.synthetic_weixin_inbox import insert, seed_history
from tests.integration.test_weixin_ingress_atomic import world


def validator():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.dispatch_integrity') is not None, 'D2c needs dispatch provenance validation'
    return importlib.import_module('cn_contract.weixin_inbox.dispatch_integrity').validate_dispatch_records


@pytest.mark.parametrize('version', [v for v in VERSIONS if v != 'weixin-dispatch-v1'])
@pytest.mark.parametrize('native', [False, True])
def test_known_pre_dispatch_schema_without_table_stays_readable(version, native):
    # Dropping the known-schema check would incorrectly reject an actual old archive.
    with closing(sqlite3.connect(':memory:')) as connection:
        for kind, _, _, sql in schema_rows(version, native=native):
            if kind == 'table':
                connection.execute(sql)
        for kind, _, _, sql in schema_rows(version, native=native):
            if kind != 'table' and sql is not None:
                connection.execute(sql)
        engine = create_engine('sqlite://', creator=lambda: connection)
        with Session(engine) as db:
            assert validator()(db) == []


def test_unknown_schema_is_rejected_even_without_dispatch_table():
    with Session(create_engine('sqlite://')) as db:
        with pytest.raises(ValueError, match='WEIXIN_DISPATCH_INTEGRITY'):
            validator()(db, allow_dispatch=True)


def corrupt(db, sql, values=None):
    """Model an altered archive while restoring its exact immutable schema afterward."""
    triggers = db.execute(text("SELECT name,sql FROM sqlite_master WHERE type='trigger'")).all()
    for name, _ in triggers:
        db.execute(text('DROP TRIGGER '+name))
    db.execute(text('PRAGMA ignore_check_constraints=ON'))
    try:
        db.execute(text(sql), values or {})
    finally:
        db.execute(text('PRAGMA ignore_check_constraints=OFF'))
        for _, statement in triggers:
            db.execute(text(statement))


def rehash_receipt(db, identifier):
    value = dict(db.execute(text('SELECT * FROM weixin_dispatch_receipts WHERE id=:id'),
        {'id':str(identifier)}).mappings().one())
    value.pop('receipt_sha256')
    corrupt(db, 'UPDATE weixin_dispatch_receipts SET receipt_sha256=:sha WHERE id=:id',
        {'id':str(identifier), 'sha':sha(value)})


def rehash_poll(db, identifier):
    value = dict(db.execute(text('SELECT * FROM weixin_poll_receipts WHERE id=:id'),
        {'id':str(identifier)}).mappings().one())
    value.pop('receipt_sha256')
    value['descriptors'] = []
    for stored in db.execute(text('SELECT * FROM weixin_inbox_descriptors WHERE poll_id=:id ORDER BY ordinal'),
            {'id':str(identifier)}).mappings():
        item = dict(stored)
        raw = item.pop('payload_json')
        item['payload'] = json.loads(raw) if raw is not None else None
        value['descriptors'].append(item)
    corrupt(db, 'UPDATE weixin_poll_receipts SET receipt_sha256=:sha WHERE id=:id',
        {'id':str(identifier), 'sha':sha(value)})


def dispatch_row(db, seed, descriptor, cursor, at):
    """Independent archive fixture only; root tests the actual dispatch service separately."""
    mapping = next(item for item in seed['mappings'] if item.id == descriptor.mapping_id)
    payload = descriptor.payload.model_dump(mode='json')
    task_event = dict(id=str(uuid4()), binding_id=str(mapping.task_binding_id),
        event_id=descriptor.source_event_id, payload_sha256=sha(payload),
        payload_json=canonical_json(payload), created_at=at.isoformat().replace('+00:00','Z'))
    insert(db, 'task_inbox_events', task_event)
    row = dict(id=str(uuid4()), descriptor_id=str(descriptor.id), account_id=str(seed['account_id']),
        mapping_id=str(mapping.id), actor_id=str(seed['actor'].user_id),
        task_binding_id=str(mapping.task_binding_id), task_event_id=task_event['id'],
        source_event_id=descriptor.source_event_id, payload_sha256=task_event['payload_sha256'],
        expected_task_cursor=cursor, next_task_cursor=cursor+1, created_at=task_event['created_at'])
    row['receipt_sha256'] = sha(row)
    insert(db, 'weixin_dispatch_receipts', row)
    db.execute(text('UPDATE task_channel_bindings SET cursor=:cursor WHERE id=:id'),
        {'cursor':cursor+1, 'id':str(mapping.task_binding_id)})
    return row


@pytest.fixture
def history(tmp_path):
    root = tmp_path/'独立虚构派发历史'
    initialize_workspace(root, USERNAME, PASSWORD, data_parent=tmp_path)
    database = Database('sqlite:///'+str(root/'workbench.db'), root/'protected', load_settings(), initialize_schema=False)
    backup._mark_storage_flags(database)
    try:
        with database.session() as db:
            token, _ = login(USERNAME, PASSWORD, db)
            actor = authenticate(token, db)
            other = provision_user('独立虚构其他派发者', 'synthetic-password', {d.Role.HANDLING_LAWYER}, db)
        seed = seed_history(database, actor)
        first, second = seed['receipts'][:2]
        mapping = seed['mappings'][0]
        extra = []
        with database.session() as db:
            for poll, message_id in ((first, '105'), (second, '106')):
                source = event_id(seed['account'].bot_account_id, mapping.sender_peer_id, message_id)
                descriptor = d.WeixinInboxDescriptor(id=uuid4(), poll_id=poll.id, ordinal=5,
                    sender_peer_id=mapping.sender_peer_id, upstream_message_id=message_id,
                    source_event_id=source, source_sha256=sha(['independent-dispatch', message_id]),
                    status='accepted_pending_dispatch', mapping_id=mapping.id,
                    payload=d.TaskInboxEventInput(event_id=source, text='独立虚构后续说明'+message_id))
                values = descriptor.model_dump(mode='json', exclude={'payload'})
                values['payload_json'] = canonical_json(descriptor.payload.model_dump(mode='json'))
                insert(db, 'weixin_inbox_descriptors', values)
                corrupt(db, 'UPDATE weixin_poll_receipts SET descriptor_count=5 WHERE id=:id', {'id':str(poll.id)})
                rehash_poll(db, poll.id)
                extra.append(descriptor)
            accepted = (first.descriptors[0], extra[0], extra[1])
            receipts = tuple(dispatch_row(db, seed, item, cursor, at) for item, cursor, at in (
                (accepted[0], 0, first.created_at+timedelta(milliseconds=100)),
                (accepted[1], 3, first.created_at+timedelta(milliseconds=200)),
                (accepted[2], 8, second.created_at+timedelta(milliseconds=100))))
            peer_receipt = dispatch_row(db, seed, first.descriptors[1], 0, first.created_at+timedelta(milliseconds=300))
        yield database, seed, receipts, peer_receipt, other
    finally:
        database.engine.dispose()


def test_full_native_history_accepts_desktop_cursor_gaps_without_writing(history):
    from cn_contract.task_drafts.integrity import validate_task_records
    from cn_contract.weixin_inbox.integrity import validate_weixin_records

    database, _, _, _, _ = history
    with database.session() as db:
        before = db.connection().connection.total_changes
        assert validate_weixin_records(db, allow_inbox=True) == []
        assert validate_task_records(db) is None
        assert validator()(db, allow_dispatch=True) == []
        assert db.connection().connection.total_changes == before
        assert db.scalar(text('SELECT count(*) FROM weixin_dispatch_receipts')) == 4
        assert db.scalar(text('SELECT count(*) FROM task_draft_events')) == 0


def test_nonempty_dispatch_rejects_partial_archive(history):
    database, _, _, _, _ = history
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            validator()(db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'


def test_nonempty_dispatch_rejects_nonnative_archive(history):
    database, _, _, _, _ = history
    with database.session() as db:
        db.execute(text('DROP TABLE local_workspace_identity'))
        with pytest.raises(ValueError, match='WEIXIN_DISPATCH_INTEGRITY'):
            validator()(db, allow_dispatch=True)


@pytest.mark.parametrize('damage', [
    'receipt_hash', 'receipt_uuid', 'descriptor_uuid', 'actor', 'account', 'mapping', 'binding', 'task_event',
    'source', 'payload_hash', 'task_source', 'task_hash', 'task_payload', 'task_noncanonical',
    'descriptor_payload', 'descriptor_poll', 'descriptor_blocked', 'descriptor_duplicate',
    'peer', 'conversation_owner', 'conversation_workspace', 'scope_conversation',
    'created_before_poll', 'created_before_mapping', 'created_before_event',
    'account_revoked', 'mapping_revoked', 'cursor_behind', 'cursor_fraction', 'overlap',
    'receipt_order', 'prefix_ordinal', 'prefix_poll',
])
def test_coherent_receipt_rehash_cannot_hide_broken_historical_provenance(history, damage):
    database, seed, receipts, peer_receipt, other = history
    first = receipts[0]
    target = first['id']
    other_account = seed_history(database, seed['actor'], bot_account_id='independent-other-dispatch-bot')['account_id'] if damage == 'account' else None
    with database.session() as db:
        if damage in ('actor', 'account', 'mapping', 'binding', 'task_event', 'source', 'payload_hash', 'receipt_uuid', 'descriptor_uuid'):
            key, value = {
                'actor':('actor_id', str(other)), 'account':('account_id', str(other_account)),
                'mapping':('mapping_id', str(seed['mappings'][1].id)),
                'binding':('task_binding_id', str(seed['task_binding_ids'][1])),
                'task_event':('task_event_id', peer_receipt['task_event_id']),
                'source':('source_event_id', 'wx1:'+'f'*64), 'payload_hash':('payload_sha256', 'f'*64),
                'receipt_uuid':('id', target.upper()), 'descriptor_uuid':('descriptor_id', first['descriptor_id'].upper()),
            }[damage]
            # Remove its other receipt so UNIQUE does not obscure the provenance rejection.
            if damage == 'task_event':
                corrupt(db, 'DELETE FROM weixin_dispatch_receipts WHERE id=:id', {'id':peer_receipt['id']})
            if damage == 'descriptor_uuid':
                db.execute(text('PRAGMA defer_foreign_keys=ON'))
                corrupt(db, 'UPDATE weixin_inbox_descriptors SET id=:value WHERE id=:id', {'id':first['descriptor_id'], 'value':value})
                corrupt(db, 'UPDATE weixin_inbox_descriptors SET prior_descriptor_id=:value WHERE prior_descriptor_id=:id', {'id':first['descriptor_id'], 'value':value})
                rehash_poll(db, seed['receipts'][0].id)
                rehash_poll(db, seed['receipts'][1].id)
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET '+key+'=:value WHERE id=:id', {'id':target, 'value':value})
            target = value if key == 'id' else target
        elif damage == 'receipt_hash':
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET receipt_sha256=:sha WHERE id=:id', {'id':target, 'sha':'f'*64})
        elif damage.startswith('task_'):
            key, value = {'task_source':('event_id', 'wx1:'+'e'*64), 'task_hash':('payload_sha256', 'f'*64),
                'task_payload':('payload_json', canonical_json({**seed['receipts'][0].descriptors[0].payload.model_dump(mode='json'), 'text':'coherently altered fiction'})),
                'task_noncanonical':('payload_json', json.dumps(seed['receipts'][0].descriptors[0].payload.model_dump(mode='json')))}[damage]
            corrupt(db, 'UPDATE task_inbox_events SET '+key+'=:value WHERE id=:id', {'id':first['task_event_id'], 'value':value})
            if damage == 'task_payload':
                digest = sha(json.loads(value))
                corrupt(db, 'UPDATE task_inbox_events SET payload_sha256=:sha WHERE id=:id', {'id':first['task_event_id'], 'sha':digest})
                corrupt(db, 'UPDATE weixin_dispatch_receipts SET payload_sha256=:sha WHERE id=:id', {'id':target, 'sha':digest})
        elif damage.startswith('descriptor_'):
            if damage == 'descriptor_payload':
                payload = seed['receipts'][0].descriptors[0].payload.model_dump(mode='json')
                corrupt(db, 'UPDATE weixin_inbox_descriptors SET payload_json=:raw WHERE id=:id',
                    {'id':first['descriptor_id'], 'raw':canonical_json({**payload, 'text':'changed fictional descriptor'})})
            elif damage == 'descriptor_poll':
                corrupt(db, 'UPDATE weixin_dispatch_receipts SET descriptor_id=:id WHERE id=:receipt',
                    {'id':str(seed['receipts'][1].descriptors[1].id), 'receipt':target})
            elif damage == 'descriptor_blocked':
                corrupt(db, "UPDATE weixin_inbox_descriptors SET status='blocked',reason='message_invalid',payload_json=NULL WHERE id=:id", {'id':first['descriptor_id']})
            else:
                corrupt(db, 'UPDATE weixin_dispatch_receipts SET descriptor_id=:id WHERE id=:receipt',
                    {'id':str(seed['receipts'][1].descriptors[0].id), 'receipt':target})
            rehash_poll(db, seed['receipts'][0].id)
        elif damage == 'peer':
            corrupt(db, "UPDATE weixin_peer_bindings SET sender_peer_id='changed-fictional-peer' WHERE id=:id", {'id':first['mapping_id']})
        elif damage.startswith('conversation_'):
            field = 'owner_id' if damage == 'conversation_owner' else 'workspace_id'
            corrupt(db, 'UPDATE assistant_conversations SET '+field+'=:value WHERE id=:id',
                {'id':str(seed['conversation_ids'][0]), 'value':str(other) if field == 'owner_id' else str(uuid4())})
        elif damage == 'scope_conversation':
            scope = seed['mappings'][0].scope.model_dump(mode='json')
            scope['conversation_id'] = str(seed['conversation_ids'][1])
            corrupt(db, 'UPDATE weixin_peer_bindings SET scope_json=:raw,scope_sha256=:sha WHERE id=:id',
                {'id':first['mapping_id'], 'raw':canonical_json(scope), 'sha':sha(scope)})
        elif damage.startswith('created_before_'):
            poll = seed['receipts'][0]
            if damage == 'created_before_mapping':
                at = seed['mappings'][0].created_at-timedelta(microseconds=1)
            elif damage == 'created_before_event':
                at = poll.created_at+timedelta(milliseconds=99)
            else:
                at = poll.created_at-timedelta(microseconds=1)
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET created_at=:at WHERE id=:id', {'id':target, 'at':at.isoformat().replace('+00:00','Z')})
        elif damage.endswith('_revoked'):
            table, identifier = ('weixin_accounts', first['account_id']) if damage == 'account_revoked' else ('weixin_peer_bindings', first['mapping_id'])
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':identifier, 'at':first['created_at'], 'actor':first['actor_id'], 'reason':'fictional historical revoke'})
        elif damage in ('cursor_behind', 'cursor_fraction'):
            corrupt(db, 'UPDATE task_channel_bindings SET cursor=:cursor WHERE id=:id',
                {'id':first['task_binding_id'], 'cursor':0 if damage == 'cursor_behind' else 9.5})
        elif damage == 'overlap':
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET expected_task_cursor=0,next_task_cursor=1 WHERE id=:id', {'id':receipts[1]['id']})
            rehash_receipt(db, receipts[1]['id'])
        elif damage == 'receipt_order':
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET created_at=:at WHERE id=:id',
                {'id':receipts[1]['id'], 'at':seed['receipts'][2].created_at.isoformat().replace('+00:00','Z')})
            rehash_receipt(db, receipts[1]['id'])
        elif damage.startswith('prefix_'):
            skipped = receipts[0] if damage == 'prefix_ordinal' else receipts[1]
            corrupt(db, 'DELETE FROM weixin_dispatch_receipts WHERE id=:id', {'id':skipped['id']})
        if damage != 'receipt_hash' and not (damage.startswith('prefix_') and target == receipts[0]['id']):
            rehash_receipt(db, target)
        with pytest.raises(ValueError, match='WEIXIN_DISPATCH_INTEGRITY'):
            validator()(db, allow_dispatch=True)


def test_wall_clock_event_before_logical_poll_is_valid_with_later_receipt(history):
    database, seed, receipts, _, _ = history
    with database.session() as db:
        # Account chronology may advance beyond the independent TaskInbox wall clock.
        event_at = seed['receipts'][0].created_at-timedelta(microseconds=1)
        corrupt(db, 'UPDATE task_inbox_events SET created_at=:at WHERE id=:id',
            {'id':receipts[0]['task_event_id'], 'at':event_at.isoformat().replace('+00:00','Z')})
        assert validator()(db, allow_dispatch=True) == []


def test_later_revocation_current_scope_and_dynamic_task_state_do_not_rewrite_receipts(history):
    database, seed, receipts, _, _ = history
    with database.session() as db:
        at = seed['receipts'][-1].created_at+timedelta(seconds=1)
        for table, identifier in (('weixin_accounts', seed['account_id']), ('weixin_peer_bindings', seed['mapping_ids'][0])):
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':str(identifier), 'at':at.isoformat().replace('+00:00','Z'), 'actor':str(seed['actor'].user_id), 'reason':'later fictional revocation'})
        corrupt(db, "UPDATE assistant_conversations SET input_revision=input_revision+1,archived_at=:at WHERE id=:id",
            {'id':str(seed['conversation_ids'][0]), 'at':at.isoformat().replace('+00:00','Z')})
        db.execute(text('UPDATE task_channel_bindings SET cursor=20 WHERE id=:id'), {'id':receipts[0]['task_binding_id']})
        assert validator()(db, allow_dispatch=True) == []


def test_empty_current_schema_needs_no_full_archive_permission(history):
    database, _, _, _, _ = history
    with database.session() as db:
        corrupt(db, 'DELETE FROM weixin_dispatch_receipts')
        assert validator()(db) == []


@pytest.mark.parametrize('damage', ['none', 'task_payload', 'descriptor_payload', 'actor', 'cursor'])
def test_actual_dispatch_history_has_the_same_provenance_guards(world, damage):
    from cn_contract.weixin_inbox import dispatch
    from tests.integration.test_weixin_ingress_atomic import setup

    _, database, actor, _, _ = world
    ingress, account, request, response = setup(world)
    poll = ingress.record_synthetic_poll(actor, account.id, request, response, database=database)
    descriptor = poll.descriptors[0]
    receipt = dispatch.dispatch_synthetic_descriptor(actor, descriptor.id, database=database)
    assert dispatch.find_dispatch_receipt(actor, descriptor.id, database=database) == receipt
    with database.session() as db:
        assert validator()(db, allow_dispatch=True) == []
        if damage == 'none':
            return
        if damage in ('task_payload', 'descriptor_payload'):
            payload = {**descriptor.payload.model_dump(mode='json'), 'text':'篡改后的独立虚构文本'}
            if damage == 'task_payload':
                corrupt(db, 'UPDATE task_inbox_events SET payload_json=:raw,payload_sha256=:sha WHERE id=:id',
                    {'id':str(receipt.task_event_id), 'raw':canonical_json(payload), 'sha':sha(payload)})
                corrupt(db, 'UPDATE weixin_dispatch_receipts SET payload_sha256=:sha WHERE id=:id',
                    {'id':str(receipt.id), 'sha':sha(payload)})
                rehash_receipt(db, receipt.id)
            else:
                corrupt(db, 'UPDATE weixin_inbox_descriptors SET payload_json=:raw WHERE id=:id',
                    {'id':str(descriptor.id), 'raw':canonical_json(payload)})
                rehash_poll(db, poll.id)
        elif damage == 'actor':
            other = provision_user('独立虚构派发篡改者', 'synthetic-password', {d.Role.HANDLING_LAWYER}, db)
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET actor_id=:actor WHERE id=:id',
                {'id':str(receipt.id), 'actor':str(other)})
            rehash_receipt(db, receipt.id)
        else:
            corrupt(db, 'UPDATE task_channel_bindings SET cursor=0 WHERE id=:id', {'id':str(receipt.task_binding_id)})
        with pytest.raises(ValueError, match='WEIXIN_DISPATCH_INTEGRITY'):
            validator()(db, allow_dispatch=True)
