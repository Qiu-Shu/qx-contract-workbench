"""Material previews are read-only; native consent alone authorizes submission."""
from uuid import UUID
from fastapi import Request
from .. import domain as d
from ..assistant import service, material_preparation
from ..security import ServiceError
from ..ops.storage import require_active
from .request_context import actor_in, body_input


def register_routes(app, database, runtime, tasks):
    base = '/api/assistant/conversations/{identifier}'

    def actor_for(request, identifier):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            service._owned(actor, identifier, db)
            require_active(db)
            return actor

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
