"""Authenticated reconciliation of a fenced recovery copy, never current approval."""
import json
import re
from uuid import UUID

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select

from ..persistence import MatterRow, MembershipRow, DocumentRow, ExportRow, read_original, read_version
from ..exports.storage import ExportRecordRow
from ..ops.storage import quarantined, read_historical_artifact
from ..security import ServiceError, authorize
from .request_context import actor_in


def attach_recovery(app, database):
    with database.session() as db:
        if not quarantined(db): return
    app.state.recovery_copy=True

    @app.middleware('http')
    async def readonly(request, call_next):
        path=request.url.path
        safe_api=(path in ('/api/login','/api/logout','/api/session','/api/matters','/api/intakes')
                  or path.startswith('/api/recovery/') or re.fullmatch(r'/api/intakes/[0-9a-f-]{36}(?:/revisions/[1-9][0-9]*)?',path))
        safe_api = safe_api or path in ('/api/assistant/skills','/api/assistant/conversations') or re.fullmatch(
            r'/api/assistant/(?:conversations/[0-9a-f-]{36}(?:/runs/by-request/[0-9a-f-]{36})?|runs/[0-9a-f-]{36}(?:/events)?)',path)
        if ((request.method not in ('GET','HEAD','OPTIONS') and path not in ('/api/login','/api/logout'))
                or path.startswith('/api/') and not safe_api):
            return JSONResponse({'code':'BLOCKED_LIVE'},status_code=409)
        assistant_page = path == '/assistant' or re.fullmatch(
            r'/assistant/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', path)
        if (request.method=='GET' and not path.startswith(('/api/','/static/','/recovery'))
                and path!='/login' and not assistant_page):
            return RedirectResponse('/recovery',status_code=303)
        return await call_next(request)

    def render(**values):
        return HTMLResponse(app.state.template_environment.get_template('recovery.html').render(**values))

    @app.get('/recovery',response_class=HTMLResponse)
    def overview(request:Request, offset:int=0):
        if offset<0:raise ServiceError('STATE_CONFLICT',422)
        from ..intake.service import listing
        with database.session() as db:
            actor=actor_in(request,db)
            cases=[]
            for row in db.scalars(select(MatterRow).join(MembershipRow,MembershipRow.matter_id==MatterRow.id)
                    .where(MembershipRow.user_id==str(actor.user_id))):
                try:authorize(actor,UUID(row.id),'read',db)
                except ServiceError:continue
                cases.append({'id':row.id,'title':json.loads(row.payload)['title']})
            intakes=listing(actor,db,offset=offset)
        return render(cases=cases,intakes=intakes,documents=None,artifacts=None,record=None)

    @app.get('/recovery/matters/{matter_id}',response_class=HTMLResponse)
    def matter(matter_id:UUID,request:Request):
        with database.session() as db:
            actor_in(request,db,matter_id)
            row=db.get(MatterRow,str(matter_id)); title=json.loads(row.payload)['title']
            documents=[json.loads(r.payload) for r in db.scalars(select(DocumentRow).where(DocumentRow.matter_id==str(matter_id)))]
            artifacts=[{'id':r.id,'kind':'历史 Word 工作稿'} for r in db.scalars(select(ExportRow).where(ExportRow.matter_id==str(matter_id)))]
            artifacts.extend({'id':r.ref,'kind':'历史修订 Word'} for r in db.scalars(select(ExportRecordRow).where(
                ExportRecordRow.matter_id==str(matter_id),ExportRecordRow.kind=='patch_result')) if json.loads(r.payload).get('status')=='applied')
        return render(title=title,matter_id=matter_id,documents=documents,artifacts=artifacts,record=None,cases=None)

    @app.get('/recovery/intakes/{identifier}',response_class=HTMLResponse)
    def intake(identifier:UUID,request:Request,revision:int|None=None):
        from ..intake.service import read
        if revision is not None and revision<1:raise ServiceError('STATE_CONFLICT',422)
        with database.session() as db:
            actor=actor_in(request,db);record=read(identifier,actor,db,revision=revision)
        return render(record=record,cases=None,documents=None,artifacts=None)

    @app.get('/api/recovery/matters/{matter_id}/originals/{version_id}')
    def original(matter_id:UUID,version_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id);raw=read_original(matter_id,version_id,actor,db)
            version=read_version(matter_id,version_id,actor,db)
        extension={'application/pdf':'.pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document':'.docx'}.get(version.mime,'.bin')
        return Response(raw,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="original-{version_id}{extension}"'})

    @app.get('/api/recovery/matters/{matter_id}/artifacts/{artifact_id}')
    def artifact(matter_id:UUID,artifact_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            row=db.get(ExportRow,str(artifact_id))
            if row is None:row=db.scalar(select(ExportRecordRow).where(ExportRecordRow.ref==str(artifact_id)))
            if row is None or row.matter_id!=str(matter_id):raise ServiceError('CROSS_MATTER_DENIED',403)
            raw=read_historical_artifact(artifact_id,actor,db=db)
        return Response(raw,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        headers={'Content-Disposition':f'attachment; filename="historical-{artifact_id}.docx"'})
