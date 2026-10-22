"""Authenticated local profile commands and immutable history; no model dispatch."""
import re
from uuid import UUID

from fastapi import Path, Request
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..assistant import profile_store, service
from ..ops.storage import require_active
from ..security import ServiceError
from .request_context import actor_in, body_input

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH = re.compile(rf'/api/assistant/conversations/{_UUID}/profile(?:/revisions/[1-9][0-9]*|/receipts/{_UUID})?')


def is_profile_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def register_routes(app, database):
    base = '/api/assistant/conversations/{cid}/profile'

    def authorize(request, cid, *, write=False):
        with database.session() as db:
            actor = actor_in(request, db, write=write)
            service._owned(actor, cid, db)
            if write:
                require_active(db)
        return actor

    @app.get(base)
    def current(cid:UUID, request:Request):
        return profile_store.read_profile(authorize(request, cid), cid, database=database)

    @app.get(base+'/revisions/{revision}')
    def historical(cid:UUID, request:Request, revision:int=Path(ge=1,le=2**63-1)):
        return profile_store.read_profile(authorize(request, cid), cid, database=database, revision=revision)

    @app.get(base+'/receipts/{request_id}')
    def receipt(cid:UUID, request_id:UUID, request:Request):
        return profile_store.find_receipt(authorize(request, cid), cid, request_id, database=database)

    @app.post(base+'/commits')
    async def commit(cid:UUID, request:Request):
        authorize(request, cid, write=True)
        value = await body_input(request, d.ProfileCommitInput)
        actor = authorize(request, cid, write=True)
        if value.patch.scope.conversation_id != cid:
            raise ServiceError('VERSION_CONFLICT', 409)
        return await run_in_threadpool(profile_store.save_profile, actor, value, database=database)
