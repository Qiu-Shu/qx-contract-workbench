"""One application lifecycle owns newly committed model and local research work."""
import asyncio
from functools import partial
from uuid import UUID

from sqlalchemy import text

from .. import domain as d
from ..ops.storage import require_active
from ..security import ServiceError
from . import service
from .providers import attempts, judge_attempts, judge_execution
from .providers.judge_policy import JudgeRuntime
from .providers.registry import resolve_runtime
from .runner import execute_attempt

MAX_ACTIVE_TASKS = 4


class GenerationTasks:
    """start/submit run synchronously on the application's lifespan event loop."""

    def __init__(self, database, runtime, *, judge_runtime=None, library_adapter=None):
        if judge_runtime is not None and type(judge_runtime) is not JudgeRuntime:
            raise TypeError('trusted JudgeRuntime required')
        self.database = database
        self.runtime = runtime
        self.judge_runtime = judge_runtime
        self.library_adapter = library_adapter
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
            conversation = service._owned(actor, conversation_id, db)
            if request.requested_skill is not None:
                raise ServiceError('NOT_SUPPORTED', 422)
            # Select once under current DB authority. This same lease survives
            # dispatch; a later setting/grant cannot switch this attempt.
            runtime = resolve_runtime(self.runtime, actor, service._snapshot(conversation))
            if runtime is None:
                raise ServiceError('BLOCKED_LIVE', 403)
            # Database.session's BEGIN IMMEDIATE makes this classification and
            # the existing idempotent enqueue one serialized transaction.
            previous = db.scalar(text('''SELECT id FROM assistant_runs
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':str(conversation_id), 'request':str(request.request_id)})
            if previous is None:
                self._admit()
            view = attempts.enqueue_generation(actor, conversation_id, request, db, runtime)
            auxiliary = self._reserve_judge(actor, view, db) if previous is None else None
        if previous is not None:
            return view
        # No task receives authority before the new durable attempt commits.
        self._dispatch(view.id, view.run_id, self._execute(actor, view.id, runtime, auxiliary))
        return view

    def submit_material(self, actor, conversation_id, request):
        from . import material_preparation as inputs, material_attempts
        request = d.MainMaterialSelection.model_validate(request.model_dump(mode='python'))
        with self.database.session() as db:
            conversation = service._owned(actor, conversation_id, db)
            runtime = resolve_runtime(self.runtime, actor, service._snapshot(conversation))
            if runtime is None:
                raise ServiceError('BLOCKED_LIVE', 403)
            config, _ = runtime.snapshot_for(actor, request.expected_scope)
            previous = attempts._previous(conversation_id, request.request_id, db)
            if previous:
                saved = attempts._input(attempts._row(previous['attempt_id'], db))
                if type(saved) is not d.MainMaterialPreparedInput or inputs.selection_for(saved.request.basis) != request:
                    raise ServiceError('VERSION_CONFLICT', 409)
                return attempts.read_attempt(actor, UUID(previous['attempt_id']), db)
            self._admit()
        basis = inputs.preview(actor, request, self.database, config)
        with self.database.session() as db:
            view = material_attempts.enqueue(actor, request, basis, db, runtime)
        self._dispatch(view.id, view.run_id, self._execute(actor, view.id, runtime, None))
        return view

    def submit_profile(self, actor, conversation_id, request):
        """One profile-purpose answer, using the existing single-attempt lifecycle."""
        if type(request) is not d.MainProfileSubmission:
            raise ValueError('profile submission required')
        request = d.MainProfileSubmission.model_validate(request.model_dump(mode='python'))
        message = d.AssistantMessageInput.model_validate(
            request.model_dump(mode='python', exclude={'project_intake'}))
        with self.database.session() as db:
            conversation = service._owned(actor, conversation_id, db)
            runtime = resolve_runtime(self.runtime, actor, service._snapshot(conversation))
            if runtime is None:
                raise ServiceError('BLOCKED_LIVE', 403)
            previous = db.scalar(text('''SELECT id FROM assistant_runs
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':str(conversation_id), 'request':str(request.request_id)})
            if previous is None:
                self._admit()
            view = attempts.enqueue_profile(actor, conversation_id, message, db, runtime,
                                            project_intake=request.project_intake)
        if previous is None:
            # The committed purpose-bound lease never reserves or runs Jev.
            self._dispatch(view.id, view.run_id, self._execute(actor, view.id, runtime, None))
        return view

    def submit_context(self, actor, conversation_id, request):
        """One source-bound answer; the context branch never reserves or runs Jev."""
        request = d.MainContextSubmission.model_validate(request.model_dump(mode='python'))
        with self.database.session() as db:
            conversation = service._owned(actor, conversation_id, db)
            runtime = resolve_runtime(self.runtime, actor, service._snapshot(conversation))
            if runtime is None:
                raise ServiceError('BLOCKED_LIVE', 403)
            previous = db.scalar(text('''SELECT id FROM assistant_runs
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':str(conversation_id), 'request':str(request.request_id)})
            if previous is None:
                self._admit()
            view = attempts.enqueue_context(actor, conversation_id, request, db, runtime)
        if previous is not None:
            return view
        # A valid Jev grant is explicitly ignored: zero reservation, zero calls.
        if view.input_format == 'library-context-v2':
            adapter = self.library_adapter
            if adapter is None:
                from .tools.library import LegalLibraryAdapter
                adapter = LegalLibraryAdapter(None)
            self._dispatch(view.id, view.run_id, self._execute_rounds(actor, view.id, runtime, adapter))
        else:
            self._dispatch(view.id, view.run_id, self._execute(actor, view.id, runtime, None))
        return view

    def submit_research(self, actor, conversation_id, request):
        from . import research
        request = d.AssistantMessageInput.model_validate(request.model_dump(mode='python'))
        with self.database.session() as db:
            service._owned(actor, conversation_id, db)
            previous = db.scalar(text('''SELECT id FROM assistant_runs
                WHERE conversation_id=:cid AND request_id=:request'''),
                {'cid':str(conversation_id), 'request':str(request.request_id)})
            if previous is None:
                self._admit()
            view = research.enqueue_research(actor, conversation_id, request, db)
        if previous is None:
            self._dispatch(view.run.id, view.run.id, self._execute_research(actor, view.run.id), local=True)
        return view

    def _dispatch(self, identifier, run_id, coroutine, *, local=False):
        try:
            task = asyncio.create_task(coroutine, name='assistant-generation')
        except Exception:
            coroutine.close()
            self._last_error = 'GENERATION_TASK_FAILED'
            self._release_unsent(run_id, local=local)
            raise ServiceError('STATE_CONFLICT', 503) from None
        self._tasks[identifier] = task
        task.add_done_callback(partial(self._finished, identifier, run_id, local))

    async def _execute_research(self, actor, run_id):
        from . import research
        from .tools.library import LegalLibraryAdapter
        adapter = self.library_adapter if self.library_adapter is not None else LegalLibraryAdapter(None)
        worker = asyncio.create_task(asyncio.to_thread(
            research.execute_research, actor, run_id, self.database, adapter))
        cancelled = False
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                if not cancelled:
                    self._release_unsent(run_id, local=True)
                cancelled = True
            except Exception:
                break
        # A cancelled await cannot kill a thread. Keep its admission slot until
        # it exits, after sealing the run against any late publication.
        if cancelled:
            if not worker.cancelled():
                worker.exception()
            raise asyncio.CancelledError()
        return worker.result()

    def _reserve_judge(self, actor, main, db):
        if self.judge_runtime is None:
            return None
        transaction = db.get_transaction()
        auxiliary = judge_attempts.reserve(actor, main.run_id, db, self.judge_runtime, optional=True)
        if transaction is None or db.get_transaction() is not transaction or not transaction.is_active:
            raise ServiceError('STATE_CONFLICT', 409)
        return auxiliary

    async def _execute(self, actor, identifier, runtime, auxiliary):
        if auxiliary is not None:
            await judge_execution.execute_attempt(actor, auxiliary.id, self.database, self.judge_runtime)
        # The original main lease still performs its own current-scope, session,
        # cancellation and permission checks after the optional wait.
        return await execute_attempt(actor, identifier, self.database, runtime)

    async def _execute_rounds(self, actor, identifier, runtime, adapter):
        from .rounds_runner import execute_context_run
        return await execute_context_run(actor, identifier, self.database, runtime, adapter)

    def _release_unsent(self, run_id, *, local=False):
        try:
            with self.database.session() as db:
                require_active(db)
                if local:
                    from .research import interrupt_research
                    interrupt_research(run_id, db)
                    return
                # This run belongs to this manager. Never recover unrelated or
                # claimed attempts; the existing runner owns their settlement.
                attempts.cancel_reserved_for_run(run_id, db)
                judge_attempts.cancel_reserved_for_run(run_id, db)
        except Exception:
            self._last_error = 'GENERATION_TASK_FAILED'
            # A failed write retains the original durable marker for locked
            # startup recovery. It is never requeued here.

    def _finished(self, identifier, run_id, local, task):
        self._tasks.pop(identifier, None)
        if not task.cancelled() and task.exception() is not None:
            self._last_error = 'GENERATION_TASK_FAILED'
        self._release_unsent(run_id, local=local)

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
