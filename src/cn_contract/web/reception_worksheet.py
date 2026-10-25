"""Explicit local reception editing and preparation; model sends stay on existing routes."""
import re
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..assistant import reception_worksheet as worksheet, profile_store
from ..security import ServiceError
from .request_context import actor_in, body_input

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH = re.compile(rf'/api/assistant/conversations/{_UUID}/reception-worksheet(?:/receipts/{_UUID})?')


def is_worksheet_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def register_routes(app, database):
    base = '/api/assistant/conversations/{cid}/reception-worksheet'

    def authorize(request,cid,*,write=False):
        with database.session() as db:
            actor = actor_in(request,db,write=write)
            saved = worksheet.view(actor,cid,db)
            if write and not saved.writable:
                raise ServiceError('VERSION_CONFLICT',409)
        return actor

    def response(value):
        return JSONResponse(value.model_dump(mode='json'),headers={'Cache-Control':'no-store'})

    @app.get(base)
    def read(cid:UUID, request:Request):
        with database.session() as db:
            return response(worksheet.view(actor_in(request,db),cid,db))

    @app.post(base+'/commits')
    async def commit(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.ProfileCommitInput)
        actor = authorize(request,cid,write=True)
        worksheet.validate_commit(cid,value)
        with database.session() as db:
            value = worksheet.preserve_manual(actor_in(request,db,write=True),cid,value,db)
        return response(await run_in_threadpool(profile_store.save_profile,actor,value,database=database))

    @app.get(base+'/receipts/{request_id}')
    def receipt(cid:UUID, request_id:UUID, request:Request):
        actor = authorize(request,cid)
        value = profile_store.find_receipt(actor,cid,request_id,database=database)
        return response(value) if value is not None else JSONResponse(None,headers={'Cache-Control':'no-store'})

    @app.post(base+'/suggestions')
    async def suggestions(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.ReceptionWorksheetBasis)
        with database.session() as db:
            return response(worksheet.suggestions(actor_in(request,db,write=True),cid,value,db))

    @app.post(base+'/prepare')
    async def prepare(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.ReceptionWorksheetPrepareInput)
        with database.session() as db:
            return response(worksheet.prepare(actor_in(request,db,write=True),cid,value,db))
