"""Bounded serial rounds loop: model round -> fixed library handlers -> next/final.

Every round is a durably claimed attempt; tool calls go through the fixed
handler seam with server-owned call ids; the loop only stops on a final
candidate, an error, or a persisted bounded-stop cause.
"""
import asyncio
from uuid import uuid4

from sqlalchemy import text

from .. import domain as d
from ..review.model_adapter import strict_json
from ..security import ServiceError
from .library_handlers import begin_library_call, execute_library_handler
from .providers import attempts
from .runner import execute_attempt


def _round_state(actor, attempt_id, db):
    """Post-settle durable truth: final, failed, or the persisted plan."""
    view = attempts.read_attempt(actor, attempt_id, db)
    if view.state != 'received':
        return view, None
    if view.output is not None or view.receipt is None or view.receipt.error_code is not None:
        return view, None
    row = db.execute(text('''SELECT payload_json FROM assistant_run_events
        WHERE run_id=:run AND event_type='model.tool_plan' ORDER BY seq DESC LIMIT 1'''),
        {'run': str(view.run_id)}).mappings().first()
    if row is None:
        return view, None
    payload = strict_json(row['payload_json'])
    if payload.get('attempt_id') != str(attempt_id):
        return view, None
    return view, d.MainContextToolPlan.model_validate(payload['plan'])


async def _execute_plan(actor, run_id, plan, database, adapter):
    """Execute the persisted plan through the fixed handler seam only."""
    for item in plan.calls:
        request = d.LibraryHandlerRequest(tool=item.tool, query=item.query,
                                          saved_citation_id=item.saved_citation_id)
        call = begin_library_call(actor, run_id, uuid4(), request, database)
        # The adapter performs library I/O off the event loop; begin/publish
        # stay short in-loop transactions exactly like the attempt ledger.
        await asyncio.to_thread(execute_library_handler, actor, run_id,
                                call.event_seq, database, adapter)


async def execute_context_run(actor, attempt_id, database, runtime, adapter):
    """Drive one bounded-rounds run to a final, failed or bounded-stop state."""
    view = await execute_attempt(actor, attempt_id, database, runtime)
    while True:
        with database.session() as db:
            view, plan = _round_state(actor, view.id, db)
            if plan is None:
                return view
            row = db.execute(text('''SELECT round_no,policy_json FROM assistant_model_attempts
                WHERE id=:id'''), {'id': str(view.id)}).mappings().first()
            round_no = row['round_no']
            policy = d.MainModelPolicy.model_validate(strict_json(row['policy_json']))
            run_id = view.run_id
        if round_no >= policy.max_calls:
            # The last granted round produced a plan: stop before any tool runs.
            with database.session() as db:
                attempts.bounded_stop(actor, run_id, view.id, 'rounds_exhausted', db)
            with database.session() as db:
                return attempts.read_attempt(actor, view.id, db)
        try:
            await _execute_plan(actor, run_id, plan, database, adapter)
        except ServiceError as error:
            if error.code == 'STATE_CONFLICT':
                # The run was sealed meanwhile (cancel/recover); never re-dispatch.
                with database.session() as db:
                    return attempts.read_attempt(actor, view.id, db)
            reason = 'tool_limit' if error.code == 'LIBRARY_TOOL_LIMIT' else 'tool_rejected'
            with database.session() as db:
                attempts.bounded_stop(actor, run_id, view.id, reason, db)
            with database.session() as db:
                return attempts.read_attempt(actor, view.id, db)
        with database.session() as db:
            try:
                identifier = attempts.dispatch_round(actor, run_id, round_no + 1, db, runtime)
            except ServiceError as error:
                if error.code == 'STATE_CONFLICT':
                    # The run was sealed meanwhile (cancel/recover); never re-dispatch.
                    return attempts.read_attempt(actor, view.id, db)
                if error.code != 'BUDGET_EXCEEDED':
                    raise
                identifier = None
                stop_reason = 'budget_exhausted'
            else:
                stop_reason = 'rounds_exhausted'
        if identifier is None:
            with database.session() as db:
                attempts.bounded_stop(actor, run_id, view.id, stop_reason, db)
            with database.session() as db:
                return attempts.read_attempt(actor, view.id, db)
        view = await execute_attempt(actor, identifier, database, runtime)
