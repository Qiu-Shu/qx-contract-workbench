"""Historical material inputs verify originals, parser records and task linkage."""
from sqlalchemy import text
from .. import domain as d
from . import attachment_records as records, business, material_codec as codec, service
from .providers.policy import sha, encoded
from .material_preparation import consultation_source


def validate_input(db, row, prepared, config, policy, run, *, history_queue=None):
    basis, manifest = prepared.request.basis, prepared.request.basis.manifest
    if (row['round_no'] != 1 or policy.max_calls != 1 or run['request_id'] != str(basis.request_id)
            or run['requested_skill'] is not None or manifest.parent_business_run_id != basis.parent_business_run_id
            or codec.prepare(prepared.request, config) != prepared or sha(prepared.wire_payload_json) != row['request_sha256']):
        raise ValueError('MATERIAL_INPUT_INVALID')
    parent = db.execute(text('SELECT * FROM assistant_runs WHERE id=:id'), {'id':str(basis.parent_business_run_id)}).mappings().one()
    record = business._record(parent, db)
    if (record is None or parent['conversation_id'] != row['conversation_id']
            or record[1].task_id != manifest.stable_task_id or record[1].workflow != manifest.workflow
            or record[0].request.content != manifest.question or record[1].scope.materials_revision != basis.expected_scope.materials_revision
            or record[1].scope.input_revision > basis.expected_scope.input_revision
            or any(getattr(record[1].scope, key) != getattr(basis.expected_scope, key) for key in
                ('workspace_id', 'conversation_id', 'scope_kind', 'scope_ref', 'binding_revision'))):
        raise ValueError('MATERIAL_INPUT_INVALID')
    raw = db.scalar(text('SELECT items_json FROM assistant_material_snapshots WHERE conversation_id=:cid AND revision=:rev'),
        {'cid':row['conversation_id'], 'rev':basis.expected_scope.materials_revision})
    selected = () if basis.expected_scope.materials_revision == 0 else records.decode_items(raw)
    if tuple((item.attachment_id, item.parse_revision) for item in selected) != tuple(
            (item.attachment_id, item.parse_revision) for item in manifest.materials):
        raise ValueError('MATERIAL_INPUT_INVALID')
    expected_sources = [consultation_source(parent, record[0].request.content)]
    for material in manifest.materials:
        attachment = db.execute(text('SELECT * FROM assistant_attachments WHERE id=:id'), {'id':str(material.attachment_id)}).mappings().one()
        parsed = records.parse_view(records.parse_row(row['conversation_id'], material.attachment_id, material.parse_revision, db))
        if (attachment['conversation_id'] != row['conversation_id'] or attachment['sha256'] != material.original_sha256
                or attachment['original_name'] != material.name or parsed.result_sha256 != material.result_sha256
                or parsed.reading_status != material.reading_status or parsed.result is None
                or parsed.result.pages != material.pages or parsed.result.parts != material.parts
                or parsed.result.unsupported_parts != material.unread_parts or parsed.result.quality_issues != material.quality_issues):
            raise ValueError('MATERIAL_INPUT_INVALID')
        for anchor in parsed.result.anchors:
            if anchor.quote:
                ref = d.ProfileDocumentRef(kind='document', conversation_id=row['conversation_id'], attachment_id=material.attachment_id,
                    original_sha256=material.original_sha256, parse_revision=material.parse_revision,
                    result_sha256=material.result_sha256, anchor=anchor)
                expected_sources.append(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref))
    context = tuple(source for source in manifest.sources if isinstance(source.reference, d.ProfileMessageRef)
                    and source.reference.message_id != record[1].message_id)
    if context:
        from .material_history import statement_sources
        if context != statement_sources(db, record[1], selected):
            raise ValueError('MATERIAL_INPUT_INVALID')
        expected_sources.extend(context)
    if tuple(expected_sources) != manifest.sources or codec.rebuild_basis(basis, config) != basis:
        raise ValueError('MATERIAL_INPUT_INVALID')
    if manifest.conversation_history:
        from .material_history import select_history, history_budget
        history = select_history(db, record[1].scope, manifest.stable_task_id,
            before_at=record[1].created_at, validation_queue=history_queue, budget=history_budget(context))
        if history != manifest.conversation_history:
            raise ValueError('MATERIAL_INPUT_INVALID')
    from .material_attempts import message
    if run['request_sha256'] != service._digest({'actor_id':run['actor_id'], 'workspace_id':str(basis.expected_scope.workspace_id),
            'conversation_id':row['conversation_id'], 'request':message(basis).model_dump(mode='json')}):
        raise ValueError('MATERIAL_INPUT_INVALID')


def validate_output(view, prepared):
    if view.manifest != prepared.request.basis.manifest:
        raise ValueError('MATERIAL_OUTPUT_INVALID')
    codec.validate_candidate(view.candidate, view.manifest.sources)
