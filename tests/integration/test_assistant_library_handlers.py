"""The library ledger binds durable calls and source snapshots to real runs."""
import importlib.util
import json
import sqlite3
import warnings
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.persistence import SessionRow
from cn_contract.security import ServiceError, authenticate, login, remove_membership
from tests.integration.test_assistant_storage import workspace, conversation, message, counts, add_matter
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_library_tools import revoke


def test_handler_entrypoints_exist():
    assert importlib.util.find_spec('cn_contract.assistant.library_handlers') is not None


@pytest.fixture
def ledger(workspace):
    assert importlib.util.find_spec('cn_contract.assistant.library_handlers') is not None, 'library handler is missing'
    from cn_contract.assistant import library_handlers as handlers
    from cn_contract.assistant.library_schema import initialize_storage
    database, actors, _, service = workspace
    initialize_storage(database)
    view = conversation(workspace)
    with database.session() as db:
        run = service.save_message(actors['lawyer'], view.scope.conversation_id, message(view), db)
    return database, actors['lawyer'], run, handlers


def search_request():
    return d.LibraryHandlerRequest(tool='legal_library.search',
        query=d.AssistantLibraryQuery(text='目标租赁', kind='case_csv'))


def call(ledger, request=None, call_id=None):
    database, actor, run, handlers = ledger
    return handlers.begin_library_call(actor, run.id, call_id or uuid4(), request or search_request(), database)


def execute(ledger, value, adapter):
    database, actor, _, handlers = ledger
    return handlers.execute_library_handler(actor, value.run_id, value.event_seq, database, adapter)


def totals(database):
    with database.session() as db:
        return tuple(db.scalar(text('SELECT COUNT(*) FROM ' + table)) for table in
            ('assistant_handler_receipts', 'assistant_library_citations'))


def denied(code, action):
    with pytest.raises(ServiceError) as caught:
        action()
    assert caught.value.code == code


def test_search_original_and_replay_keep_server_owned_immutable_history(ledger, library, monkeypatch):
    database, actor, run, handlers = ledger
    adapter = LegalLibraryAdapter(library[0])
    first = call(ledger)
    result = execute(ledger, first, adapter)
    assert not result.replayed and result.receipt.event_seq == first.event_seq
    assert len(result.receipt.result.citation_ids) > 0
    saved_id = result.receipt.result.citation_ids[0]
    with database.session() as db:
        saved = handlers.read_saved_citation(actor, saved_id, db)
    assert saved.citation == result.receipt.result.result.page.citations[0]
    read = call(ledger, d.LibraryHandlerRequest(tool='legal_library.read_original', saved_citation_id=saved_id))
    checked = execute(ledger, read, adapter)
    assert checked.receipt.result.result.citation == saved.citation
    assert checked.receipt.result.citation_ids != (saved_id,)
    def forbidden(*args):
        pytest.fail('replay must not touch the external library')
    monkeypatch.setattr(adapter, 'search', forbidden)
    monkeypatch.setattr(adapter, 'read_original', forbidden)
    replay = execute(ledger, first, adapter)
    assert replay.replayed and replay.receipt == result.receipt
    assert counts(database) == (1, 1, 3)


def test_call_identity_and_eight_call_budget_include_unfinished_events(ledger):
    database, actor, run, handlers = ledger
    identifier = uuid4()
    first = call(ledger, call_id=identifier)
    assert call(ledger, call_id=identifier) == first
    denied('VERSION_CONFLICT', lambda: call(ledger, d.LibraryHandlerRequest(
        tool='legal_library.search', query=d.AssistantLibraryQuery(text='different')), identifier))
    for _ in range(7):
        call(ledger)
    denied('LIBRARY_TOOL_LIMIT', lambda: call(ledger))
    assert counts(database) == (1, 1, 9) and totals(database) == (0, 0)


def test_concurrent_same_call_has_one_event_and_one_receipt(ledger, monkeypatch):
    identifier = uuid4()
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = list(pool.map(lambda _: call(ledger, call_id=identifier), range(2)))
    assert calls[0] == calls[1]
    adapter = LegalLibraryAdapter(None)
    barrier = Barrier(2)
    def read(query):
        barrier.wait(timeout=10)
        return d.LibraryCitationPage(query=query, state='not_configured')
    monkeypatch.setattr(adapter, 'search', read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: execute(ledger, calls[0], adapter), range(2)))
    assert {item.replayed for item in values} == {True, False}
    assert values[0].receipt == values[1].receipt
    assert totals(ledger[0]) == (1, 0) and counts(ledger[0]) == (1, 1, 2)


def unread(monkeypatch):
    adapter = LegalLibraryAdapter(None)
    def reject(*args):
        pytest.fail('denied call touched the library')
    monkeypatch.setattr(adapter, 'search', reject)
    monkeypatch.setattr(adapter, 'read_original', reject)
    return adapter


@pytest.mark.parametrize('kind', ['session', 'expired', 'disabled', 'role'])
@pytest.mark.parametrize('during', [False, True])
def test_current_principal_checked_before_and_after_io(ledger, monkeypatch, kind, during):
    database, actor, _, _ = ledger
    first = call(ledger)
    if during:
        adapter = LegalLibraryAdapter(None)
        def read(query):
            revoke(database, actor, kind)
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
    else:
        revoke(database, actor, kind)
        adapter = unread(monkeypatch)
    denied('CROSS_MATTER_DENIED' if kind == 'role' else 'AUTHORIZATION_REQUIRED',
        lambda: execute(ledger, first, adapter))
    assert totals(database) == (0, 0)


@pytest.mark.parametrize('change', ['cancel', 'state', 'scope', 'composer', 'fence'])
@pytest.mark.parametrize('during', [False, True])
def test_run_scope_and_restore_fence_checked_before_and_after_io(ledger, monkeypatch, change, during):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actor, run, _ = ledger
    first = call(ledger)
    def alter():
        with database.session() as db:
            if change == 'fence':
                db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
            elif change in ('cancel', 'state'):
                db.execute(text('UPDATE assistant_runs SET ' +
                    ('cancel_requested=1' if change == 'cancel' else "state='completed'") + ' WHERE id=:id'), {'id':str(run.id)})
            else:
                field = 'input_revision' if change == 'scope' else 'composer_revision'
                db.execute(text('UPDATE assistant_conversations SET ' + field + '=' + field + '+1 WHERE id=:id'),
                    {'id':str(run.scope.conversation_id)})
    if during:
        adapter = LegalLibraryAdapter(None)
        def read(query):
            alter()
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
    else:
        alter()
        adapter = unread(monkeypatch)
    code = 'BLOCKED_LIVE' if change == 'fence' else ('STATE_CONFLICT' if change in ('cancel', 'state') else 'VERSION_CONFLICT')
    denied(code, lambda: execute(ledger, first, adapter))
    denied(code, lambda: call(ledger, call_id=first.payload.call_id))
    assert totals(database) == (0, 0)


def test_new_session_can_read_history_but_cannot_execute_old_session_run(ledger, library, monkeypatch):
    database, actor, run, handlers = ledger
    first = call(ledger)
    result = execute(ledger, first, LegalLibraryAdapter(library[0]))
    identifier = result.receipt.result.citation_ids[0]
    with database.session() as db:
        db.get(SessionRow, str(actor.session_id)).revoked = True
        token, _ = login('lawyer', 'only-fictional-password', db)
        current = authenticate(token, db)
        db.execute(text('UPDATE assistant_conversations SET composer_revision=composer_revision+1 WHERE id=:id'),
            {'id':str(run.scope.conversation_id)})
    with database.session() as db:
        assert handlers.read_saved_citation(current, identifier, db).scope == run.scope
    denied('AUTHORIZATION_REQUIRED', lambda: handlers.execute_library_handler(
        current, run.id, first.event_seq, database, unread(monkeypatch)))


def test_current_and_historical_matter_access_both_required(workspace, library):
    from cn_contract.assistant import library_handlers as handlers
    from cn_contract.assistant.library_schema import initialize_storage
    database, actors, _, service = workspace
    initialize_storage(database)
    actor = actors['lawyer']
    original_matter, new_matter = add_matter(database, actor), add_matter(database, actor)
    view = conversation(workspace, scope_kind='matter', scope_ref=original_matter)
    with database.session() as db:
        run = service.save_message(actor, view.scope.conversation_id, message(view), db)
    context = database, actor, run, handlers
    result = execute(context, call(context), LegalLibraryAdapter(library[0]))
    identifier = result.receipt.result.citation_ids[0]
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET scope_ref=:ref,binding_revision=binding_revision+1 WHERE id=:id'),
            {'id':str(view.scope.conversation_id), 'ref':str(new_matter)})
        remove_membership(original_matter, actor.user_id, db)
    with database.session() as db:
        denied('CROSS_MATTER_DENIED', lambda: handlers.read_saved_citation(actor, identifier, db))
    # Another owner may not use a valid ID, even when the current conversation is public-looking.
    with database.session() as db:
        denied('CROSS_MATTER_DENIED', lambda: handlers.read_saved_citation(actors['reviewer'], identifier, db))


@pytest.mark.parametrize('table', ['assistant_handler_receipts', 'assistant_library_citations'])
def test_caught_publish_failure_rolls_back_whole_receipt_in_caller_transaction(ledger, library, table):
    database, actor, _, handlers = ledger
    first = call(ledger)
    adapter = LegalLibraryAdapter(library[0])
    result = d.AssistantLibraryToolResult(tool='legal_library.search', scope=first.payload.scope,
        page=adapter.search(first.payload.request.query))
    with database.session() as db:
        db.execute(text('CREATE TRIGGER synthetic_failure BEFORE INSERT ON ' + table +
            " BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE_CONTENT'); END"))
    with database.session() as db:
        denied('LIBRARY_RECORD_INVALID', lambda: handlers._publish_in_session(actor, first, result, db))
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_handler_receipts')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_library_citations')) == 0
    assert totals(database) == (0, 0)


def test_caller_rollback_removes_successful_receipt_and_citations(ledger, library):
    database, actor, _, handlers = ledger
    first = call(ledger)
    result = d.AssistantLibraryToolResult(tool='legal_library.search', scope=first.payload.scope,
        page=LegalLibraryAdapter(library[0]).search(first.payload.request.query))
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        with database.session() as db:
            assert not handlers._publish_in_session(actor, first, result, db).replayed
            raise RuntimeError('synthetic interruption')
    assert totals(database) == (0, 0)


def test_request_copied_dto_and_arbitrary_event_rejected_without_io(ledger, monkeypatch):
    database, actor, run, handlers = ledger
    request = search_request().model_copy(update={'query':d.AssistantLibraryQuery().model_copy(update={'text':b'SYNTHETIC_PRIVATE'})})
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always')
        denied('LIBRARY_TOOL_INPUT_INVALID', lambda: call(ledger, request))
    assert recorded == []
    denied('LIBRARY_RECORD_INVALID', lambda: handlers.execute_library_handler(actor, run.id, 1, database, unread(monkeypatch)))
    denied('LIBRARY_TOOL_INPUT_INVALID', lambda: handlers.execute_library_handler(actor, run.id, True, database, unread(monkeypatch)))
    assert counts(database) == (1, 1, 1)


def test_each_database_transaction_starts_immediate_and_io_holds_no_lock(ledger, monkeypatch):
    database, _, _, _ = ledger
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(database.engine, 'before_cursor_execute', capture)
    try:
        first = call(ledger)
        assert statements[0] == 'BEGIN IMMEDIATE'
        adapter = LegalLibraryAdapter(None)
        def read(query):
            with sqlite3.connect(database.engine.url.database, timeout=0) as connection:
                connection.execute('BEGIN IMMEDIATE')
                connection.rollback()
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
        assert not execute(ledger, first, adapter).replayed
    finally:
        event.remove(database.engine, 'before_cursor_execute', capture)


def test_result_size_bound_fails_before_insert_and_does_not_leak_contents(ledger, monkeypatch):
    first = call(ledger)
    adapter = LegalLibraryAdapter(None)
    def read(query):
        return d.LibraryCitationPage(query=query, state='ready', generation_id='a' * 32,
            coverage={'SYNTHETIC_PRIVATE_CONTENT' + 'x' * 270000:1})
    monkeypatch.setattr(adapter, 'search', read)
    denied('LIBRARY_RECORD_INVALID', lambda: execute(ledger, first, adapter))
    assert totals(ledger[0]) == (0, 0)


def test_begin_input_uses_only_server_loaded_record_from_same_run(ledger, workspace, library):
    database, actor, run, handlers = ledger
    result = execute(ledger, call(ledger), LegalLibraryAdapter(library[0]))
    identifier = result.receipt.result.citation_ids[0]
    view = conversation(workspace)
    with database.session() as db:
        second = workspace[3].save_message(actor, view.scope.conversation_id, message(view), db)
    request = d.LibraryHandlerRequest(tool='legal_library.read_original', saved_citation_id=identifier)
    denied('CROSS_MATTER_DENIED', lambda: handlers.begin_library_call(actor, second.id, uuid4(), request, database))
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_run_events WHERE run_id=:id'), {'id':str(second.id)}) == 1


def test_client_held_event_changes_cannot_replace_persisted_request(ledger):
    first = call(ledger)
    forged = first.model_copy(update={'payload':first.payload.model_copy(update={
        'request':d.LibraryHandlerRequest(tool='legal_library.search', query=d.AssistantLibraryQuery(text='another'))})})
    result = execute(ledger, forged, LegalLibraryAdapter(None))
    assert result.receipt.request == first.payload.request
    assert result.receipt.request != forged.payload.request


def test_restored_history_is_readable_without_restarting_any_call(ledger, library):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actor, _, handlers = ledger
    result = execute(ledger, call(ledger), LegalLibraryAdapter(library[0]))
    with database.session() as db:
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
        assert handlers.read_saved_citation(actor, result.receipt.result.citation_ids[0], db).citation == result.receipt.result.result.page.citations[0]
    assert totals(database)[0] == 1


def test_private_publish_revalidates_result_and_scope(ledger):
    database, actor, _, handlers = ledger
    first = call(ledger)
    result = d.AssistantLibraryToolResult(tool='legal_library.search', scope=first.payload.scope,
        page=d.LibraryCitationPage(query=first.payload.request.query, state='not_configured'))
    wrong = result.model_copy(update={'scope':result.scope.model_copy(update={'input_revision':99})})
    with database.session() as db:
        denied('LIBRARY_RECORD_INVALID', lambda: handlers._publish_in_session(actor, first, wrong, db))
    assert totals(database) == (0, 0)


def test_io_failure_keeps_current_run_gate_and_does_not_create_receipt(ledger, monkeypatch):
    database, actor, run, _ = ledger
    first = call(ledger)
    adapter = LegalLibraryAdapter(None)
    def fail(query):
        with database.session() as db:
            db.execute(text('UPDATE assistant_runs SET cancel_requested=1 WHERE id=:id'), {'id':str(run.id)})
        raise OSError('SYNTHETIC_PRIVATE_LOCATION')
    monkeypatch.setattr(adapter, 'search', fail)
    denied('STATE_CONFLICT', lambda: execute(ledger, first, adapter))
    assert totals(database) == (0, 0)


def test_private_publish_original_cannot_replace_persisted_source_snapshot(ledger, library):
    database, actor, _, handlers = ledger
    first = execute(ledger, call(ledger), LegalLibraryAdapter(library[0]))
    saved_id = first.receipt.result.citation_ids[0]
    original = first.receipt.result.result.page.citations[0]
    read = call(ledger, d.LibraryHandlerRequest(tool='legal_library.read_original', saved_citation_id=saved_id))
    changed = original.model_copy(update={'title':'另一份虚构来源'})
    result = d.AssistantLibraryToolResult(tool='legal_library.read_original', scope=read.payload.scope, citation=changed)
    before = totals(database)
    with database.session() as db:
        denied('LIBRARY_RECORD_INVALID', lambda: handlers._publish_in_session(actor, read, result, db))
    assert totals(database) == before


def test_different_call_ids_racing_for_last_slot_do_not_exceed_eight(ledger):
    for _ in range(7):
        call(ledger)
    def create(_):
        try:
            return call(ledger).event_seq
        except ServiceError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(create, range(2)))
    assert set(outcomes) == {9, 'LIBRARY_TOOL_LIMIT'}
    assert counts(ledger[0]) == (1, 1, 9)


def test_failed_begin_does_not_consume_call_identity(ledger):
    database, actor, run, handlers = ledger
    identifier = uuid4()
    with database.session() as db:
        db.execute(text("CREATE TRIGGER synthetic_begin_fail BEFORE INSERT ON assistant_run_events BEGIN SELECT RAISE(ABORT,'SYNTHETIC_PRIVATE'); END"))
    denied('LIBRARY_RECORD_INVALID', lambda: call(ledger, call_id=identifier))
    assert counts(database) == (1, 1, 1)
    with database.session() as db:
        db.execute(text('DROP TRIGGER synthetic_begin_fail'))
    assert call(ledger, call_id=identifier).event_seq == 2


def test_session_loss_blocks_receipt_replay_without_reading_source(ledger, monkeypatch):
    first = call(ledger)
    execute(ledger, first, LegalLibraryAdapter(None))
    revoke(ledger[0], ledger[1], 'session')
    denied('AUTHORIZATION_REQUIRED', lambda: execute(ledger, first, unread(monkeypatch)))


def test_malformed_stored_event_is_rejected_with_fixed_code(ledger, monkeypatch):
    database, actor, run, handlers = ledger
    first = call(ledger)
    with database.session() as db:
        db.execute(text('DROP TRIGGER immutable_assistant_run_events_update'))
        db.execute(text('UPDATE assistant_run_events SET payload_json=:raw WHERE run_id=:run AND seq=:seq'),
            {'raw':' ' + first.payload.model_dump_json(), 'run':str(run.id), 'seq':first.event_seq})
    denied('LIBRARY_RECORD_INVALID', lambda: execute(ledger, first, unread(monkeypatch)))
    assert totals(database) == (0, 0)


def test_rehashed_outer_rows_do_not_allow_wrong_citation_identity_in_history(ledger, library):
    from cn_contract.assistant.library_records import sha
    from cn_contract.config import canonical_json
    from tests.integration.test_assistant_attachment_backup import corrupt
    database, actor, _, handlers = ledger
    result = execute(ledger, call(ledger), LegalLibraryAdapter(library[0]))
    identifier = result.receipt.result.citation_ids[0]
    with database.session() as db:
        citation = dict(db.execute(text('SELECT * FROM assistant_library_citations WHERE id=:id'),
            {'id':str(identifier)}).mappings().one())
        receipt = dict(db.execute(text('SELECT * FROM assistant_handler_receipts WHERE id=:id'),
            {'id':citation['receipt_id']}).mappings().one())
    value = json.loads(citation['citation_json'])
    value['citation_id'] = '0' * 64
    raw = canonical_json(value)
    payload = json.loads(receipt['result_json'])
    payload['result']['page']['citations'][0] = value
    payload_raw = canonical_json(payload)
    corrupt(database, 'assistant_library_citations',
        'UPDATE assistant_library_citations SET citation_json=?,citation_sha256=? WHERE id=?',
        (raw, sha(raw), str(identifier)))
    corrupt(database, 'assistant_handler_receipts',
        'UPDATE assistant_handler_receipts SET result_json=?,result_sha256=? WHERE id=?',
        (payload_raw, sha(payload_raw), receipt['id']))
    with database.session() as db:
        denied('LIBRARY_RECORD_INVALID', lambda: handlers.read_saved_citation(actor, identifier, db))


def test_publish_rejects_wrong_content_identity_before_persisting_any_row(ledger, library):
    database, actor, _, handlers = ledger
    first = call(ledger)
    page = LegalLibraryAdapter(library[0]).search(first.payload.request.query)
    changed = page.citations[0].model_copy(update={'citation_id':'0' * 64})
    page = page.model_copy(update={'citations':(changed, *page.citations[1:])})
    result = d.AssistantLibraryToolResult(tool='legal_library.search', scope=first.payload.scope, page=page)
    with database.session() as db:
        denied('LIBRARY_RECORD_INVALID', lambda: handlers._publish_in_session(actor, first, result, db))
    assert totals(database) == (0, 0)
