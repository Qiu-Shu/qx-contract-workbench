"""Bounded synthetic-only bridge; business result and task mapping commit together.

No worker, network, model authorization or outbound delivery is started here.
The existing Mock review remains behind the existing human fact confirmation.
"""
from io import BytesIO
from uuid import UUID

from sqlalchemy import select

from .. import domain as d
from ..assistant.service import _digest
from ..documents.ingest import ingest
from ..ops.storage import require_active
from ..persistence import DocumentRow, read_matter, read_version, get_fact_snapshot, get_parse_result
from ..review.storage import read_run, _row as review_row
from ..security import ServiceError, authorize
from ..web import services
from . import service
from .mock_policy import sources as _sources


def _case(execution, matter_id, actor, db):
    authorize(actor, matter_id, 'upload', db)
    matter = read_matter(matter_id, actor, db)
    if matter.status == 'archived' or not matter.client_ref.startswith('SYNTHETIC-'):
        raise ServiceError('STATE_CONFLICT', 409)
    scope = execution.manifest.scope
    if scope.scope_kind == 'matter' and scope.scope_ref != matter_id:
        raise ServiceError('CROSS_MATTER_DENIED', 403)
    return matter


def _check_versions(execution, actor, db):
    if execution.matter_id is None or not execution.document_versions:
        raise ServiceError('STATE_CONFLICT', 409)
    _case(execution, execution.matter_id, actor, db)
    sources = _sources(execution, actor, db)
    if set(sources) != set(execution.source_versions):
        raise ServiceError('VERSION_CONFLICT', 409)
    current = {version.id: version.sha256 for version in
        services.current_versions(execution.matter_id, actor, db)}
    if current != dict(execution.document_versions):
        raise ServiceError('VERSION_CONFLICT', 409)
    for source_id, version_id in execution.source_versions.items():
        version = read_version(execution.matter_id, version_id, actor, db)
        if version.sha256 != sources[source_id][0]['sha256']:
            raise ServiceError('VERSION_CONFLICT', 409)


def prepare_execution(actor, execution_id, value, *, db):
    value = d.TaskExecutionPrepareInput.model_validate_json(value.model_dump_json())
    execution = service.read_execution(actor, execution_id, db)
    require_active(db)
    _case(execution, value.matter_id, actor, db)
    sources = _sources(execution, actor, db)
    if execution.matter_id is not None:
        if execution.matter_id != value.matter_id:
            raise ServiceError('VERSION_CONFLICT', 409)
        _check_versions(execution, actor, db)
        return execution
    if execution.state != 'prepared':
        raise ServiceError('STATE_CONFLICT', 409)
    if db.scalar(select(DocumentRow.id).where(DocumentRow.matter_id == str(value.matter_id)).limit(1)):
        raise ServiceError('STATE_CONFLICT', 409)
    # SAVEPOINT owns all newly created original files; rollback removes only these.
    with db.begin_nested():
        service.advance_execution(actor, execution.id, 'creating_matter', db, expected_state='prepared')
        versions, links = {}, {}
        order = sorted(sources, key=lambda key: (key != execution.manifest.main_attachment_id, str(key)))
        for source_id in order:
            row, parsed, raw = sources[source_id]
            version = ingest(BytesIO(raw), d.UploadMeta(matter_id=value.matter_id,
                original_name=row['original_name'], mime=row['mime'], baseline_view=parsed.baseline_view,
                supersedes_id=None), actor, db=db)
            services.candidate_parse(value.matter_id, version.id, actor, db, synthetic_task=True)
            versions[version.id] = version.sha256
            links[source_id] = version.id
        return service.advance_execution(actor, execution.id, 'awaiting_facts', db,
            expected_state='creating_matter', matter_id=value.matter_id,
            document_versions=versions, source_versions=links, prepare_request_id=value.request_id)


def create_and_prepare(actor, execution_id, value, *, db):
    value = d.TaskExecutionCreateInput.model_validate_json(value.model_dump_json())
    execution = service.read_execution(actor, execution_id, db)
    require_active(db)
    if value.matter.material_mode != 'synthetic' or value.matter.reviewer_username:
        raise ServiceError('STATE_CONFLICT', 409)
    if execution.matter_id:
        matter = _case(execution, execution.matter_id, actor, db)
        if (execution.prepare_request_id != value.request_id or any(
                getattr(matter, key) != getattr(value.matter, key)
                for key in ('title', 'contract_type', 'review_mode', 'position', 'objectives'))):
            raise ServiceError('VERSION_CONFLICT', 409)
        _check_versions(execution, actor, db)
        return execution
    if execution.state != 'prepared':
        raise ServiceError('STATE_CONFLICT', 409)
    _sources(execution, actor, db)
    with db.begin_nested():
        matter = services.create_matter(value.matter, actor, db)
        return prepare_execution(actor, execution_id,
            d.TaskExecutionPrepareInput(request_id=value.request_id, matter_id=matter.id), db=db)


def read_context(actor, execution_id, *, db):
    execution = service.read_execution(actor, execution_id, db)
    if execution.matter_id is None:
        return d.TaskExecutionContext(execution=execution)
    matter = read_matter(execution.matter_id, actor, db)
    facts = get_fact_snapshot(matter.id, matter.active_fact_version, actor, db) if matter.active_fact_version else None
    parses = tuple(parsed for version_id in execution.document_versions
                   if (parsed := get_parse_result(matter.id, version_id, actor, db)) is not None)
    review = read_run(matter.id, execution.review_run_id, actor, db=db, current=False) if execution.review_run_id else None
    if review:
        saved = d.ReviewContext.model_validate_json(review_row(matter.id, review.id, actor, db).context_json)
        facts = saved.fact_snapshot
        if facts.sha256 != review.manifest.fact_snapshot_sha256:
            raise ServiceError('VERSION_CONFLICT', 409)
    elif execution.state == 'awaiting_facts':
        _check_versions(execution, actor, db)
    return d.TaskExecutionContext(execution=execution, facts=facts, parses=parses, review=review)


def review_execution(actor, execution_id, value, *, db):
    value = d.TaskExecutionReviewInput.model_validate_json(value.model_dump_json())
    execution = service.read_execution(actor, execution_id, db)
    require_active(db)
    _check_versions(execution, actor, db)
    authorize(actor, execution.matter_id, 'review', db)
    digest = _digest(value.review.model_dump(mode='json'))
    if execution.review_run_id is not None:
        if execution.review_input_sha256 != digest:
            raise ServiceError('VERSION_CONFLICT', 409)
        read_run(execution.matter_id, execution.review_run_id, actor, db=db, current=True)
        return execution
    if execution.state != 'awaiting_facts':
        raise ServiceError('STATE_CONFLICT', 409)
    if dict(value.review.document_hashes) != dict(execution.document_versions):
        raise ServiceError('VERSION_CONFLICT', 409)
    services.verify_review_input(execution.matter_id, value.review, actor, db)
    with db.begin_nested():
        service.advance_execution(actor, execution.id, 'running', db, expected_state='awaiting_facts')
        run_id = UUID(services.review(execution.matter_id, value.review, actor, db, synthetic_task=True,
            task_execution_id=execution.id))
        run = read_run(execution.matter_id, run_id, actor, db=db, current=True)
        return service.advance_execution(actor, execution.id,
            'completed' if run.status == 'completed' else 'failed', db, expected_state='running',
            review_run_id=run_id, review_request_id=value.request_id,
            review_input_sha256=digest, error=run.error_code)
