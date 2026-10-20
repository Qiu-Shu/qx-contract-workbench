"""Rebuild a bounded draft from saved citations; no grants, writes or dispatch."""
from .. import domain as d
from ..ops.storage import require_active
from ..security import ServiceError
from . import service
from .attachment_records import items
from .library_handlers import read_saved_citation
from .providers.context_preview import build_preview, project_source


def preview_context(actor, conversation_id, selection, db, *, config=None):
    selection = d.MainContextSelection.model_validate(selection.model_dump(mode='python'))
    conversation = service._owned(actor, conversation_id, db)
    require_active(db)
    service._expected(conversation, selection)
    if not conversation['draft_input'].strip() or items(conversation, db):
        raise ServiceError('NOT_SUPPORTED', 422)
    scope = service._snapshot(conversation)
    sources = []
    for identifier in selection.citation_ids:
        saved = read_saved_citation(actor, identifier, db)
        original = saved.scope
        if (any(getattr(original, key) != getattr(scope, key) for key in
                ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision'))
                or original.input_revision > scope.input_revision
                or original.materials_revision > scope.materials_revision):
            raise ServiceError('CROSS_MATTER_DENIED', 403)
        sources.append(project_source(saved))
    manifest = d.MainContextManifest(format_version='saved-library-context-v1',
        question=conversation['draft_input'], sources=tuple(sources))
    return build_preview(manifest, scope, conversation['composer_revision'], config)
