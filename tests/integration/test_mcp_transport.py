import pytest
from uuid import uuid4
from cn_contract.security import ServiceError
from tests.helpers.synthetic_qcc import api, setup, ready, run, sdk_server


def test_installed_sdk_real_loopback_roundtrip(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.qcc_mcp import QccTransport
    with sdk_server() as (cfg, counts, server):
        endpoint, ref, binding, value = run(ready(database, actor, matter, r, cfg=cfg))
        with database.session() as db:
            transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
            result = run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
            assert result.status.value == 'sent_unknown'
            assert result.raw_ref and result.billing_known and transport.dispatch_count == 1
        assert counts['initialize'] == 2 and counts['list'] == 2 and counts['call'] == 1


def test_redirect_zero_tool_dispatch(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    with sdk_server(redirect='http://example.invalid/never') as (cfg, counts, server):
        with database.session() as db:
            endpoint = r.provision_synthetic_endpoint(cfg, actor=actor, db=db)
            with pytest.raises(ServiceError):
                run(r.discover_tools(endpoint, actor=actor, matter_id=matter.id, db=db))
        assert counts['http'] == 1 and counts['call'] == 0


@pytest.mark.parametrize('escaped', [False, True])
def test_secret_reflection_rejected_without_logging(tmp_path, caplog, escaped):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.mcp_client import SecretStore
    from cn_contract.providers.qcc_mcp import QccTransport
    import logging
    secret = 'IndependentFictionalSecretT07'
    store = SecretStore(); store.register('synthetic-secret:test', secret)
    caplog.set_level(logging.DEBUG)
    with sdk_server(reflect=secret, escaped=escaped) as (cfg, counts, server):
        cfg = cfg.model_copy(update={'secret_ref': 'synthetic-secret:test'})
        with database.session() as db:
            endpoint = r.provision_synthetic_endpoint(cfg, actor=actor, db=db)
            catalog = run(r.discover_tools(endpoint, actor=actor, matter_id=matter.id, db=db, secrets=store))
            price = r.register_synthetic_price(endpoint, actor=actor, db=db)
            from cn_contract.domain import BindingInput
            tool = catalog.tools[0]
            value = BindingInput(capability_key='synthetic.identity', provider=catalog.provider, tool_name=tool.name,
                input_schema_snapshot=tool.input_schema_snapshot, output_schema_snapshot=tool.output_schema_snapshot,
                schema_hash=r.schema_hash(tool), endpoint_config_ref=endpoint, unit_price=0, price_unit='synthetic_credit/call',
                price_snapshot_id=price, approved_by=None, approved_at=None)
            pending = r.bind_capability(value, actor=actor, db=db)
            ref = r.binding_reference(pending, actor=actor, db=db); binding = r.approve_binding(ref, actor=actor, db=db)
            result = run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db, secrets=store).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
            assert result.status.value == 'sent_unknown'
            assert secret not in str(r.read_raw(result.raw_ref, actor=actor, matter_id=matter.id, db=db))
        assert counts['call'] == 1 and secret not in caplog.text


@pytest.mark.parametrize('endpoint', ['http://localhost:8123/mcp', 'http://127.0.0.1:8123/other',
                                    'http://127.0.0.1:8123/mcp?next=external', 'http://user:secret@127.0.0.1:8123/mcp'])
def test_loopback_requires_exact_origin_and_path(endpoint):
    r = api()
    assert not r.allowed_synthetic_endpoint(endpoint)


@pytest.mark.parametrize('direction', ['input', 'output'])
def test_server_drift_without_explicit_discovery_blocks_call(tmp_path, direction):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.qcc_mcp import QccTransport
    with sdk_server() as (cfg, counts, server):
        endpoint, ref, binding, value = run(ready(database, actor, matter, r, cfg=cfg))
        server.remove_tool('synthetic_identity')
        if direction == 'input':
            def changed(name: str, new_required: str) -> dict[str, str | bool]:
                counts['call'] += 1
                return {'synthetic': True}
        else:
            def changed(name: str) -> dict[str, str | bool | int]:
                counts['call'] += 1
                return {'synthetic': True, 'new': 1}
        server.add_tool(changed, name='synthetic_identity', structured_output=True)
        with database.session() as db:
            transport = QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db)
            with pytest.raises(ServiceError) as error:
                run(transport.invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
            assert error.value.code == 'TOOL_UNBOUND'
            assert transport.dispatch_count == 0 and counts['call'] == 0
            assert not r.read_binding(ref, actor=actor, db=db).enabled


def test_unknown_bound_claim_causes_zero_additional_http(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.qcc_mcp import QccTransport
    with sdk_server() as (cfg, counts, server):
        endpoint, ref, binding, value = run(ready(database, actor, matter, r, cfg=cfg))
        previous = dict(counts)
        with database.session() as db, pytest.raises(ServiceError):
            run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(
                binding.model_copy(update={'tool_name': 'fake'}), {'name': 'SYNTHETIC'}, uuid4()))
        assert counts == previous


@pytest.mark.parametrize('payload', [b'{"key":1,"key":2}', b'{"key":NaN}', b'{"key":1e999}', b'['*1000+b'0'+b']'*1000,
    b'{"private\\u004bey":"value"}', b'{"key":"private\\u004bey"}'])
def test_raw_decoded_json_bounds_and_reflection(payload):
    from cn_contract.providers.mcp_client import _check_private_response
    with pytest.raises(ServiceError):
        _check_private_response(payload, 'privateKey')


def test_success_response_partial_pages_preserves_known_status(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.qcc_mcp import QccTransport
    with sdk_server(state='success', pages_complete=False) as (cfg, counts, server):
        endpoint, ref, binding, value = run(ready(database, actor, matter, r, cfg=cfg))
        with database.session() as db:
            result = run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
            assert result.status.value == 'success'
            raw = r.read_raw(result.raw_ref, actor=actor, matter_id=matter.id, db=db)
            assert raw['structured']['pages_complete'] is False
            assert counts['call'] == 1


def test_known_sdk_error_without_structured_is_failed(tmp_path):
    database, actor, matter, r = setup(tmp_path)
    from cn_contract.providers.qcc_mcp import QccTransport
    from mcp_types import CallToolResult, TextContent
    with sdk_server() as (cfg, counts, server):
        server.remove_tool('synthetic_identity')
        def known_error(name: str) -> CallToolResult:
            counts['call'] += 1
            return CallToolResult(is_error=True, content=[TextContent(type='text', text='SYNTHETIC_KNOWN_ERROR')])
        server.add_tool(known_error, name='synthetic_identity', structured_output=False)
        endpoint, ref, binding, value = run(ready(database, actor, matter, r, cfg=cfg))
        with database.session() as db:
            result = run(QccTransport(endpoint, actor=actor, matter_id=matter.id, db=db).invoke(binding, {'name': 'SYNTHETIC'}, uuid4()))
            assert result.status.value == 'failed'
            raw = r.read_raw(result.raw_ref, actor=actor, matter_id=matter.id, db=db)
            assert raw['is_error'] is True and raw['structured'] is None


def test_first_initialize_private_header_not_logged(tmp_path, caplog):
    import logging
    from cn_contract.providers.mcp_client import SecretStore
    database, actor, matter, r = setup(tmp_path)
    canary = 'IndependentFirstRequestCanaryT07'
    store = SecretStore(); store.register('synthetic-secret:first', canary)
    caplog.set_level(logging.DEBUG)
    with sdk_server(reflect=canary, reflect_header_on='initialize') as (cfg, counts, server):
        cfg = cfg.model_copy(update={'secret_ref': 'synthetic-secret:first'})
        with database.session() as db:
            endpoint = r.provision_synthetic_endpoint(cfg, actor=actor, db=db)
            with pytest.raises(ServiceError):
                run(r.discover_tools(endpoint, actor=actor, matter_id=matter.id, db=db, secrets=store))
        assert counts['call'] == 0 and canary not in caplog.text
