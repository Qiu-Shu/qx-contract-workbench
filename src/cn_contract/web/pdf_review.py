"""Authorized immutable PDF bytes and measured local rendering assets."""
from uuid import UUID

from fastapi import Request
from fastapi.responses import Response

from ..documents.pdfjs_assets import read_pdfjs_asset
from ..persistence import read_original, read_version
from ..security import ServiceError
from .services import current_versions


def pdf_page_geometry(data):
    import pypdfium2 as pdfium
    document=pdfium.PdfDocument(data)
    try:
        if len(document)>200:raise ServiceError('FILE_LIMIT',413)
        result=[]
        for index in range(len(document)):
            page=document[index]
            try:result.append({'media':page.get_mediabox(),'crop':page.get_cropbox()})
            finally:page.close()
        return result
    finally:document.close()


def register_routes(app, database, actor_in, authenticate_first, body_input, write):
    from ..domain import PageVerificationInput
    from ..documents import proofreading
    from ..documents import ocr_candidates
    from ..domain import PageOCRInput
    from starlette.concurrency import run_in_threadpool

    @app.post('/api/matters/{matter_id}/page-ocr')
    async def ocr(matter_id: UUID, request: Request):
        authenticate_first(request,matter_id,'candidate_facts')
        value=await body_input(request,PageOCRInput)
        def execute():
            original=write(request,matter_id,'page_ocr',value,
                lambda actor,db:ocr_candidates.prepare_page_ocr(matter_id,value,actor,db),permission='candidate_facts',prepare_only=True)
            if not isinstance(original,bytes):return original  # validated idempotent replay
            result=ocr_candidates.predict_page(original,value)
            return write(request,matter_id,'page_ocr',value,
                lambda actor,db:ocr_candidates.save_page_ocr(matter_id,value,result,actor,db),permission='candidate_facts')
        return await run_in_threadpool(execute)

    @app.get('/api/matters/{matter_id}/page-ocr')
    def ocr_history(matter_id: UUID, request: Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            return [r.model_dump(mode='json') for r in ocr_candidates.current_candidates(matter_id,actor,db)]

    @app.post('/api/matters/{matter_id}/page-verifications')
    async def submit(matter_id: UUID, request: Request):
        authenticate_first(request,matter_id,'confirm_facts')
        value=await body_input(request,PageVerificationInput)
        return write(request,matter_id,'page_verification',value,
            lambda actor,db:proofreading.submit_page_verification(matter_id,value,actor,db))

    @app.get('/api/matters/{matter_id}/page-verifications')
    def history(matter_id: UUID, request: Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            return [r.model_dump(mode='json') for r in proofreading.history(matter_id,actor,db)]

    @app.get('/api/matters/{matter_id}/documents/{version_id}/original')
    def original(matter_id: UUID, version_id: UUID, request: Request, sha256: str = ''):
        with database.session() as db:
            actor = actor_in(request, db, matter_id)
            version = read_version(matter_id, version_id, actor, db)
            if version.id not in {item.id for item in current_versions(matter_id, actor, db)} or sha256 != version.sha256:
                raise ServiceError('VERSION_CONFLICT', 409)
            from ..documents.ingest import DOCX_MIME
            if version.mime not in ('application/pdf', DOCX_MIME): raise ServiceError('FILE_UNSUPPORTED', 415)
            data = read_original(matter_id, version_id, actor, db)
        if version.mime == DOCX_MIME:
            return Response(data, media_type=DOCX_MIME, headers={
                'Content-Disposition':'attachment; filename="original.docx"', 'X-Content-SHA256':version.sha256,
                'Cache-Control':'no-store'})
        return Response(data, media_type='application/pdf', headers={
            'Content-Disposition':'inline; filename="original.pdf"', 'X-Content-SHA256':version.sha256,
            'X-QX-PDF-Geometry':__import__('json').dumps(pdf_page_geometry(data),separators=(',',':'),allow_nan=False)})

    @app.get('/static/pdfjs/{name:path}')
    def asset(name: str):
        raw, mime = read_pdfjs_asset(name)
        return Response(raw, media_type=mime)
