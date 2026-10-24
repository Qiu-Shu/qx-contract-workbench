"""Bounded attachment transport; source storage and parsing live in the service."""
import json
import re
from pathlib import PurePath
from uuid import UUID

from fastapi import Path, Query, Request
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from .. import domain as d
from ..assistant import attachments as service
from ..assistant.attachment_records import owned_attachment
from ..assistant.service import _owned
from ..ops.storage import require_active
from ..security import ServiceError
from .request_context import actor_in, body_input, unique

METADATA_LIMIT = 64*1024
_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH = re.compile(
    rf'/api/assistant/conversations/{_UUID}/(?:materials(?:/by-request/{_UUID})?|'
    rf'attachments/(?:by-request/{_UUID}|{_UUID}(?:/original|/parses/'
    rf'(?:by-request/{_UUID}|[1-9][0-9]*(?:/anchors/{_UUID})?))?))')


def is_attachment_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


async def multipart_input(request, limit):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower() != 'multipart/form-data':
        raise ServiceError('FILE_UNSUPPORTED',400)

    async def bounded_stream():
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit:
                raise ServiceError('FILE_LIMIT',413)
            yield chunk

    parser = MultiPartParser(request.headers,bounded_stream(),max_files=1,max_fields=1,max_part_size=METADATA_LIMIT)
    # The bounded multipart stays in memory; only the service stages on the workspace volume.
    parser.spool_max_size = limit
    try:
        return await parser.parse()
    except MultiPartException:
        raise ServiceError('FILE_UNSUPPORTED',400) from None


def register_routes(app, database):
    from ..task_drafts.synthetic import PDF_HASHES
    database._assistant_synthetic_hashes = app.state.synthetic_upload_hashes | PDF_HASHES
    base = '/api/assistant/conversations/{cid}'

    def authorize(request, cid, *, write=False, attachment=None):
        with database.session() as db:
            actor = actor_in(request,db,write=write)
            _owned(actor,cid,db)
            if attachment is not None:
                owned_attachment(actor,cid,attachment,db)
            if write:
                require_active(db)
        return actor

    async def write(request, cid, model, operation, *, attachment=None):
        authorize(request,cid,write=True,attachment=attachment)
        value = await body_input(request,model)
        actor = authorize(request,cid,write=True,attachment=attachment)
        arguments = (actor,cid,value) if attachment is None else (actor,cid,attachment,value)
        return await run_in_threadpool(operation,*arguments,database=database)

    @app.get(base+'/materials')
    def materials(cid:UUID,request:Request):
        return service.read_materials(authorize(request,cid),cid,database=database)

    @app.get(base+'/materials/by-request/{request_id}')
    def material_receipt(cid:UUID,request_id:UUID,request:Request):
        return service.find_material_request(authorize(request,cid),cid,request_id,database=database)

    @app.put(base+'/materials')
    async def selection(cid:UUID,request:Request):
        revision = await write(request,cid,d.AssistantMaterialSelectionInput,service.select_materials)
        return {'materials_revision':revision}

    @app.post(base+'/attachments',status_code=201)
    async def upload(cid:UUID,request:Request):
        authorize(request,cid,write=True)
        file_limit = database.settings.upload_max_file_mib*1024**2
        form = None
        try:
            form = await multipart_input(request,file_limit+METADATA_LIMIT)
            parts = list(form.multi_items())
            if len(parts) != 2 or {key for key,_ in parts} != {'file','metadata'}:
                raise ServiceError('FILE_UNSUPPORTED',400)
            file, metadata = form['file'], form['metadata']
            if not isinstance(file,UploadFile) or not isinstance(metadata,str):
                raise ServiceError('FILE_UNSUPPORTED',400)
            if file.size is None or file.size > file_limit:
                raise ServiceError('FILE_LIMIT',413)
            if len(metadata.encode('utf-8')) > METADATA_LIMIT:
                raise ServiceError('FILE_LIMIT',413)
            payload = json.loads(metadata,object_pairs_hook=unique,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))
            value = d.AssistantAttachmentInput.model_validate(payload)
            if file.filename != value.original_name or file.content_type != value.mime:
                raise ServiceError('FILE_UNSUPPORTED',400)
            actor = authorize(request,cid,write=True)
            return await run_in_threadpool(service.ingest_attachment,actor,cid,value,file.file,database=database)
        except (ValueError,TypeError,RecursionError,UnicodeDecodeError,ValidationError):
            raise ServiceError('STATE_CONFLICT',422) from None
        finally:
            if form is not None:
                await form.close()

    @app.get(base+'/attachments/by-request/{request_id}')
    def upload_receipt(cid:UUID,request_id:UUID,request:Request):
        return service.find_attachment_request(authorize(request,cid),cid,request_id,database=database)

    @app.get(base+'/attachments/{identifier}')
    def attachment(cid:UUID,identifier:UUID,request:Request):
        return service.read_attachment(authorize(request,cid),cid,identifier,database=database)

    @app.get(base+'/attachments/{identifier}/original')
    def original(cid:UUID,identifier:UUID,request:Request):
        view = service.read_attachment(authorize(request,cid),cid,identifier,database=database)
        raw = service.read_original(authorize(request,cid),cid,identifier,database=database)
        suffix = PurePath(view.original_name).suffix.lower()
        return Response(raw,media_type='application/octet-stream',
            headers={'Content-Disposition':f'attachment; filename="original-{identifier}{suffix}"'})

    @app.post(base+'/attachments/{identifier}/parses')
    async def parse(cid:UUID,identifier:UUID,request:Request):
        return await write(request,cid,d.AssistantAttachmentParseInput,service.parse_attachment,attachment=identifier)

    @app.get(base+'/attachments/{identifier}/parses/by-request/{request_id}')
    def parse_receipt(cid:UUID,identifier:UUID,request_id:UUID,request:Request):
        return service.find_parse_request(authorize(request,cid),cid,identifier,request_id,database=database)

    @app.get(base+'/attachments/{identifier}/parses/{revision}')
    def parsed(cid:UUID,identifier:UUID,request:Request,revision:int=Path(ge=1)):
        return service.read_parse(authorize(request,cid),cid,identifier,revision,database=database)

    @app.get(base+'/attachments/{identifier}/parses/{revision}/anchors/{anchor_id}')
    def excerpt(cid:UUID,identifier:UUID,anchor_id:UUID,request:Request,revision:int=Path(ge=1),
                quote_sha256:str=Query(pattern=r'^[0-9a-f]{64}$')):
        return service.read_excerpt(authorize(request,cid),cid,identifier,revision,anchor_id,quote_sha256,database=database)
