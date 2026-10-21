"""Preview send-basis extension: data for the native approval step, never a grant."""
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant.context_preview import assemble_context, preview_context
from cn_contract.assistant.providers.context_codec import build_basis
from cn_contract.assistant.providers.rounds_codec import build_basis_rounds
from tests.integration.test_assistant_context_preview_service import selected
from tests.integration.test_assistant_storage import workspace, conversation, counts
from tests.integration.test_assistant_research_service import research
from tests.integration.test_assistant_library_adapter import library


def config(**changes):
    values = dict(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='synthetic-ceiling')
    values.update(changes)
    return d.MainModelConfig(**values)


def test_preview_without_request_id_keeps_previous_bytes(workspace, research, library):
    database, _, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids)
    with database.session() as db:
        preview = preview_context(actor, view.scope.conversation_id, selection, db,
                                  config=config())
    assert preview.state == 'ready' and preview.send_basis is None
    assert preview.sending_enabled is False
    # The new optional field is the only payload difference from the pre-slice response.
    assert set(preview.model_dump(mode='json')) == {
        'scope', 'composer_revision', 'manifest', 'manifest_sha256', 'system_text', 'state',
        'model', 'config_sha256', 'max_input_bytes', 'wire_payload_json', 'wire_sha256',
        'wire_bytes', 'sending_enabled', 'send_basis'}


def test_preview_with_request_id_carries_exact_send_basis(workspace, research, library):
    database, _, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    request_id = uuid4()
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids,
        request_id=request_id)
    before = counts(database)
    with database.session() as db:
        preview = preview_context(actor, view.scope.conversation_id, selection, db,
                                  config=config())
        conversation_row = service._owned(actor, view.scope.conversation_id, db)
        scope, manifest, records = assemble_context(actor, conversation_row, ids, db)
        expected = build_basis(request_id, manifest, scope,
                               conversation_row['composer_revision'], config(), records)
    assert preview.state == 'ready' and preview.send_basis == expected
    assert preview.send_basis.request_id == request_id
    assert preview.send_basis.input_format == 'library-context-v1'
    assert preview.sending_enabled is False
    assert counts(database) == before, 'basis assembly must not write anything'


def test_preview_rounds_selection_carries_v2_send_basis(workspace, research, library):
    database, _, _, service = workspace
    actor, view, ids = selected(workspace, research, library)
    request_id = uuid4()
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids, max_rounds=2,
        request_id=request_id)
    with database.session() as db:
        preview = preview_context(actor, view.scope.conversation_id, selection, db,
                                  config=config())
        conversation_row = service._owned(actor, view.scope.conversation_id, db)
        scope, manifest, records = assemble_context(actor, conversation_row, ids, db)
        expected = build_basis_rounds(request_id, manifest, scope,
                                      conversation_row['composer_revision'], config(), records)
    assert preview.state == 'ready' and preview.send_basis == expected
    assert preview.send_basis.input_format == 'library-context-v2'
    assert preview.send_basis.template_version == 'saved-library-context-system-v2'


def test_oversized_or_unconfigured_preview_never_carries_a_basis(workspace, research, library):
    database, _, _, _ = workspace
    actor, view, ids = selected(workspace, research, library)
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids,
        request_id=uuid4())
    with database.session() as db:
        oversized = preview_context(actor, view.scope.conversation_id, selection, db,
                                    config=config(max_input_bytes=1))
        unconfigured = preview_context(actor, view.scope.conversation_id, selection, db)
    assert oversized.state == 'input_too_large' and oversized.send_basis is None
    assert unconfigured.state == 'not_configured' and unconfigured.send_basis is None


def test_preview_dto_rejects_a_basis_that_does_not_match_the_preview(workspace, research, library):
    database, _, _, _ = workspace
    actor, view, ids = selected(workspace, research, library)
    selection = d.MainContextSelection(expected_scope=view.scope,
        expected_composer_revision=view.composer_revision, citation_ids=ids,
        request_id=uuid4())
    with database.session() as db:
        preview = preview_context(actor, view.scope.conversation_id, selection, db,
                                  config=config())
    mutations = ['wire', 'manifest', 'scope']
    if len(preview.send_basis.source_bindings) >= 2:
        mutations.append('order')
    for mutate in mutations:
        basis = preview.send_basis.model_dump(mode='python')
        if mutate == 'wire':
            basis['wire_sha256'] = '0' * 64
        elif mutate == 'manifest':
            basis['manifest_sha256'] = '0' * 64
        elif mutate == 'scope':
            basis['expected_composer_revision'] += 1
        else:
            basis['source_bindings'] = tuple(reversed(basis['source_bindings']))
        with pytest.raises(ValueError, match='CONTEXT_PREVIEW_INVALID'):
            d.MainContextPreview.model_validate(
                {**preview.model_dump(mode='python'), 'send_basis': basis})
