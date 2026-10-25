"""Explicit local generations preserve history without resuming account intake."""
import importlib
import importlib.util
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import service as conversations
from cn_contract.ops.storage import RestoreFenceRow
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError
from cn_contract.storage_schema import identify_schema, VERSIONS
from cn_contract.weixin_inbox import accounts
from tests.helpers.synthetic_weixin_generations import setup_history, state
from tests.integration.test_weixin_ingress_atomic import world


def api():
    assert importlib.util.find_spec('cn_contract.weixin_inbox.generations') is not None, 'D2g1 needs explicit atomic generation append and lookup'
    return importlib.import_module('cn_contract.weixin_inbox.generations')


@pytest.fixture
def history(world):
    return setup_history(world)


def request(history, previous=None, *, index=0, **changes):
    target, binding = history['targets'][index]
    return d.WeixinPeerGenerationInput(**{**dict(request_id=uuid4(),
        expected_generation=previous.generation if previous else 0,
        expected_previous_generation_sha256=previous.generation_sha256 if previous else None,
        expected_previous_scope_sha256=previous.scope_sha256 if previous else history['grant'].scope_sha256,
        expected_checkpoint_revision=history['grant'].checkpoint_revision,
        task_binding_id=binding.id, expected_scope=target.scope, reason='独立虚构显式跨对话目标追加'), **changes})


def test_public_append_two_generations_and_fixed_lookup_preserve_all_other_history(history):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    before = state(database, generations=False)
    unknown = uuid4()
    assert service.find_peer_generation(actor, mapping.id, unknown, database=database) is None
    first_request = request(history)
    first = service.append_synthetic_generation(actor, mapping.id, first_request, database=database)
    assert first.generation == 1 and first.actor_id == actor.user_id and first.root_mapping_id == mapping.id
    assert first.previous_generation_sha256 is None and first.previous_scope_sha256 == history['grant'].scope_sha256
    assert first.scope == history['targets'][0][0].scope and first.checkpoint_revision == 2
    assert first.created_at > max(mapping.created_at, history['grant'].created_at,
        history['peer_poll'].created_at, history['dispatched'].created_at, history['targets'][0][1].created_at)
    second_request = request(history, first, index=1)
    second = service.append_synthetic_generation(actor, mapping.id, second_request, database=database)
    assert second.generation == 2 and second.previous_generation_sha256 == first.generation_sha256
    assert second.previous_scope_sha256 == first.scope_sha256 and second.created_at > first.created_at
    assert service.append_synthetic_generation(actor, mapping.id, first_request, database=database) == first
    assert service.find_peer_generation(actor, mapping.id, first_request.request_id, database=database) == first
    assert service.find_peer_generation(actor, mapping.id, second_request.request_id, database=database) == second
    assert service.find_peer_generation(actor, mapping.id, unknown, database=database) is None
    assert state(database, generations=False) == before
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM weixin_peer_generations')) == 2
        assert db.scalar(text('SELECT count(*) FROM assistant_runs')) == 0


def denied(code, operation, *args, **kwargs):
    with pytest.raises(ServiceError) as failure:
        operation(*args, **kwargs)
    assert failure.value.code == code
    assert failure.value.status_code == (401 if code == 'AUTHORIZATION_REQUIRED' else 403 if code == 'CROSS_MATTER_DENIED' else 409)


@pytest.mark.parametrize('change', ['generation', 'previous_hash', 'scope_hash', 'checkpoint', 'binding', 'scope', 'reason'])
def test_same_request_requires_original_complete_input_before_returning_fixed_record(history, change):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    value = request(history)
    first = service.append_synthetic_generation(actor, mapping.id, value, database=database)
    changes = {'generation':dict(expected_generation=1, expected_previous_generation_sha256=first.generation_sha256),
        'previous_hash':dict(expected_generation=1, expected_previous_generation_sha256='f'*64),
        'scope_hash':dict(expected_previous_scope_sha256='f'*64), 'checkpoint':dict(expected_checkpoint_revision=3),
        'binding':dict(task_binding_id=uuid4()), 'scope':dict(expected_scope=value.expected_scope.model_copy(update={'input_revision':1})),
        'reason':dict(reason='独立虚构不同理由')}[change]
    before = state(database)
    denied('VERSION_CONFLICT', service.append_synthetic_generation, actor, mapping.id,
        value.model_copy(update=changes), database=database)
    assert service.find_peer_generation(actor, mapping.id, value.request_id, database=database) == first
    assert state(database) == before


@pytest.mark.parametrize('change', ['generation', 'previous_hash', 'scope_hash', 'checkpoint', 'scope'])
def test_new_append_requires_exact_generation_scope_and_checkpoint_cas(history, change):
    service = api(); value = request(history); database = history['database']
    changes = {'generation':dict(expected_generation=1, expected_previous_generation_sha256='a'*64),
        'previous_hash':dict(expected_generation=2, expected_previous_generation_sha256='b'*64),
        'scope_hash':dict(expected_previous_scope_sha256='f'*64),
        'checkpoint':dict(expected_checkpoint_revision=1),
        'scope':dict(expected_scope=value.expected_scope.model_copy(update={'materials_revision':1}))}[change]
    before = state(database)
    denied('VERSION_CONFLICT', service.append_synthetic_generation, history['actor'], history['mapping'].id,
        value.model_copy(update=changes), database=database)
    assert state(database) == before


@pytest.mark.parametrize('occupied', ['root', 'original_peer', 'previous', 'other_root_generation'])
def test_new_target_cannot_reuse_root_or_any_occupied_binding(history, occupied):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    previous = None
    if occupied == 'root':
        with database.session() as db:
            target = conversations.read_conversation(actor, mapping.scope.conversation_id, db)
        value = request(history, task_binding_id=mapping.task_binding_id, expected_scope=target.scope)
    elif occupied == 'original_peer':
        value = request(history, task_binding_id=history['peer'].task_binding_id, expected_scope=history['peer_view'].scope)
    elif occupied == 'previous':
        previous = service.append_synthetic_generation(actor, mapping.id, request(history), database=database)
        value = request(history, previous)
    else:
        peer_request = request(history, expected_previous_scope_sha256=history['peer'].scope_sha256)
        service.append_synthetic_generation(actor, history['peer'].id, peer_request, database=database)
        value = request(history)
    before = state(database)
    denied('VERSION_CONFLICT', service.append_synthetic_generation, actor, mapping.id, value, database=database)
    assert state(database) == before


@pytest.mark.parametrize('changed', ['owner', 'workspace', 'missing_binding'])
def test_new_target_is_resolved_from_actual_owned_workspace_binding(history, changed):
    from cn_contract.security import provision_user
    service = api(); database = history['database']; value = request(history)
    with database.session() as db:
        if changed == 'owner':
            other = provision_user('独立虚构目标他人', 'synthetic-password', {d.Role.HANDLING_LAWYER}, db)
            db.execute(text('UPDATE assistant_conversations SET owner_id=:owner WHERE id=:id'),
                {'owner':str(other), 'id':str(value.expected_scope.conversation_id)})
        elif changed == 'workspace':
            db.execute(text('UPDATE assistant_conversations SET workspace_id=:workspace WHERE id=:id'),
                {'workspace':str(uuid4()), 'id':str(value.expected_scope.conversation_id)})
        else:
            value = value.model_copy(update={'task_binding_id':uuid4()})
    before = state(database)
    denied('CROSS_MATTER_DENIED', service.append_synthetic_generation, history['actor'], history['mapping'].id,
        value, database=database)
    assert state(database) == before


@pytest.mark.parametrize('changed', ['account', 'peer', 'restore', 'session', 'role', 'root_archived', 'target_archived', 'previous_archived'])
def test_append_rechecks_live_principal_revocation_fence_and_all_three_conversations(history, changed):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    value = request(history)
    if changed == 'previous_archived':
        first = service.append_synthetic_generation(actor, mapping.id, value, database=database)
        value = request(history, first, index=1)
    if changed in ('account', 'peer'):
        operation = accounts.revoke_synthetic_account if changed == 'account' else accounts.revoke_synthetic_peer
        operation(actor, history['account'].id if changed == 'account' else mapping.id,
            d.WeixinRevokeInput(reason='独立虚构当前撤权'), database=database)
    else:
        with database.session() as db:
            if changed == 'session':
                db.get(SessionRow, str(actor.session_id)).revoked = True
            elif changed == 'role':
                db.get(UserRow, str(actor.user_id)).roles = '["assistant"]'
            elif changed == 'restore':
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='1'*64, manifest_sha256='2'*64, payload='{}'))
            else:
                cid = (history['view'].scope.conversation_id if changed == 'root_archived' else
                    history['targets'][0][0].scope.conversation_id)
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                    {'id':str(cid), 'at':datetime.now(timezone.utc).isoformat()})
    before = state(database)
    code = ('BLOCKED_LIVE' if changed == 'restore' else 'AUTHORIZATION_REQUIRED' if changed == 'session'
        else 'CROSS_MATTER_DENIED' if changed == 'role' else 'STATE_CONFLICT')
    denied(code, service.append_synthetic_generation, actor, mapping.id, value, database=database)
    assert state(database) == before


@pytest.mark.parametrize('changed', ['scope', 'root_archived', 'target_archived', 'peer', 'account', 'restore'])
def test_find_is_fixed_read_only_metadata_after_scope_growth_archive_revocation_or_restore(history, changed):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    value = request(history)
    first = service.append_synthetic_generation(actor, mapping.id, value, database=database)
    if changed in ('account', 'peer'):
        operation = accounts.revoke_synthetic_account if changed == 'account' else accounts.revoke_synthetic_peer
        operation(actor, history['account'].id if changed == 'account' else mapping.id,
            d.WeixinRevokeInput(reason='独立虚构追加后永久撤权'), database=database)
    else:
        with database.session() as db:
            if changed == 'restore':
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='1'*64, manifest_sha256='2'*64, payload='{}'))
            elif changed == 'scope':
                conversations.save_draft(actor, first.scope.conversation_id, d.AssistantDraftInput(
                    expected_scope=first.scope, expected_composer_revision=0, content='独立虚构人工草稿'), db)
                db.execute(text('UPDATE assistant_conversations SET input_revision=1 WHERE id=:id'),
                    {'id':str(first.scope.conversation_id)})
            else:
                cid = mapping.scope.conversation_id if changed == 'root_archived' else first.scope.conversation_id
                db.execute(text('UPDATE assistant_conversations SET archived_at=:at WHERE id=:id'),
                    {'id':str(cid), 'at':datetime.now(timezone.utc).isoformat()})
    before = state(database)
    with database.session() as db:
        before_audits = db.scalar(text('SELECT count(*) FROM audit_events'))
    assert service.find_peer_generation(actor, mapping.id, value.request_id, database=database) == first
    assert service.find_peer_generation(actor, mapping.id, uuid4(), database=database) is None
    with database.session() as db:
        assert db.scalar(text('SELECT count(*) FROM audit_events')) == before_audits
    assert state(database) == before
    denied('VERSION_CONFLICT' if changed == 'scope' else 'BLOCKED_LIVE' if changed == 'restore' else 'STATE_CONFLICT',
        service.append_synthetic_generation, actor, mapping.id, value, database=database)
    assert state(database) == before


@pytest.mark.parametrize('kind', ['input', 'materials'])
def test_append_time_is_strictly_after_selected_real_sources_even_when_wall_clock_moves_back(history, monkeypatch, kind):
    from cn_contract.assistant import attachments, attachment_records
    service = api(); database = history['database']; actor = history['actor']; target = history['targets'][0][0]
    future = datetime.now(timezone.utc)+timedelta(days=1)
    if kind == 'input':
        monkeypatch.setattr(conversations, '_at', lambda:future.isoformat())
        with database.session() as db:
            run = conversations.save_message(actor, target.scope.conversation_id, d.AssistantMessageInput(
                request_id=uuid4(), expected_scope=target.scope, expected_composer_revision=0,
                content='独立虚构来源时间回拨测试'), db)
            assert run.state == 'queued'
            scope = run.scope
    else:
        monkeypatch.setattr(attachment_records, '_at', lambda:future.isoformat())
        assert attachments.select_materials(actor, target.scope.conversation_id, d.AssistantMaterialSelectionInput(
            request_id=uuid4(), expected_scope=target.scope, items=()), database=database) == 1
        with database.session() as db:
            scope = conversations.read_conversation(actor, target.scope.conversation_id, db).scope
    monkeypatch.setattr(service, '_at', lambda:history['mapping'].created_at.isoformat())
    before = state(database, generations=False)
    value = service.append_synthetic_generation(actor, history['mapping'].id, request(history, expected_scope=scope), database=database)
    assert value.created_at == future+timedelta(microseconds=1)
    assert state(database, generations=False) == before


@pytest.mark.parametrize('kind', ['input', 'materials'])
def test_current_counter_without_selected_source_is_rejected_before_any_generation(history, kind):
    service = api(); database = history['database']; target = history['targets'][0][0]
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET '+kind+'_revision=1 WHERE id=:id'),
            {'id':str(target.scope.conversation_id)})
        scope = conversations.read_conversation(history['actor'], target.scope.conversation_id, db).scope
    before = state(database)
    denied('VERSION_CONFLICT', service.append_synthetic_generation, history['actor'], history['mapping'].id,
        request(history, expected_scope=scope), database=database)
    assert state(database) == before


@pytest.mark.parametrize('family', ['inbox', 'dispatch', 'grant', 'generation'])
@pytest.mark.parametrize('operation', ['append', 'find'])
def test_complete_history_damage_is_generic_conflict_before_append_or_unknown_lookup(history, family, operation):
    from tests.integration.test_weixin_dispatch_integrity import corrupt
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    value = request(history)
    if family == 'generation':
        first = service.append_synthetic_generation(actor, mapping.id, value, database=database)
        value = request(history, first, index=1)
    with database.session() as db:
        if family == 'inbox':
            corrupt(db, 'UPDATE weixin_accounts SET checkpoint_revision=99')
        elif family == 'dispatch':
            corrupt(db, 'UPDATE weixin_dispatch_receipts SET receipt_sha256=:sha', {'sha':'f'*64})
        elif family == 'grant':
            corrupt(db, 'UPDATE weixin_peer_scope_grants SET grant_sha256=:sha', {'sha':'f'*64})
        else:
            corrupt(db, 'UPDATE weixin_peer_generations SET generation_sha256=:sha', {'sha':'f'*64})
    before = state(database)
    function = service.append_synthetic_generation if operation == 'append' else service.find_peer_generation
    denied('VERSION_CONFLICT', function, actor, mapping.id, value if operation == 'append' else uuid4(), database=database)
    assert state(database) == before


@pytest.mark.parametrize('changed', ['previous_schema', 'pre_inbox_schema', 'unknown_schema'])
@pytest.mark.parametrize('operation', ['append', 'find'])
def test_both_generation_services_reject_prior_or_unknown_schema_without_upgrade(history, changed, operation):
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    with database.session() as db:
        if changed in ('previous_schema','pre_inbox_schema'):
            db.execute(text('DROP TABLE weixin_descriptor_generations'))
        if changed == 'pre_inbox_schema':
            for name in ('weixin_peer_generations', 'weixin_peer_scope_grants', 'weixin_dispatch_receipts',
                    'weixin_inbox_descriptors', 'weixin_poll_receipts', 'weixin_peer_bindings', 'weixin_accounts'):
                db.execute(text('DROP TABLE '+name))
        else:
            db.execute(text('DROP TABLE weixin_peer_generations' if changed == 'previous_schema' else 'CREATE TABLE future_schema(id TEXT)'))
    with database.session() as db:
        before = [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        if changed == 'pre_inbox_schema':
            assert identify_schema(before, native=True) == VERSIONS[12]
        elif changed == 'previous_schema':
            assert identify_schema(before, native=True) == VERSIONS[15]
    function = service.append_synthetic_generation if operation == 'append' else service.find_peer_generation
    denied('VERSION_CONFLICT', function, actor, mapping.id, request(history) if operation == 'append' else uuid4(), database=database)
    with database.session() as db:
        assert [tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))] == before


@pytest.mark.parametrize('position', ['root', 'previous_target', 'new_target'])
@pytest.mark.parametrize('changed', ['membership', 'matter_archived', 'intake_owner'])
def test_append_and_find_recheck_current_projected_case_and_intake_authority(history, position, changed):
    from cn_contract.matters import create_matter
    from cn_contract.persistence import MatterRow, MembershipRow
    from cn_contract.security import provision_user
    service = api(); database = history['database']; actor = history['actor']; mapping = history['mapping']
    first = service.append_synthetic_generation(actor, mapping.id, request(history), database=database)
    value = request(history, first, index=1)
    cid = (mapping.scope.conversation_id if position == 'root' else first.scope.conversation_id
        if position == 'previous_target' else value.expected_scope.conversation_id)
    with database.session() as db:
        matter = create_matter(d.MatterCreateInput(title='独立虚构代际当前权限案件', contract_type='sales',
            review_mode='pre_sign', position='buyer', objectives=('仅当前权限测试',)), actor, db)
        intake_id = uuid4()
        db.execute(text('''INSERT INTO intake_cases(id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES(:id,:owner,:request,:sha,1,:matter)'''), dict(id=str(intake_id), owner=str(actor.user_id),
                request=str(uuid4()), sha='a'*64, matter=str(matter.id)))
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
            {'id':str(cid), 'intake':str(intake_id)})
        if changed == 'membership':
            db.delete(db.get(MembershipRow, (str(matter.id), str(actor.user_id))))
        elif changed == 'matter_archived':
            db.get(MatterRow, str(matter.id)).status = 'archived'
        else:
            other = provision_user('独立虚构投影他人', 'synthetic-password', {d.Role.HANDLING_LAWYER}, db)
            db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),
                {'id':str(intake_id), 'owner':str(other)})
    before = state(database)
    denied('CROSS_MATTER_DENIED', service.append_synthetic_generation, actor, mapping.id, value, database=database)
    if position == 'new_target':
        assert service.find_peer_generation(actor, mapping.id, first.request_id, database=database) == first
        assert service.find_peer_generation(actor, mapping.id, uuid4(), database=database) is None
    else:
        denied('CROSS_MATTER_DENIED', service.find_peer_generation, actor, mapping.id, first.request_id, database=database)
    # Existing ACL denial audit writes are allowed; all source and task rows remain fixed.
    assert state(database) == before


@pytest.mark.parametrize('operation', ['append', 'find'])
def test_principal_authentication_precedes_unknown_root_lookup(world, operation):
    service = api(); _, database, actor, target, binding = world
    with database.session() as db:
        db.get(SessionRow, str(actor.session_id)).revoked = True
    value = d.WeixinPeerGenerationInput(request_id=uuid4(), expected_generation=0,
        expected_previous_generation_sha256=None, expected_previous_scope_sha256='a'*64,
        expected_checkpoint_revision=0, task_binding_id=binding.id, expected_scope=target.scope,
        reason='独立虚构身份优先测试')
    denied('AUTHORIZATION_REQUIRED', service.append_synthetic_generation if operation == 'append' else service.find_peer_generation,
        actor, uuid4(), value if operation == 'append' else uuid4(), database=database)


def test_service_revalidates_model_copy_before_any_generation_append(history):
    from pydantic import ValidationError
    service = api(); database = history['database']; value = request(history)
    before = state(database)
    with pytest.raises(ValidationError):
        service.append_synthetic_generation(history['actor'], history['mapping'].id,
            value.model_copy(update={'expected_generation':False}), database=database)
    assert state(database) == before


def test_schema17_public_generation_append_and_lookup_remain_supported(history):
    service=api();database=history['database'];actor=history['actor'];mapping=history['mapping']
    with database.session() as db:
        db.execute(text('DROP TABLE weixin_descriptor_generations'))
        rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        assert identify_schema(rows,native=True)=='weixin-generations-v1'
    value=request(history)
    created=service.append_synthetic_generation(actor,mapping.id,value,database=database)
    assert service.find_peer_generation(actor,mapping.id,value.request_id,database=database)==created
    with database.session() as db:
        rows=[tuple(row) for row in db.execute(text('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))]
        assert identify_schema(rows,native=True)=='weixin-generations-v1'
