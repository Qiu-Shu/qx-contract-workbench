"""Independent fictional generations preserve old sources and do not enable runtime."""
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
from cn_contract.assistant import service as conversations
from cn_contract.config import canonical_json
from cn_contract.record_codec import sha
from cn_contract.security import ServiceError
from cn_contract.storage_schema import VERSIONS, schema_rows
from cn_contract.task_drafts import service as tasks
from tests.helpers.synthetic_weixin_inbox import insert, poll_receipt
from tests.integration.test_weixin_dispatch_integrity import corrupt, rehash_receipt
from tests.integration.test_weixin_reauthorization_integrity import history as scope_history, world, grant_row, store_grant


def validator():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.generation_integrity') is not None, 'D2f needs independent target-generation history validation'
    return importlib.import_module('cn_contract.weixin_inbox.generation_integrity').validate_peer_generations


@pytest.mark.parametrize('version', [value for value in VERSIONS if value not in ('weixin-generations-v1', 'weixin-target-provenance-v1')])
@pytest.mark.parametrize('native', [False, True])
def test_known_pre_generation_schema_is_still_readable(version, native):
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


def test_unknown_schema_is_rejected_even_without_generation_table():
    with Session(create_engine('sqlite://')) as db:
        with pytest.raises(ValueError, match='WEIXIN_GENERATION_INTEGRITY'):
            validator()(db, allow_generations=True)


def generation_row(mapping, actor, number, target, binding, previous, checkpoint, at):
    row = dict(id=str(uuid4()), root_mapping_id=str(mapping.id), generation=number, request_id=str(uuid4()),
        actor_id=str(actor.user_id), task_binding_id=str(binding.id), scope=target.scope.model_dump(mode='json'),
        scope_sha256=sha(target.scope.model_dump(mode='json')),
        previous_generation_sha256=previous.get('generation_sha256'), previous_scope_sha256=previous['scope_sha256'],
        checkpoint_revision=checkpoint, created_at=at.isoformat().replace('+00:00','Z'), reason='独立虚构跨对话代际历史')
    row['generation_sha256'] = sha(row)
    return row


def store_generation(db, row):
    values = {key:value for key,value in row.items() if key != 'scope'}
    values['scope_json'] = canonical_json(row['scope'])
    insert(db, 'weixin_peer_generations', values)


def rehash_generation(db, identifier, *, scope=None):
    row = dict(db.execute(text('SELECT * FROM weixin_peer_generations WHERE id=:id'), {'id':str(identifier)}).mappings().one())
    row.pop('generation_sha256')
    saved = json.loads(row.pop('scope_json'))
    if scope is not None:
        saved = scope
        row['scope_sha256'] = sha(scope)
        corrupt(db, 'UPDATE weixin_peer_generations SET scope_json=:raw,scope_sha256=:sha WHERE id=:id',
            {'id':str(identifier), 'raw':canonical_json(scope), 'sha':row['scope_sha256']})
    row['scope'] = saved
    corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha WHERE id=:id', {'id':str(identifier), 'sha':sha(row)})


@pytest.fixture
def generation_history(scope_history):
    """Generation rows are SQL archive fixtures, never evidence of a runtime switch."""
    database, actor, mapping, grants, polls, receipts, other = scope_history
    with database.session() as db:
        targets, bindings, generations = [], [], []
        previous = grants[-1]
        for number in (1, 2):
            target = conversations.create_conversation(actor, d.AssistantConversationCreateInput(
                request_id=uuid4(), display_title='独立虚构代际目标'+str(number)), db)
            binding = tasks.create_binding(actor, target.scope.conversation_id, db)
            row = generation_row(mapping, actor, number, target, binding, previous, 3,
                polls[0].created_at+timedelta(seconds=9+number))
            store_generation(db, row)
            targets.append(target); bindings.append(binding); generations.append(row)
            previous = row
    return dict(database=database, actor=actor, mapping=mapping, grants=grants, polls=polls,
        receipts=receipts, other=other, targets=tuple(targets), bindings=tuple(bindings), generations=tuple(generations))


def test_two_generations_accept_distinct_target_revisions_without_rewriting_old_sources(generation_history):
    from cn_contract.weixin_inbox.integrity import validate_weixin_records
    from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
    from cn_contract.weixin_inbox.grant_integrity import validate_peer_scope_grants

    sample = generation_history; database = sample['database']
    with database.session() as db:
        before = db.connection().connection.total_changes
        rows = {table:[tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))] for table in (
            'weixin_peer_bindings', 'weixin_peer_scope_grants', 'weixin_poll_receipts',
            'weixin_inbox_descriptors', 'weixin_dispatch_receipts', 'task_inbox_events')}
        assert validator()(db, allow_generations=True) == []
        assert validate_weixin_records(db, allow_inbox=True) == []
        assert validate_dispatch_records(db, allow_dispatch=True) == []
        assert validate_peer_scope_grants(db, allow_grants=True) == []
        assert db.connection().connection.total_changes == before
        assert sample['generations'][0]['scope']['input_revision'] == 0 < sample['grants'][-1]['scope']['input_revision']
        for table, expected in rows.items():
            assert [tuple(row) for row in db.execute(text('SELECT * FROM '+table+' ORDER BY rowid'))] == expected


def test_nonempty_generations_require_full_native_archive(generation_history):
    database = generation_history['database']
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            validator()(db)
        assert error.value.code == 'DATA_POLICY_UNAPPROVED'
        db.execute(text('DROP TABLE local_workspace_identity'))
        with pytest.raises(ValueError, match='WEIXIN_GENERATION_INTEGRITY'):
            validator()(db, allow_generations=True)


@pytest.mark.parametrize('damage', [
    'hash', 'id', 'request_uuid', 'actor', 'gap', 'previous_generation_hash', 'previous_scope_first',
    'previous_scope_next', 'scope_hash', 'scope_noncanonical', 'scope_binding', 'scope_workspace',
    'target_owner', 'target_workspace', 'root_target', 'binding_occupied_by_mapping', 'checkpoint_low',
    'checkpoint_high', 'before_poll', 'equal_dispatch', 'equal_grant', 'equal_binding', 'equal_previous',
    'account_revoked', 'root_revoked', 'later_poll', 'later_dispatch', 'later_grant',
])
def test_recomputed_hash_cannot_hide_invalid_target_chain_or_activity_boundary(generation_history, damage):
    sample = generation_history; database = sample['database']; mapping = sample['mapping']
    first, second = sample['generations']; target = first['id']
    with database.session() as db:
        if damage == 'hash':
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha WHERE id=:id', {'id':target, 'sha':'f'*64})
        elif damage in ('id', 'request_uuid', 'actor', 'gap', 'previous_generation_hash', 'previous_scope_first', 'previous_scope_next', 'scope_hash', 'checkpoint_low', 'checkpoint_high'):
            if damage in ('previous_generation_hash', 'previous_scope_next'):
                target = second['id']
            key, value = {'id':('id', target.upper()), 'request_uuid':('request_id', first['request_id'].upper()),
                'actor':('actor_id', str(sample['other'])), 'gap':('generation',3),
                'previous_generation_hash':('previous_generation_sha256','e'*64),
                'previous_scope_first':('previous_scope_sha256',mapping.scope_sha256),
                'previous_scope_next':('previous_scope_sha256',sample['grants'][-1]['scope_sha256']),
                'scope_hash':('scope_sha256','f'*64), 'checkpoint_low':('checkpoint_revision',2), 'checkpoint_high':('checkpoint_revision',4)}[damage]
            corrupt(db, 'UPDATE weixin_peer_generations SET '+key+'=:value WHERE id=:id', {'id':target, 'value':value})
            target = value if key == 'id' else target
        elif damage == 'scope_noncanonical':
            corrupt(db, 'UPDATE weixin_peer_generations SET scope_json=:raw WHERE id=:id', {'id':target, 'raw':json.dumps(first['scope'])})
        elif damage in ('scope_binding', 'scope_workspace'):
            scope = dict(first['scope'])
            scope['conversation_id' if damage == 'scope_binding' else 'workspace_id'] = str(uuid4())
            rehash_generation(db, target, scope=scope)
        elif damage in ('target_owner', 'target_workspace'):
            key = 'owner_id' if damage == 'target_owner' else 'workspace_id'
            corrupt(db, 'UPDATE assistant_conversations SET '+key+'=:value WHERE id=:id',
                {'id':first['scope']['conversation_id'], 'value':str(sample['other']) if key == 'owner_id' else str(uuid4())})
        elif damage == 'root_target':
            corrupt(db, 'UPDATE weixin_peer_generations SET task_binding_id=:binding WHERE id=:id', {'id':target, 'binding':str(mapping.task_binding_id)})
            rehash_generation(db, target, scope=mapping.scope.model_dump(mode='json'))
        elif damage == 'binding_occupied_by_mapping':
            values = mapping.model_dump(mode='json', exclude={'scope'})
            values.update(id=str(uuid4()), sender_peer_id='independent-generation-occupied-peer',
                task_binding_id=first['task_binding_id'], scope_sha256=first['scope_sha256'],
                created_at=(d.WeixinPeerGeneration(**first).created_at-timedelta(microseconds=1)).isoformat().replace('+00:00','Z'))
            values['scope_json'] = canonical_json(first['scope'])
            insert(db, 'weixin_peer_bindings', values)
        elif damage in ('before_poll', 'equal_dispatch', 'equal_grant', 'equal_binding', 'equal_previous'):
            if damage == 'equal_dispatch':
                db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
            if damage == 'before_poll':
                at = sample['polls'][-1].created_at-timedelta(microseconds=1)
            elif damage == 'equal_dispatch':
                at = d.WeixinDispatchReceipt(**sample['receipts'][-1]).created_at
            elif damage == 'equal_grant':
                at = d.WeixinPeerScopeGrant(**sample['grants'][-1]).created_at
            elif damage == 'equal_binding':
                at = sample['bindings'][0].created_at
            else:
                at = d.WeixinPeerGeneration(**first).created_at; target = second['id']
            corrupt(db, 'UPDATE weixin_peer_generations SET created_at=:at WHERE id=:id', {'id':target, 'at':at.isoformat().replace('+00:00','Z')})
        elif damage.endswith('_revoked'):
            table, identifier = ('weixin_accounts', mapping.account_id) if damage == 'account_revoked' else ('weixin_peer_bindings', mapping.id)
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':str(identifier), 'at':first['created_at'], 'actor':first['actor_id'], 'reason':'独立虚构代际前撤权'})
        elif damage == 'later_poll':
            # Frozen v17 forbids all later polls; v18 validates their complete prefixes.
            db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
            db.execute(text('DROP TABLE weixin_descriptor_generations'))
            poll = sample['polls'][-1]
            at = d.WeixinPeerGeneration(**first).created_at+timedelta(seconds=5)
            later = poll_receipt(mapping.account_id, 3, poll.next_cursor, poll.next_cursor, (), at)
            insert(db, 'weixin_poll_receipts', later.model_dump(mode='json', exclude={'descriptors'}))
            db.execute(text('UPDATE weixin_accounts SET checkpoint_revision=4 WHERE id=:id'), {'id':str(mapping.account_id)})
        elif damage == 'later_dispatch':
            # Frozen v18 keeps the global dispatch barrier; v19 versions delivery separately.
            db.execute(text('DROP INDEX weixin_dispatch_binding_cursor'))
            at = d.WeixinPeerGeneration(**first).created_at+timedelta(seconds=5)
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET created_at=:at WHERE id=:id', {'id':sample['receipts'][-1]['id'], 'at':at.isoformat().replace('+00:00','Z')})
            rehash_receipt(db, sample['receipts'][-1]['id'])
        else:
            scope = {**sample['grants'][-1]['scope'], 'input_revision':3}
            at = d.WeixinPeerGeneration(**first).created_at+timedelta(seconds=5)
            store_grant(db, grant_row(mapping, sample['actor'], 3, sample['grants'][-1]['scope_sha256'], scope, 3, at))
        if damage != 'hash':
            rehash_generation(db, target)
        with pytest.raises(ValueError, match='WEIXIN_GENERATION_INTEGRITY'):
            validator()(db, allow_generations=True)


@pytest.mark.parametrize('family', ['inbox', 'dispatch', 'grant'])
def test_old_weixin_validators_keep_executing_in_schema17(generation_history, family):
    sample = generation_history; database = sample['database']
    with database.session() as db:
        if family == 'inbox':
            from cn_contract.weixin_inbox.integrity import validate_weixin_records
            corrupt(db, 'UPDATE weixin_accounts SET checkpoint_revision=99')
            callback, keyword, code = validate_weixin_records, 'allow_inbox', 'WEIXIN_INBOX_INTEGRITY'
        elif family == 'dispatch':
            from cn_contract.weixin_inbox.dispatch_integrity import validate_dispatch_records
            corrupt(db, 'UPDATE task_inbox_events SET payload_sha256=:sha WHERE id=:id', {'id':sample['receipts'][0]['task_event_id'], 'sha':'f'*64})
            callback, keyword, code = validate_dispatch_records, 'allow_dispatch', 'WEIXIN_DISPATCH_INTEGRITY'
        else:
            from cn_contract.weixin_inbox.grant_integrity import validate_peer_scope_grants
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET previous_scope_sha256=:sha WHERE id=:id', {'id':sample['grants'][1]['id'], 'sha':'f'*64})
            from tests.integration.test_weixin_reauthorization_integrity import rehash_grant
            rehash_grant(db, sample['grants'][1]['id'])
            callback, keyword, code = validate_peer_scope_grants, 'allow_grants', 'WEIXIN_GRANT_INTEGRITY'
        with pytest.raises(ValueError, match=code):
            callback(db, **{keyword:True})


def test_utc_spelling_and_later_permanent_revocation_preserve_valid_generations(generation_history):
    sample = generation_history; database = sample['database']; first, second = sample['generations']
    with database.session() as db:
        corrupt(db, 'UPDATE weixin_peer_generations SET created_at=:at WHERE id=:id', {'id':first['id'], 'at':first['created_at'].replace('Z','+00:00')})
        for table, identifier in (('weixin_accounts', sample['mapping'].account_id), ('weixin_peer_bindings', sample['mapping'].id)):
            corrupt(db, 'UPDATE '+table+' SET revoked_at=:at,revoked_by=:actor,revoke_reason=:reason WHERE id=:id',
                {'id':str(identifier), 'at':(d.WeixinPeerGeneration(**second).created_at+timedelta(seconds=1)).isoformat(),
                 'actor':first['actor_id'], 'reason':'独立虚构后续永久撤权'})
        assert validator()(db, allow_generations=True) == []


def point_generation_at_scope(db, sample, scope):
    """Keep the entire generation hash chain coherent while changing its source."""
    first, second = sample['generations']
    rehash_generation(db, first['id'], scope=scope.model_dump(mode='json'))
    saved = db.execute(text('SELECT scope_sha256,generation_sha256 FROM weixin_peer_generations WHERE id=:id'),
        {'id':first['id']}).mappings().one()
    corrupt(db, '''UPDATE weixin_peer_generations SET previous_scope_sha256=:scope,
        previous_generation_sha256=:generation WHERE id=:id''',
        {'id':second['id'], 'scope':saved['scope_sha256'], 'generation':saved['generation_sha256']})
    rehash_generation(db, second['id'])


def save_target_source(sample, kind, at, monkeypatch):
    """Public local saves create actual source rows; no worker or provider runs."""
    from cn_contract.assistant import attachments, attachment_records
    database, actor, target = sample['database'], sample['actor'], sample['targets'][0]
    if kind == 'input':
        monkeypatch.setattr(conversations, '_at', lambda:at.isoformat())
        with database.session() as db:
            run = conversations.save_message(actor, target.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=target.scope, expected_composer_revision=target.composer_revision,
                content='独立虚构目标消息来源时间'), db)
            assert run.state == 'queued'
            return run.scope
    monkeypatch.setattr(attachment_records, '_at', lambda:at.isoformat())
    revision = attachments.select_materials(actor, target.scope.conversation_id, d.AssistantMaterialSelectionInput(
        request_id=uuid4(), expected_scope=target.scope, items=()), database=database)
    assert revision == 1
    with database.session() as db:
        return conversations.read_conversation(actor, target.scope.conversation_id, db).scope


@pytest.mark.parametrize('kind', ['input', 'materials'])
@pytest.mark.parametrize('timing', ['missing', 'future', 'prior', 'equal'])
def test_generation_scope_source_must_exist_at_its_effective_time(generation_history, monkeypatch, kind, timing):
    sample = generation_history; database = sample['database']; target = sample['targets'][0]
    at = d.WeixinPeerGeneration(**sample['generations'][0]).created_at
    if timing == 'missing':
        scope = target.scope.model_copy(update={kind+'_revision':1})
    else:
        offset = {'future':1, 'prior':-1, 'equal':0}[timing]
        scope = save_target_source(sample, kind, at+timedelta(microseconds=offset), monkeypatch)
    with database.session() as db:
        if timing == 'missing':
            # A current counter alone is not historical proof of a revision.
            corrupt(db, 'UPDATE assistant_conversations SET '+kind+'_revision=1 WHERE id=:id',
                {'id':str(target.scope.conversation_id)})
        point_generation_at_scope(db, sample, scope)
        if timing in ('missing', 'future'):
            with pytest.raises(ValueError, match='WEIXIN_GENERATION_INTEGRITY'):
                validator()(db, allow_generations=True)
        else:
            assert validator()(db, allow_generations=True) == []


@pytest.mark.parametrize('kind', ['input', 'materials'])
def test_generation_scope_source_zero_allows_later_ordinary_conversation_activity(generation_history, monkeypatch, kind):
    sample = generation_history
    at = d.WeixinPeerGeneration(**sample['generations'][0]).created_at
    current_scope = save_target_source(sample, kind, at+timedelta(microseconds=1), monkeypatch)
    assert getattr(current_scope, kind+'_revision') == 1
    with sample['database'].session() as db:
        assert validator()(db, allow_generations=True) == []
