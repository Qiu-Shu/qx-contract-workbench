"""Source-bound previews are local reads, never execution or authority."""
import importlib.util
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.security import ServiceError
from tests.integration.test_assistant_research_service import research, request
from tests.integration.test_assistant_storage import workspace, conversation, counts
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_attachments import material_workspace


def selected(workspace, research, library):
    database, actors, _, service = workspace
    actor = actors['lawyer']
    view = conversation(workspace)
    with database.session() as db:
        result = research.enqueue_research(actor, view.scope.conversation_id, request(view), db)
    result = research.execute_research(actor, result.run.id, database, LegalLibraryAdapter(library[0]))
    ids = result.receipts[0].result.citation_ids
    assert ids
    with database.session() as db:
        view = service.read_conversation(actor, view.scope.conversation_id, db)
        view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
            expected_scope=view.scope, expected_composer_revision=view.composer_revision,
            content=' 请按所选历史片段列出需要核对的问题。\n保留不同结论。 '), db)
    return actor, view, ids


def test_preview_reconstructs_saved_sources_without_library_or_model(workspace, research, library, monkeypatch):
    assert importlib.util.find_spec('cn_contract.assistant.context_preview') is not None, 'context preview service missing'
    from cn_contract.assistant.context_preview import preview_context
    database, _, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    before = counts(database)
    def forbidden(*args, **kwargs):
        pytest.fail('preview must only read persisted citations')
    monkeypatch.setattr(LegalLibraryAdapter, 'search', forbidden)
    monkeypatch.setattr(LegalLibraryAdapter, 'read_original', forbidden)
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids)
    with database.session() as db:
        preview = preview_context(actor, view.scope.conversation_id, selection, db)
        assert preview.manifest.question == view.draft_input
        assert tuple(item.saved_citation_id for item in preview.manifest.sources) == ids
        assert preview.state == 'not_configured' and preview.sending_enabled is False
        assert preview.wire_payload_json is None
        assert service.read_conversation(actor, view.scope.conversation_id, db) == view
        for table in ('assistant_model_attempts', 'assistant_model_outputs', 'assistant_judge_attempts'):
            assert db.scalar(text('SELECT COUNT(*) FROM ' + table)) == 0
    assert counts(database) == before


@pytest.mark.parametrize('change,code', [
    ('other_actor','CROSS_MATTER_DENIED'), ('other_conversation','CROSS_MATTER_DENIED'),
    ('unknown_citation','CROSS_MATTER_DENIED'), ('old_binding','CROSS_MATTER_DENIED'),
    ('future_source','CROSS_MATTER_DENIED'), ('stale_draft','VERSION_CONFLICT'),
    ('archived','VERSION_CONFLICT'), ('empty','NOT_SUPPORTED'), ('restore','BLOCKED_LIVE'),
])
def test_preview_refuses_unapproved_or_stale_source_context(workspace, research, library, change, code):
    from cn_contract.assistant.context_preview import preview_context
    from cn_contract.ops.storage import RestoreFenceRow
    database, actors, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    if change == 'other_actor': actor = actors['reviewer']
    elif change == 'unknown_citation': ids = (uuid4(),)
    elif change == 'other_conversation':
        view = conversation(workspace)
        with database.session() as db:
            view = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=view.scope, expected_composer_revision=view.composer_revision, content='另一对话问题'), db)
    elif change in {'old_binding','future_source','archived'}:
        statements = {'old_binding':'binding_revision=binding_revision+1',
            'future_source':'input_revision=0', 'archived':"archived_at='2026-01-01T00:00:00Z'"}
        with database.session() as db:
            db.execute(text('UPDATE assistant_conversations SET '+statements[change]+' WHERE id=:id'),
                {'id':str(view.scope.conversation_id)})
            view = service.read_conversation(actor, view.scope.conversation_id, db)
    elif change == 'restore':
        with database.session() as db:
            db.add(RestoreFenceRow(ref=str(uuid4()), archive_sha256='a'*64, manifest_sha256='b'*64, payload='{}'))
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids)
    if change in {'stale_draft','empty'}:
        with database.session() as db:
            updated = service.save_draft(actor, view.scope.conversation_id, d.AssistantDraftInput(
                expected_scope=view.scope, expected_composer_revision=view.composer_revision,
                content='新问题' if change == 'stale_draft' else ' '), db)
            if change == 'empty':
                selection = selection.model_copy(update={'expected_composer_revision':updated.composer_revision})
    before = counts(database)
    with database.session() as db:
        with pytest.raises(ServiceError) as error:
            preview_context(actor, view.scope.conversation_id, selection, db)
        assert error.value.code == code
    assert counts(database) == before


def test_selected_attachment_is_rejected_but_deselected_history_is_allowed(workspace, research, library, material_workspace):
    from io import BytesIO
    from cn_contract.assistant import attachments
    from cn_contract.assistant.context_preview import preview_context
    database, _, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    raw = material_workspace[-1]
    receipt = attachments.ingest_attachment(actor, view.scope.conversation_id, d.AssistantAttachmentInput(
        request_id=uuid4(), expected_scope=view.scope, original_name='独立合成.docx',
        mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        policy=d.AssistantMaterialPolicy(local_processing_accepted=True)), BytesIO(raw), database=database)
    with database.session() as db:
        view = service.read_conversation(actor, view.scope.conversation_id, db)
        selection = d.MainContextSelection(expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, citation_ids=ids)
        with pytest.raises(ServiceError) as error:
            preview_context(actor, view.scope.conversation_id, selection, db)
        assert error.value.code == 'NOT_SUPPORTED'
    attachments.select_materials(actor, view.scope.conversation_id, d.AssistantMaterialSelectionInput(
        request_id=uuid4(), expected_scope=view.scope, items=()), database=database)
    with database.session() as db:
        view = service.read_conversation(actor, view.scope.conversation_id, db)
        selection = d.MainContextSelection(expected_scope=view.scope,
            expected_composer_revision=view.composer_revision, citation_ids=ids)
        assert preview_context(actor, view.scope.conversation_id, selection, db).manifest.question == view.draft_input
