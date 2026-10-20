"""Explicit local research owns its call; history never reruns a query."""
import importlib.util
from io import BytesIO
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.security import ServiceError
from tests.integration.test_assistant_storage import workspace, conversation
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_library_tools import revoke
from tests.integration.test_assistant_attachments import material_workspace


@pytest.fixture
def research(workspace):
    assert importlib.util.find_spec('cn_contract.assistant.research') is not None, 'local research service missing'
    from cn_contract.assistant import research
    from cn_contract.assistant.library_schema import initialize_storage
    from cn_contract.assistant.model_schema import initialize_storage as model_storage
    from cn_contract.assistant.judge_schema import initialize_storage as judge_storage
    model_storage(workspace[0])
    judge_storage(workspace[0])
    initialize_storage(workspace[0])
    return research


def request(view, **changes):
    values = dict(expected_scope=view.scope, expected_composer_revision=view.composer_revision,
        request_id=uuid4(), content='目标租赁', requested_skill='legal_research')
    return d.AssistantMessageInput(**(values | changes))


def test_local_research_persists_result_and_replay_without_model(workspace, research, library, monkeypatch):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    view = conversation(workspace)
    value = request(view)
    with database.session() as db:
        first = research.enqueue_research(actor, view.scope.conversation_id, value, db)
    assert first.run.state == 'queued' and first.receipts == ()
    adapter = LegalLibraryAdapter(library[0])
    result = research.execute_research(actor, first.run.id, database, adapter)
    assert result.run.state == 'completed' and len(result.receipts) == 1
    assert result.receipts[0].result.result.page.state == 'ready'
    assert result.receipts[0].result.citation_ids
    def forbidden(*args):
        pytest.fail('saved history or replay queried the library')
    monkeypatch.setattr(adapter, 'search', forbidden)
    with database.session() as db:
        assert research.enqueue_research(actor, view.scope.conversation_id, value, db) == result
        assert research.find_research(actor, view.scope.conversation_id, value.request_id, db) == result
        assert research.read_research(actor, first.run.id, db) == result
        current = service._owned(actor, view.scope.conversation_id, db)
        history = research.read_history(actor, current,
            d.MainGenerationHistoryQuery(message_ids=(first.run.message_id,)), db)
        assert history.items[0].research == result
        for table in ('assistant_model_attempts', 'assistant_model_outputs', 'assistant_judge_attempts'):
            assert db.scalar(text('SELECT COUNT(*) FROM ' + table)) == 0


def test_other_actor_cannot_interrupt_an_owned_research(workspace, research):
    database, actors, _, _ = workspace
    view = conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actors['lawyer'], view.scope.conversation_id, request(view), db)
    with pytest.raises(ServiceError, match='authorized'):
        research.execute_research(actors['reviewer'], first.run.id, database, LegalLibraryAdapter(None))
    with database.session() as db:
        assert research.read_research(actors['lawyer'], first.run.id, db).run.state == 'queued'


def test_restored_fence_remains_read_only_even_during_trusted_cleanup(workspace, research):
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, _ = workspace
    view = conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actors['lawyer'], view.scope.conversation_id, request(view), db)
        db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    with database.session() as db:
        research.interrupt_research(first.run.id, db)
        assert research.read_research(actors['lawyer'], first.run.id, db) == first
    with pytest.raises(ServiceError) as error:
        research.execute_research(actors['lawyer'], first.run.id, database, LegalLibraryAdapter(None))
    assert error.value.code == 'BLOCKED_LIVE'
    with database.session() as db:
        assert research.read_research(actors['lawyer'], first.run.id, db) == first


@pytest.mark.parametrize('change', [{'requested_skill':None}, {'attachment_ids':(uuid4(),)}, {'content':'字'*201}])
def test_unsupported_input_never_creates_dispatch_intent(workspace, research, change):
    database, actors, _, service = workspace
    view = conversation(workspace)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            research.enqueue_research(actors['lawyer'], view.scope.conversation_id, request(view, **change), db)
        assert error.value.code in {'NOT_SUPPORTED', 'LIBRARY_TOOL_INPUT_INVALID'}
        assert service.read_conversation(actors['lawyer'], view.scope.conversation_id, db) == view


def test_old_saved_message_even_with_b1_call_is_not_adopted(workspace, research):
    from cn_contract.assistant import library_handlers
    database, actors, _, service = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    value = request(view)
    with database.session() as db:
        old = service.save_message(actor, view.scope.conversation_id, value, db)
    library_handlers.begin_library_call(actor, old.id, uuid4(), d.LibraryHandlerRequest(
        tool='legal_library.search', query=d.AssistantLibraryQuery(text=value.content)), database)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            research.enqueue_research(actor, view.scope.conversation_id, value, db)
        assert error.value.code == 'STATE_CONFLICT'
        assert service.get_run(actor, old.id, db).state == 'queued'
        current = service._owned(actor, view.scope.conversation_id, db)
        assert research.read_history(actor, current,
            d.MainGenerationHistoryQuery(message_ids=(old.message_id,)), db).items == ()


def test_changed_idempotency_body_is_rejected(workspace, research):
    database, actors, _, _ = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    value = request(view)
    with database.session() as db:
        original = research.enqueue_research(actor, view.scope.conversation_id, value, db)
        with pytest.raises(ServiceError) as error:
            research.enqueue_research(actor, view.scope.conversation_id, value.model_copy(update={'content':'另外关键词'}), db)
        assert error.value.code == 'VERSION_CONFLICT'
        assert research.read_research(actor, original.run.id, db) == original


def test_call_registration_failure_rolls_back_message_run_and_initial_event(workspace, research, monkeypatch):
    from cn_contract.assistant import library_handlers
    database, actors, _, service = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    original = library_handlers.begin_library_call_in_session
    def failing(*args):
        original(*args)
        raise ServiceError('LIBRARY_RECORD_INVALID', 409)
    monkeypatch.setattr(library_handlers, 'begin_library_call_in_session', failing)
    with database.session() as db:
        with pytest.raises(ServiceError):
            research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
        assert service.read_conversation(actor, view.scope.conversation_id, db) == view
        for table in ('assistant_messages', 'assistant_runs', 'assistant_run_events'):
            assert db.scalar(text('SELECT COUNT(*) FROM ' + table)) == 0


@pytest.mark.parametrize('state', ['not_configured', 'not_ready', 'timeout', 'ready'])
def test_unavailable_or_empty_result_has_honest_receipt_without_retry(workspace, research, monkeypatch, state):
    database, actors, _, _ = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
    adapter = LegalLibraryAdapter(None)
    calls = []
    def read(query):
        calls.append(query)
        return d.LibraryCitationPage(query=query, state=state,
            generation_id='a'*32 if state in {'ready', 'timeout'} else None)
    monkeypatch.setattr(adapter, 'search', read)
    result = research.execute_research(actor, first.run.id, database, adapter)
    assert result.run.state == 'completed'
    assert result.receipts[0].result.result.page.state == state
    assert research.execute_research(actor, first.run.id, database, adapter) == result
    assert len(calls) == 1


@pytest.mark.parametrize('change', ['cancel', 'composer', 'revoke', 'interrupt'])
def test_late_result_rechecks_current_authority_and_never_publishes(workspace, research, monkeypatch, change):
    database, actors, _, service = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
    adapter = LegalLibraryAdapter(None)
    def read(query):
        if change == 'revoke':
            revoke(database, actor, 'session')
        else:
            with database.session() as db:
                if change == 'interrupt':
                    research.interrupt_research(first.run.id, db)
                elif change == 'cancel':
                    service.cancel_run(actor, first.run.id, d.AssistantCancelInput(request_id=uuid4()), db)
                else:
                    current = service.read_conversation(actor, view.scope.conversation_id, db)
                    service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
                        expected_scope=current.scope, expected_composer_revision=current.composer_revision,
                        content='新的草稿'), db)
        return d.LibraryCitationPage(query=query, state='not_configured')
    monkeypatch.setattr(adapter, 'search', read)
    with pytest.raises(ServiceError) as error:
        research.execute_research(actor, first.run.id, database, adapter)
    assert error.value.code in {'AUTHORIZATION_REQUIRED', 'STATE_CONFLICT', 'VERSION_CONFLICT'}
    with database.session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_handler_receipts')) == 0
        expected = {'cancel':'cancelled', 'interrupt':'interrupted'}.get(change, 'failed')
        assert db.scalar(text('SELECT state FROM assistant_runs WHERE id=:id'), {'id':str(first.run.id)}) == expected


def test_unexpected_error_is_fixed_code_and_never_recorded_verbatim(workspace, research, monkeypatch):
    database, actors, _, service = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
    adapter = LegalLibraryAdapter(None)
    def bad(query):
        raise RuntimeError('DO-NOT-STORE-SYNTHETIC-DETAIL')
    monkeypatch.setattr(adapter, 'search', bad)
    with pytest.raises(ServiceError) as error:
        research.execute_research(actor, first.run.id, database, adapter)
    assert error.value.code == 'LOCAL_RESEARCH_FAILED'
    with database.session() as db:
        saved = service.get_run(actor, first.run.id, db)
        assert saved.state == 'failed'
        assert 'DO-NOT-STORE' not in saved.model_dump_json()
        assert saved.events[-1].payload['error_code'] == 'LOCAL_RESEARCH_FAILED'


def test_new_draft_and_input_do_not_hide_authorized_saved_history(workspace, research):
    database, actors, _, service = workspace
    actor, view = actors['lawyer'], conversation(workspace)
    with database.session() as db:
        first = research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
    result = research.execute_research(actor, first.run.id, database, LegalLibraryAdapter(None))
    with database.session() as db:
        current = service.read_conversation(actor, view.scope.conversation_id, db)
        service.save_message(actor, view.scope.conversation_id, request(current, requested_skill=None), db)
        current = service._owned(actor, view.scope.conversation_id, db)
        history = research.read_history(actor, current,
            d.MainGenerationHistoryQuery(message_ids=(first.run.message_id,)), db)
        assert history.items[0].research == result
        assert history.scope.input_revision == result.run.scope.input_revision + 1
        with pytest.raises(ServiceError):
            research.read_history(actor, current, d.MainGenerationHistoryQuery(message_ids=(uuid4(),)), db)


def test_selected_material_blocks_query_but_deselected_history_does_not(material_workspace, research):
    from cn_contract.assistant import attachments, service
    database, actors, view, upload, raw = material_workspace
    actor, cid = actors['lawyer'], view.scope.conversation_id
    attachments.ingest_attachment(actor, cid, upload, BytesIO(raw), database=database)
    with database.session() as db:
        current = service.read_conversation(actor, cid, db)
        with pytest.raises(ServiceError) as error:
            research.enqueue_research(actor, cid, request(current), db)
        assert error.value.code == 'NOT_SUPPORTED'
    selected = attachments.read_materials(actor, cid, database=database)
    attachments.select_materials(actor, cid, d.AssistantMaterialSelectionInput(
        request_id=uuid4(), expected_scope=selected.scope, items=()), database=database)
    with database.session() as db:
        current = service.read_conversation(actor, cid, db)
        run = research.enqueue_research(actor, cid, request(current), db)
    assert research.execute_research(actor, run.run.id, database, LegalLibraryAdapter(None)).run.state == 'completed'
