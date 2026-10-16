"""Independent synthetic conversations exercise real SQLite command boundaries."""
import importlib.util
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.config import load_settings
from cn_contract.persistence import Database, MatterRow, SessionRow, UserRow
from cn_contract.security import ServiceError, authenticate, login, provision_user, set_membership


def test_assistant_storage_module_exists():
    assert importlib.util.find_spec('cn_contract.assistant') is not None


@pytest.fixture
def workspace(tmp_path):
    from cn_contract.assistant import schema, service
    from cn_contract.intake.schema import initialize_storage as intake_storage
    from cn_contract.ops.storage import initialize_storage as ops_storage
    database = Database('sqlite:///' + str(tmp_path / 'synthetic.sqlite'), tmp_path / 'protected', load_settings())
    intake_storage(database)
    ops_storage(database)
    schema.initialize_storage(database)
    workspace_id = uuid4()
    actors = {}
    with database.session() as db:
        db.execute(text('CREATE TABLE local_workspace_identity (id TEXT PRIMARY KEY NOT NULL)'))
        db.execute(text('INSERT INTO local_workspace_identity VALUES (:id)'), {'id':str(workspace_id)})
        for name, role in [('lawyer', d.Role.HANDLING_LAWYER), ('reviewer', d.Role.REVIEWING_LAWYER),
                           ('assistant', d.Role.ASSISTANT), ('admin', d.Role.ADMIN)]:
            provision_user(name, 'only-fictional-password', {role}, db)
            token, _ = login(name, 'only-fictional-password', db)
            actors[name] = authenticate(token, db)
    yield database, actors, workspace_id, service
    database.engine.dispose()


def conversation(workspace, **options):
    database, actors, _, service = workspace
    with database.session() as db:
        return service.create_conversation(actors['lawyer'],
            d.AssistantConversationCreateInput(request_id=uuid4(), display_title='独立合成咨询', **options), db)


def message(value, **changes):
    return d.AssistantMessageInput(expected_scope=value.scope,
        expected_composer_revision=value.composer_revision, request_id=uuid4(),
        content=' 原话：合成客户称对方未交货。\n请核对材料。 ', **changes)


def counts(database):
    with database.session() as db:
        return tuple(db.scalar(text('SELECT COUNT(*) FROM ' + name)) for name in
            ('assistant_messages', 'assistant_runs', 'assistant_run_events'))


def assert_denied(code, function, *args):
    with pytest.raises(ServiceError) as result:
        function(*args)
    assert result.value.code == code
    return result.value


def test_create_roundtrip_same_key_and_conflict(workspace):
    database, actors, wid, service = workspace
    request = d.AssistantConversationCreateInput(request_id=uuid4(), display_title='合成咨询')
    with database.session() as db:
        first = service.create_conversation(actors['lawyer'], request, db)
    with database.session() as db:
        assert service.create_conversation(actors['lawyer'], request, db) == first
        assert service.read_conversation(actors['lawyer'], first.scope.conversation_id, db) == first
        assert first.scope.workspace_id == wid
        assert first.scope.scope_ref is None
        assert first.scope.input_revision == first.scope.materials_revision == first.composer_revision == 0
        assert first.messages == ()
    with database.session() as db:
        assert_denied('VERSION_CONFLICT', service.create_conversation, actors['lawyer'],
            request.model_copy(update={'display_title':'different'}), db)


def test_draft_send_and_new_draft_keep_sent_snapshot(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        drafted = service.save_draft(actors['lawyer'], first.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=first.scope, expected_composer_revision=0, content='尚未发送'), db)
        assert drafted.scope == first.scope
        assert drafted.composer_revision == 1
        assert drafted.draft_input == '尚未发送'
    request = message(drafted, requested_skill='client_reply')
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, request, db)
        assert run.state == 'queued' and run.selected_provider is run.selected_model is None
        assert run.scope.input_revision == 1
        assert run.events[0].event_type == 'message.accepted'
        assert run.events[0].audience == 'internal'
    with database.session() as db:
        sent = service.read_conversation(actors['lawyer'], first.scope.conversation_id, db)
        assert sent.messages[0].content == request.content
        assert sent.messages[0].role == 'user'
        assert sent.draft_input == '' and sent.composer_revision == 2
        typing = service.save_draft(actors['lawyer'], first.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=sent.scope, expected_composer_revision=2, content='下一条未发送'), db)
        assert typing.scope == run.scope
        assert service.get_run(actors['lawyer'], run.id, db) == run
        assert service.save_message(actors['lawyer'], first.scope.conversation_id, request, db) == run
    assert counts(database) == (1, 1, 1)


def test_replay_conflict_and_busy_do_not_add_history(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    request = message(first)
    with database.session() as db:
        service.save_message(actors['lawyer'], first.scope.conversation_id, request, db)
    with database.session() as db:
        assert_denied('VERSION_CONFLICT', service.save_message, actors['lawyer'], first.scope.conversation_id,
            request.model_copy(update={'content':'另一内容'}), db)
        latest = service.read_conversation(actors['lawyer'], first.scope.conversation_id, db)
        assert_denied('ASSISTANT_BUSY', service.save_message, actors['lawyer'], first.scope.conversation_id, message(latest), db)
    assert counts(database) == (1, 1, 1)


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_send_serializes_same_key_or_busy(workspace, same_key):
    database, actors, _, service = workspace
    first = conversation(workspace)
    request = message(first)
    barrier = Barrier(2)
    def send(index):
        selected = request if same_key or index == 0 else request.model_copy(update={'request_id':uuid4()})
        barrier.wait(timeout=10)
        try:
            with database.session() as db:
                return str(service.save_message(actors['lawyer'], first.scope.conversation_id, selected, db).id)
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(send, range(2)))
    if same_key:
        assert len(set(results)) == 1 and results[0] not in {'ASSISTANT_BUSY', 'VERSION_CONFLICT'}
    else:
        assert 'ASSISTANT_BUSY' in results
        assert len(set(results)) == 2
    assert counts(database) == (1, 1, 1)


@pytest.mark.parametrize('field', ['workspace_id', 'conversation_id', 'binding_revision', 'input_revision', 'materials_revision'])
def test_stale_or_forged_scope_rejected(workspace, field):
    database, actors, _, service = workspace
    first = conversation(workspace)
    value = uuid4() if field.endswith('_id') else getattr(first.scope, field) + 1
    request = message(first).model_copy(update={'expected_scope':first.scope.model_copy(update={field:value})})
    with database.session() as db:
        assert_denied('VERSION_CONFLICT', service.save_message, actors['lawyer'], first.scope.conversation_id, request, db)
    assert counts(database) == (0, 0, 0)


def test_stale_composer_and_attachments_rejected(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        assert_denied('VERSION_CONFLICT', service.save_draft, actors['lawyer'], first.scope.conversation_id,
            d.AssistantDraftInput(expected_scope=first.scope, expected_composer_revision=1, content='stale'), db)
        assert_denied('NOT_SUPPORTED', service.save_message, actors['lawyer'], first.scope.conversation_id,
            message(first, attachment_ids=(uuid4(),)), db)
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('other', ['reviewer', 'assistant', 'admin'])
def test_other_owner_cannot_read_write_or_get_run(workspace, other):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
    for action, argument in [('read_conversation', first.scope.conversation_id), ('get_run', run.id)]:
        with database.session() as db:
            assert_denied('CROSS_MATTER_DENIED', getattr(service, action), actors[other], argument, db)
    with database.session() as db:
        assert_denied('CROSS_MATTER_DENIED', service.save_message, actors[other], first.scope.conversation_id, message(first), db)


@pytest.mark.parametrize('name', ['assistant', 'admin'])
def test_unapproved_role_cannot_create_conversation(workspace, name):
    database, actors, _, service = workspace
    with database.session() as db:
        assert_denied('CROSS_MATTER_DENIED', service.create_conversation, actors[name],
            d.AssistantConversationCreateInput(request_id=uuid4()), db)


@pytest.mark.parametrize('revocation', ['session', 'expired', 'disabled', 'role'])
def test_old_actor_and_replay_recheck_current_principal(workspace, revocation):
    database, actors, _, service = workspace
    first = conversation(workspace)
    actor = actors['lawyer']
    request = message(first)
    with database.session() as db:
        run = service.save_message(actor, first.scope.conversation_id, request, db)
    with database.session() as db:
        if revocation == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
        elif revocation == 'expired':
            db.get(SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif revocation == 'disabled':
            db.get(UserRow, str(actor.user_id)).disabled = True
        else:
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
    error = 'CROSS_MATTER_DENIED' if revocation == 'role' else 'AUTHORIZATION_REQUIRED'
    for function, arguments in [(service.read_conversation, (first.scope.conversation_id,)),
                                (service.get_run, (run.id,)),
                                (service.save_message, (first.scope.conversation_id, request))]:
        with database.session() as db:
            assert_denied(error, function, actor, *arguments, db)
    assert counts(database) == (1, 1, 1)


def add_matter(database, actor):
    identifier = uuid4()
    with database.session() as db:
        db.add(MatterRow(id=str(identifier), title='合成案件', status='draft', payload='{}'))
        db.flush()
        set_membership(identifier, actor.user_id, db)
    return identifier


def add_intake(database, actor, matter_id=None):
    identifier = uuid4()
    with database.session() as db:
        db.execute(text('''INSERT INTO intake_cases
            (id,owner_id,request_id,request_sha256,current_revision,matter_id)
            VALUES (:id,:owner,:request,:digest,1,:matter)'''),
            {'id':str(identifier), 'owner':str(actor.user_id), 'request':str(uuid4()),
             'digest':'a'*64, 'matter':str(matter_id) if matter_id else None})
    return identifier


@pytest.mark.parametrize('scope_kind', ['matter', 'intake'])
def test_membership_revocation_hides_bound_conversation_and_run(workspace, scope_kind):
    database, actors, _, service = workspace
    matter_id = add_matter(database, actors['lawyer'])
    scope_ref = matter_id if scope_kind == 'matter' else add_intake(database, actors['lawyer'], matter_id)
    first = conversation(workspace, scope_kind=scope_kind, scope_ref=scope_ref)
    request = message(first)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, request, db)
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
    for function, args in [(service.read_conversation, (first.scope.conversation_id,)),
                           (service.get_run, (run.id,)), (service.save_message, (first.scope.conversation_id, request))]:
        with database.session() as db:
            assert_denied('CROSS_MATTER_DENIED', function, actors['lawyer'], *args, db)


def test_current_intake_conversion_and_projection_recheck_authorization(workspace):
    database, actors, _, service = workspace
    intake_id = add_intake(database, actors['lawyer'])
    first = conversation(workspace, scope_kind='intake', scope_ref=intake_id)
    unbound = conversation(workspace)
    forbidden_matter = add_matter(database, actors['reviewer'])
    with database.session() as db:
        db.execute(text('UPDATE intake_cases SET matter_id=:matter WHERE id=:id'),
            {'id':str(intake_id), 'matter':str(forbidden_matter)})
        db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
            {'id':str(unbound.scope.conversation_id), 'intake':str(intake_id)})
    for value in (first, unbound):
        with database.session() as db:
            assert_denied('CROSS_MATTER_DENIED', service.read_conversation,
                actors['lawyer'], value.scope.conversation_id, db)


@pytest.mark.parametrize('table,statement', [
    ('assistant_messages', "UPDATE assistant_messages SET content='tampered'"),
    ('assistant_messages', 'DELETE FROM assistant_messages'),
    ('assistant_run_events', "UPDATE assistant_run_events SET payload_json='{}'"),
    ('assistant_run_events', 'DELETE FROM assistant_run_events'),
    ('assistant_runs', "UPDATE assistant_runs SET scope_snapshot='{}'"),
    ('assistant_runs', 'DELETE FROM assistant_runs'),
    ('assistant_conversations', 'DELETE FROM assistant_conversations')])
def test_immutable_history(workspace, table, statement):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
    with pytest.raises(Exception, match='IMMUTABLE_RECORD'):
        with database.session() as db:
            db.execute(text(statement))
    assert counts(database) == (1, 1, 1)


def test_restore_fence_blocks_every_write_but_allows_current_reads(workspace):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, service = workspace
    first = conversation(workspace)
    request = message(first)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, request, db)
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    with database.session() as db:
        assert service.read_conversation(actors['lawyer'], first.scope.conversation_id, db).messages
        assert service.get_run(actors['lawyer'], run.id, db) == run
    writes = [(service.create_conversation, (d.AssistantConversationCreateInput(request_id=uuid4()),)),
              (service.save_draft, (first.scope.conversation_id, d.AssistantDraftInput(
                  expected_scope=first.scope, expected_composer_revision=0, content='new'))),
              (service.save_message, (first.scope.conversation_id, request))]
    for function, args in writes:
        with database.session() as db:
            assert_denied('BLOCKED_LIVE', function, actors['lawyer'], *args, db)
    assert counts(database) == (1, 1, 1)


def test_restore_quarantines_only_unfinished_runs_and_is_idempotent(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
        assert service.quarantine_runs(db) == 1
        assert service.quarantine_runs(db) == 0
        stored = service.get_run(actors['lawyer'], run.id, db)
        assert stored.state == 'blocked'
        assert [event.seq for event in stored.events] == [1, 2]
        assert stored.events[1].event_type == 'restore.quarantined'
        assert stored.scope == run.scope


def test_failed_event_rolls_back_message_run_and_revision(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        db.execute(text("CREATE TRIGGER synthetic_event_failure BEFORE INSERT ON assistant_run_events BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"))
    with pytest.raises(Exception, match='synthetic failure'):
        with database.session() as db:
            service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
    assert counts(database) == (0, 0, 0)
    with database.session() as db:
        assert service.read_conversation(actors['lawyer'], first.scope.conversation_id, db) == first


def test_missing_native_identity_is_not_created_from_request(workspace):
    database, actors, _, service = workspace
    with database.session() as db:
        db.execute(text('DROP TABLE local_workspace_identity'))
        assert_denied('STATE_CONFLICT', service.create_conversation, actors['lawyer'],
            d.AssistantConversationCreateInput(request_id=uuid4()), db)
        assert db.scalar(text("SELECT COUNT(*) FROM sqlite_master WHERE name='local_workspace_identity'")) == 0


def test_reviewer_can_create_but_cannot_borrow_another_intake_or_session(workspace):
    database, actors, _, service = workspace
    intake_id = add_intake(database, actors['lawyer'])
    with database.session() as db:
        approved = service.create_conversation(actors['reviewer'],
            d.AssistantConversationCreateInput(request_id=uuid4()), db)
        assert approved.scope.workspace_id == workspace[2]
        assert_denied('CROSS_MATTER_DENIED', service.create_conversation, actors['reviewer'],
            d.AssistantConversationCreateInput(request_id=uuid4(), scope_kind='intake', scope_ref=intake_id), db)
        forged = actors['lawyer'].model_copy(update={'session_id':actors['reviewer'].session_id})
        assert_denied('AUTHORIZATION_REQUIRED', service.create_conversation, forged,
            d.AssistantConversationCreateInput(request_id=uuid4()), db)


def test_identity_change_and_current_intake_owner_revoke_existing_access(workspace):
    database, actors, _, service = workspace
    intake_id = add_intake(database, actors['lawyer'])
    first = conversation(workspace, scope_kind='intake', scope_ref=intake_id)
    with database.session() as db:
        db.execute(text('UPDATE intake_cases SET owner_id=:owner WHERE id=:id'),
            {'owner':str(actors['reviewer'].user_id), 'id':str(intake_id)})
        assert_denied('CROSS_MATTER_DENIED', service.read_conversation, actors['lawyer'], first.scope.conversation_id, db)
    unbound = conversation(workspace)
    with database.session() as db:
        db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
        assert_denied('CROSS_MATTER_DENIED', service.read_conversation, actors['lawyer'], unbound.scope.conversation_id, db)


def test_service_revalidates_unchecked_model_copy(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    request = message(first).model_copy(update={'expected_composer_revision':True})
    with database.session() as db:
        with pytest.raises(ValidationError):
            service.save_message(actors['lawyer'], first.scope.conversation_id, request, db)
    assert counts(database) == (0, 0, 0)


def test_finished_run_does_not_block_a_new_input_or_get_requarantined(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
        db.execute(text("UPDATE assistant_runs SET state='failed' WHERE id=:id"), {'id':str(run.id)})
        assert service.quarantine_runs(db) == 0
        current = service.read_conversation(actors['lawyer'], first.scope.conversation_id, db)
        second = service.save_message(actors['lawyer'], first.scope.conversation_id, message(current), db)
        assert second.scope.input_revision == 2
        assert second.id != run.id
        assert service.get_run(actors['lawyer'], run.id, db).state == 'failed'
    assert counts(database) == (2, 2, 2)


def test_caught_write_failure_uses_savepoint_not_partial_commit(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        db.execute(text("CREATE TRIGGER synthetic_event_failure BEFORE INSERT ON assistant_run_events BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END"))
    with database.session() as db:
        with pytest.raises(Exception, match='synthetic failure'):
            service.save_message(actors['lawyer'], first.scope.conversation_id, message(first), db)
        assert service.read_conversation(actors['lawyer'], first.scope.conversation_id, db) == first
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('changes', [{'workspace_id':str(uuid4())}, {'owner_id':str(uuid4())},
                                    {'scope_kind':'intake'}, {'scope_ref':str(uuid4())}])
def test_create_dto_does_not_accept_untrusted_identity_or_partial_scope(changes):
    with pytest.raises(ValidationError):
        d.AssistantConversationCreateInput(request_id=uuid4(), **changes)


@pytest.mark.parametrize('changes', [{'requested_skill':'arbitrary_code'}, {'content':'   '}, {'content':'bad\x00text'},
                                    {'content':'x'*20001}, {'expected_composer_revision':True}])
def test_message_boundary_validation(changes):
    payload = dict(request_id=uuid4(), expected_scope=dict(workspace_id=uuid4(), conversation_id=uuid4(),
        scope_kind='conversation', scope_ref=None, binding_revision=1, input_revision=0, materials_revision=0),
        expected_composer_revision=0, content='合成原话')
    with pytest.raises(ValidationError):
        d.AssistantMessageInput(**{**payload, **changes})
