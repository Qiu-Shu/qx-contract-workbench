from datetime import datetime, timezone
from uuid import uuid4
import pytest
from cn_contract.security import ServiceError
from tests.helpers.synthetic_qcc import setup, ready, run, config


def test_owner_grant_required(tmp_path):
    database, actor, matter, r = setup(tmp_path, grant=False)
    with database.session() as db, pytest.raises(ServiceError):
        r.register_endpoint(config(), actor=actor, db=db)


def test_client_approval_is_not_authority(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    _, _, _, value = run(ready(database, actor, matter, r))
    forged = value.model_copy(update={'approved_by': actor.user_id, 'approved_at': datetime.now(timezone.utc)})
    with database.session() as db, pytest.raises(ServiceError):
        r.bind_capability(forged, actor=actor, db=db)


def test_unknown_tool_zero_requests(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, value = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    with database.session() as db:
        transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
        with pytest.raises(ServiceError):
            run(transport.invoke(binding.model_copy(update={'tool_name': 'invented'}), {'name': 'SYNTHETIC'}, uuid4()))
        assert transport.dispatch_count == 0


def test_output_schema_drift_invalidates_binding(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    with database.session() as db:
        r.register_mock_catalog_variant(endpoint, 'output_changed', actor=actor, db=db)
        run(r.discover_tools(endpoint, actor=actor, matter_id=matter.id, db=db))
        assert not r.read_binding(ref, actor=actor, db=db).enabled


def test_live_and_process_transport_block_before_send(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    for cfg in (config('https://example.invalid/mcp', 'streamable_http'), config('cmd /c attack', 'stdio')):
        with database.session() as db, pytest.raises(ServiceError) as error:
            r.register_endpoint(cfg, actor=actor, db=db)
        assert error.value.code == 'BLOCKED_LIVE'


def test_mock_raw_protected_and_unknown_not_clean(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    with database.session() as db:
        transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
        result = run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert result.status.value == 'sent_unknown'
        assert result.raw_ref and result.raw_sha256 and result.billing_known
        assert r.read_raw(result.raw_ref, actor=actor, matter_id=matter.id, db=db)['synthetic'] is True


def test_case_lawyer_can_use_owner_approved_binding_without_manage_permission(tmp_path):
    database, owner, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, owner, matter, r))
    from cn_contract.security import provision_user, set_membership, login, authenticate
    from cn_contract.domain import Role
    from cn_contract.providers.qcc_mcp import QccTransport
    with database.session() as db:
        user = provision_user('only-lawyer', 'local-test-password', {Role.HANDLING_LAWYER}, db)
        set_membership(matter.id, user, db)
        token, _ = login('only-lawyer', 'local-test-password', db); actor = authenticate(token, db)
        result = run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert result.raw_ref and result.billing_known
        with pytest.raises(ServiceError):
            r.register_synthetic_price(endpoint, actor=actor, db=db)


@pytest.mark.parametrize('field', ['schema_hash', 'provider', 'input_schema_snapshot', 'output_schema_snapshot', 'price_snapshot_id', 'unit_price', 'price_unit'])
def test_binding_rejects_client_claims(tmp_path, field):
    database, actor, matter, r = setup(tmp_path)
    _, _, _, value = run(ready(database, actor, matter, r))
    from decimal import Decimal
    bad = {'schema_hash': '0'*64, 'provider': 'qcc', 'input_schema_snapshot': {}, 'output_schema_snapshot': {},
           'price_snapshot_id': uuid4(), 'unit_price': Decimal('1'), 'price_unit': 'credits/unknown'}
    with database.session() as db, pytest.raises(ServiceError):
        r.bind_capability(value.model_copy(update={field: bad[field]}), actor=actor, db=db)


def test_latest_price_invalidates_binding(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    with database.session() as db:
        r.register_synthetic_price(endpoint, actor=actor, db=db)
        assert not r.read_binding(ref, actor=actor, db=db).enabled


def test_input_drift_detected_at_dispatch_before_business_call(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    with database.session() as db:
        r.register_mock_catalog_variant(endpoint, 'input_changed', actor=actor, db=db)
        transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
        with pytest.raises(ServiceError):
            run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert transport.dispatch_count == 0
        assert not r.read_binding(ref, actor=actor, db=db).enabled


def test_cross_matter_and_expired_session_zero_dispatch(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    from cn_contract.security import revoke_session
    with database.session() as db:
        transport = QccTransport(endpoint, actor=actor, matter_id=uuid4(), db=db)
        with pytest.raises(ServiceError): run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert transport.dispatch_count == 0
        revoke_session(actor.session_id, db)
        transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
        with pytest.raises(ServiceError): run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert transport.dispatch_count == 0


def test_raw_is_immutable(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError
    with database.session() as db:
        result = run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        with pytest.raises(DatabaseError):
            with db.begin_nested():
                db.execute(text('UPDATE provider_records SET payload=:payload WHERE ref=:ref'), {'payload': '{}', 'ref': result.raw_ref})


@pytest.mark.parametrize('schema', [{'$ref': 'https://example.invalid/schema'}, {'a': {'$ref': 'file:///private'}},
    {'$dynamicRef': 'http://127.0.0.1:9999/forbidden'}, {'a': {'$recursiveRef': 'http://example.invalid/schema'}}])
def test_external_schema_refs_block(schema):
    from tests.helpers.synthetic_qcc import api
    with pytest.raises(ServiceError): api().validate_schema(schema)


def test_owner_revocation_blocks_case_use(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.qcc_mcp import QccTransport
    with database.session() as db:
        r.revoke_binding_manager(actor.user_id, db=db)
        transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
        with pytest.raises(ServiceError): run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert transport.dispatch_count == 0


def test_failed_receipt_write_rolls_back_raw_atomically(tmp_path, monkeypatch):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    import cn_contract.providers.qcc_mcp as q
    from cn_contract.providers.storage import ProviderRecordRow
    from sqlalchemy import select, func
    original = q.append
    def fail(kind, *args, **kwargs):
        if kind == 'invoke': raise RuntimeError('synthetic receipt storage failure')
        return original(kind, *args, **kwargs)
    monkeypatch.setattr(q, 'append', fail)
    with database.session() as db:
        with pytest.raises(RuntimeError):
            run(q.QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert db.scalar(select(func.count()).select_from(ProviderRecordRow).where(ProviderRecordRow.kind.in_(['raw','invoke']))) == 0


def test_mock_no_network(tmp_path, monkeypatch):
    database, actor, matter, r = setup(tmp_path)
    import socket
    def no_network(*args, **kwargs): raise AssertionError('mock may not dispatch network')
    from cn_contract.providers.qcc_mcp import QccTransport
    async def check():
        # Windows asyncio creates a private socketpair before this coroutine;
        # prohibit provider network only after the event loop exists.
        monkeypatch.setattr(socket.socket, 'connect', no_network)
        endpoint, ref, binding, _ = await ready(database, actor, matter, r)
        with database.session() as db:
            result = await QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, str(uuid4()))
            assert result.billing_known and result.charged_credits == 0
    run(check())


def test_revoke_during_call_preserves_receipt_but_rejects_old_session(tmp_path, monkeypatch):
    database, actor, matter, r = setup(tmp_path)
    endpoint, ref, binding, _ = run(ready(database, actor, matter, r))
    from cn_contract.providers.mock_qcc import MockQccTransport
    from cn_contract.providers.qcc_mcp import QccTransport
    from cn_contract.providers.storage import ProviderRecordRow
    from cn_contract.security import revoke_session
    from sqlalchemy import select
    with database.session() as db:
        original = MockQccTransport.invoke
        async def revoke(self, name, arguments, correlation_id):
            raw = await original(self, name, arguments, correlation_id)
            revoke_session(actor.session_id, db)
            return raw
        monkeypatch.setattr(MockQccTransport, 'invoke', revoke)
        with pytest.raises(ServiceError) as error:
            run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
        assert error.value.code == 'AUTHORIZATION_REQUIRED'
        raw = db.scalar(select(ProviderRecordRow).where(ProviderRecordRow.kind == 'raw'))
        receipt = db.scalar(select(ProviderRecordRow).where(ProviderRecordRow.kind == 'invoke'))
        assert raw and receipt
        raw_ref = raw.ref
    with database.session() as db, pytest.raises(ServiceError):
        r.read_raw(raw_ref, actor=actor, matter_id=matter.id, db=db)
