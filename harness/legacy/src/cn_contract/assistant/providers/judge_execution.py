"""Execute exactly one persisted claim, with no database transaction across HTTP."""
import asyncio

from ... import domain as d
from ...security import ServiceError
from . import judge_attempts as attempts
from .jev import JevCancelledError
from .judge_policy import copy


async def execute_attempt(actor, identifier, database, runtime):
    runtime.bind_execution()
    with database.session() as db:
        claimed = attempts.claim(actor, identifier, db, runtime)
    if claimed is None:
        with database.session() as db:
            return attempts.read_attempt(actor, identifier, db)
    token, request, config = claimed
    provider = runtime.provider

    def guard(value, expected):
        try:
            with database.session() as db:
                attempts.preflight(actor, identifier, token, value, expected, db, runtime)
        except (ServiceError, ValueError) as error:
            return 'no_budget' if getattr(error, 'code', None) == 'BUDGET_EXCEEDED' else 'stale_scope'
        return None

    cancelled = False
    try:
        # The exact JevProvider owns the one deadline, including parsed receipts
        # during cleanup. A second earlier timer would erase received accounting.
        result = await provider.judge(request, expected_config=config, preflight=guard)
    except JevCancelledError as error:
        cancelled = True; result = error.result
    except asyncio.CancelledError:
        cancelled = True; result = None
    except Exception:
        result = None
    try:
        # The cancellation channel crosses the same identity boundary as success.
        result = copy(d.JudgeResult, result)
        if (result.local_request_id != request.local_request_id or result.scope != request.scope
                or result.input_hash != attempts.jev_codec.input_hash(request, config)):
            raise ValueError()
        if cancelled and (result.evidence != 'received' or result.status == 'ok'):
            raise ValueError()
    except Exception:
        result = None
    with database.session() as db:
        if result is None:
            row = attempts._row(identifier, db)
            result = attempts.fallback(row)
        attempts.settle(actor, identifier, token, result, db, runtime)
    if cancelled:
        raise asyncio.CancelledError()
    with database.session() as db:
        return attempts.read_attempt(actor, identifier, db)
