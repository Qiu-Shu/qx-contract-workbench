"""Rebuild selected material bytes from authorized storage, without disclosure."""
from uuid import UUID
from sqlalchemy import text
from .. import domain as d
from ..security import ServiceError
from ..ops.storage import require_active
from . import service, attachment_records as records, attachment_files, business
from .material_codec import build_basis
from .providers.policy import encoded, sha
from . import material_history


def consultation_source(parent, question):
    scope = d.ScopeSnapshot.model_validate_json(parent['scope_snapshot'])
    ref = d.ProfileMessageRef(kind='message', conversation_id=scope.conversation_id,
        message_id=parent['message_id'], source_revision=scope.input_revision, start=0, end=len(question),
        quote=question, quote_sha256=sha(question))
    return d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref)


def require_parent_active(parent):
    if parent['cancel_requested'] or parent['state'] in ('cancelled', 'blocked'):
        raise ServiceError('VERSION_CONFLICT', 409)


def assemble(actor, selection, db, *, historical=False):
    cid = selection.expected_scope.conversation_id
    conversation = service._owned(actor, cid, db)
    if not historical:
        require_active(db)
        service._expected(conversation, selection)
    parent = service._owned_run(actor, selection.parent_business_run_id, db)
    if not historical:
        require_parent_active(parent)
    record = business._record(parent, db)
    if record is None:
        raise ServiceError('VERSION_CONFLICT', 409)
    result = record[1]
    if (parent['conversation_id'] != str(cid) or result.task_id is None or result.workflow is None
            or any(getattr(result.scope, key) != getattr(selection.expected_scope, key) for key in
                ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision'))
            or result.scope.input_revision > selection.expected_scope.input_revision
            or result.scope.materials_revision != selection.expected_scope.materials_revision):
        raise ServiceError('VERSION_CONFLICT', 409)
    if historical:
        raw = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
            {'cid':str(cid), 'rev':selection.expected_scope.materials_revision})
        items = records.decode_items(raw) if raw is not None else ()
    else:
        items = records.items(conversation, db)
    files, sources, rows = [], [consultation_source(parent, record[0].request.content)], []
    for item in items:
        row = records.owned_attachment(actor, cid, item.attachment_id, db)
        if item.parse_revision is None:
            raise ServiceError('MATERIAL_NOT_READABLE', 409)
        parsed = records.parse_view(records.parse_row(cid, item.attachment_id, item.parse_revision, db))
        if parsed.result is None:
            raise ServiceError('MATERIAL_NOT_READABLE', 409)
        result_data = parsed.result
        files.append(d.MainMaterialFile(attachment_id=item.attachment_id, name=row['original_name'],
            original_sha256=row['sha256'], parse_revision=item.parse_revision, result_sha256=parsed.result_sha256,
            reading_status=parsed.reading_status, pages=result_data.pages, parts=result_data.parts,
            unread_parts=result_data.unsupported_parts, quality_issues=result_data.quality_issues))
        rows.append(dict(row))
        for anchor in result_data.anchors:
            if not anchor.quote:
                continue
            ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=item.attachment_id,
                original_sha256=row['sha256'], parse_revision=item.parse_revision,
                result_sha256=parsed.result_sha256, anchor=anchor)
            sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref))
    # Bounds reject the complete selection; no implicit prefix truncation.
    context = material_history.statement_sources(db, result, items)
    sources.extend(context)
    manifest = d.MainMaterialManifest(workflow=result.workflow, stable_task_id=result.task_id,
        parent_business_run_id=result.run_id, question=record[0].request.content,
        materials=tuple(files), sources=tuple(sources), conversation_history=material_history.select_history(
            db, result.scope, result.task_id, before_at=result.created_at, attachment_rows=rows,
            budget=material_history.history_budget(context)))
    return manifest, rows


def preview(actor, selection, database, config):
    with database.session() as db:
        manifest, rows = assemble(actor, selection, db)
    for row in rows:
        attachment_files.read_checked(row, database)
    with database.session() as db:
        current, current_rows = assemble(actor, selection, db)
        if current != manifest or rows != current_rows:
            raise ServiceError('VERSION_CONFLICT', 409)
    return build_basis(selection, manifest, config)


def selection_for(basis):
    return d.MainMaterialSelection.model_validate(basis.model_dump(include=set(d.MainMaterialSelection.model_fields)))
