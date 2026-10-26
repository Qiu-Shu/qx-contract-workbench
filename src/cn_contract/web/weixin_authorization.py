"""Authenticated desktop projections and explicit local authorization records."""
import re
from uuid import UUID

from fastapi import Request
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..security import ServiceError
from ..weixin_inbox import conversation, pending
from .request_context import actor_in, body_input, same_origin, unique

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH = re.compile(rf'/api/assistant/conversations/{_UUID}/weixin-authorization(?:/(?:refreshes|generations)/by-request/{_UUID}|/generations/head|/dispatches/by-descriptor/{_UUID})?')


def is_weixin_authorization_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def register_routes(app, database):
    base = '/api/assistant/conversations/{cid}/weixin-authorization'

    def authorize(request, cid, *, write=False, generation=False):
        with database.session() as db:
            actor = actor_in(request, db, write=write)
            if write:
                context = conversation._generation_context if generation else conversation._refresh_context
                context(actor, cid, db)
            else:
                same_origin(request)
                conversation._context(actor, cid, db)
        return actor

    @app.get(base)
    def current(cid:UUID, request:Request):
        return conversation.read_authorization(authorize(request, cid), cid, database=database)

    @app.get(base+'/pending')
    def list_pending(cid:UUID, request:Request):
        actor = authorize(request, cid)
        try:
            values = unique(request.query_params.multi_items())
            if 'limit' in values:
                if re.fullmatch(r'(?:[1-9]|1[0-9]|20)', values['limit']) is None:
                    raise ValueError('invalid page limit')
                values['limit'] = int(values['limit'])
            query = d.WeixinPendingQuery.model_validate(values)
        except ValueError:
            raise ServiceError('STATE_CONFLICT', 422) from None
        return pending.list_pending_descriptors(actor, cid, query, database=database)

    @app.post(base+'/refresh')
    async def refresh(cid:UUID, request:Request):
        authorize(request, cid, write=True)
        value = await body_input(request, d.WeixinPeerRefreshInput)
        actor = authorize(request, cid, write=True)
        return await run_in_threadpool(conversation.refresh_authorization, actor, cid, value, database=database)

    @app.get(base+'/refreshes/by-request/{request_id}')
    def find(cid:UUID, request_id:UUID, request:Request):
        return conversation.find_refresh(authorize(request, cid), cid, request_id, database=database)

    @app.post(base+'/generations')
    async def append_generation(cid:UUID, request:Request):
        authorize(request, cid, write=True, generation=True)
        value = await body_input(request, d.WeixinPeerGenerationInput)
        actor = authorize(request, cid, write=True, generation=True)
        return await run_in_threadpool(conversation.append_generation, actor, cid, value, database=database)

    @app.get(base+'/generations/by-request/{request_id}')
    def find_generation(cid:UUID, request_id:UUID, request:Request):
        return conversation.find_generation(authorize(request, cid), cid, request_id, database=database)

    @app.get(base+'/generations/head')
    def generation_head(cid:UUID, request:Request):
        return conversation.read_generation_head(authorize(request, cid), cid, database=database)

    @app.post(base+'/dispatches')
    async def dispatch_descriptor(cid:UUID, request:Request):
        authorize(request, cid, write=True, generation=True)
        value = await body_input(request, d.WeixinGenerationDispatchInput)
        actor = authorize(request, cid, write=True, generation=True)
        return await run_in_threadpool(conversation.dispatch_descriptor, actor, cid, value, database=database)

    @app.get(base+'/dispatches/by-descriptor/{descriptor_id}')
    def find_dispatch(cid:UUID, descriptor_id:UUID, request:Request):
        return conversation.find_dispatch(authorize(request, cid), cid, descriptor_id, database=database)
