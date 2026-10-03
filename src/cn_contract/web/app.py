"""Synthetic-only local HTTP workbench over explicit current service instances."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError
from sqlalchemy import select
from starlette.exceptions import HTTPException

from ..config import Settings
from .. import domain as d
from ..persistence import (Database, MembershipRow, MatterRow, read_matter, read_version, get_parse_result,
    get_fact_snapshot, transition_matter, set_position, _material_changed)
from ..security import (ServiceError, authenticate, authorize, verify_csrf, login, revoke_session)
from ..facts.confirm import confirm_facts
from ..facts.storage import trusted_parse
from ..facts.party import resolve_party
from ..documents.ingest import ingest
from ..review.synthetic import EXPECTED_HASHES
from ..review.storage import read_run
from ..queries import planner, ledger
from ..queries.gateway import authenticate_execution
from ..exports import approvals
from . import services, storage as s
from .jobs import start_job, run_next_job, claim_next_job, recover_jobs
from .storage import get_job
from .dependencies import service_error_handler

TEMPLATES=Path(__file__).with_name('templates')
STATIC=Path(__file__).with_name('static')


def initialize_storage(database):
    # Explicitly register each existing storage family. App import is pure.
    from ..authorities.storage import initialize_storage as authorities
    from ..rules.storage import initialize_storage as rules
    from ..facts.storage import initialize_storage as facts
    from ..review.storage import initialize_storage as reviews
    from ..providers.storage import initialize_storage as providers
    from ..queries.storage import initialize_storage as queries
    from ..exports.storage import initialize_storage as exports
    for init in (authorities,rules,facts,reviews,providers,queries,exports,s.initialize_storage):init(database)


def same_origin(request):
    origin=request.headers.get('origin')
    if origin:
        parsed=urlsplit(origin)
        if parsed.scheme not in ('http','https') or origin.rstrip('/')!=str(request.base_url).rstrip('/'):
            raise ServiceError('CROSS_MATTER_DENIED',403)
    if request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:
        raise ServiceError('CROSS_MATTER_DENIED',403)


def actor_in(request,db,matter_id=None,action='read',*,write=False):
    actor=authenticate(request.cookies.get('qx_session'),db)
    if write:
        same_origin(request);verify_csrf(actor,request.headers.get('X-CSRF-Token'),matter_id or UUID(int=0),db)
    if matter_id is not None:authorize(actor,matter_id,action,db)
    return actor


async def bounded_body(request,limit):
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>limit:raise ServiceError('FILE_LIMIT',413)
        data.extend(chunk)
    request._body=bytes(data)
    return bytes(data)


def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate key')
        result[k]=v
    return result


async def body_input(request,model):
    try:
        raw=await bounded_body(request,256*1024)
        payload=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite')))
        todo=[(payload,0)]
        while todo:
            value,depth=todo.pop()
            if depth>30:raise ValueError('depth')
            if isinstance(value,dict):todo.extend((v,depth+1) for v in value.values())
            elif isinstance(value,list):todo.extend((v,depth+1) for v in value)
        return model.model_validate(payload)
    except (ValueError,TypeError,RecursionError,UnicodeDecodeError,ValidationError):
        raise ServiceError('STATE_CONFLICT',422) from None


def project_bundle(bundle):
    return {**bundle.model_dump(mode='json',exclude={'artifacts'}),'draft':True,
        'artifacts':[a.model_dump(mode='json',exclude={'storage_ref'}) for a in bundle.artifacts],
        'limitations':['虚构/mock草案，不能正式签发','对外原件包修改需人工；完整补丁后法律与数值重审未实现']}


def create_app(settings: Settings, *, database: Database, synthetic_upload_hashes=None, synthetic_loopback_endpoints=(),
               synthetic_signing_user_ids=()):
    if not isinstance(database,Database):raise TypeError('explicit Database required')
    settings=Settings.model_validate(settings.model_dump(mode='python'))
    if settings.model_dump()!=database.settings.model_dump():raise ValueError('configured Settings mismatch')
    s.require_storage(database)
    allowed=frozenset(synthetic_upload_hashes) if synthetic_upload_hashes is not None else frozenset(EXPECTED_HASHES.values())
    if not allowed or any(not isinstance(v,str) or len(v)!=64 for v in allowed):raise ValueError('fixed synthetic hash registry required')
    environment=Environment(loader=FileSystemLoader(str(TEMPLATES)),autoescape=True,undefined=StrictUndefined)
    app=FastAPI(title='群兴合同审查工作台 · 独立虚构演示',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.database=database;app.state.template_environment=environment
    app.state.synthetic_upload_hashes=allowed
    loopbacks=frozenset(synthetic_loopback_endpoints)
    signing=frozenset(str(v) for v in synthetic_signing_user_ids)
    from ..providers.qcc_registry import allowed_synthetic_endpoint
    if any(not allowed_synthetic_endpoint(v) for v in loopbacks):raise ValueError('explicit synthetic loopback URLs only')
    database._web_synthetic_loopback_endpoints=loopbacks
    app.add_exception_handler(ServiceError,service_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error):return await service_error_handler(request,ServiceError('STATE_CONFLICT',422))

    @app.exception_handler(HTTPException)
    async def http_error(request,error):
        return await service_error_handler(request,ServiceError('FILE_UNSUPPORTED' if error.status_code==400 else 'NOT_SUPPORTED',error.status_code))

    @app.middleware('http')
    async def headers(request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    def authenticate_first(request,matter_id=None,action='read'):
        with database.session() as db:
            actor=actor_in(request,db,matter_id,action,write=True)
            if matter_id is None and action=='create' and not actor.roles & {d.Role.HANDLING_LAWYER,d.Role.REVIEWING_LAWYER}:
                from ..security import deny
                deny(actor,UUID(int=0),'authorization_denied',db)
            return actor

    def write(request,matter_id,action,value,operation,*,permission='confirm_facts',result_matter=None):
        key=request.headers.get('Idempotency-Key');payload=value.model_dump(mode='json')
        with database.session() as db:
            actor=actor_in(request,db,None if matter_id.int==0 else matter_id,permission,write=True)
            if matter_id.int==0 and not actor.roles & {d.Role.HANDLING_LAWYER,d.Role.REVIEWING_LAWYER}:
                from ..security import deny
                deny(actor,matter_id,'authorization_denied',db)
            previous=None
            if key:
                # Reuse the strict key syntax, without manufacturing any job.
                s.find_idempotent(matter_id,actor,'validation',key,s.sha(payload),db)
                previous=db.scalar(select(s.HttpWriteRow).where(s.HttpWriteRow.matter_scope==str(matter_id),
                    s.HttpWriteRow.actor_id==str(actor.user_id),s.HttpWriteRow.action==action,s.HttpWriteRow.idempotency_key==key))
                if previous:
                    if previous.request_sha256!=s.sha(payload):raise ServiceError('VERSION_CONFLICT',409)
                    actual_matter=UUID(previous.response_matter_id)
                    authorize(actor,actual_matter,permission,db)
                    if s.fingerprint(actual_matter,actor,db)!=previous.response_matter_sha256:
                        raise ServiceError('APPROVAL_STALE',409)
                    response=json.loads(previous.payload)
                    # Matter hashes alone cannot certify a still-approved patch
                    # or bundle. Re-enter the original T09 current/approval gate.
                    if action=='patch_approve':
                        from ..exports.storage import load_patch
                        services.current_run(actual_matter,value.run_id,value.run_sha256,actor,db)
                        load_patch(actual_matter,d.Patch.model_validate(response),actor,db)
                    elif action=='preview':
                        services.current_run(actual_matter,value.run_id,value.run_sha256,actor,db)
                        bundle=approvals.read_bundle(UUID(response['id']),actor,db=db)
                        if project_bundle(bundle)!=response:raise ServiceError('APPROVAL_STALE',409)
                    elif action.startswith('decision:'):
                        services.current_run(actual_matter,value.run_id,value.run_sha256,actor,db)
                    elif action=='query_plan' or action.startswith('query_approve:'):
                        plan=planner.read_plan(UUID(response['id']),actor,matter_id=actual_matter,db=db)
                        if plan.plan_sha256!=response['plan_sha256']:raise ServiceError('PLAN_CHANGED',409)
                    return response
            with db.begin_nested():
                result=operation(actor,db)
                response=result.model_dump(mode='json') if isinstance(result,d.DomainModel) else result
                if key:
                    target=UUID(response['id']) if result_matter=='created' else matter_id
                    db.add(s.HttpWriteRow(id=str(uuid4()),matter_scope=str(matter_id),response_matter_id=str(target),actor_id=str(actor.user_id),
                        action=action,idempotency_key=key,request_sha256=s.sha(payload),
                        response_matter_sha256=s.fingerprint(target,actor,db),payload=s.encode(response)))
                    db.flush()
                return response

    @app.post('/api/login')
    async def login_api(request:Request):
        same_origin(request);value=await body_input(request,d.LoginInput)
        with database.session() as db:token,csrf=login(value.username,value.password,db)
        response=JSONResponse({'csrf_token':csrf})
        response.set_cookie('qx_session',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=8*60*60)
        # CSRF is a non-authentication token; cookie is same-origin/Strict and
        # still compared to the protected real session hash by the backend.
        response.set_cookie('qx_csrf',csrf,httponly=False,samesite='strict',secure=request.url.scheme=='https',max_age=8*60*60)
        return response

    @app.get('/api/session')
    def session_api(request:Request):
        with database.session() as db:
            actor=actor_in(request,db)
            from ..persistence import UserRow
            user=db.get(UserRow,str(actor.user_id))
            return {'username':user.username,'roles':sorted(r.value for r in actor.roles)}

    @app.post('/api/logout')
    def logout_api(request:Request):
        with database.session() as db:
            actor=actor_in(request,db,write=True);revoke_session(actor.session_id,db)
        response=JSONResponse({'ok':True});response.delete_cookie('qx_session');response.delete_cookie('qx_csrf');return response

    @app.get('/api/matters')
    def matters_api(request:Request):
        with database.session() as db:
            actor=actor_in(request,db)
            if not actor.roles & {d.Role.HANDLING_LAWYER,d.Role.REVIEWING_LAWYER,d.Role.ASSISTANT}:return []
            ids=db.scalars(select(MembershipRow.matter_id).where(MembershipRow.user_id==str(actor.user_id))).all()
            return [read_matter(UUID(i),actor,db).model_dump(mode='json') for i in ids]

    @app.post('/api/matters',status_code=201)
    async def create_api(request:Request):
        authenticate_first(request,action='create')
        value=await body_input(request,d.MatterCreateInput)
        def operation(actor,db):
            matter=services.create_matter(value,actor,db)
            # Only fixed server demo configuration supplies sign-capable IDs.
            # No client role/can_sign flag is accepted or trusted.
            for membership in db.scalars(select(MembershipRow).where(MembershipRow.matter_id==str(matter.id))):
                if membership.user_id in signing:membership.can_sign=True
            return matter
        return write(request,UUID(int=0),'create',value,operation,permission='read',result_matter='created')

    @app.get('/api/matters/{matter_id}')
    def matter_api(matter_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            return {'matter':read_matter(matter_id,actor,db).model_dump(mode='json'),
                    'documents':[services.public_version(v) for v in services.current_versions(matter_id,actor,db)],
                    'synthetic':True,'qcc_enabled':False,'model_provider':'mock'}

    @app.post('/api/matters/{matter_id}/position')
    async def position_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'update_position');value=await body_input(request,d.PositionInput)
        def operation(actor,db):
            matter=set_position(matter_id,value.position,actor,db);row=db.get(MatterRow,str(matter_id));payload=json.loads(row.payload)
            if tuple(payload['objectives'])!=value.objectives:
                payload['objectives']=list(value.objectives);row.payload=d.Matter.model_validate(payload).model_dump_json()
                _material_changed(matter_id,db,'awaiting_fact_confirmation')
            return read_matter(matter_id,actor,db)
        return write(request,matter_id,'position',value,operation,permission='update_position')

    @app.post('/api/matters/{matter_id}/documents',status_code=202)
    async def upload_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'upload')
        await bounded_body(request,settings.upload_max_file_mib*1024*1024+64*1024)
        try:
            form=await request.form(max_files=1,max_fields=4,max_part_size=64*1024)
            file=form.get('file')
            if file is None or not hasattr(file,'read'):raise ServiceError('FILE_UNSUPPORTED',400)
            data=await file.read(settings.upload_max_file_mib*1024*1024+1)
            if len(data)>settings.upload_max_file_mib*1024*1024:raise ServiceError('FILE_LIMIT',413)
            digest=hashlib.sha256(data).hexdigest()
            if digest not in allowed:raise ServiceError('DATA_POLICY_UNAPPROVED',409)
            meta=d.UploadMeta(matter_id=matter_id,original_name=file.filename,mime=file.content_type,
                baseline_view=form.get('baseline_view') or None,supersedes_id=form.get('supersedes_id') or None)
        except (ValueError,ValidationError):raise ServiceError('FILE_UNSUPPORTED',400) from None
        finally:
            if 'form' in locals():await form.close()
        key=request.headers.get('Idempotency-Key')
        parameters={**meta.model_dump(mode='json'),'content_sha256':digest}
        with database.session() as db:
            actor=actor_in(request,db,matter_id,'upload',write=True)
            previous=s.find_idempotent(matter_id,actor,'parse',key,s.sha(parameters),db)
            if previous:
                saved=json.loads(previous.payload);version=read_version(matter_id,UUID(saved['version_id']),actor,db)
                if version.id not in {v.id for v in services.current_versions(matter_id,actor,db)}:raise ServiceError('APPROVAL_STALE',409)
                return {'job_id':previous.id,'version_id':str(version.id),'sha256':version.sha256}
            with db.begin_nested():
                version=ingest(BytesIO(data),meta,actor,db=db)
                row=s.enqueue(matter_id,actor,'parse',key,{'version_id':str(version.id)},db,digest=s.sha(parameters))
                result={'job_id':row.id,'version_id':str(version.id),'sha256':version.sha256}
            return result

    @app.get('/api/matters/{matter_id}/documents/{version_id}/anchors')
    def anchors_api(matter_id:UUID,version_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id);version=read_version(matter_id,version_id,actor,db)
            if version.id not in {v.id for v in services.current_versions(matter_id,actor,db)}:raise ServiceError('VERSION_CONFLICT',409)
            parsed=get_parse_result(matter_id,version_id,actor,db)
            if parsed is None:raise ServiceError('FACTS_UNCONFIRMED',409)
            return trusted_parse(matter_id,version_id,actor,db,parsed)

    @app.get('/api/matters/{matter_id}/facts')
    def facts_api(matter_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id);matter=read_matter(matter_id,actor,db)
            if matter.active_fact_version is None:raise ServiceError('FACTS_UNCONFIRMED',409)
            return get_fact_snapshot(matter_id,matter.active_fact_version,actor,db)

    @app.post('/api/matters/{matter_id}/facts/confirm')
    async def confirm_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.FactsConfirmInput)
        def operation(actor,db):
            snapshot=confirm_facts(matter_id,value.fact_version,value.decisions,actor,db=db)
            if snapshot.facts and all(f.confirmation_status in {'confirmed','corrected','rejected'} for f in snapshot.facts):
                transition_matter(matter_id,'ready_for_review',actor,db)
            return snapshot
        return write(request,matter_id,'facts_confirm',value,operation)

    @app.post('/api/matters/{matter_id}/reviews',status_code=202)
    async def review_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'review');value=await body_input(request,d.ReviewStartInput)
        with database.session() as db:
            actor=actor_in(request,db,matter_id,'review',write=True)
            payload=value.model_dump(mode='json');key=request.headers.get('Idempotency-Key')
            previous=s.find_idempotent(matter_id,actor,'review',key,s.sha(payload),db)
            if previous:
                if s.fingerprint(matter_id,actor,db)!=previous.matter_sha256:raise ServiceError('APPROVAL_STALE',409)
                if previous.result_ref:read_run(matter_id,UUID(previous.result_ref),actor,db=db,current=True)
                return {'job_id':previous.id}
            services.verify_review_input(matter_id,value,actor,db)
            row=s.enqueue(matter_id,actor,'review',key,payload,db)
            return {'job_id':row.id}

    @app.get('/api/matters/{matter_id}/reviews/{run_id}')
    def review_read_api(matter_id:UUID,run_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id);run=read_run(matter_id,run_id,actor,db=db)
            return {**run.model_dump(mode='json'),'run_sha256':s.sha(run.model_dump(mode='json')),
                    'decisions':services.decisions(matter_id,run_id,actor,db)}

    @app.get('/api/matters/{matter_id}/reviews')
    def run_list_api(matter_id:UUID,request:Request):
        from ..review.storage import ReviewRunRow
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            return [{'id':r.id,'created_at':r.timestamp.isoformat()} for r in db.scalars(select(ReviewRunRow)
                .where(ReviewRunRow.matter_id==str(matter_id)).order_by(ReviewRunRow.timestamp.desc()))]

    @app.post('/api/matters/{matter_id}/findings/{finding_id}/decision',status_code=201)
    async def decision_api(matter_id:UUID,finding_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.FindingDecisionInput)
        return write(request,matter_id,'decision:'+str(finding_id),value,lambda a,db:services.save_decision(matter_id,finding_id,value,a,db))

    @app.post('/api/matters/{matter_id}/patches/approve',status_code=201)
    async def patch_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.PatchApproveInput)
        return write(request,matter_id,'patch_approve',value,lambda a,db:services.approve_exact_patch(matter_id,value,a,db))

    @app.post('/api/matters/{matter_id}/exports/preview',status_code=201)
    async def preview_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.ExportPreviewInput)
        def operation(actor,db):
            run=services.current_run(matter_id,value.run_id,value.run_sha256,actor,db)
            patches=services.approved_patches(matter_id,value.patch_ids,actor,db)
            return project_bundle(approvals.prepare_exports(run,value.audience,patches,actor,db=db))
        return write(request,matter_id,'preview',value,operation)

    @app.get('/api/matters/{matter_id}/patches')
    def patches_api(matter_id:UUID,run_id:UUID,request:Request):
        from ..exports.storage import ExportRecordRow,load_patch
        with database.session() as db:
            actor=actor_in(request,db,matter_id);read_run(matter_id,run_id,actor,db=db)
            result=[]
            for row in db.scalars(select(ExportRecordRow).where(ExportRecordRow.kind=='patch_approval',ExportRecordRow.matter_id==str(matter_id))):
                payload=json.loads(row.payload)
                if payload['run_id']!=str(run_id):continue
                patch=d.Patch.model_validate(payload['patch'])
                try:load_patch(matter_id,patch,actor,db,write=False)
                except ServiceError:continue
                result.append(patch.model_dump(mode='json'))
            return result

    @app.post('/api/matters/{matter_id}/approvals')
    async def approve_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'approve');value=await body_input(request,d.FormalApprovalInput)
        saved_error=None
        with database.session() as db:
            actor=actor_in(request,db,matter_id,'approve',write=True)
            bundle=approvals.read_bundle(value.bundle_id,actor,db=db)
            if bundle.matter_id!=matter_id:raise ServiceError('CROSS_MATTER_DENIED',403)
            if bundle.audience!=value.scope:raise ServiceError('VERSION_CONFLICT',409)
            services.current_run(matter_id,bundle.run_id,value.review_snapshot_hash,actor,db)
            try:approvals.approve_bundle(bundle.id,value.artifact_manifest_hash,actor,db=db)
            except ServiceError as error:
                if error.code!='BLOCKED_LIVE':raise
                saved_error=error
        if saved_error:raise saved_error
        raise ServiceError('BLOCKED_LIVE',403)

    @app.get('/api/matters/{matter_id}/exports/{artifact_id}/download')
    def download_api(matter_id:UUID,artifact_id:UUID,request:Request):
        from ..persistence import read_export
        with database.session() as db:
            actor=actor_in(request,db,matter_id);artifact=read_export(matter_id,artifact_id,actor,db)
            raw=approvals.download_artifact(artifact.id,actor,db=db).getvalue()
        return Response(raw,media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={'Content-Disposition':f'attachment; filename="draft-{artifact_id}.docx"'})

    @app.get('/api/jobs/{job_id}')
    def job_api(job_id:UUID,request:Request):
        with database.session() as db:actor=actor_in(request,db)
        return s.get_job(job_id,actor,database=database)

    @app.get('/api/matters/{matter_id}/query-status')
    def query_status_api(matter_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            from ..queries.storage import authorize_query
            # Read-only assistants may see the budget and closed configuration.
            try:
                actual=ledger.read_budget(matter_id,actor,db=db)
                budget={k:str(v) if hasattr(v,'as_tuple') else v for k,v in actual.items()}
                budget['approved']=True
            except ServiceError as error:
                if error.code!='BUDGET_UNAPPROVED':raise
                budget={'approved':False,'case_limit':str(settings.qcc_case_budget_credits),'unit':'synthetic_credit',
                        'message':'预算未批准；默认20为上限，不是已授权费用'}
            return {'enabled':False,'live':'BLOCKED_LIVE','budget':budget,
                    'max_calls':settings.qcc_max_calls,'default_pages':1,'auto_retries':0}

    @app.get('/api/matters/{matter_id}/parties')
    def parties_api(matter_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id);return services.read_parties(matter_id,actor,db)

    @app.post('/api/matters/{matter_id}/parties/candidates')
    def party_candidates_api(matter_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db,matter_id,'candidate_facts',write=True)
            return services.register_document_party(matter_id,actor,db)

    @app.post('/api/matters/{matter_id}/parties/select')
    async def party_select_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.PartySelectionInput)
        def operation(actor,db):
            party=next((p for p in services.read_parties(matter_id,actor,db) if p.id==value.party_id),None)
            if party is None:raise ServiceError('PARTY_AMBIGUOUS',409)
            decision=d.PartyDecision(selected_candidate_id=value.candidate_id,reason=value.reason,confirmed_by=actor.user_id)
            return resolve_party(party.candidate_evidence,decision,matter_id=matter_id,role=party.role,name_raw=party.name_raw,
                actor=actor,db=db,party_id=party.id)
        return write(request,matter_id,'party_select',value,operation)

    @app.post('/api/matters/{matter_id}/query-plans',status_code=201)
    async def query_plan_api(matter_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.QueryPlanInput)
        if value.matter_id!=matter_id:raise ServiceError('CROSS_MATTER_DENIED',403)
        return write(request,matter_id,'query_plan',value,lambda a,db:planner.create_query_plan(value,a,db=db))

    @app.post('/api/matters/{matter_id}/query-plans/{plan_id}/approve')
    async def query_approve_api(matter_id:UUID,plan_id:UUID,request:Request):
        authenticate_first(request,matter_id,'confirm_facts');value=await body_input(request,d.PlanApproveInput)
        return write(request,matter_id,'query_approve:'+str(plan_id),value,
            lambda a,db:planner.approve_plan(plan_id,value.plan_sha256,a,matter_id=matter_id,db=db))

    @app.post('/api/matters/{matter_id}/query-plans/{plan_id}/execute',status_code=202)
    async def query_execute_api(matter_id:UUID,plan_id:UUID,request:Request):
        # T08 exact short authentication/CSRF before any queue or network.
        actor=authenticate_execution(database,request.cookies.get('qx_session'),request.headers.get('X-CSRF-Token'),matter_id=matter_id)
        same_origin(request);value=await body_input(request,d.PlanApproveInput)
        with database.session() as db:
            actor=actor_in(request,db,matter_id,'confirm_facts',write=True)
            plan=planner.read_plan(plan_id,actor,matter_id=matter_id,db=db,require_approved=True)
            if plan.plan_sha256!=value.plan_sha256:raise ServiceError('PLAN_CHANGED',409)
            if plan.scope!='Q0':
                from ..providers.qcc_registry import read_binding,read_case_endpoint
                for item in plan.items:
                    binding=read_binding(item.tool_binding_ref,actor=actor,matter_id=matter_id,db=db)
                    endpoint=read_case_endpoint(binding.endpoint_config_ref,actor=actor,matter_id=matter_id,db=db)
                    if (endpoint['provider']!='synthetic_mcp_loopback' or not endpoint['synthetic'] or endpoint['live_allowed']
                            or endpoint['config']['endpoint'] not in loopbacks):
                        raise ServiceError('BLOCKED_LIVE',409)
            row=s.enqueue(matter_id,actor,'query',request.headers.get('Idempotency-Key'),{'plan_id':str(plan_id),'plan_sha256':value.plan_sha256},db)
            return {'job_id':row.id}

    def page(request,matter_id=None,section='cases'):
        with database.session() as db:
            actor=actor_in(request,db,matter_id)
            matter=read_matter(matter_id,actor,db) if matter_id else None
        return HTMLResponse(environment.get_template('workbench.html').render(section=section,matter=matter,
            matter_id=str(matter_id) if matter_id else '',synthetic=True))

    @app.get('/',response_class=HTMLResponse)
    def index(request:Request):
        if not request.cookies.get('qx_session'):
            return HTMLResponse(environment.get_template('login.html').render())
        return page(request)

    @app.get('/login',response_class=HTMLResponse)
    def login_page(request:Request):return HTMLResponse(environment.get_template('login.html').render())

    @app.get('/matters/{matter_id}',response_class=HTMLResponse)
    def intake_page(matter_id:UUID,request:Request):return page(request,matter_id,'intake')
    @app.get('/matters/{matter_id}/facts',response_class=HTMLResponse)
    def facts_page(matter_id:UUID,request:Request):return page(request,matter_id,'facts')
    @app.get('/matters/{matter_id}/review',response_class=HTMLResponse)
    def review_page(matter_id:UUID,request:Request):return page(request,matter_id,'review')
    @app.get('/matters/{matter_id}/queries',response_class=HTMLResponse)
    def queries_page(matter_id:UUID,request:Request):return page(request,matter_id,'queries')
    @app.get('/matters/{matter_id}/exports',response_class=HTMLResponse)
    def exports_page(matter_id:UUID,request:Request):return page(request,matter_id,'exports')

    @app.get('/static/{name}')
    def static_file(name:str):
        if name not in {'workbench.js','workbench.css'}:raise ServiceError('NOT_SUPPORTED',404)
        return Response((STATIC/name).read_bytes(),media_type='text/javascript' if name.endswith('.js') else 'text/css')
    return app
