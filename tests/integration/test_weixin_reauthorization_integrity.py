"""Independent fictional grant archives verify authorization history without replay."""
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
from cn_contract.config import canonical_json
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError, provision_user
from cn_contract.storage_schema import VERSIONS, schema_rows
from cn_contract.weixin_offline import event_id
from tests.helpers.synthetic_weixin_inbox import insert, poll_receipt
from tests.integration.test_weixin_dispatch_integrity import corrupt, dispatch_row, rehash_poll, rehash_receipt
from tests.integration.test_weixin_ingress_atomic import setup, world


def validator():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.grant_integrity') is not None, 'D2d needs immutable scope-grant history validation'
    return importlib.import_module('cn_contract.weixin_inbox.grant_integrity').validate_peer_scope_grants


@pytest.mark.parametrize('version', [value for value in VERSIONS if value != 'weixin-reauthorization-v1'])
@pytest.mark.parametrize('native', [False, True])
def test_known_pre_grant_schema_remains_readable(version, native):
    with closing(sqlite3.connect(':memory:')) as connection:
        rows = schema_rows(version, native=native)
        for kind, _, _, sql in rows:
            if kind == 'table':
                connection.execute(sql)
        for kind, _, _, sql in rows:
            if kind != 'table' and sql is not None:
                connection.execute(sql)
        with Session(create_engine('sqlite://', creator=lambda: connection)) as db:
            assert validator()(db) == []


def test_unknown_schema_without_grant_table_is_rejected():
    with Session(create_engine('sqlite://')) as db:
        with pytest.raises(ValueError, match='WEIXIN_GRANT_INTEGRITY'):
            validator()(db, allow_grants=True)


def grant_row(mapping, actor, revision, previous, scope, checkpoint, at):
    values = dict(id=str(uuid4()), mapping_id=str(mapping.id), request_id=str(uuid4()),
        actor_id=str(actor.user_id), revision=revision, previous_scope_sha256=previous,
        scope=scope, scope_sha256=sha(scope), checkpoint_revision=checkpoint,
        created_at=at.isoformat().replace('+00:00','Z'), reason='独立虚构同目标重新授权')
    values['grant_sha256'] = sha(values)
    return values


def store_grant(db, values):
    row = {key:value for key,value in values.items() if key != 'scope'}
    row['scope_json'] = canonical_json(values['scope'])
    insert(db, 'weixin_peer_scope_grants', row)


def rehash_grant(db, identifier, *, scope=None):
    row = dict(db.execute(text('SELECT * FROM weixin_peer_scope_grants WHERE id=:id'),
        {'id':str(identifier)}).mappings().one())
    row.pop('grant_sha256')
    saved_scope = json.loads(row.pop('scope_json'))
    if scope is not None:
        saved_scope = scope
        row['scope_sha256'] = sha(scope)
        corrupt(db, 'UPDATE weixin_peer_scope_grants SET scope_json=:raw,scope_sha256=:sha WHERE id=:id',
            {'id':str(identifier), 'raw':canonical_json(scope), 'sha':row['scope_sha256']})
    row['scope'] = saved_scope
    corrupt(db, 'UPDATE weixin_peer_scope_grants SET grant_sha256=:sha WHERE id=:id',
        {'id':str(identifier), 'sha':sha(row)})


@pytest.fixture
def history(world):
    """Only the first poll uses runtime; all later rows are independent archive metadata."""
    _, database, actor, view, binding = world
    ingress, account, request, response = setup(world)
    first = ingress.record_synthetic_poll(actor, account.id, request, response, database=database)
    with database.session() as db:
        raw_mapping = dict(db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'),
            {'id':str(first.descriptors[0].mapping_id)}).mappings().one())
        mapping = d.WeixinPeerBindingSnapshot(**{key:value for key,value in raw_mapping.items() if key != 'scope_json'},
            scope=d.ScopeSnapshot.model_validate_json(raw_mapping['scope_json']))
        other = provision_user('独立虚构其他授权人', 'synthetic-password', {d.Role.HANDLING_LAWYER}, db)
        scopes = ({**mapping.scope.model_dump(mode='json'), 'input_revision':2, 'materials_revision':1},
            {**mapping.scope.model_dump(mode='json'), 'input_revision':2, 'materials_revision':3})
        grants = (grant_row(mapping, actor, 1, mapping.scope_sha256, scopes[0], 1, first.created_at+timedelta(seconds=1)),
            grant_row(mapping, actor, 2, sha(scopes[0]), scopes[1], 2, first.created_at+timedelta(seconds=3)))
        for grant in grants:
            store_grant(db, grant)
        polls = [first]
        for revision in (1, 2):
            identifier = uuid4()
            source = event_id(account.bot_account_id, mapping.sender_peer_id, str(revision+1))
            descriptor = d.WeixinInboxDescriptor(id=uuid4(), poll_id=identifier, ordinal=1,
                sender_peer_id=mapping.sender_peer_id, upstream_message_id=str(revision+1), source_event_id=source,
                source_sha256=sha(['independent-grant-message',revision]), status='accepted_pending_dispatch',
                mapping_id=mapping.id, payload=d.TaskInboxEventInput(event_id=source, text='独立虚构续收内容'))
            poll = poll_receipt(account.id, revision, polls[-1].next_cursor, 'synthetic-grant:'+str(revision),
                (descriptor,), first.created_at+timedelta(seconds=revision*2))
            insert(db, 'weixin_poll_receipts', poll.model_dump(mode='json', exclude={'descriptors'}))
            values = descriptor.model_dump(mode='json', exclude={'payload'})
            values['payload_json'] = canonical_json(descriptor.payload.model_dump(mode='json'))
            insert(db, 'weixin_inbox_descriptors', values)
            polls.append(poll)
            db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=:revision,upstream_cursor=:cursor WHERE id=:id'),
                {'id':str(account.id), 'revision':poll.next_revision, 'cursor':poll.next_cursor})
        # Independent metadata permits later current revisions and archive state.
        corrupt(db, 'UPDATE assistant_conversations SET input_revision=4,materials_revision=5,archived_at=:at WHERE id=:id',
            {'id':str(view.scope.conversation_id), 'at':(first.created_at+timedelta(seconds=5)).isoformat().replace('+00:00','Z')})
        seed = dict(account_id=account.id, actor=actor, mappings=(mapping,))
        receipts = tuple(dispatch_row(db, seed, poll.descriptors[0], index,
            poll.created_at+timedelta(milliseconds=500)) for index,poll in enumerate(polls))
    return database, actor, mapping, grants, tuple(polls), receipts, other


def test_complete_grant_history_is_read_only_and_preserves_original_mapping(history):
    from cn_contract.weixin_inbox.integrity import validate_weixin_records
    from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records

    database, _, mapping, _, _, _, _ = history
    with database.session() as db:
        before = db.connection().connection.total_changes
        original = dict(db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'), {'id':str(mapping.id)}).mappings().one())
        assert validator()(db, allow_grants=True) == []
        assert validate_weixin_records(db, allow_inbox=True) == []
        assert validate_dispatch_records(db, allow_dispatch=True) == []
        assert db.connection().connection.total_changes == before
        assert dict(db.execute(text('SELECT * FROM weixin_peer_bindings WHERE id=:id'), {'id':str(mapping.id)}).mappings().one()) == original


def test_nonempty_grants_need_full_native_archive(history):
    database, *_ = history
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            validator()(db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        db.execute(text('DROP TABLE local_workspace_identity'))
        with pytest.raises(ValueError, match='WEIXIN_GRANT_INTEGRITY'):
            validator()(db, allow_grants=True)


@pytest.mark.parametrize('damage', [
    'hash', 'uuid', 'request_uuid', 'actor', 'revision_gap', 'previous_hash', 'scope_hash', 'scope_noncanonical',
    'workspace', 'conversation', 'scope_kind', 'scope_ref', 'binding_revision', 'input_regression',
    'materials_regression', 'no_growth', 'future_scope', 'checkpoint_low', 'checkpoint_high',
    'same_mapping_time', 'same_previous_time', 'poll_before_grant', 'poll_after_grant_wrong_revision',
    'account_revoked', 'mapping_revoked', 'conversation_owner', 'conversation_workspace',
])
def test_rehashed_grants_cannot_hide_broken_chain_or_historical_boundary(history, damage):
    database, _, mapping, grants, polls, receipts, other = history
    target = grants[1]['id']
    with database.session() as db:
        if damage == 'hash':
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET grant_sha256=:sha WHERE id=:id', {'id':target, 'sha':'f'*64})
        elif damage in ('uuid', 'request_uuid', 'actor', 'revision_gap', 'previous_hash', 'scope_hash', 'checkpoint_low', 'checkpoint_high'):
            key, value = {'uuid':('id', target.upper()), 'request_uuid':('request_id', grants[1]['request_id'].upper()),
                'actor':('actor_id', str(other)), 'revision_gap':('revision',3), 'previous_hash':('previous_scope_sha256','f'*64),
                'scope_hash':('scope_sha256','f'*64), 'checkpoint_low':('checkpoint_revision',1), 'checkpoint_high':('checkpoint_revision',3)}[damage]
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET '+key+'=:value WHERE id=:id', {'id':target, 'value':value})
            target = value if key == 'id' else target
        elif damage == 'scope_noncanonical':
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET scope_json=:raw WHERE id=:id',
                {'id':target, 'raw':json.dumps(grants[1]['scope'])})
        elif damage in ('workspace', 'conversation', 'scope_kind', 'scope_ref', 'binding_revision',
                'input_regression', 'materials_regression', 'no_growth', 'future_scope'):
            scope = dict(grants[1]['scope'])
            if damage in ('workspace', 'conversation'):
                scope[damage+'_id'] = str(uuid4())
            elif damage == 'scope_kind':
                scope['scope_kind'], scope['scope_ref'] = 'matter', str(uuid4())
            elif damage == 'scope_ref':
                scope['scope_ref'] = str(uuid4())
            elif damage == 'binding_revision':
                scope['binding_revision'] += 1
            elif damage == 'input_regression':
                scope['input_revision'] = 1
            elif damage == 'materials_regression':
                scope['materials_revision'] = 0
            elif damage == 'no_growth':
                scope = dict(grants[0]['scope'])
            else:
                scope['input_revision'] = 999
            rehash_grant(db, target, scope=scope)
        elif damage.startswith('same_'):
            at = mapping.created_at if damage == 'same_mapping_time' else d.WeixinPeerScopeGrant(**grants[0]).created_at
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET created_at=:at WHERE id=:id',
                {'id':target, 'at':at.isoformat().replace('+00:00','Z')})
        elif damage == 'poll_before_grant':
            at = d.WeixinPeerScopeGrant(**grants[0]).created_at-timedelta(microseconds=1)
            corrupt(db, 'UPDATE weixin_poll_receipts SET created_at=:at WHERE id=:id',
                {'id':str(polls[1].id), 'at':at.isoformat().replace('+00:00','Z')})
            rehash_poll(db, polls[1].id)
        elif damage == 'poll_after_grant_wrong_revision':
            corrupt(db, 'UPDATE weixin_poll_receipts SET created_at=:at WHERE id=:id',
                {'id':str(polls[1].id), 'at':grants[1]['created_at']})
            rehash_poll(db, polls[1].id)
        elif damage.endswith('_revoked'):
            table, identifier = ('weixin_accounts', mapping.account_id) if damage == 'account_revoked' else ('weixin_peer_bindings', mapping.id)
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':str(identifier), 'at':grants[1]['created_at'], 'actor':grants[1]['actor_id'], 'reason':'虚构历史撤权'})
        elif damage.startswith('conversation_'):
            key = 'owner_id' if damage == 'conversation_owner' else 'workspace_id'
            corrupt(db, 'UPDATE assistant_conversations SET '+key+'=:value WHERE id=:id',
                {'id':str(mapping.scope.conversation_id), 'value':str(other) if key == 'owner_id' else str(uuid4())})
        if damage != 'hash':
            rehash_grant(db, target)
        with pytest.raises(ValueError, match='WEIXIN_GRANT_INTEGRITY'):
            validator()(db, allow_grants=True)


@pytest.mark.parametrize('family', ['inbox', 'dispatch'])
def test_successor_gate_still_rejects_each_existing_history_family(history, family):
    database, _, _, _, _, receipts, _ = history
    with database.session() as db:
        if family == 'inbox':
            from cn_contract.weixin_inbox.integrity import validate_weixin_records
            corrupt(db, 'UPDATE weixin_accounts SET checkpoint_revision=99')
            callback, keyword, code = validate_weixin_records, 'allow_inbox', 'WEIXIN_INBOX_INTEGRITY'
        else:
            from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
            corrupt(db, 'UPDATE task_inbox_events SET payload_sha256=:sha WHERE id=:id', {'id':receipts[0]['task_event_id'], 'sha':'f'*64})
            callback, keyword, code = validate_dispatch_records, 'allow_dispatch', 'WEIXIN_DISPATCH_INTEGRITY'
        with pytest.raises(ValueError, match=code):
            callback(db, **{keyword:True})


@pytest.mark.parametrize('family', ['inbox', 'dispatch'])
def test_each_existing_validator_checks_the_grant_chain_too(history, family):
    database, _, _, grants, _, _, _ = history
    with database.session() as db:
        corrupt(db, 'UPDATE weixin_peer_scope_grants SET previous_scope_sha256=:sha WHERE id=:id', {'id':grants[1]['id'], 'sha':'f'*64})
        rehash_grant(db, grants[1]['id'])
        if family == 'inbox':
            from cn_contract.weixin_inbox.integrity import validate_weixin_records
            callback, keyword, code = validate_weixin_records, 'allow_inbox', 'WEIXIN_INBOX_INTEGRITY'
        else:
            from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
            callback, keyword, code = validate_dispatch_records, 'allow_dispatch', 'WEIXIN_DISPATCH_INTEGRITY'
        with pytest.raises(ValueError, match=code):
            callback(db, **{keyword:True})


def test_history_scope_selection_uses_only_grants_effective_at_that_utc_boundary(history):
    database, _, mapping, grants, polls, _, _ = history
    module = importlib.import_module('cn_contract.weixin_inbox.grant_integrity')
    assert callable(getattr(module, '_scope_at', None)), 'D2d needs independent historical scope selection'
    values = tuple(d.WeixinPeerScopeGrant(**row) for row in grants)
    with database.session() as db:
        assert module._scope_at(mapping, values, polls[0].created_at).model_dump(mode='json') == mapping.scope.model_dump(mode='json')
        for value in values:
            before = module._scope_at(mapping, values, value.created_at-timedelta(microseconds=1))
            at = module._scope_at(mapping, values, value.created_at)
            assert at == value.scope and before != at


def test_later_revocation_and_current_metadata_do_not_invalidate_prior_grants(history):
    database, actor, mapping, _, polls, _, _ = history
    with database.session() as db:
        for table, identifier in (('weixin_accounts', mapping.account_id), ('weixin_peer_bindings', mapping.id)):
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':str(identifier), 'at':(polls[-1].created_at+timedelta(seconds=2)).isoformat().replace('+00:00','Z'),
                 'actor':str(actor.user_id), 'reason':'虚构后续撤权'})
        assert validator()(db, allow_grants=True) == []
