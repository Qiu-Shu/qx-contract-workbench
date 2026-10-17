"""Synthetic history pages and durable request lookup for the chat homepage."""
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.persistence import SessionRow, UserRow
from tests.integration.test_assistant_storage import (
    workspace, conversation, message, counts, add_matter, add_intake, assert_denied,
)


def append_messages(database, identifier, number, *, start=0):
    ids = [uuid4() for _ in range(number)]
    with database.session() as db:
        db.execute(text('''INSERT INTO assistant_messages
            (id,conversation_id,role,content,source_revision,created_at)
            VALUES (:id,:conversation,'assistant',:content,1,:at)'''), [
                {'id':str(identifier_), 'conversation':str(identifier),
                 'content':f'独立合成段落 {start + index}', 'at':'2026-01-01T00:00:00+00:00'}
                for index, identifier_ in enumerate(ids)])
    return ids


def test_message_pages_preserve_order_duplicates_and_stable_cursor_on_append(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    ids = append_messages(database, identifier, 101)
    with database.session() as db:
        newest = service.read_conversation_page(actors['lawyer'], identifier, db)
    assert [item.id for item in newest.messages] == ids[51:]
    assert newest.next_before == ids[51] and newest.latest_run is None
    appended = append_messages(database, identifier, 2, start=101)
    with database.session() as db:
        middle = service.read_conversation_page(actors['lawyer'], identifier, db, before=newest.next_before)
        oldest = service.read_conversation_page(actors['lawyer'], identifier, db, before=middle.next_before)
        empty = service.read_conversation_page(actors['lawyer'], identifier, db, before=ids[0])
        refreshed = service.read_conversation_page(actors['lawyer'], identifier, db)
    assert [len(page.messages) for page in (newest, middle, oldest)] == [50, 50, 1]
    assert [item.id for page in (oldest, middle, newest) for item in page.messages] == ids
    assert oldest.next_before is None and empty.messages == () and empty.next_before is None
    assert [item.id for item in refreshed.messages] == ids[53:] + appended
    assert all(item.source_revision == 1 for item in newest.messages)
    assert len({item.created_at for item in newest.messages}) == 1


def test_page_reads_only_bounded_history_and_summary_never_reads_event_body(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    with database.session() as db:
        run = service.save_message(actors['lawyer'], identifier, message(first), db)
        # Invalid body deliberately proves the summary does not deserialize it.
        db.execute(text('''INSERT INTO assistant_run_events VALUES
            (:id,2,'synthetic.progress','internal','not JSON','2026-01-01T00:00:00+00:00')'''),
            {'id':str(run.id)})
    append_messages(database, identifier, 101)
    statements = []
    def observe(conn, cursor, statement, parameters, context, many):
        statements.append((statement.lower(), parameters))
    event.listen(database.engine, 'before_cursor_execute', observe)
    try:
        with database.session() as db:
            page = service.read_conversation_page(actors['lawyer'], identifier, db, limit=2)
            found = service.find_run(actors['lawyer'], identifier, run.request_id, db)
    finally:
        event.remove(database.engine, 'before_cursor_execute', observe)
    assert len(page.messages) == 2 and page.latest_run == found
    assert found.last_event_seq == 2 and found.request_sha256 == run.request_sha256
    assert 'events' not in found.model_dump()
    queries = [(sql, params) for sql, params in statements if 'from assistant_messages' in sql]
    assert len(queries) == 1 and 'limit' in queries[0][0] and 3 in queries[0][1]
    assert all('payload_json' not in sql for sql, _ in statements)
    assert all('max(seq)' in sql for sql, _ in statements if 'from assistant_run_events' in sql)


def test_find_run_survives_connection_restart_and_reports_latest_inserted_state(workspace, monkeypatch):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    with database.session() as db:
        request = message(first, requested_skill='client_reply')
        cancelled = service.save_message(actor, identifier, request, db)
        service.cancel_run(actor, cancelled.id, d.AssistantCancelInput(request_id=uuid4()), db)
        current = service.read_conversation(actor, identifier, db)
        # Time is not insertion order: the latest durable run may have an older timestamp.
        with monkeypatch.context() as clock:
            clock.setattr(service, '_at', lambda:'2000-01-01T00:00:00+00:00')
            queued = service.save_message(actor, identifier, message(current), db)
    database.engine.dispose()
    before = counts(database)
    with database.session() as db:
        old = service.find_run(actor, identifier, request.request_id, db)
        recent = service.read_conversation_page(actor, identifier, db).latest_run
        assert old.id == cancelled.id and old.state == 'cancelled' and old.cancel_requested
        assert old.request_sha256 == cancelled.request_sha256 and old.last_event_seq == 2
        assert old.scope == cancelled.scope and old.requested_skill == 'client_reply'
        assert recent.id == queued.id and recent.state == 'queued' and recent.last_event_seq == 1
        assert service.find_run(actor, identifier, uuid4(), db) is None
        assert service.save_message(actor, identifier, request, db).id == cancelled.id
    assert counts(database) == before


def test_empty_page_unknown_request_and_exact_page_boundary_do_not_write(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    with database.session() as db:
        empty = service.read_conversation_page(actors['lawyer'], identifier, db)
        assert empty.messages == () and empty.next_before is empty.latest_run is None
        assert service.find_run(actors['lawyer'], identifier, uuid4(), db) is None
    assert counts(database) == (0, 0, 0)
    ids = append_messages(database, identifier, 2)
    with database.session() as db:
        exact = service.read_conversation_page(actors['lawyer'], identifier, db, limit=2)
    assert [item.id for item in exact.messages] == ids and exact.next_before is None


def test_cursor_is_scoped_to_conversation_even_for_same_owner(workspace):
    database, actors, _, service = workspace
    first, other = conversation(workspace), conversation(workspace)
    foreign_id = append_messages(database, other.scope.conversation_id, 1)[0]
    with database.session() as db:
        for cursor in (foreign_id, uuid4()):
            assert_denied('CROSS_MATTER_DENIED', lambda:service.read_conversation_page(
                actors['lawyer'], first.scope.conversation_id, db, before=cursor))
        run = service.save_message(actors['lawyer'], other.scope.conversation_id, message(other), db)
        assert service.find_run(actors['lawyer'], first.scope.conversation_id, run.request_id, db) is None


@pytest.mark.parametrize('changes', [{'limit':0}, {'limit':51}, {'limit':True}, {'limit':'2'},
                                   {'limit':1.5}, {'before':'invalid'}])
def test_page_query_rejects_invalid_bounds(workspace, changes):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db, pytest.raises(ValidationError):
        service.read_conversation_page(actors['lawyer'], first.scope.conversation_id, db, **changes)


@pytest.mark.parametrize('page_size', [0, 51, True, '2', 1.5])
def test_invalid_page_size_cannot_mutate_even_when_error_caught_in_transaction(workspace, page_size):
    database, actors, _, service = workspace
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    with database.session() as db:
        with pytest.raises(ValidationError):
            service.create_conversation(actors['lawyer'],
                d.AssistantConversationCreateInput(request_id=uuid4()), db, page_size=page_size)
        with pytest.raises(ValidationError):
            service.save_draft(actors['lawyer'], identifier,
                d.AssistantDraftInput(expected_scope=first.scope, expected_composer_revision=0,
                                      content='不能被保存的合成草稿'), db, page_size=page_size)
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_conversations')) == 1
        assert service.read_conversation(actors['lawyer'], identifier, db) == first


def test_create_replay_and_draft_opt_into_pages_without_breaking_legacy_default(workspace):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    request = d.AssistantConversationCreateInput(request_id=uuid4())
    with database.session() as db:
        first = service.create_conversation(actor, request, db, page_size=2)
        assert type(first) is d.AssistantConversationPageView and first.messages == ()
    identifier = first.scope.conversation_id
    ids = append_messages(database, identifier, 5)
    with database.session() as db:
        limited = service.create_conversation(actor, request, db, page_size=2)
        assert [item.id for item in limited.messages] == ids[-2:] and limited.next_before == ids[-2]
        legacy = service.create_conversation(actor, request, db)
        assert type(legacy) is d.AssistantConversationView and len(legacy.messages) == 5
        draft = service.save_draft(actor, identifier, d.AssistantDraftInput(expected_scope=first.scope,
            expected_composer_revision=0, content='合成草稿'), db, page_size=2)
        assert type(draft) is d.AssistantConversationPageView and len(draft.messages) == 2
        assert draft.draft_input == '合成草稿' and draft.composer_revision == 1
        full = service.save_draft(actor, identifier, d.AssistantDraftInput(expected_scope=draft.scope,
            expected_composer_revision=1, content='合成下一版'), db)
        assert type(full) is d.AssistantConversationView and len(full.messages) == 5


@pytest.mark.parametrize('revocation', ['session', 'expired', 'disabled', 'role', 'workspace', 'other_owner'])
def test_history_and_lookup_recheck_current_authorization(workspace, revocation):
    database, actors, _, service = workspace
    first = conversation(workspace)
    actor = actors['lawyer']
    with database.session() as db:
        run = service.save_message(actor, first.scope.conversation_id, message(first), db)
        if revocation == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
        elif revocation == 'expired':
            db.get(SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif revocation == 'disabled':
            db.get(UserRow, str(actor.user_id)).disabled = True
        elif revocation == 'role':
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
        elif revocation == 'workspace':
            db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
        else:
            actor = actors['reviewer']
    code = 'AUTHORIZATION_REQUIRED' if revocation in {'session', 'expired', 'disabled'} else 'CROSS_MATTER_DENIED'
    with database.session() as db:
        assert_denied(code, service.read_conversation_page, actor, first.scope.conversation_id, db)
        assert_denied(code, service.find_run, actor, first.scope.conversation_id, run.request_id, db)
        assert_denied(code, service.find_run, actor, first.scope.conversation_id, uuid4(), db)


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
def test_history_and_lookup_recheck_linked_matter_access(workspace, scope_kind):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    matter_id = add_matter(database, actor)
    intake_id = add_intake(database, actor, matter_id)
    options = {} if scope_kind == 'projection' else {'scope_kind':scope_kind,
        'scope_ref':matter_id if scope_kind == 'matter' else intake_id}
    first = conversation(workspace, **options)
    identifier = first.scope.conversation_id
    with database.session() as db:
        if scope_kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id), 'id':str(identifier)})
        run = service.save_message(actor, identifier, message(first), db)
        page = service.read_conversation_page(actor, identifier, db)
        assert page.latest_run.id == run.id
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
    with database.session() as db:
        assert_denied('CROSS_MATTER_DENIED', service.read_conversation_page, actor, identifier, db)
        assert_denied('CROSS_MATTER_DENIED', service.find_run, actor, identifier, run.request_id, db)


def test_restore_fence_preserves_read_only_blocked_run_lookup(workspace):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, service = workspace
    first = conversation(workspace)
    identifier = first.scope.conversation_id
    with database.session() as db:
        run = service.save_message(actors['lawyer'], identifier, message(first), db)
        assert service.quarantine_runs(db) == 1
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    before = counts(database)
    with database.session() as db:
        found = service.find_run(actors['lawyer'], identifier, run.request_id, db)
        page = service.read_conversation_page(actors['lawyer'], identifier, db)
        assert found.id == run.id and found.state == 'blocked' and found.last_event_seq == 2
        assert page.latest_run == found and len(page.messages) == 1
        assert service.find_run(actors['lawyer'], identifier, uuid4(), db) is None
    assert counts(database) == before
