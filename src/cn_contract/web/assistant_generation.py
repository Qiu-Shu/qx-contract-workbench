"""Explicit HTTP generation; status and receipt reads never dispatch work."""
from contextlib import asynccontextmanager
import re
from uuid import UUID

from fastapi import Request
from sqlalchemy import text

from .. import domain as d
from ..assistant import service
from ..assistant.attachment_records import items
from ..assistant.providers import attempts
from ..assistant.providers.policy import MainModelRuntime, add_costs, prepare, require_policy, reservation, sha
from ..ops.storage import quarantined, require_active
from ..security import ServiceError
from .request_context import actor_in, body_input

_UUID=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH=re.compile(rf'/api/assistant/(?:attempts/{_UUID}|conversations/{_UUID}/'
    rf'(?:generation-capability|generations/by-request/{_UUID}))')


def is_generation_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def _capability(actor, conversation, db, runtime, tasks):
    scope=service._snapshot(conversation)
    content=conversation['draft_input']
    digest=sha(content) if content.strip() else None

    def result(state):
        return d.MainGenerationCapability(scope=scope,composer_revision=conversation['composer_revision'],
            content_sha256=digest,state=state)

    if quarantined(db):return result('restored_read_only')
    if runtime is None:return result('unconfigured')
    try:config,policy=runtime.snapshot()
    except (ValueError,TypeError,AttributeError):return result('unconfigured')
    if not config.enabled:return result('unconfigured')
    if conversation['archived_at'] is not None or items(conversation,db):return result('unsupported')
    if not tasks.accepting or db.scalar(text('''SELECT id FROM assistant_runs WHERE conversation_id=:cid
        AND state IN ('queued','preparing','routing','retrieving','generating','persisting') LIMIT 1'''),
        {'cid':conversation['id']}):
        return result('busy')
    if digest is None:return result('empty')
    try:
        require_policy(config,policy,actor,scope,digest)
        # Canonical UUID widths are fixed; this checks the complete future wire byte cap.
        prepare(d.MainRequest(run_id=UUID(int=0),scope=scope,message_id=UUID(int=0),
            content=content,source_sha256=digest),config)
        used,calls=attempts._budget(policy,db)
    except ServiceError:return result('unapproved')
    except ValueError:return result('unsupported')
    if add_costs((used,reservation(config)))>policy.max_total_usd or calls>=policy.max_calls:
        return result('budget_exhausted')
    return result('ready')


def attach_generation(app, database, runtime=None):
    if runtime is not None and not isinstance(runtime,MainModelRuntime):
        raise TypeError('trusted MainModelRuntime required')
    tasks=None
    if runtime is not None:
        from ..assistant.task_manager import GenerationTasks
        tasks=GenerationTasks(database,runtime)
    app.state.assistant_generation_tasks=tasks
    previous=app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            with database.session() as db:
                active=tasks is not None and not quarantined(db)
            if active:tasks.start()
            try:yield
            finally:
                if active:await tasks.close()

    app.router.lifespan_context=lifespan
    base='/api/assistant/conversations/{identifier}'

    @app.get(base+'/generation-capability')
    async def capability(identifier:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db)
            conversation=service._owned(actor,identifier,db)
            return _capability(actor,conversation,db,runtime,tasks)

    @app.post(base+'/generations',status_code=202)
    async def generate(identifier:UUID,request:Request):
        def authorize():
            with database.session() as db:
                actor=actor_in(request,db,write=True)
                service._owned(actor,identifier,db)
                require_active(db)
            return actor
        authorize()
        value=await body_input(request,d.AssistantMessageInput)
        actor=authorize()
        if value.requested_skill is not None:raise ServiceError('NOT_SUPPORTED',422)
        if tasks is None:raise ServiceError('BLOCKED_LIVE',403)
        try:return tasks.submit(actor,identifier,value)
        except ValueError:
            # Valid HTTP text may still exceed the configured UTF-8 wire limit.
            raise ServiceError('STATE_CONFLICT',422) from None

    @app.get('/api/assistant/attempts/{identifier}')
    def attempt(identifier:UUID,request:Request):
        with database.session() as db:
            return attempts.read_attempt(actor_in(request,db),identifier,db)

    @app.get(base+'/generations/by-request/{request_id}')
    def find(identifier:UUID,request_id:UUID,request:Request):
        with database.session() as db:
            actor=actor_in(request,db)
            service._owned(actor,identifier,db)
            found=db.scalar(text('''SELECT a.id FROM assistant_model_attempts a JOIN assistant_runs r
                ON r.id=a.run_id WHERE a.conversation_id=:cid AND r.request_id=:request'''),
                {'cid':str(identifier),'request':str(request_id)})
            return attempts.read_attempt(actor,UUID(found),db) if found else None
