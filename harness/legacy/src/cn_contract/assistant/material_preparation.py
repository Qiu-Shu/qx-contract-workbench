"""Rebuild selected material bytes from authorized storage, without disclosure."""
from uuid import UUID
from sqlalchemy import text
from .. import domain as d
from ..security import ServiceError
from ..ops.storage import require_active
from . import service, attachment_records as records, attachment_files, business
from .material_codec import build_preview_basis
from .providers.policy import encoded, sha
from . import material_history
from ..integrations.skill_registry import resolve_for, contract_review_for, criminal_analysis_for, trademark_triage_for
from .case_evidence import select_method

CURRENT_CONTRACT_HISTORY_FORMAT = 'contract-full-text-v1'


def consultation_source(parent, question):
    scope = d.ScopeSnapshot.model_validate_json(parent['scope_snapshot'])
    ref = d.ProfileMessageRef(kind='message', conversation_id=scope.conversation_id,
        message_id=parent['message_id'], source_revision=scope.input_revision, start=0, end=len(question),
        quote=question, quote_sha256=sha(question))
    return d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref)


def require_parent_active(parent):
    if parent['cancel_requested'] or parent['state'] in ('cancelled', 'blocked'):
        raise ServiceError('VERSION_CONFLICT', 409)


def require_criminal_scope(db, result, files, criminal):
    if criminal is not None:
        return
    # Current policy follows accepted requests, including those denied before a model attempt.
    rows = db.execute(text('''SELECT r.* FROM assistant_runs r
        JOIN assistant_run_events e ON e.run_id=r.id AND e.event_type='business.accepted'
        WHERE r.conversation_id=:cid
        AND json_extract(e.payload_json,'$.workflow') IN ('case','court')'''),
        {'cid':str(result.scope.conversation_id)}).mappings()
    selected_ids = {item.attachment_id for item in files}
    for row in rows:
        accepted, previous = business._record(row, db)
        if criminal_analysis_for('case', accepted.request.content, ()) is None:
            continue
        if previous.task_id == result.task_id:
            raise ServiceError('CRIMINAL_SCOPE_REQUIRED', 409)
        raw = db.scalar(text('''SELECT items_json FROM assistant_material_snapshots
            WHERE conversation_id=:cid AND revision=:rev'''),
            {'cid':str(result.scope.conversation_id), 'rev':previous.scope.materials_revision})
        if raw is not None and selected_ids.intersection(item.attachment_id for item in records.decode_items(raw)):
            raise ServiceError('CRIMINAL_SCOPE_REQUIRED', 409)


def assemble(actor, selection, db, *, historical=False, case_method=None, contract_review=None,
        criminal_analysis=None, trademark_triage=None, enforce_policy=False, history_format=None):
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
    if (not historical or enforce_policy) and result.workflow == 'court' and any(business._command(
            s.reference.quote, ('刑事', '公诉', '检察官')) for s in sources if s.reference.kind == 'message'):
        raise ServiceError('CRIMINAL_HEARING_UNAVAILABLE', 409)
    if not historical and result.workflow == 'contract' and not any(s.reference.kind == 'document' for s in sources):
        raise ServiceError('MATERIAL_NOT_READABLE', 409)
    criminal = criminal_analysis if historical else criminal_analysis_for(result.workflow, record[0].request.content, sources)
    if criminal is not None and (not historical or enforce_policy):
        from .criminal_analysis import ANALYSIS_TOPICS, STRATEGY_TOPICS
        question = record[0].request.content
        if any(business._latest_command(question, words) is True
                and business._latest_command(question, words, current=True) is False
                for words in (ANALYSIS_TOPICS, STRATEGY_TOPICS)):
            raise ServiceError('MATERIAL_INSTRUCTION_CONFLICT', 409)
    try:
        trademark = trademark_triage if historical else trademark_triage_for(result.workflow, record[0].request.content)
        if not historical and trademark is None:
            from .trademark_triage import select_method as select_trademark_method
            # Live routing must not fall back when the frozen method cannot represent it.
            if select_trademark_method(result.workflow, record[0].request.content, reported_scope=True) is not None:
                raise ValueError('MATERIAL_INSTRUCTION_CONFLICT')
    except ValueError as error:
        if str(error) in ('IP_SCOPE_UNSUPPORTED', 'MATERIAL_INSTRUCTION_CONFLICT'):
            raise ServiceError(str(error), 409) from None
        raise
    if trademark is not None and criminal is not None:
        raise ServiceError('IP_SCOPE_UNSUPPORTED', 409)
    if trademark is not None and not any(s.reference.kind == 'document' for s in sources):
        raise ServiceError('MATERIAL_NOT_READABLE', 409)
    # File-only historical reads in runner do not select a protocol; current() checks the saved one.
    if not historical or enforce_policy:
        require_criminal_scope(db, result, files, criminal)
    if criminal is not None:
        # No criminal redaction approval exists yet; never infer it from text or a model.
        synthetic_hashes = getattr(db.info.get('database'), '_assistant_synthetic_hashes', ())
        if (not files or not any(s.reference.kind == 'document' for s in sources)
                or any(item.original_sha256 not in synthetic_hashes for item in files)
                or any(d.AssistantMaterialPolicy.model_validate_json(row['policy_json']).material_mode != 'synthetic' for row in rows)):
            raise ServiceError('DATA_POLICY_UNAPPROVED', 409)
    capability = resolve_for(db, result.workflow)
    registry = getattr(db.info.get('database'), '_capability_registry', None)
    knowledge = registry.retrieve(result.workflow, record[0].request.content + '\n' + '\n'.join(
        item.reference.anchor.quote for item in sources if isinstance(item.reference, d.ProfileDocumentRef))[:4000]) if registry else None
    hearing = None
    if capability is not None and capability.kind == 'local_adapter':
        from ..integrations.hearing_context import build
        synthetic_hashes = getattr(db.info.get('database'), '_assistant_synthetic_hashes', ())
        hearing = build(db, result, files, capability,
            synthetic=bool(files) and all(item.original_sha256 in synthetic_hashes for item in files))
    if not historical:
        history_format = CURRENT_CONTRACT_HISTORY_FORMAT if result.workflow == 'contract' else None
    contract = contract_review if historical else contract_review_for(result.workflow, files, sources)
    if contract is not None and contract.method_id == 'contract-review-v3':
        from .material_stance import contract_stance_sources
        sources.extend(contract_stance_sources(db, result, record[0].request.content))
    manifest = d.MainMaterialManifest(workflow=result.workflow, stable_task_id=result.task_id,
        parent_business_run_id=result.run_id, question=record[0].request.content,
        capability=capability, hearing=hearing, knowledge=knowledge,
        case_method=case_method if historical else (None if criminal or trademark else select_method(result.workflow, record[0].request.content)),
        criminal_analysis=criminal,
        trademark_triage=trademark,
        contract_review=contract,
        history_format=history_format,
        materials=tuple(files), sources=tuple(sources), conversation_history=material_history.select_history(
            db, result.scope, result.task_id, before_at=result.created_at, attachment_rows=rows,
            budget=material_history.history_budget(context, history_format), history_format=history_format,
            require_latest=result.workflow == 'contract' and not historical))
    if hearing is not None:
        from ..integrations.chiheng import material_texts
        try:
            material_texts(manifest)
        except ValueError:
            raise ServiceError('HEARING_MATERIAL_LIMIT', 409) from None
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
    return build_preview_basis(selection, manifest, config)


def selection_for(basis):
    return d.MainMaterialSelection.model_validate(basis.model_dump(include=set(d.MainMaterialSelection.model_fields)))
