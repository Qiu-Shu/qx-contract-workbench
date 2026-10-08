"""Offline MCP boundary tests: only registered fictional inputs may execute."""

import importlib
import importlib.util
import json
from itertools import product

import anyio
import pytest
from mcp.shared.exceptions import MCPError


FIXTURES = ('sales', 'service', 'lease', 'nda')
OPERATIONS = ('extract_facts', 'review_chunk', 'review_cross_clauses')
MODELS = ('deepseek-flash', 'deepseek-v4-pro')
CANARY = 'INDEPENDENT_FICTIONAL_MCP_CANARY'


def api():
    assert importlib.util.find_spec('cn_contract.mcp') is not None, 'offline MCP package missing'
    assert importlib.util.find_spec('cn_contract.mcp.offline_server') is not None, 'offline MCP entry missing'
    return importlib.import_module('cn_contract.mcp.offline_server')


def run(awaitable):
    async def execute():
        return await awaitable
    return anyio.run(execute)


def test_discovery_exposes_exact_three_strict_tools():
    tools = run(api().create_server().list_tools())
    assert {tool.name for tool in tools} == {'workbench_status', 'deepseek_offline_example', 'read_selected_case'}
    schemas = {tool.name: tool.input_schema for tool in tools}
    assert schemas['workbench_status']['properties'] == {}
    for schema in schemas.values():
        assert schema['additionalProperties'] is False
    example = schemas['deepseek_offline_example']
    assert set(example['required']) == {'fixture', 'operation', 'model'}
    assert set(example['properties']) == {'fixture', 'operation', 'model'}
    assert example['properties']['fixture']['enum'] == list(FIXTURES)
    assert example['properties']['operation']['enum'] == list(OPERATIONS)
    assert example['properties']['model']['enum'] == list(MODELS)


def test_status_is_explicitly_offline_and_exposes_unestablished_limits():
    status = api().workbench_status().model_dump(mode='json')
    assert status['synthetic'] is True
    assert status['status'] == 'OFFLINE_ONLY'
    assert status['real_models_enabled'] is False and status['qcc_enabled'] is False
    assert status['production_status'] == 'PRODUCTION_BLOCKED'
    assert status['transport_frame_limit'] == 'NOT_ESTABLISHED'
    assert status['os_cpu_memory_sandbox'] == 'NOT_ESTABLISHED'


@pytest.mark.parametrize('fixture,operation,model', list(product(FIXTURES, OPERATIONS, MODELS)))
def test_registered_fixture_operation_model_roundtrip(fixture, operation, model):
    result = api().deepseek_offline_example(fixture, operation, model).model_dump(mode='json')
    assert result['fixture'] == fixture
    assert result['synthetic'] is True and result['status'] == 'OFFLINE_ONLY'
    assert result['response_origin'] == 'manually_constructed_not_supplier'
    assert result['legal_opinion'] is False
    assert result['reply']['model'] == model and result['reply']['operation'] == operation
    assert result['reply']['usage']['cost'] is None
    assert result['reply']['usage']['unit'] == 'USD'
    assert result['reply']['usage']['pricing_status'] == 'unknown'
    assert result['reply']['payload']['operation'] == operation
    assert result['reply']['payload']['synthetic'] is True
    request = result['request']
    assert request['model'] == model and request['stream'] is False
    assert len(request['messages']) == 2
    projected = json.loads(request['messages'][1]['content'])
    assert projected['operation'] == operation
    assert 1 <= len(projected['anchors']) <= 32
    assert projected['anchors'][0]['quote'].startswith('SYNTHETIC T06：')
    assert result['fixture_sha256'] in {
        '227545e4f7804bc9ae5da0afeacfd57df81cff883e803c9d3c8dfc040bc9f9d3',
        '27083b24eba3f1e18ff60ce704184d398976770ce4a960d9326a91bdc450fead',
        'dfeb4031c2d24d5ac8ba0f89eac0a7d40ed6ce88533b245f1ab5d7c06f308770',
        'c3b27a05b60cf656053af95e74d908f0d90038b58247bd5ea7fba9a742789e0c'}


@pytest.mark.parametrize('field', ['raw', 'text', 'path', 'url', 'key', 'token', 'rates', 'actor',
    'approval', 'budget', 'max_tokens', 'context', 'api_key', 'response', 'arguments', '_meta'])
def test_argument_dto_rejects_any_extra_field(field):
    domain = importlib.import_module('cn_contract.domain')
    dto = getattr(domain, 'McpOfflineExampleArguments', None)
    assert dto is not None, 'offline argument DTO missing'
    with pytest.raises(ValueError):
        dto.model_validate({'fixture': 'sales', 'operation': 'extract_facts',
                            'model': 'deepseek-flash', field: CANARY})


@pytest.mark.parametrize('field,value', [
    ('fixture', '../sales_basic.docx'), ('fixture', 'https://example.invalid'),
    ('fixture', 'unknown'), ('fixture', ''), ('fixture', None), ('fixture', True),
    ('fixture', 1), ('fixture', ['sales']), ('fixture', {'value': 'sales'}),
    ('operation', 'review'), ('operation', None), ('operation', 1),
    ('model', 'deepseek-chat'), ('model', None), ('model', False)])
def test_example_rejects_wrong_enum_and_exact_type(field, value):
    arguments = {'fixture': 'sales', 'operation': 'extract_facts', 'model': 'deepseek-flash'}
    arguments[field] = value
    with pytest.raises(MCPError) as error:
        api().deepseek_offline_example(**arguments)
    assert error.value.message == 'OFFLINE_REQUEST_REJECTED'
    assert error.value.data is None


def test_fixture_drift_fails_closed_without_echoing_source(tmp_path, monkeypatch):
    module = api()
    (tmp_path / 'sales_basic.docx').write_text(CANARY, encoding='utf-8')
    monkeypatch.setattr(module, '_FIXTURE_DIRECTORY', tmp_path)
    with pytest.raises(MCPError) as error:
        module.deepseek_offline_example('sales', 'extract_facts', 'deepseek-flash')
    assert error.value.message == 'OFFLINE_EXAMPLE_UNAVAILABLE'
    assert CANARY not in str(error.value) and str(tmp_path) not in str(error.value)


def test_lease_injection_stays_data_with_no_tools_or_credentials():
    result = api().deepseek_offline_example('lease', 'review_cross_clauses', 'deepseek-flash')
    wire = result.request
    package = json.loads(wire['messages'][1]['content'])
    assert any('执行shell' in anchor['quote'] for anchor in package['anchors'])
    assert 'tools' not in wire and 'api_key' not in wire and 'url' not in wire
    assert result.reply.payload['operation'] == 'review_cross_clauses'
    assert result.reply.payload['legal_opinion'] is False


def test_status_does_not_read_a_fixture_or_case_file(monkeypatch):
    module = api()
    from pathlib import Path
    def forbidden(*args, **kwargs):
        raise AssertionError('status must not read any file')
    monkeypatch.setattr(Path, 'open', forbidden)
    assert module.workbench_status().status == 'OFFLINE_ONLY'


def test_example_never_uses_environment_database_or_network(monkeypatch):
    module = api()
    import os
    import socket
    import sqlite3
    def forbidden(*args, **kwargs):
        raise AssertionError('offline example cannot use an external dependency')
    monkeypatch.setattr(os, 'getenv', forbidden)
    monkeypatch.setattr(type(os.environ), '__getitem__', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(sqlite3, 'connect', forbidden)
    assert module.deepseek_offline_example('sales', 'extract_facts', 'deepseek-flash').synthetic is True


@pytest.mark.parametrize('linked_parent', ['fixture_directory', 'ancestor_directory'])
@pytest.mark.parametrize('link_kind', ['symlink', 'junction'])
def test_fixture_parent_link_is_rejected_before_any_content_read(tmp_path, monkeypatch, linked_parent, link_kind):
    module = api()
    import io
    target = tmp_path / 'invented-target'
    target.mkdir()
    if linked_parent == 'fixture_directory':
        fixture_directory = target
    else:
        fixture_directory = target / 'synthetic'
        fixture_directory.mkdir()
    (fixture_directory / 'sales_basic.docx').write_bytes(CANARY.encode())
    nominal = tmp_path / 'invented-nominal'
    if link_kind == 'symlink':
        nominal.symlink_to(target, target_is_directory=True)
    else:
        import subprocess
        import sys
        if sys.platform != 'win32':
            pytest.skip('NTFS junction boundary requires Windows')
        nominal_value = str(nominal).replace("'", "''")
        target_value = str(target).replace("'", "''")
        creation = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            f"New-Item -ItemType Junction -Path '{nominal_value}' -Value '{target_value}' -ErrorAction Stop | Out-Null"],
            capture_output=True, text=True, timeout=10)
        assert creation.returncode == 0, 'test junction creation failed before exercising product'
        assert nominal.is_junction()
    selected = nominal if linked_parent == 'fixture_directory' else nominal / 'synthetic'
    monkeypatch.setattr(module, '_FIXTURE_DIRECTORY', selected)
    original = io.open
    reads = []
    def observed(file, mode='r', *args, **kwargs):
        reads.append(file)
        return original(file, mode, *args, **kwargs)
    monkeypatch.setattr(io, 'open', observed)
    with pytest.raises(MCPError) as error:
        module.deepseek_offline_example('sales', 'extract_facts', 'deepseek-flash')
    assert error.value.message == 'OFFLINE_EXAMPLE_UNAVAILABLE'
    assert reads == [], 'linked ancestor content was opened before refusal'
