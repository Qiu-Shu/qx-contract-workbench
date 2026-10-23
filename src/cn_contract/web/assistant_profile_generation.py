"""Explicit profile preview and generation; only native control can grant consent."""
from uuid import UUID

from fastapi import Request

from .. import domain as d
from ..assistant import service
from ..assistant.profile_preparation_service import build_profile_basis
from ..assistant.providers.policy import MainModelRuntime, validated
from ..assistant.providers.registry import MainModelRegistry
from ..ops.storage import require_active
from ..security import ServiceError
from .request_context import actor_in, body_input


def register_routes(app, database, runtime, tasks):
    base = '/api/assistant/conversations/{identifier}'

    def authorize(request, identifier, db):
        actor = actor_in(request, db, write=True)
        conversation = service._owned(actor, identifier, db)
        require_active(db)
        return actor, conversation

    @app.post(base+'/profile-preview')
    async def preview(identifier: UUID, request: Request):
        with database.session() as db:
            authorize(request, identifier, db)
        value = await body_input(request, d.MainProfileSelection)
        with database.session() as db:
            actor, conversation = authorize(request, identifier, db)
            try:
                config = None
                if isinstance(runtime, MainModelRegistry):
                    config = runtime.configuration()
                elif isinstance(runtime, MainModelRuntime):
                    config = validated(d.MainModelConfig, runtime.provider.config.model_dump(mode='python'))
                if config is None or not config.enabled:
                    raise ServiceError('BLOCKED_LIVE', 403)
                message = d.AssistantMessageInput(request_id=value.request_id,
                    expected_scope=value.expected_scope,
                    expected_composer_revision=value.expected_composer_revision,
                    content=conversation['draft_input'])
                return build_profile_basis(actor, identifier, message, db, config=config,
                                           project_intake=value.project_intake)
            except (ValueError, TypeError, AttributeError):
                raise ServiceError('STATE_CONFLICT', 422) from None

    @app.post(base+'/profile-generations', status_code=202)
    async def generate(identifier: UUID, request: Request):
        with database.session() as db:
            authorize(request, identifier, db)
        value = await body_input(request, d.MainProfileSubmission)
        with database.session() as db:
            actor, _ = authorize(request, identifier, db)
        try:
            return tasks.submit_profile(actor, identifier, value)
        except ValueError:
            raise ServiceError('STATE_CONFLICT', 422) from None
