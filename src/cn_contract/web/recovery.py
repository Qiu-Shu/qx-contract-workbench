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
from .assistant_attachments import is_attachment_read_path
from .assistant_generation import is_generation_read_path
from .assistant_research import is_research_read_path
from .assistant_profiles import is_profile_read_path
from .evidence_worksheet import is_evidence_read_path
from .reception_worksheet import is_worksheet_read_path
from .task_drafts import is_task_read_path
from .weixin_authorization import is_weixin_authorization_read_path


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
        safe_api = safe_api or is_attachment_read_path(path)
        safe_api = safe_api or is_generation_read_path(path)
        safe_api = safe_api or is_research_read_path(path)
        safe_api = safe_api or is_profile_read_path(path)
        safe_api = safe_api or is_worksheet_read_path(path)
        safe_api = safe_api or is_evidence_read_path(path)
        safe_api = safe_api or is_task_read_path(path)
        safe_api = safe_api or is_weixin_authorization_read_path(path)
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

    @app.get('/recovery/task-executions/{identifier}',response_class=HTMLResponse)
    def task_history(identifier:UUID,request:Request):
        from ..domain import CoverageId
        from ..exports.audience_filter import DIMENSIONS
        from ..review.storage import read_run
        from ..task_drafts.service import read_execution
        with database.session() as db:
            actor=actor_in(request,db)
            execution=read_execution(actor,identifier,db)
            run=None
            if execution.review_run_id is not None:
                run=read_run(execution.matter_id,execution.review_run_id,actor,db=db,current=False)
                if (run.manifest.model_provider!='mock' or run.id!=execution.review_run_id
                        or dict(run.manifest.document_hashes)!=dict(execution.document_versions)):
                    raise ServiceError('VERSION_CONFLICT',409)
            names={media.attachment_id:media.name for event in execution.manifest.events for media in event.media}
            sources={version:names.get(source,'原件') for source,version in execution.source_versions.items()}
            documents=[{'id':version,'sha256':digest,'name':sources.get(version,'原件')}
                       for version,digest in execution.document_versions.items()]
        return HTMLResponse(app.state.template_environment.get_template('recovery_task.html').render(
            execution=execution,run=run,documents=documents,
            coverage_names=dict(zip(CoverageId,DIMENSIONS,strict=True))))

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
