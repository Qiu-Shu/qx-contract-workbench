"""Exact one-item synthetic engineering path and fail-closed real smoke entry."""
import json
from uuid import UUID

from ..persistence import Database
from ..security import ServiceError
from ..queries import storage, planner, ledger
from ..ops.storage import require_active


def _current(plan_id, actor, *, database, matter_id, approval_id=None):
    if not isinstance(database, Database) or actor is None or matter_id is None:
        raise ServiceError('BLOCKED_LIVE', 403)
    with storage.factory_transaction(database, actor, matter_id) as db:
        storage.authorize_query(actor, matter_id, db)
        require_active(db)
        value = planner.read_plan(plan_id, actor, matter_id=matter_id, db=db, require_approved=True)
        if value.scope == 'Q0' or len(value.items) != 1 or value.items[0].pages != 1 or value.max_calls != 1:
            raise ServiceError('QUERY_SCOPE_UNAPPROVED', 403)
        row = planner._row(plan_id, matter_id, db)
        approved = storage.latest('plan_approval', row.ref, db)
        if approval_id is not None:
            supplied = storage.by_ref(approval_id, 'plan_approval', db)
            if not supplied or not approved or supplied.ref != approved.ref or supplied.parent != row.ref:
                raise ServiceError('PLAN_UNAPPROVED', 403)
            payload = json.loads(supplied.payload)
            if payload.get('approved') is not True or payload.get('plan_sha256') != value.plan_sha256:
                raise ServiceError('PLAN_UNAPPROVED', 403)
        state = ledger.read_budget(matter_id, actor, db=db)
        if state['approved_credits'] <= 0 or state['incident']:
            raise ServiceError('BUDGET_EXCEEDED', 403)
        # Unknown/confirmed replays are delegated to the same T08 durable key;
        # no alternate invocation or newly created plan is used here.
        return value


async def run_live_smoke(approval_id: UUID, plan_id: UUID, actor, *, database=None, matter_id=None):
    if not isinstance(approval_id, UUID) or not isinstance(plan_id, UUID):
        raise ServiceError('BLOCKED_LIVE', 403)
    _current(plan_id, actor, database=database, matter_id=matter_id, approval_id=approval_id)
    # A case plan approval is an actual engineering record, but it is not the
    # absent real account/license/region/data/key/official-price/adapter grant.
    # There is deliberately no live transport injection, environment fallback,
    # or branch accepting a caller's production-ready boolean.
    raise ServiceError('BLOCKED_LIVE', 403)


async def run_synthetic_smoke(plan_id: UUID, actor, *, database, matter_id):
    """Server engineering API only; no CLI or HTTP switch upgrades real smoke."""
    value = _current(plan_id, actor, database=database, matter_id=matter_id)
    from ..providers import qcc_registry
    with storage.factory_transaction(database, actor, matter_id) as db:
        # Re-read after the first short transaction, then the T08 gateway checks
        # again at reserve/mark/claim. No transaction spans provider IO.
        current = planner.read_plan(plan_id, actor, matter_id=matter_id, db=db, require_approved=True)
        if current != value:
            raise ServiceError('PLAN_CHANGED', 409)
        binding = qcc_registry.read_binding(value.items[0].tool_binding_ref, actor=actor, matter_id=matter_id, db=db)
        endpoint = qcc_registry.read_case_endpoint(binding.endpoint_config_ref, actor=actor, matter_id=matter_id, db=db)
        if endpoint.get('synthetic') is not True or endpoint.get('live_allowed') is not False:
            raise ServiceError('BLOCKED_LIVE', 403)
    from ..queries.gateway import execute_plan
    receipts = await execute_plan(plan_id, actor, database=database, matter_id=matter_id,
        expected_plan_sha256=value.plan_sha256)
    if len(receipts) != 1 or 'SYNTHETIC_ONLY' not in receipts[0].coverage_limit:
        raise ServiceError('BLOCKED_LIVE', 409)
    return receipts[0]
