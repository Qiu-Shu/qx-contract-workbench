"""Synthetic task transport; ownership is checked before and after body parsing."""
import re
from uuid import UUID

from fastapi import Request

from .. import domain as d
from ..assistant.service import _owned
from ..ops.storage import require_active
from ..task_drafts import service
from .request_context import actor_in, body_input

_UUID=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_READ_PATH=re.compile(rf'/api/(?:assistant/conversations/{_UUID}/task-drafts|task-drafts/{_UUID}|task-executions/{_UUID})')


def is_task_read_path(path):
    return _READ_PATH.fullmatch(path) is not None


def register_routes(app, database):
    async def write(request, identifier, model, read, operation):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            read(actor, identifier, db=db)
            require_active(db)
        value = await body_input(request, model)
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            read(actor, identifier, db=db)
            require_active(db)
            return operation(actor, identifier, value, db=db)

    @app.post('/api/assistant/conversations/{cid}/task-bindings')
    def binding(cid: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            _owned(actor, cid, db)
            require_active(db)
            return service.create_binding(actor, cid, db=db)

    @app.get('/api/assistant/conversations/{cid}/task-drafts')
    def listing(cid: UUID, request: Request):
        with database.session() as db:
            return service.list_drafts(actor_in(request, db), cid, db=db)

    @app.post('/api/task-bindings/{identifier}/batches')
    async def receive(identifier: UUID, request: Request):
        return await write(request, identifier, d.TaskInboxBatchInput,
                           service.read_binding, service.receive_batch)

    @app.get('/api/task-drafts/{identifier}')
    def draft(identifier: UUID, request: Request):
        with database.session() as db:
            return service.read_draft(actor_in(request, db), identifier, db=db)

    @app.patch('/api/task-drafts/{identifier}')
    async def update(identifier: UUID, request: Request):
        return await write(request, identifier, d.TaskDraftUpdateInput,
                           service.read_draft, service.update_draft)

    @app.post('/api/task-drafts/{identifier}/freeze')
    async def freeze(identifier: UUID, request: Request):
        return await write(request, identifier, d.TaskFreezeInput,
                           service.read_draft, service.freeze_draft)

    @app.get('/api/task-executions/{identifier}')
    def execution(identifier: UUID, request: Request):
        with database.session() as db:
            return service.read_execution(actor_in(request, db), identifier, db=db)

    @app.post('/api/task-executions/{identifier}/cancel')
    def cancel(identifier: UUID, request: Request):
        with database.session() as db:
            actor = actor_in(request, db, write=True)
            service.read_execution(actor, identifier, db=db)
            require_active(db)
            return service.cancel_execution(actor, identifier, db=db)

    @app.post('/api/task-executions/{identifier}/prepare')
    async def prepare(identifier: UUID, request: Request):
        from ..task_drafts.bridge import prepare_execution
        return await write(request, identifier, d.TaskExecutionPrepareInput,
                           service.read_execution, prepare_execution)

    @app.post('/api/task-executions/{identifier}/review')
    async def review(identifier: UUID, request: Request):
        from ..task_drafts.bridge import review_execution
        return await write(request, identifier, d.TaskExecutionReviewInput,
                           service.read_execution, review_execution)
