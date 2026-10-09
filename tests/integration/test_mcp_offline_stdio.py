"""Actual local child initialize/list/call/refuse/shutdown, never a supplier."""

import json
import sys
from tempfile import TemporaryFile

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.exceptions import MCPError
import pytest

from tests.helpers.offline_mcp_child import CANARY, ROOT, child, initialize
from tests.unit.test_mcp_offline import api


def test_stdlib_child_handshake_discovery_calls_and_clean_shutdown():
    api()
    with child() as (process, send, stderr):
        init = initialize(send)
        assert init['serverInfo']['name'] == 'qx-contract-offline'
        tools = send('tools/list', {}, request_id=2)['result']['tools']
        assert {tool['name'] for tool in tools} == {'workbench_status', 'deepseek_offline_example', 'read_selected_case', 'submit_selected_candidates'}
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {}}, request_id=3)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
        example = send('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-v4-pro'}}, request_id=4)
        body = example['result']['structuredContent']
        assert body['reply']['model'] == 'deepseek-v4-pro'
        assert body['reply']['usage']['cost'] is None and body['legal_opinion'] is False
        assert CANARY not in json.dumps(example)
    assert process.returncode == 0
    assert ''.join(stderr) == ''


def test_wire_raw_arguments_and_unopened_methods_are_safely_refused():
    api()
    requests = [
        ('tools/call', {'name': 'workbench_status', 'arguments': {'actor': CANARY}}),
        ('tools/call', {'name': 'workbench_status', 'arguments': None}),
        ('tools/call', {'name': CANARY, 'arguments': {}}),
        ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'sales', 'operation': 'extract_facts', 'model': 'deepseek-flash', 'raw': CANARY}}),
        ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': True, 'operation': 'extract_facts', 'model': 'deepseek-flash'}}),
        ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': CANARY, 'operation': 'extract_facts', 'model': 'deepseek-flash'}}),
        ('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': {'traceparent': CANARY}}),
        ('resources/read', {'uri': 'file:///' + CANARY}),
        ('resources/list', {'cursor': CANARY}),
        ('resources/templates/list', {}),
        ('prompts/get', {'name': CANARY}),
        ('prompts/list', {}),
        (CANARY, {'private': CANARY})]
    with child() as (process, send, stderr):
        initialize(send)
        for index, (method, params) in enumerate(requests, 2):
            response = send(method, params, request_id='CORRELATION-' + str(index))
            assert response['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
            assert 'data' not in response['error']
            assert CANARY not in json.dumps(response['error'])
            assert response['id'] not in json.dumps(response['error'])
        # Rejection must leave the finite controlled session usable.
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {}}, request_id=99)
        assert status['result']['structuredContent']['real_models_enabled'] is False
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_preinitialize_and_malformed_initialization_errors_are_sanitized():
    api()
    with child() as (process, send, stderr):
        before = send('tools/call', {'name': 'workbench_status', 'arguments': {}}, request_id=CANARY)
        assert before['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        malformed = send('initialize', {'clientInfo': {'name': CANARY}}, request_id=2)
        assert malformed['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        assert CANARY not in json.dumps(malformed['error'])
        initialize(send)
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_empty_sdk_protocol_metadata_is_accepted_without_relaxing_arguments():
    api()
    with child() as (process, send, stderr):
        initialize(send)
        listing = send('tools/list', {'_meta': {}}, request_id=2)
        assert len(listing['result']['tools']) == 4
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': {}}, request_id=3)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
        rejected = send('tools/call', {'name': 'workbench_status', 'arguments': {'_meta': {}}}, request_id=4)
        assert rejected['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
    assert process.returncode == 0 and ''.join(stderr) == ''


@pytest.mark.parametrize('metadata', [None, True, 1, '', [], {'traceparent': CANARY}, {'private': CANARY}])
def test_nonprotocol_metadata_is_rejected(metadata):
    api()
    with child() as (process, send, stderr):
        initialize(send)
        for method, params in [
            ('tools/list', {'_meta': metadata}),
            ('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': metadata})]:
            response = send(method, params, request_id=2)
            assert response['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
            assert CANARY not in json.dumps(response['error'])
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_server_runs_without_otel_even_with_a_recording_provider_installed():
    api()
    # Public OTel API installs a calibrated trap. Any server-side span attempt
    # causes a real startup/request failure; the SDK client is not in this child.
    launch_code = '''
from opentelemetry.trace import TracerProvider, set_tracer_provider, get_tracer
class Trap:
    def start_as_current_span(self, *args, **kwargs):
        raise RuntimeError("INDEPENDENT_FICTIONAL_MCP_CANARY")
    def start_span(self, *args, **kwargs):
        raise RuntimeError("INDEPENDENT_FICTIONAL_MCP_CANARY")
class Provider(TracerProvider):
    def get_tracer(self, *args, **kwargs):
        return Trap()
set_tracer_provider(Provider())
try:
    get_tracer("calibration").start_as_current_span("calibration")
except RuntimeError:
    pass
else:
    raise AssertionError("trace trap was not installed")
import runpy
runpy.run_module("cn_contract.mcp.offline_server", run_name="__main__")
'''
    with child(launch_code=launch_code) as (process, send, stderr):
        initialize(send)
        assert len(send('tools/list', {}, request_id=2)['result']['tools']) == 4
        response = send('tools/call', {'name': CANARY, 'arguments': {}}, request_id=3)
        assert response['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        result = send('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'lease', 'operation': 'review_chunk', 'model': 'deepseek-flash'}}, request_id=4)
        assert result['result']['structuredContent']['token_origin'] == 'invented_example_counts_not_supplier'
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_installed_sdk_client_actual_stdio_roundtrip_and_refusal():
    api()
    async def exercise():
        with anyio.fail_after(20), TemporaryFile(mode='w+', encoding='utf-8') as errors:
            parameters = StdioServerParameters(command=sys.executable,
                args=['-X', 'utf8', '-m', 'cn_contract.mcp.offline_server'], env={}, cwd=str(ROOT))
            async with stdio_client(parameters, errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert len(tools.tools) == 4
                    result = await session.call_tool('deepseek_offline_example', {
                        'fixture': 'sales', 'operation': 'extract_facts', 'model': 'deepseek-flash'})
                    assert result.structured_content['response_origin'] == 'manually_constructed_not_supplier'
                    with pytest.raises(MCPError) as error:
                        await session.call_tool('workbench_status', {'path': CANARY})
                    assert error.value.message == 'OFFLINE_REQUEST_REJECTED'
            errors.seek(0)
            assert errors.read() == ''
    anyio.run(exercise)


def test_first_frame_modern_protocol_error_is_sanitized_before_tool_middleware():
    api()
    with child() as (process, send, stderr):
        response = send('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': {
            'io.modelcontextprotocol/protocolVersion': CANARY,
            'io.modelcontextprotocol/clientCapabilities': {}}}, request_id='FIRST-' + CANARY)
        assert 'error' in response
        assert CANARY not in json.dumps(response['error'])
        assert response['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        assert 'data' not in response['error']
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_initialize_after_modern_opening_error_is_sanitized_before_tool_middleware():
    api()
    with child() as (process, send, stderr):
        first = send('tools/list', {'_meta': {
            'io.modelcontextprotocol/protocolVersion': '2026-07-28',
            'io.modelcontextprotocol/clientCapabilities': {}}}, request_id=1)
        assert first['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        response = send('initialize', {'protocolVersion': CANARY, 'capabilities': {},
            'clientInfo': {'name': 'synthetic-repair-test', 'version': '1'}}, request_id=2)
        assert 'error' in response
        assert CANARY not in json.dumps(response['error'])
        assert response['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
        assert 'data' not in response['error']
    assert process.returncode == 0 and ''.join(stderr) == ''
