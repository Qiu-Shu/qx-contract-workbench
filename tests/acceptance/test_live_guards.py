"""T13 actual backend guards; technical fixtures never confer real approval."""
import asyncio
import importlib
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from cn_contract.domain import ReadinessEvidence
from cn_contract.security import ServiceError
from tests.helpers.synthetic_queries import setup, plan, api


def service(module, name):
    try:
        value = importlib.import_module('cn_contract.live.' + module)
    except ModuleNotFoundError as exc:
        assert exc.name not in {'cn_contract.live', 'cn_contract.live.' + module}, 'T13 backend guard is required'
        raise
    result = getattr(value, name, None)
    assert callable(result), 'T13 backend service is required'
    return result


def evidence(refs=()):
    return ReadinessEvidence(**{name: refs for name in ReadinessEvidence.model_fields})


def approval(world, value):
    with world[0].session() as db:
        row = api()._row(value.id, world[3].id, db)
        return __import__('uuid').UUID(api('storage').latest('plan_approval', row.ref, db).ref)


def no_ledger(world):
    with world[0].session() as db:
        assert db.scalar(select(func.count()).select_from(api('storage').QueryLedgerRow)) == 0


def test_no_approval_no_request(tmp_path):
    world = setup(tmp_path); value = plan(world)
    run = service('guards', 'run_live_smoke')
    with pytest.raises(ServiceError) as error:
        asyncio.run(run(uuid4(), value.id, world[2], database=world[0], matter_id=world[3].id))
    assert error.value.code in {'BLOCKED_LIVE', 'PLAN_UNAPPROVED'}
    no_ledger(world)


def test_mock_not_production(tmp_path):
    path = tmp_path/'all-approved.json'
    path.write_text('{"decision":"GO","mock":false,"approved":true}', encoding='utf-8')
    result = service('readiness', 'assess_go_live')(evidence((str(path),)))
    assert result.decision == 'BLOCKED' and result.reasons['real_evidence_trust'] == 'NOT_IMPLEMENTED'


def test_missing_legal_benchmark():
    result = service('readiness', 'assess_go_live')(evidence())
    assert result.decision == 'BLOCKED' and result.reasons['legal_gold'] == 'PENDING_TWO_REAL_REVIEWERS'


@pytest.mark.parametrize('pages', [1, 2])
def test_scoped_live(tmp_path, pages):
    world = setup(tmp_path, price='5')
    from tests.helpers.synthetic_qcc import sdk_server
    from tests.helpers.synthetic_queries import bind_loopback
    with sdk_server() as (cfg, counts, server):
        server.remove_tool('synthetic_identity')
        @server.tool(name='synthetic_identity', structured_output=True)
        def paged(name: str, page: int = 1) -> dict[str, str | bool]:
            counts['call'] += 1
            return {'synthetic': True, 'state': 'unknown', 'pages_complete': False, 'trace': str(uuid4())}
        world = bind_loopback(world, cfg)
        authorization = None
        if pages > 1:
            with world[0].session() as db:
                authorization = api().approve_query_scope(world[3].id, world[4].id,
                    '独立虚构履约身份核验', 'Q1', world[2], db=db, max_pages=pages)
        value = plan(world, pages=pages, authorization_id=authorization)
        run = service('guards', 'run_live_smoke')
        with pytest.raises(ServiceError) as error:
            asyncio.run(run(approval(world, value), value.id, world[2], database=world[0], matter_id=world[3].id))
        assert error.value.code == ('BLOCKED_LIVE' if pages == 1 else 'QUERY_SCOPE_UNAPPROVED')
        assert counts['call'] == 0
        no_ledger(world)


@pytest.mark.parametrize('mode', ['success', 'timeout'])
def test_separate_synthetic_smoke_exact_one_durable_call(tmp_path, mode):
    world = setup(tmp_path, mode=mode); value = plan(world)
    run = service('guards', 'run_synthetic_smoke')
    first = asyncio.run(run(value.id, world[2], database=world[0], matter_id=world[3].id))
    second = asyncio.run(run(value.id, world[2], database=world[0], matter_id=world[3].id))
    assert first.id == second.id and 'SYNTHETIC_ONLY' in first.coverage_limit
    with world[0].session() as db:
        state = api('ledger').read_budget(world[3].id, world[2], db=db)
        assert state['calls'] == 1 and state['remaining'] == 5
        assert db.scalar(select(func.count()).select_from(api('storage').QueryLedgerRow)) == 1
    assert first.billing_state == ('confirmed' if mode == 'success' else 'sent_unknown')


@pytest.mark.parametrize('change', ['revoked_session', 'membership', 'role', 'plan_revoke', 'price', 'budget_revoke'])
def test_live_current_backend_denials_before_dispatch(tmp_path, change):
    world = setup(tmp_path); value = plan(world); ref = approval(world, value)
    from cn_contract.persistence import MembershipRow, UserRow
    from cn_contract.security import revoke_session
    with world[0].session() as db:
        if change == 'revoked_session': revoke_session(world[2].session_id, db)
        elif change == 'membership': db.delete(db.get(MembershipRow, (str(world[3].id), str(world[2].user_id))))
        elif change == 'role': db.get(UserRow, str(world[2].user_id)).roles = '["assistant"]'
        elif change == 'plan_revoke': api().revoke_plan(value.id, world[2], matter_id=world[3].id, db=db)
        elif change == 'price': api('storage').register_synthetic_price(world[5], '10', actor=world[1], db=db)
        else: api().revoke_case_budget(world[3].id, world[2], db=db)
    with pytest.raises(ServiceError):
        asyncio.run(service('guards', 'run_live_smoke')(ref, value.id, world[2], database=world[0], matter_id=world[3].id))
    no_ledger(world)


def test_current_protected_billing_incident_is_no_go(tmp_path):
    from tests.helpers.synthetic_queries import execute
    world = setup(tmp_path, mode='overcharge'); value = plan(world)
    execute(world, value)
    decision = service('readiness', 'assess_go_live')(evidence(), database=world[0], actor=world[2], matter_id=world[3].id)
    assert decision.decision == 'NO_GO' and decision.reasons['engineering_ledger'] == 'HARD_FAIL_BILLING_INCIDENT'
    assert decision.real_evidence_trust == 'NOT_IMPLEMENTED' and decision.real_provider_requests == 0


def test_six_references_and_forged_domain_go_never_authorize(tmp_path):
    from cn_contract.domain import ReadinessDecision
    from pydantic import ValidationError
    refs = evidence((str(tmp_path/'anything.json'),))
    with pytest.raises(ValidationError):
        ReadinessDecision(decision='GO', evidence=refs, reasons={'all': 'client PASS'})
    result = service('readiness', 'assess_go_live')(refs)
    assert result.decision == 'BLOCKED' and result.evidence is None


def test_readiness_reference_bytes_are_data_and_change_hash(tmp_path):
    from cn_contract.config import PROJECT_ROOT
    root = PROJECT_ROOT/'.audit-local'/('t13-untrusted-'+uuid4().hex)
    root.mkdir()
    path = root/'data.py'
    marker = root/'not-executed'
    path.write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("bad")\n', encoding='utf-8')
    first = service('readiness', 'assess_go_live')(evidence((str(path),)))
    assert first.decision == 'BLOCKED' and len([k for k in first.evidence_hashes if not k.startswith('server/')]) == 6 and not marker.exists()
    path.write_text('{"decision":"GO","lawyers":["same","same"],"scores":100}', encoding='utf-8')
    second = service('readiness', 'assess_go_live')(evidence((str(path),)))
    assert first.evidence_hashes != second.evidence_hashes and second.decision == 'BLOCKED'


def test_real_cli_missing_backend_nonzero_no_force_no_keys():
    import json, subprocess, sys
    from cn_contract.config import PROJECT_ROOT
    args = [sys.executable, '-X', 'utf8', '-m', 'cn_contract.cli', 'qcc-smoke', '--approval-id', str(uuid4()), '--plan-id', str(uuid4())]
    result = subprocess.run(args, cwd=PROJECT_ROOT, capture_output=True, encoding='utf-8', shell=False)
    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data['code'] == 'BLOCKED_LIVE' and data['real_provider_requests'] == data['paid_requests'] == data['material_uploads'] == 0
    force = subprocess.run([*args, '--force'], cwd=PROJECT_ROOT, capture_output=True, encoding='utf-8', shell=False)
    assert force.returncode != 0 and 'unrecognized arguments' in force.stderr


@pytest.mark.parametrize('incident', [False, True])
def test_protected_incident_survives_budget_revocation(tmp_path, incident):
    from tests.helpers.synthetic_queries import execute
    world = setup(tmp_path, mode='overcharge' if incident else 'success')
    execute(world, plan(world))
    with world[0].session() as db:
        api().revoke_case_budget(world[3].id, world[2], db=db)
    result = service('readiness', 'assess_go_live')(evidence(), database=world[0], actor=world[2], matter_id=world[3].id)
    assert result.decision == ('NO_GO' if incident else 'BLOCKED')


def test_actual_canonical_source_and_runtime_gates_reread():
    import hashlib
    from cn_contract.config import PROJECT_ROOT
    result = service('readiness', 'assess_go_live')(evidence())
    assert result.server_gate_counts == {'source': 9, 'runtime': 59, 'total': 77}
    assert result.evidence_hashes['server/source_lock'] == hashlib.sha256((PROJECT_ROOT/'sources/upstream.lock.json').read_bytes()).hexdigest()
    assert result.evidence_hashes['server/config'] == hashlib.sha256((PROJECT_ROOT/'config/defaults.json').read_bytes()).hexdigest()
    assert result.decision == 'BLOCKED'


@pytest.mark.parametrize('ref', ['https://no-request.invalid/private', '\\\\no-request.invalid\\share\\file.json', 'sources/upstream.lock.json:private', 'C:/outside/private.json'])
def test_unsafe_ref_denied_before_filesystem_probe(ref, monkeypatch):
    module = importlib.import_module('cn_contract.live.readiness')
    probed = []
    original = module.checked_file
    def observed(path, *args, **kwargs):
        probed.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(module, 'checked_file', observed)
    result = module.assess_go_live(evidence((ref,)))
    assert result.decision == 'BLOCKED' and probed == []


def test_smoke_handoff_rejects_actual_new_wider_plan_before_send(tmp_path, monkeypatch):
    from cn_contract.domain import QueryPlanInput, QueryItemInput
    from tests.helpers.synthetic_qcc import sdk_server
    from tests.helpers.synthetic_queries import bind_loopback
    from cn_contract.queries import gateway
    world = setup(tmp_path)
    with sdk_server() as (cfg, counts, server):
        server.remove_tool('synthetic_identity')
        @server.tool(name='synthetic_identity', structured_output=True)
        def paged(name: str, page: int = 1) -> dict[str, str | bool]:
            counts['call'] += 1
            return {'synthetic': True, 'state': 'success', 'pages_complete': True, 'trace': str(uuid4())}
        world = bind_loopback(world, cfg)
        with world[0].session() as db:
            scope = api().approve_query_scope(world[3].id, world[4].id, '独立虚构履约身份核验', 'Q1', world[2], db=db, max_pages=2)
        value = plan(world, authorization_id=scope)
        original = gateway.execute_plan
        async def change_in_handoff(*args, **kwargs):
            with world[0].session() as db:
                wider = api().create_query_plan(QueryPlanInput(matter_id=world[3].id, party_id=world[4].id,
                    purpose=value.purpose, items=(QueryItemInput(capability_key='synthetic.identity', pages=2),),
                    authorization_id=scope, scope='Q1'), world[2], db=db, plan_id=value.id)
                api().approve_plan(wider.id, wider.plan_sha256, world[2], matter_id=world[3].id, db=db)
            return await original(*args, **kwargs)
        monkeypatch.setattr(gateway, 'execute_plan', change_in_handoff)
        with pytest.raises(ServiceError):
            asyncio.run(service('guards', 'run_synthetic_smoke')(value.id, world[2], database=world[0], matter_id=world[3].id))
        assert counts['call'] == 0
        no_ledger(world)
