"""Synthetic SQLite coverage for bounded assistant listings and run controls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError
from tests.integration.test_assistant_storage import (
    workspace, conversation, message, add_matter, add_intake, assert_denied,
)


def queued(workspace):
    database, actors, _, service = workspace
    value = conversation(workspace)
    with database.session() as db:
        return service.save_message(actors['lawyer'], value.scope.conversation_id, message(value), db)


def append_events(database, run, sequences):
    with database.session() as db:
        for sequence in sequences:
            db.execute(text('''INSERT INTO assistant_run_events
                (run_id,seq,event_type,audience,payload_json,created_at)
                VALUES (:id,:seq,'synthetic.progress','internal',:payload,:at)'''),
                {'id':str(run.id), 'seq':sequence, 'payload':canonical_json({'synthetic':True}),
                 'at':datetime.now(timezone.utc).isoformat()})


def test_listing_keyset_order_does_not_load_messages_or_drafts(workspace):
    database, actors, _, service = workspace
    values = [conversation(workspace) for _ in range(5)]
    timestamp = datetime.now(timezone.utc).isoformat()
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET created_at=:at'), {'at':timestamp})
    statements = []
    def observe(conn, cursor, statement, parameters, context, many):
        statements.append(statement.lower())
    event.listen(database.engine, 'before_cursor_execute', observe)
    try:
        pages = []
        cursor = None
        while True:
            with database.session() as db:
                page = service.list_conversations(actors['lawyer'], db, cursor=cursor, limit=2)
            pages.append(page)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
    finally:
        event.remove(database.engine, 'before_cursor_execute', observe)
    assert [item.scope.conversation_id for page in pages for item in page.items] == sorted(
        [value.scope.conversation_id for value in values], key=str, reverse=True)
    assert [len(page.items) for page in pages] == [2, 2, 1]
    assert all(set(item.model_dump()) == {
        'scope', 'display_title', 'composer_revision', 'created_at', 'archived_at'}
        for page in pages for item in page.items)
    assert not any('assistant_messages' in sql or 'assistant_run_events' in sql for sql in statements)
    batch_queries = [sql for sql in statements if 'order by created_at desc,id desc' in sql]
    assert len(batch_queries) == 3 and all('limit' in sql for sql in batch_queries)


@pytest.mark.parametrize('linked', ['matter', 'intake', 'projection'])
def test_listing_scans_bounded_inaccessible_batch_and_continues(workspace, linked):
    database, actors, _, service = workspace
    visible = conversation(workspace)
    matter_id = add_matter(database, actors['lawyer'])
    intake_id = add_intake(database, actors['lawyer'], matter_id)
    options = {'scope_kind':linked, 'scope_ref':matter_id if linked == 'matter' else intake_id}
    values = [conversation(workspace, **({} if linked == 'projection' else options)) for _ in range(2)]
    with database.session() as db:
        if linked == 'projection':
            for value in values:
                db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                    {'intake':str(intake_id), 'id':str(value.scope.conversation_id)})
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
    with database.session() as db:
        page = service.list_conversations(actors['lawyer'], db, limit=2)
        assert page.items == () and page.next_cursor == values[0].scope.conversation_id
    with database.session() as db:
        following = service.list_conversations(actors['lawyer'], db, cursor=page.next_cursor, limit=2)
        assert [item.scope.conversation_id for item in following.items] == [visible.scope.conversation_id]
        assert following.next_cursor is None


def test_listing_cursor_rejects_other_owner_unknown_and_workspace_identity(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    with database.session() as db:
        for cursor in (first.scope.conversation_id, uuid4()):
            assert_denied('CROSS_MATTER_DENIED', lambda:service.list_conversations(
                actors['reviewer'], db, cursor=cursor))
        assert service.list_conversations(actors['reviewer'], db).items == ()
        db.execute(text('UPDATE local_workspace_identity SET id=:id'), {'id':str(uuid4())})
        assert service.list_conversations(actors['lawyer'], db).items == ()
        assert_denied('CROSS_MATTER_DENIED', lambda:service.list_conversations(
            actors['lawyer'], db, cursor=first.scope.conversation_id))


def test_listing_includes_archived_summary_without_mutating_it(workspace):
    database, actors, _, service = workspace
    first = conversation(workspace)
    archived_at = datetime.now(timezone.utc)
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET archived_at=:at'), {'at':archived_at.isoformat()})
        page = service.list_conversations(actors['lawyer'], db)
        assert page.items[0].archived_at == archived_at
        assert page.items[0].scope == first.scope


def test_cancel_queued_records_single_event_and_allows_following_input(workspace):
    database, actors, _, service = workspace
    run = queued(workspace)
    request = d.AssistantCancelInput(request_id=uuid4())
    with database.session() as db:
        cancelled = service.cancel_run(actors['lawyer'], run.id, request, db)
        assert cancelled.state == 'cancelled' and cancelled.cancel_requested
        assert cancelled.events[-1].event_type == 'run.cancelled'
        assert cancelled.events[-1].payload['request_id'] == str(request.request_id)
        assert cancelled.events[-1].audience == 'internal'
        assert cancelled.events[-1].seq == 2
        assert service.cancel_run(actors['lawyer'], run.id, request, db) == cancelled
        assert service.cancel_run(actors['lawyer'], run.id, d.AssistantCancelInput(request_id=uuid4()), db) == cancelled
        current = service.read_conversation(actors['lawyer'], run.scope.conversation_id, db)
        next_run = service.save_message(actors['lawyer'], run.scope.conversation_id, message(current), db)
        assert next_run.state == 'queued' and next_run.scope.input_revision == 2


@pytest.mark.parametrize('state', ['awaiting_input', 'preparing', 'routing', 'retrieving', 'generating', 'persisting'])
def test_cancellation_matches_durable_runner_state(workspace, state):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':str(run.id)})
        cancelled = service.cancel_run(actors['lawyer'], run.id, d.AssistantCancelInput(request_id=uuid4()), db)
        assert cancelled.state == ('cancelled' if state == 'awaiting_input' else state)
        assert cancelled.cancel_requested
        assert cancelled.events[-1].event_type == ('run.cancelled' if state == 'awaiting_input' else 'run.cancel_requested')
        assert 'cost' not in cancelled.events[-1].payload
        assert len(cancelled.events) == 2
        assert service.cancel_run(actors['lawyer'], run.id,
            d.AssistantCancelInput(request_id=uuid4()), db) == cancelled
        if state != 'awaiting_input':
            current = service.read_conversation(actors['lawyer'], run.scope.conversation_id, db)
            assert_denied('ASSISTANT_BUSY', service.save_message, actors['lawyer'],
                run.scope.conversation_id, message(current), db)


@pytest.mark.parametrize('state', ['completed', 'cancelled', 'failed', 'interrupted', 'blocked'])
def test_terminal_cancellation_is_noop_even_when_not_previously_requested(workspace, state):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        db.execute(text('UPDATE assistant_runs SET state=:state WHERE id=:id'), {'state':state, 'id':str(run.id)})
        previous = service.get_run(actors['lawyer'], run.id, db)
        assert service.cancel_run(actors['lawyer'], run.id, d.AssistantCancelInput(request_id=uuid4()), db) == previous


@pytest.mark.parametrize('same_key', [True, False])
def test_concurrent_cancel_is_one_immutable_event(workspace, same_key):
    database, actors, _, service = workspace
    run = queued(workspace)
    request = d.AssistantCancelInput(request_id=uuid4())
    barrier = Barrier(2)
    def cancel(index):
        chosen = request if same_key or index == 0 else d.AssistantCancelInput(request_id=uuid4())
        barrier.wait(timeout=10)
        with database.session() as db:
            return service.cancel_run(actors['lawyer'], run.id, chosen, db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(cancel, range(2)))
    assert results[0] == results[1]
    assert len(results[0].events) == 2


def test_failed_cancel_event_rolls_back_inside_caught_transaction(workspace):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        db.execute(text("CREATE TRIGGER synthetic_cancel_failure BEFORE INSERT ON assistant_run_events WHEN NEW.seq>1 BEGIN SELECT RAISE(ABORT,'synthetic failure'); END"))
    with database.session() as db:
        with pytest.raises(Exception, match='synthetic failure'):
            service.cancel_run(actors['lawyer'], run.id, d.AssistantCancelInput(request_id=uuid4()), db)
        assert service.get_run(actors['lawyer'], run.id, db) == run
    with database.session() as db:
        assert service.get_run(actors['lawyer'], run.id, db) == run


def test_event_pages_resume_contiguously_without_loading_history(workspace, monkeypatch):
    database, actors, _, service = workspace
    run = queued(workspace)
    append_events(database, run, range(2, 8))
    def forbidden(*args):
        raise AssertionError('unbounded get_run is not an event page')
    monkeypatch.setattr(service, 'get_run', forbidden)
    with database.session() as db:
        first = service.read_events(actors['lawyer'], run.id, db, limit=3)
        assert first.run_id == run.id and first.conversation_id == run.scope.conversation_id
        assert first.state == 'queued' and first.has_more
        assert [item.seq for item in first.events] == [1, 2, 3] and first.next_after_seq == 3
        second = service.read_events(actors['lawyer'], run.id, db, after_seq=first.next_after_seq, limit=3)
        assert [item.seq for item in second.events] == [4, 5, 6] and second.has_more
        final = service.read_events(actors['lawyer'], run.id, db, after_seq=second.next_after_seq, limit=3)
        assert [item.seq for item in final.events] == [7] and not final.has_more and final.next_after_seq == 7
        empty = service.read_events(actors['lawyer'], run.id, db, after_seq=7)
        assert empty.events == () and empty.next_after_seq == 7 and not empty.has_more
    append_events(database, run, [8])
    with database.session() as db:
        resumed = service.read_events(actors['lawyer'], run.id, db, after_seq=empty.next_after_seq)
        assert [item.seq for item in resumed.events] == [8] and resumed.next_after_seq == 8


@pytest.mark.parametrize('after_seq', [0, 1, 2, 3, 5])
def test_event_cursor_rejects_missing_future_and_discontinuous_sequence(workspace, after_seq):
    database, actors, _, service = workspace
    run = queued(workspace)
    append_events(database, run, [3, 4])
    with database.session() as db:
        error = assert_denied('STATE_CONFLICT', lambda:service.read_events(
            actors['lawyer'], run.id, db, after_seq=after_seq))
        assert error.status_code == 409


@pytest.mark.parametrize('other', ['reviewer', 'assistant', 'admin'])
def test_other_owner_cannot_cancel_or_read_events(workspace, other):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        assert_denied('CROSS_MATTER_DENIED', service.cancel_run, actors[other], run.id,
            d.AssistantCancelInput(request_id=uuid4()), db)
        assert_denied('CROSS_MATTER_DENIED', service.read_events, actors[other], run.id, db)
        if other != 'reviewer':
            assert_denied('CROSS_MATTER_DENIED', service.list_conversations, actors[other], db)
        assert service.get_run(actors['lawyer'], run.id, db) == run


@pytest.mark.parametrize('revocation', ['session', 'expired', 'disabled', 'role'])
def test_every_control_rechecks_current_principal(workspace, revocation):
    database, actors, _, service = workspace
    run = queued(workspace)
    actor = actors['lawyer']
    with database.session() as db:
        if revocation == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
        elif revocation == 'expired':
            db.get(SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif revocation == 'disabled':
            db.get(UserRow, str(actor.user_id)).disabled = True
        else:
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])
    for action, args in [(service.list_conversations, ()), (service.read_events, (run.id,)),
                         (service.cancel_run, (run.id, d.AssistantCancelInput(request_id=uuid4())))]:
        with database.session() as db:
            assert_denied('CROSS_MATTER_DENIED' if revocation == 'role' else 'AUTHORIZATION_REQUIRED',
                action, actor, *args, db)


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
def test_every_control_rechecks_linked_matter_between_pages(workspace, scope_kind):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    matter_id = add_matter(database, actor)
    intake_id = add_intake(database, actor, matter_id)
    options = {} if scope_kind == 'projection' else {'scope_kind':scope_kind,
        'scope_ref':matter_id if scope_kind == 'matter' else intake_id}
    value = conversation(workspace, **options)
    with database.session() as db:
        if scope_kind == 'projection':
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id), 'id':str(value.scope.conversation_id)})
        run = service.save_message(actor, value.scope.conversation_id, message(value), db)
        assert service.read_events(actor, run.id, db).next_after_seq == 1
    with database.session() as db:
        db.execute(text('DELETE FROM matter_memberships WHERE matter_id=:id'), {'id':str(matter_id)})
    with database.session() as db:
        assert service.list_conversations(actor, db).items == ()
        assert_denied('CROSS_MATTER_DENIED', lambda:service.read_events(actor, run.id, db, after_seq=1))
        assert_denied('CROSS_MATTER_DENIED', service.cancel_run, actor, run.id,
            d.AssistantCancelInput(request_id=uuid4()), db)


def test_restore_fence_allows_pages_but_blocks_cancel_replay(workspace):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, service = workspace
    run = queued(workspace)
    request = d.AssistantCancelInput(request_id=uuid4())
    with database.session() as db:
        cancelled = service.cancel_run(actors['lawyer'], run.id, request, db)
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    with database.session() as db:
        assert service.list_conversations(actors['lawyer'], db).items
        assert service.read_events(actors['lawyer'], run.id, db).events == cancelled.events
        assert_denied('BLOCKED_LIVE', service.cancel_run, actors['lawyer'], run.id, request, db)


@pytest.mark.parametrize('changes', [{'limit':0}, {'limit':51}, {'limit':True}, {'cursor':'not-a-uuid'}])
def test_listing_validates_bounds_and_cursor(workspace, changes):
    database, actors, _, service = workspace
    with database.session() as db:
        with pytest.raises(ValidationError):
            service.list_conversations(actors['lawyer'], db, **changes)


@pytest.mark.parametrize('changes', [{'limit':0}, {'limit':101}, {'limit':True}, {'after_seq':-1}, {'after_seq':True}])
def test_events_validate_strict_bounds(workspace, changes):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        with pytest.raises(ValidationError):
            service.read_events(actors['lawyer'], run.id, db, **changes)


def test_cancel_revalidates_unchecked_input(workspace):
    database, actors, _, service = workspace
    run = queued(workspace)
    with database.session() as db:
        request = d.AssistantCancelInput(request_id=uuid4()).model_copy(update={'request_id':'invalid'})
        with pytest.warns(UserWarning, match='Pydantic serializer warnings'):
            with pytest.raises(ValidationError):
                service.cancel_run(actors['lawyer'], run.id, request, db)
        assert service.get_run(actors['lawyer'], run.id, db) == run
