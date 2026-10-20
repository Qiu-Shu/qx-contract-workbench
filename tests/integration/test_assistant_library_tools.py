"""Library tool authorization uses real conversations and independent synthetic data."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import warnings
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.persistence import SessionRow, UserRow
from cn_contract.security import ServiceError, remove_membership
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.assistant.tools.service import execute_tool
from tests.integration.test_assistant_storage import workspace, conversation, counts, add_matter, add_intake
from tests.integration.test_assistant_library_adapter import library


def search_call(view):
    return d.AssistantLibraryToolCall(tool='legal_library.search', expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, query=d.AssistantLibraryQuery(text='虚构租赁'))


def deny(code, function):
    with pytest.raises(ServiceError) as caught:
        function()
    assert caught.value.code == code


def unread_adapter(monkeypatch):
    adapter = LegalLibraryAdapter(None)
    def forbidden(*args):
        pytest.fail('a denied call must not read the library')
    monkeypatch.setattr(adapter, 'search', forbidden)
    monkeypatch.setattr(adapter, 'read_original', forbidden)
    return adapter


def test_unconfigured_local_library_is_an_honest_read_without_new_run(workspace):
    database, actors, _, _ = workspace
    view = conversation(workspace)
    before = counts(database)
    call = d.AssistantLibraryToolCall(tool='legal_library.search', expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, query=d.AssistantLibraryQuery(text='虚构租赁'))
    result = execute_tool(actors['lawyer'], call, database, LegalLibraryAdapter(None))
    assert result.tool == call.tool and result.scope == view.scope
    assert result.page.state == 'not_configured' and result.page.citations == ()
    assert result.citation is None and counts(database) == before


@pytest.mark.parametrize('other', ['reviewer', 'assistant', 'admin'])
def test_other_owner_never_reads_the_library(workspace, monkeypatch, other):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace))
    deny('CROSS_MATTER_DENIED', lambda: execute_tool(actors[other], call, database, unread_adapter(monkeypatch)))
    assert counts(database) == (0, 0, 0)


def revoke(database, actor, kind):
    with database.session() as db:
        if kind == 'session':
            db.get(SessionRow, str(actor.session_id)).revoked = True
        elif kind == 'expired':
            db.get(SessionRow, str(actor.session_id)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif kind == 'disabled':
            db.get(UserRow, str(actor.user_id)).disabled = True
        else:
            db.get(UserRow, str(actor.user_id)).roles = json.dumps(['admin'])


@pytest.mark.parametrize('kind', ['session', 'expired', 'disabled', 'role'])
@pytest.mark.parametrize('during_read', [False, True])
def test_principal_is_current_before_and_after_read(workspace, monkeypatch, kind, during_read):
    database, actors, _, _ = workspace
    actor, call = actors['lawyer'], search_call(conversation(workspace))
    if during_read:
        adapter = LegalLibraryAdapter(None)
        def read(query):
            revoke(database, actor, kind)
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
    else:
        revoke(database, actor, kind)
        adapter = unread_adapter(monkeypatch)
    code = 'CROSS_MATTER_DENIED' if kind == 'role' else 'AUTHORIZATION_REQUIRED'
    deny(code, lambda: execute_tool(actor, call, database, adapter))
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('field', ['workspace_id', 'binding_revision', 'input_revision', 'materials_revision', 'composer_revision', 'archived_at'])
@pytest.mark.parametrize('during_read', [False, True])
def test_scope_revision_and_archive_checked_before_and_after_read(workspace, monkeypatch, field, during_read):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace))
    def change():
        value = str(uuid4()) if field == 'workspace_id' else ('2026-10-20T00:00:00+00:00' if field == 'archived_at' else 7)
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET ' + field + '=:value WHERE id=:id'),
                {'value':value, 'id':str(call.expected_scope.conversation_id)})
    if during_read:
        adapter = LegalLibraryAdapter(None)
        def read(query):
            change()
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
    else:
        change()
        adapter = unread_adapter(monkeypatch)
    code = 'CROSS_MATTER_DENIED' if field == 'workspace_id' else 'VERSION_CONFLICT'
    deny(code, lambda: execute_tool(actors['lawyer'], call, database, adapter))
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('scope_kind', ['matter', 'intake', 'projection'])
@pytest.mark.parametrize('during_read', [False, True])
def test_matter_membership_and_converted_intake_checked_on_each_side(workspace, monkeypatch, scope_kind, during_read):
    database, actors, _, _ = workspace
    actor = actors['lawyer']
    matter_id = add_matter(database, actor)
    intake_id = add_intake(database, actor, matter_id)
    if scope_kind == 'projection':
        view = conversation(workspace)
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET projection_intake_id=:intake WHERE id=:id'),
                {'intake':str(intake_id), 'id':str(view.scope.conversation_id)})
    else:
        view = conversation(workspace, scope_kind=scope_kind, scope_ref=matter_id if scope_kind == 'matter' else intake_id)
    call = search_call(view)
    def change():
        with database.session() as db:
            remove_membership(matter_id, actor.user_id, db)
    if during_read:
        adapter = LegalLibraryAdapter(None)
        def read(query):
            change()
            return d.LibraryCitationPage(query=query, state='not_configured')
        monkeypatch.setattr(adapter, 'search', read)
    else:
        change()
        adapter = unread_adapter(monkeypatch)
    deny('CROSS_MATTER_DENIED', lambda: execute_tool(actor, call, database, adapter))
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('changes', [{'tool':'shell'}, {'query':d.AssistantLibraryQuery(text='租赁').model_copy(update={'limit':99})},
    {'expected_composer_revision':True}, {'query':None}])
def test_even_copied_dto_is_revalidated_before_library_read(workspace, monkeypatch, changes):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace)).model_copy(update=changes)
    deny('LIBRARY_TOOL_INPUT_INVALID', lambda: execute_tool(actors['lawyer'], call, database, unread_adapter(monkeypatch)))


def test_invalid_copied_input_does_not_leak_query_in_serialization_warning(workspace, monkeypatch):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace))
    call = call.model_copy(update={'query':call.query.model_copy(update={'text':b'SYNTHETIC_PRIVATE_QUERY'})})
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter('always')
        deny('LIBRARY_TOOL_INPUT_INVALID', lambda: execute_tool(actors['lawyer'], call, database, unread_adapter(monkeypatch)))
    assert recorded == []


def test_file_io_does_not_hold_business_database_transaction(workspace, monkeypatch):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace))
    adapter = LegalLibraryAdapter(None)
    def read(query):
        with sqlite3.connect(database.engine.url.database, timeout=0) as connection:
            connection.execute('BEGIN IMMEDIATE')
            connection.rollback()
        return d.LibraryCitationPage(query=query, state='not_configured')
    monkeypatch.setattr(adapter, 'search', read)
    for _ in range(2):
        assert execute_tool(actors['lawyer'], call, database, adapter).page.state == 'not_configured'
    assert counts(database) == (0, 0, 0)


def test_real_search_read_and_repeat_keep_exact_source_without_creating_run(workspace, library):
    database, actors, _, _ = workspace
    view = conversation(workspace)
    adapter = LegalLibraryAdapter(library[0])
    call = search_call(view).model_copy(update={'query':d.AssistantLibraryQuery(text='目标租赁', kind='case_csv')})
    page = execute_tool(actors['lawyer'], call, database, adapter).page
    ref = page.citations[0]
    read = d.AssistantLibraryToolCall(tool='legal_library.read_original', expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation=ref)
    for _ in range(2):
        result = execute_tool(actors['lawyer'], read, database, adapter)
        assert result.page is None and result.citation == ref and result.scope == view.scope
        assert result.citation.support_status == result.citation.applicability_status == 'unverified'
    assert counts(database) == (0, 0, 0)


def test_original_result_is_discarded_when_scope_changes_during_read(workspace, library, monkeypatch):
    database, actors, _, service = workspace
    view = conversation(workspace)
    adapter = LegalLibraryAdapter(library[0])
    ref = adapter.search(d.AssistantLibraryQuery(text='目标租赁', kind='case_csv')).citations[0]
    call = d.AssistantLibraryToolCall(tool='legal_library.read_original', expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation=ref)
    original = adapter.read_original
    def read(citation):
        result = original(citation)
        with database.session() as db:
            service.save_draft(actors['lawyer'], view.scope.conversation_id,
                d.AssistantDraftInput(expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                    content='另一份独立合成材料'), db)
        return result
    monkeypatch.setattr(adapter, 'read_original', read)
    deny('VERSION_CONFLICT', lambda: execute_tool(actors['lawyer'], call, database, adapter))
    assert counts(database) == (0, 0, 0)


@pytest.mark.parametrize('error', [OSError('F:/private/secret.sqlite'), sqlite3.DatabaseError('private record'),
    ValueError('private contents'), ValueError('LIBRARY_GENERATION_STALE')])
def test_errors_are_sanitized_and_current_permission_wins(workspace, monkeypatch, error):
    database, actors, _, _ = workspace
    call = search_call(conversation(workspace))
    adapter = LegalLibraryAdapter(None)
    should_revoke = False
    def read(query):
        if should_revoke:
            revoke(database, actors['lawyer'], 'session')
        raise error
    monkeypatch.setattr(adapter, 'search', read)
    code = 'LIBRARY_GENERATION_STALE' if str(error) == 'LIBRARY_GENERATION_STALE' else 'LIBRARY_SOURCE_UNAVAILABLE'
    deny(code, lambda: execute_tool(actors['lawyer'], call, database, adapter))
    should_revoke = True
    deny('AUTHORIZATION_REQUIRED', lambda: execute_tool(actors['lawyer'], call, database, adapter))
    assert counts(database) == (0, 0, 0)
