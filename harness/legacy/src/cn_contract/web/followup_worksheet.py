"""Authenticated follow-up tracking and exact read-only recovery routes."""
import re
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..assistant import followup_worksheet as service
from ..security import ServiceError
from .request_context import actor_in, body_input

_UUID=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ=re.compile(rf'/api/assistant/conversations/{_UUID}/followups(?:/revisions/[1-9][0-9]*|/receipts/{_UUID})?')


def is_followup_read_path(path):return _READ.fullmatch(path) is not None


def register_routes(app,database):
    base='/api/assistant/conversations/{cid}/followups'
    def response(value):return JSONResponse(value.model_dump(mode='json') if value is not None else None,headers={'Cache-Control':'no-store'})

    @app.get(base)
    def read(cid:UUID,request:Request):
        with database.session() as db:return response(service.read(actor_in(request,db),cid,db))

    @app.get(base+'/revisions/{revision}')
    def historical(cid:UUID,revision:int,request:Request):
        with database.session() as db:return response(service.historical(actor_in(request,db),cid,revision,db))

    @app.get(base+'/receipts/{request_id}')
    def receipt(cid:UUID,request_id:UUID,request:Request):
        with database.session() as db:return response(service.find(actor_in(request,db),cid,request_id,db))

    @app.post(base+'/commits')
    async def commit(cid:UUID,request:Request):
        with database.session() as db:
            if not service.read(actor_in(request,db,write=True),cid,db).writable:raise ServiceError('VERSION_CONFLICT',409)
        value=await body_input(request,d.FollowupCommitInput)
        with database.session() as db:actor=actor_in(request,db,write=True)
        return response(await run_in_threadpool(service.commit,actor,cid,value,database=database))
