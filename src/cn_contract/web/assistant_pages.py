"""Authorized chat shell; conversation content is fetched through bounded APIs."""
from uuid import UUID

from fastapi import Request
from fastapi.responses import HTMLResponse

from ..assistant import service
from ..domain import Role
from ..security import ServiceError
from .request_context import actor_in


def home_url(app, actor, db):
    if getattr(app.state, 'recovery_copy', False):
        return '/recovery'
    if app.state.assistant_home_enabled and actor.roles & {Role.HANDLING_LAWYER, Role.REVIEWING_LAWYER}:
        try:
            service._workspace_id(db)
        except ServiceError:
            return '/workspace'
        return '/assistant'
    return '/workspace'


def register_routes(app, database):
    def page(request, identifier=None):
        with database.session() as db:
            actor = actor_in(request, db)
            if identifier is None:
                service._current(actor, db)
                service._workspace_id(db)
            else:
                service._owned(actor, identifier, db)
        return HTMLResponse(app.state.template_environment.get_template('assistant.html').render(
            conversation_id=str(identifier) if identifier is not None else '',
            readonly=getattr(app.state, 'recovery_copy', False),
            local_materials_enabled=getattr(database, '_local_materials_enabled', False),
            library_enabled=hasattr(app.state, 'library_root')))

    @app.get('/assistant', response_class=HTMLResponse)
    def home(request: Request):
        return page(request)

    @app.get('/assistant/{identifier}', response_class=HTMLResponse)
    def conversation(identifier: UUID, request: Request):
        return page(request, identifier)
