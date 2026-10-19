"""One application lifecycle owns only attempts it newly committed itself."""
import asyncio
from functools import partial

from sqlalchemy import text

from .. import domain as d
from ..ops.storage import require_active
from ..security import ServiceError
from . import service
from .providers import attempts
from .runner import execute_attempt

MAX_ACTIVE_TASKS = 4


class GenerationTasks:
    """start/submit run synchronously on the application's lifespan event loop."""

    def __init__(self, database, runtime):
        self.database = database
        self.runtime = runtime
        self._loop = None
        self._started = False
        self._tasks = {}
        self._closing = None
        self._last_error = None

    @property
    def active_count(self):
        return sum(not task.done() for task in self._tasks.values())

    @property
    def accepting(self):
        return self._started and self.active_count < MAX_ACTIVE_TASKS

    @property
    def last_error(self):
        # Bounded observation, with no exception object, source or credential.
        return self._last_error

    def start(self):
        loop = asyncio.get_running_loop()
        if self._started:
            if self._loop is not loop:
                raise ServiceError('STATE_CONFLICT', 409)
            return
        if self._closing is not None and not self._closing.done():
            raise ServiceError('ASSISTANT_BUSY', 409, retryable=True)
        self._loop = loop
        self._closing = None
        self._started = True

    def _admit(self):
        if not self._started or asyncio.get_running_loop() is not self._loop:
            raise ServiceError('STATE_CONFLICT', 409)
        if not self.accepting:
            raise ServiceError('ASSISTANT_BUSY', 409, retryable=True)

    def submit(self, actor, conversation_id, request):
        request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
        with self.database.session() as db:
            service._owned(actor, conversation_id, db)
            if request.requested_skill is not None:
                raise ServiceError('NOT_SUPPORTED', 422)
            if self.runtime is None:
                raise ServiceError('BLOCKED_LIVE', 403)
            # Database.session's BEGIN IMMEDIATE makes this classification and
            # the existing idempotent enqueue one serialized transaction.
            previous = db.scalar(text('''SELECT id FROM assistant_runs
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':str(conversation_id), 'request':str(request.request_id)})
            if previous is None:
                self._admit()
            view = attempts.enqueue_generation(actor, conversation_id, request, db, self.runtime)
        if previous is not None:
            return view
        # No task receives authority before the new durable attempt commits.
        coroutine = execute_attempt(actor, view.id, self.database, self.runtime)
        try:
            task = asyncio.create_task(coroutine, name='assistant-generation')
        except Exception:
            coroutine.close()
            self._last_error = 'GENERATION_TASK_FAILED'
            self._release_unsent(view.run_id)
            raise ServiceError('STATE_CONFLICT', 503) from None
        self._tasks[view.id] = task
        task.add_done_callback(partial(self._finished, view.id, view.run_id))
        return view

    def _release_unsent(self, run_id):
        try:
            with self.database.session() as db:
                require_active(db)
                # This run belongs to this manager. Never recover unrelated or
                # claimed attempts; the existing runner owns their settlement.
                attempts.cancel_reserved_for_run(run_id, db)
        except Exception:
            self._last_error = 'GENERATION_TASK_FAILED'
            # A failed write retains the original durable marker for locked
            # startup recovery. It is never requeued here.

    def _finished(self, identifier, run_id, task):
        self._tasks.pop(identifier, None)
        if not task.cancelled() and task.exception() is not None:
            self._last_error = 'GENERATION_TASK_FAILED'
        self._release_unsent(run_id)

    async def _drain(self, pending):
        await asyncio.gather(*pending, return_exceptions=True)

    async def close(self):
        if self._closing is None:
            if self._loop is not None and asyncio.get_running_loop() is not self._loop:
                raise ServiceError('STATE_CONFLICT', 409)
            self._started = False
            pending = tuple(self._tasks.values())
            # Do this before the first await: an unstarted runner cannot record
            # its own cancellation; its done callback seals the reservation.
            for task in pending:
                task.cancel()
            self._closing = asyncio.create_task(self._drain(pending), name='assistant-generation-close')
        cancelled = False
        while not self._closing.done():
            try:
                await asyncio.shield(self._closing)
            except asyncio.CancelledError:
                cancelled = True
        self._closing.result()
        if cancelled:
            raise asyncio.CancelledError()
