"""Local context previews; this endpoint cannot grant or dispatch work."""
from uuid import UUID

from fastapi import Request

from .. import domain as d
from ..assistant import service
from ..assistant.context_preview import preview_context
from ..assistant.providers.policy import MainModelRuntime, validated
from ..assistant.providers.registry import MainModelRegistry
from ..ops.storage import require_active
from ..security import ServiceError
from .request_context import actor_in, body_input


def register_routes(app, database, runtime):
    @app.post('/api/assistant/conversations/{identifier}/context-preview')
    async def preview(identifier: UUID, request: Request):
        def authorize(db):
            actor = actor_in(request, db, write=True)
            service._owned(actor, identifier, db)
            require_active(db)
            return actor
        with database.session() as db:
            authorize(db)
        value = await body_input(request, d.MainContextSelection)
        with database.session() as db:
            actor = authorize(db)
            try:
                config = None
                if isinstance(runtime, MainModelRegistry):
                    config = runtime.configuration()
                elif isinstance(runtime, MainModelRuntime):
                    config = validated(d.MainModelConfig, runtime.provider.config.model_dump(mode='python'))
                return preview_context(actor, identifier, value, db, config=config)
            except (ValueError, TypeError, AttributeError):
                raise ServiceError('STATE_CONFLICT', 422) from None
