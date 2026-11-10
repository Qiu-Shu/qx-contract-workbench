"""Explicit local research submission and offline historical snapshot reads."""
import re
from uuid import UUID

from fastapi import Request
from pydantic import ValidationError

from .. import domain as d
from ..assistant import research, service
from ..assistant.library_handlers import read_saved_citation
from ..ops.storage import require_active
from ..security import ServiceError
from .request_context import actor_in, body_input

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH = re.compile(rf'/api/assistant/(?:library-citations/{_UUID}|conversations/{_UUID}/'
    rf'(?:research-history|researches/by-request/{_UUID}))')


def is_research_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def register_routes(app, database, tasks):
    base = '/api/assistant/conversations/{identifier}'

    @app.post(base+'/researches', status_code=202)
    async def submit(identifier: UUID, request: Request):
        def authorize():
            with database.session() as db:
                actor = actor_in(request, db, write=True)
                service._owned(actor, identifier, db)
                require_active(db)
                return actor
        authorize()
        value = await body_input(request, d.AssistantMessageInput)
        actor = authorize()
        return tasks.submit_research(actor, identifier, value)

    @app.get(base+'/researches/by-request/{request_id}')
    def find(identifier: UUID, request_id: UUID, request: Request):
        with database.session() as db:
            return research.find_research(actor_in(request, db), identifier, request_id, db)

    @app.get(base+'/research-history')
    def history(identifier: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db)
            conversation = service._owned(actor, identifier, db)
            if any(key != 'message_id' for key in request.query_params):
                raise ServiceError('STATE_CONFLICT', 422)
            try:
                query = d.MainGenerationHistoryQuery(message_ids=request.query_params.getlist('message_id'))
            except ValidationError:
                raise ServiceError('STATE_CONFLICT', 422) from None
            return research.read_history(actor, conversation, query, db)

    @app.get('/api/assistant/library-citations/{identifier}')
    def citation(identifier: UUID, request: Request):
        with database.session() as db:
            return read_saved_citation(actor_in(request, db), identifier, db)
