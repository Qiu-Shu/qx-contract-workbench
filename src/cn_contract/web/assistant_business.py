"""Authenticated local business transport; a read never executes work."""
from uuid import UUID
import re
from fastapi import Request

from .. import domain as d
from ..assistant import business, service
from ..ops.storage import require_active
from .request_context import actor_in, body_input


def is_business_read_path(path):
    identifier = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    return re.fullmatch(rf'/api/assistant/conversations/{identifier}/business(?:/by-request/{identifier})?', path) is not None


def register_routes(app, database):
    base = '/api/assistant/conversations/{cid}/business'

    @app.post(base)
    async def submit(cid: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            service._owned(actor, cid, db)
            require_active(db)
        value = await body_input(request, d.BusinessInput)
        with database.session() as db:
            return business.submit(actor_in(request, db, write=True), cid, value, db)

    @app.get(base)
    def history(cid: UUID, request: Request):
        with database.session() as db:
            return business.history(actor_in(request, db), cid, db)

    @app.get(base + '/by-request/{request_id}')
    def find(cid: UUID, request_id: UUID, request: Request):
        with database.session() as db:
            found = business.find(actor_in(request, db), cid, request_id, db)
            return found[1] if found else None
