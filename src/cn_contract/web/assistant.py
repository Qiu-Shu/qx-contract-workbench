"""Authenticated transport for conversation records; GET never runs a model."""
import json
import re
import time
from uuid import UUID

from fastapi import Query, Request
from fastapi.responses import StreamingResponse

from .. import domain as d
from ..assistant import service
from ..security import ServiceError
from .request_context import actor_in, body_input, same_origin

STREAM_SECONDS = 15
POLL_SECONDS = .25
TERMINAL = frozenset({'completed','cancelled','failed','interrupted','blocked'})


def _cursor(request, after_seq):
    value = request.headers.get('Last-Event-ID')
    if value is None:
        return after_seq
    if not re.fullmatch(r'[0-9]{1,19}', value) or int(value) > 2**63-1:
        raise ServiceError('STATE_CONFLICT',422)
    return int(value)


def _events(read, first):
    """Poll window only; SQLite lock waits and socket backpressure may take longer."""
    deadline = time.monotonic()+STREAM_SECONDS
    page = first
    while True:
        for event in page.events:
            if time.monotonic() >= deadline:
                return
            envelope = {'run_id':str(page.run_id),'conversation_id':str(page.conversation_id),
                        **event.model_dump(mode='json')}
            yield f'id: {event.seq}\nevent: {event.event_type}\ndata: '+json.dumps(
                envelope,ensure_ascii=False,separators=(',',':'))+'\n\n'
        if page.state in TERMINAL and not page.has_more:
            return
        if time.monotonic() >= deadline:
            return
        if not page.has_more:
            # A comment keeps proxies alive without inventing a persisted event.
            yield ': waiting\n\n'
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(POLL_SECONDS,remaining))
        if time.monotonic() >= deadline:
            return
        try:
            page = read(page.next_after_seq)
        except ServiceError as error:
            if time.monotonic() >= deadline:
                return
            kind = 'access.revoked' if error.status_code in (401,403) else 'stream.reset'
            yield 'event: '+kind+'\ndata: '+json.dumps({'code':str(error.code)},separators=(',',':'))+'\n\n'
            return
        if time.monotonic() >= deadline:
            return


def register_routes(app, database):
    async def write(request, model, operation, *, conversation=None, run=None):
        with database.session() as db:
            actor = actor_in(request,db,write=True)
            if conversation is not None:
                service._owned(actor,conversation,db)
            elif run is not None:
                service.read_events(actor,run,db,limit=1)
            else:
                service._current(actor,db)
                service._workspace_id(db)
        value = await body_input(request,model)
        with database.session() as db:
            return operation(actor_in(request,db,write=True),value,db)

    @app.get('/api/assistant/skills')
    def skills(request:Request):
        with database.session() as db:
            service._current(actor_in(request,db),db)
            service._workspace_id(db)
        entries = [('client_reply','回复客户'),('material_organize','整理资料'),
                   ('contract_review','审查合同'),('content_draft','创作文案'),('legal_research','检索法律资料')]
        return d.AssistantSkillCatalog(items=tuple(d.AssistantSkillView(id=key,label=label,
            reason='对话执行尚未接入；已保存的输入不会自动运行模型。') for key,label in entries))

    @app.post('/api/assistant/conversations',status_code=201)
    async def create(request:Request):
        return await write(request,d.AssistantConversationCreateInput,service.create_conversation)

    @app.get('/api/assistant/conversations')
    def listing(request:Request,cursor:UUID|None=None,limit:int=Query(default=20,ge=1,le=50)):
        with database.session() as db:
            return service.list_conversations(actor_in(request,db),db,cursor=cursor,limit=limit)

    @app.get('/api/assistant/conversations/{identifier}')
    def conversation(identifier:UUID,request:Request):
        with database.session() as db:
            return service.read_conversation(actor_in(request,db),identifier,db)

    @app.put('/api/assistant/conversations/{identifier}/draft')
    async def draft(identifier:UUID,request:Request):
        return await write(request,d.AssistantDraftInput,
            lambda a,v,db:service.save_draft(a,identifier,v,db),conversation=identifier)

    @app.post('/api/assistant/conversations/{identifier}/messages',status_code=202)
    async def message(identifier:UUID,request:Request):
        return await write(request,d.AssistantMessageInput,
            lambda a,v,db:service.save_message(a,identifier,v,db),conversation=identifier)

    @app.get('/api/assistant/runs/{identifier}')
    def run(identifier:UUID,request:Request):
        with database.session() as db:
            return service.get_run(actor_in(request,db),identifier,db)

    @app.post('/api/assistant/runs/{identifier}/cancel')
    async def cancel(identifier:UUID,request:Request):
        return await write(request,d.AssistantCancelInput,
            lambda a,v,db:service.cancel_run(a,identifier,v,db),run=identifier)

    @app.get('/api/assistant/runs/{identifier}/events')
    def events(identifier:UUID,request:Request,after_seq:int=Query(default=0,ge=0,le=2**63-1)):
        same_origin(request)
        def read(after):
            with database.session() as db:
                return service.read_events(actor_in(request,db),identifier,db,after_seq=after)
        first = read(_cursor(request,after_seq))
        return StreamingResponse(_events(read,first),media_type='text/event-stream',
                                 headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})
