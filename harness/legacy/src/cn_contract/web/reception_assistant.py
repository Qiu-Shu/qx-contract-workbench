"""Explicit reception helper, reusing current owner, session, CSRF and revisions."""
from uuid import UUID

from fastapi import Query, Request

from .. import domain as d
from ..intake import service as intakes
from ..reception import assistant
from ..reception.knowledge import KnowledgeStore
from .request_context import actor_in, body_input


def attach_reception(app, database, knowledge_root):
    knowledge = KnowledgeStore(knowledge_root)
    app.state.reception_knowledge = knowledge

    def lawyer(request):
        with database.session() as db:
            intakes._lawyer(actor_in(request, db), db)

    @app.get('/api/reception/knowledge')
    def catalog(request: Request):
        lawyer(request)
        return knowledge.catalog()

    @app.get('/api/reception/knowledge/search')
    def search(request: Request, q: str = Query(min_length=1, max_length=200)):
        lawyer(request)
        return knowledge.search(q)

    @app.get('/api/reception/knowledge/sources/{identifier}')
    def source(identifier: str, request: Request, start: int = Query(default=0, ge=0, le=100000)):
        lawyer(request)
        return knowledge.page(identifier, start)

    async def write(request, identifier, model, operation):
        with database.session() as db:
            intakes._owned(identifier, actor_in(request, db, write=True), db)
        value = await body_input(request, model)
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            return operation(identifier, value, actor, db, knowledge)

    @app.post('/api/intakes/{identifier}/assistant/preview')
    async def preview(identifier: UUID, request: Request):
        return await write(request, identifier, d.ReceptionAssistantInput, assistant.preview)

    @app.post('/api/intakes/{identifier}/assistant/conversation', status_code=201)
    async def conversation(identifier: UUID, request: Request):
        return await write(request, identifier, d.ReceptionConversationInput, assistant.conversation)
