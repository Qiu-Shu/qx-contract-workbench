"""Material previews are read-only; native consent alone authorizes submission."""
from datetime import datetime
import re
from uuid import UUID
from fastapi import Request
from fastapi.responses import Response
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from .. import domain as d
from ..assistant import service, material_preparation, material_integrity, outputs
from ..assistant.model_integrity import validate_model_records
from ..assistant.providers import attempts
from ..exports.material_docx import build
from ..security import ServiceError
from ..ops.storage import require_active
from .request_context import actor_in, body_input


_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_DOCUMENT_PATH = re.compile(rf'/api/assistant/conversations/{_UUID}/material-generations/{_UUID}/document')


def is_material_generation_read_path(path):
    return _DOCUMENT_PATH.fullmatch(path) is not None


def _document_output(request, identifier, attempt_id, database):
    with database.session() as db:
        actor = actor_in(request, db)
        current = service._snapshot(service._owned(actor, identifier, db))
        try:
            attempt = attempts.read_attempt(actor, attempt_id, db)
            if attempt.scope.conversation_id != identifier:
                raise ServiceError('CROSS_MATTER_DENIED', 403)
            validate_model_records(db)
            output = attempt.output
            if (not isinstance(attempt, d.MainMaterialAttemptView)
                    or attempt.input_format != 'material-business-v1' or attempt.state != 'received'
                    or output is None or output.audience != 'internal' or output.review_status != 'unverified'
                    or attempt.receipt is None or attempt.receipt.state != 'received'
                    or attempt.receipt.error_code is not None):
                raise ValueError('material result unavailable')
            stored = db.execute(text('SELECT * FROM assistant_model_outputs WHERE attempt_id=:id'),
                {'id':str(attempt_id)}).mappings().one()
            if (str(output.id) != stored['id'] or output.run_id != attempt.run_id
                    or str(output.run_id) != stored['run_id'] or stored['conversation_id'] != str(identifier)
                    or output.scope != attempt.scope or output.scope != d.ScopeSnapshot.model_validate_json(stored['scope_json'])
                    or output.created_at != datetime.fromisoformat(stored['created_at'])):
                raise ValueError('material result identity')
            run = db.execute(text('SELECT state,conversation_id FROM assistant_runs WHERE id=:id'),
                {'id':str(attempt.run_id)}).mappings().one()
            if run['state'] != 'completed' or run['conversation_id'] != str(identifier):
                raise ValueError('material run incomplete')
            prepared = attempts._input(attempts._row(attempt_id, db))
            material_integrity.validate_output(output, prepared)
            outputs._binding(output.scope, current)
            return output
        except ValueError:
            raise ServiceError('VERSION_CONFLICT', 409) from None


def register_routes(app, database, runtime, tasks):
    base = '/api/assistant/conversations/{identifier}'

    def actor_for(request, identifier):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            service._owned(actor, identifier, db)
            require_active(db)
            return actor

    @app.get(base + '/material-generations/{attempt_id}/document')
    async def document(identifier: UUID, attempt_id: UUID, request: Request):
        output = _document_output(request, identifier, attempt_id, database)
        try:
            content = await run_in_threadpool(build, output)
        except ValueError:
            raise ServiceError('NOT_SUPPORTED', 422) from None
        if _document_output(request, identifier, attempt_id, database) != output:
            raise ServiceError('VERSION_CONFLICT', 409)
        return Response(content, media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
                'Content-Disposition':'attachment; filename="material-draft.docx"'})

    @app.post(base + '/material-preview')
    async def preview(identifier: UUID, request: Request):
        actor_for(request, identifier)
        value = await body_input(request, d.MainMaterialSelection)
        actor = actor_for(request, identifier)
        if value.expected_scope.conversation_id != identifier:
            raise ServiceError('VERSION_CONFLICT', 409)
        try:
            config = runtime.configuration() if runtime else None
            if config is None or not config.enabled:
                raise ServiceError('BLOCKED_LIVE', 403)
            return material_preparation.preview(actor, value, database, config)
        except ValueError:
            raise ServiceError('MATERIAL_INPUT_TOO_LARGE', 422) from None

    @app.post(base + '/material-generations', status_code=202)
    async def generate(identifier: UUID, request: Request):
        actor_for(request, identifier)
        value = await body_input(request, d.MainMaterialSelection)
        actor = actor_for(request, identifier)
        if value.expected_scope.conversation_id != identifier:
            raise ServiceError('VERSION_CONFLICT', 409)
        try:
            return tasks.submit_material(actor, identifier, value)
        except ValueError:
            raise ServiceError('MATERIAL_INPUT_TOO_LARGE', 422) from None
