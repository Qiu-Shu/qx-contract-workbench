"""Authenticated previews/copies/downloads of a fixed saved source and audience."""
from urllib.parse import quote
from uuid import UUID

from fastapi import Query, Request
from pydantic import ValidationError
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .. import domain as d
from ..assistant import outputs
from ..exports.assistant_docx import build
from ..security import ServiceError
from .request_context import actor_in, body_input


def register_routes(app, database):
    base = '/api/assistant/conversations/{cid}/outputs'

    def authorize(request, cid, *, write=False):
        with database.session() as db:
            actor = actor_in(request,db,write=write)
            outputs._current(actor,cid,db)

    def read(request, cid, value, *, checked=False):
        with database.session() as db:
            actor = actor_in(request,db,write=True)
            return (outputs.checked_export if checked else outputs.preview)(actor,cid,value,db)

    def response(value):
        return JSONResponse(value.model_dump(mode='json'),headers={'Cache-Control':'no-store'})

    @app.get(base)
    def listing(cid:UUID, request:Request, before:str|None=Query(default=None,max_length=300)):
        with database.session() as db:
            actor = actor_in(request,db)
            outputs._current(actor,cid,db)
            try:
                cursor = d.AssistantOutputSource.model_validate_json(before) if before is not None else None
            except ValidationError:
                raise ServiceError('NOT_SUPPORTED',422) from None
            return response(outputs.list_outputs(actor,cid,db,before=cursor))

    @app.post(base+'/preview')
    async def preview(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.AssistantOutputSelection)
        return response(read(request,cid,value))

    @app.post(base+'/copy')
    async def copy(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.AssistantOutputExportInput)
        return response(read(request,cid,value,checked=True))

    @app.post(base+'/docx')
    async def docx(cid:UUID, request:Request):
        authorize(request,cid,write=True)
        value = await body_input(request,d.AssistantOutputExportInput)
        projection = read(request,cid,value,checked=True)
        try:
            content = await run_in_threadpool(build,projection)
        except ValueError:
            raise ServiceError('NOT_SUPPORTED',422) from None
        # Rendering can take time. A completed preview never freezes permission.
        read(request,cid,value,checked=True)
        filename = projection.title+'-'+projection.content_sha256[:8]+'.docx'
        return Response(content,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                     'Content-Disposition':"attachment; filename=work-draft.docx; filename*=UTF-8''"+quote(filename)})
