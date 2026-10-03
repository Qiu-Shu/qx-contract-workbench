"""One explicitly invoked worker; every claim/auth boundary commits before work.

SQLite/local parsing and mock review remain bounded CPU work in a transaction.
Query network work always uses T08's Database Factory with no request Session.
"""
import asyncio
import json
from uuid import UUID
from sqlalchemy import select

from ..domain import ReviewStartInput,JobInput
from ..security import ServiceError,authorize
from ..queries.gateway import execute_plan
from ..providers.qcc_mcp import FactoryQccTransport
from ..queries.ledger import recover_inflight
from . import storage as s, services


def start_job(input,actor,*,database,parameters,idempotency_key):
    """Explicit JobInput API; protected payload, hash and authorization first.

    Database is a mandatory addition to the specification's abstract signature;
    importing this module never supplies an implicit database or worker.
    """
    s.require_storage(database)
    try:
        input=JobInput.model_validate_json(input.model_dump_json())
        if not isinstance(parameters,dict) or s.sha(parameters)!=input.parameters_sha256:
            raise ServiceError('VERSION_CONFLICT',409)
        if input.job_type not in {'parse','review','query'}:raise ServiceError('NOT_SUPPORTED',409)
        with database.session() as db:
            authorize(actor,input.matter_id,{'parse':'upload','review':'review','query':'confirm_facts'}[input.job_type],db)
            previous=s.find_idempotent(input.matter_id,actor,input.job_type,idempotency_key,s.sha(parameters),db)
            if input.job_type=='parse':
                if set(parameters)!={'version_id'}:raise ServiceError('VERSION_CONFLICT',409)
                from ..persistence import read_version
                version=read_version(input.matter_id,UUID(parameters['version_id']),actor,db)
                if version.id not in {v.id for v in services.current_versions(input.matter_id,actor,db)}:raise ServiceError('VERSION_CONFLICT',409)
            elif input.job_type=='review':
                if previous:
                    if s.fingerprint(input.matter_id,actor,db)!=previous.matter_sha256:raise ServiceError('APPROVAL_STALE',409)
                    if previous.result_ref:
                        from ..review.storage import read_run
                        read_run(input.matter_id,UUID(previous.result_ref),actor,db=db,current=True)
                else:services.verify_review_input(input.matter_id,ReviewStartInput.model_validate(parameters),actor,db)
            else:
                if set(parameters)!={'plan_id','plan_sha256'}:raise ServiceError('PLAN_CHANGED',409)
                from ..queries.planner import read_plan
                plan=read_plan(UUID(parameters['plan_id']),actor,matter_id=input.matter_id,db=db,require_approved=True)
                if plan.plan_sha256!=parameters['plan_sha256']:raise ServiceError('PLAN_CHANGED',409)
                if plan.scope!='Q0':
                    from ..providers.qcc_registry import read_binding,read_case_endpoint
                    allowed=getattr(database,'_web_synthetic_loopback_endpoints',frozenset())
                    for item in plan.items:
                        binding=read_binding(item.tool_binding_ref,actor=actor,matter_id=input.matter_id,db=db)
                        endpoint=read_case_endpoint(binding.endpoint_config_ref,actor=actor,matter_id=input.matter_id,db=db)
                        if endpoint['provider']!='synthetic_mcp_loopback' or not endpoint['synthetic'] or endpoint['live_allowed'] or endpoint['config']['endpoint'] not in allowed:
                            raise ServiceError('BLOCKED_LIVE',409)
            row=previous or s.enqueue(input.matter_id,actor,input.job_type,idempotency_key,parameters,db)
            return s.status(row)
    except (ValueError,TypeError,KeyError):raise ServiceError('VERSION_CONFLICT',409) from None


def claim_next_job(database):
    s.require_storage(database)
    with database.session() as db:
        row=db.scalar(select(s.JobRow).where(s.JobRow.state=='queued').order_by(s.JobRow.timestamp,s.JobRow.id).limit(1))
        if row is None:return None
        row.state='running';row.stage='正在执行';s.event(row,db)
        return UUID(row.id)


def recover_jobs(database):
    s.require_storage(database)
    with database.session() as db:
        rows=list(db.scalars(select(s.JobRow).where(s.JobRow.state=='running')))
        for row in rows:
            row.state='blocked';row.stage='上次执行状态未知，需人工核对'
            row.error_code='QUERY_STATE_UNKNOWN' if row.kind=='query' else 'STATE_CONFLICT'
            s.event(row,db)
        count=len(rows)
    recover_inflight(database)
    return count


def run_next_job(database):
    identifier=claim_next_job(database)
    if identifier is None:return None
    try:
        with database.session() as db:
            row=db.get(s.JobRow,str(identifier));actor=s.valid_actor(row,db);matter_id=UUID(row.matter_id)
            if s.fingerprint(matter_id,actor,db)!=row.matter_sha256:raise ServiceError('VERSION_CONFLICT',409)
            payload=json.loads(row.payload);kind=row.kind
        if kind=='query':
            with database.session() as db:
                from ..queries.planner import read_plan
                from ..providers.qcc_registry import read_binding,read_case_endpoint
                plan=read_plan(UUID(payload['plan_id']),actor,matter_id=matter_id,db=db,require_approved=True)
                if plan.plan_sha256!=payload['plan_sha256']:raise ServiceError('PLAN_CHANGED',409)
                if plan.scope!='Q0':
                    allowed=getattr(database,'_web_synthetic_loopback_endpoints',frozenset())
                    for item in plan.items:
                        binding=read_binding(item.tool_binding_ref,actor=actor,matter_id=matter_id,db=db)
                        endpoint=read_case_endpoint(binding.endpoint_config_ref,actor=actor,matter_id=matter_id,db=db)
                        if endpoint['provider']!='synthetic_mcp_loopback' or endpoint['live_allowed'] or not endpoint['synthetic'] or endpoint['config']['endpoint'] not in allowed:
                            raise ServiceError('BLOCKED_LIVE',409)
            # No HTTP or worker transaction spans the external SDK call.
            transport=FactoryQccTransport(database,actor=actor,matter_id=matter_id)
            receipts=asyncio.run(execute_plan(UUID(payload['plan_id']),actor,transport,database=database,matter_id=matter_id))
            if any(r.billing_state!='confirmed' for r in receipts):raise ServiceError('QUERY_STATE_UNKNOWN',409)
            if any(r.status!='success' for r in receipts):raise ServiceError('NOT_SUPPORTED',502)
            result=str(payload['plan_id'])
        else:
            with database.session() as db:
                row=db.get(s.JobRow,str(identifier));actor=s.valid_actor(row,db)
                if s.fingerprint(matter_id,actor,db)!=row.matter_sha256:raise ServiceError('VERSION_CONFLICT',409)
                if kind=='parse':result=services.candidate_parse(matter_id,UUID(payload['version_id']),actor,db)
                elif kind=='review':result=services.review(matter_id,ReviewStartInput.model_validate(payload),actor,db)
                else:raise ServiceError('NOT_SUPPORTED',409)
                s.valid_actor(row,db)
                # Expected post-operation snapshot permits this parse's own new
                # facts while rejecting a concurrent change before completion.
                post_fingerprint=s.fingerprint(matter_id,actor,db)
        with database.session() as db:
            row=db.get(s.JobRow,str(identifier));actor=s.valid_actor(row,db)
            if kind=='query':
                if s.fingerprint(matter_id,actor,db)!=row.matter_sha256:raise ServiceError('VERSION_CONFLICT',409)
                from ..queries.planner import read_plan
                plan=read_plan(UUID(payload['plan_id']),actor,matter_id=matter_id,db=db,require_approved=True)
                if plan.plan_sha256!=payload['plan_sha256']:raise ServiceError('PLAN_CHANGED',409)
            elif kind=='review':
                from ..review.storage import read_run
                run=read_run(matter_id,UUID(result),actor,db=db,current=True)
            elif kind=='parse':
                if s.fingerprint(matter_id,actor,db)!=post_fingerprint:raise ServiceError('VERSION_CONFLICT',409)
                if UUID(result) not in {v.id for v in services.current_versions(matter_id,actor,db)}:raise ServiceError('VERSION_CONFLICT',409)
                from ..persistence import get_parse_result
                from ..facts.storage import trusted_parse
                trusted_parse(matter_id,UUID(result),actor,db,get_parse_result(matter_id,UUID(result),actor,db))
            # T06 deliberately persists failed runs/usage/attempts. Its return
            # value certifies evidence storage, not successful model output.
            if kind=='review' and run.status=='failed':
                row.state='failed';row.stage='审查输出失败，记录已保留';row.error_code=run.error_code
            else:row.state='completed';row.stage='已完成'
            row.result_ref=result;s.event(row,db)
    except ServiceError as error:
        with database.session() as db:
            row=db.get(s.JobRow,str(identifier));row.state='blocked' if error.status_code in (401,403,409) else 'failed'
            row.stage='需要补充或重新授权' if row.state=='blocked' else '执行失败'
            # JobStatus accepts the sole domain enum; rare provider-only codes map
            # to the conservative uncertainty code, never leak provider strings.
            from ..domain import ErrorCode
            row.error_code=error.code if error.code in set(ErrorCode) else 'QUERY_STATE_UNKNOWN'
            s.event(row,db)
    except Exception:
        with database.session() as db:
            row=db.get(s.JobRow,str(identifier));row.state='failed';row.stage='执行失败，需人工核对'
            row.error_code='STATE_CONFLICT';s.event(row,db)
    with database.session() as db:return s.status(db.get(s.JobRow,str(identifier)))
