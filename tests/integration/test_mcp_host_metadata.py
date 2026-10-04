"""Reproduce the installed Codex host's integer progress-token envelope."""

import json

import pytest

from tests.helpers.offline_mcp_child import CANARY, child


def initialize_like_local_host(send):
    response = send('initialize', {'protocolVersion': '2025-06-18',
        'capabilities': {'elicitation': {'form': {}, 'url': {}}},
        'clientInfo': {'name': 'synthetic-host-compatibility-test',
                       'title': 'Local synthetic host test', 'version': '1'}})
    assert 'result' in response
    send('notifications/initialized', request_id=None)


@pytest.mark.parametrize('token', [0, 1, 2**63 - 1])
def test_host_integer_progress_token_allows_discovery_and_fixed_tools(token):
    with child() as (process, send, stderr):
        initialize_like_local_host(send)
        metadata = {'progressToken': token}
        listing = send('tools/list', {'_meta': metadata}, request_id=2)
        assert 'result' in listing, listing
        assert {item['name'] for item in listing['result']['tools']} == {
            'workbench_status', 'deepseek_offline_example'}
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                    '_meta': metadata}, request_id=3)
        body = status['result']['structuredContent']
        assert body['status'] == 'OFFLINE_ONLY'
        assert body['real_models_enabled'] is False and body['qcc_enabled'] is False
        example = send('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-v4-pro'},
            '_meta': metadata}, request_id=4)['result']['structuredContent']
        assert example['legal_opinion'] is False
        assert example['reply']['usage']['cost'] is None
        assert '_meta' not in example['request'] and 'progressToken' not in json.dumps(example)
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_progress_metadata_cannot_carry_content_or_expand_business_arguments():
    invalid = [None, True, 1, [], '', {'progressToken': True}, {'progressToken': -1},
        {'progressToken': 2**63}, {'progressToken': 1.0}, {'progressToken': CANARY},
        {'progressToken': None}, {'progressToken': []}, {'progressToken': {'raw': CANARY}},
        {'progressToken': 1, 'raw': CANARY}, {'progressToken': 1, 'traceparent': CANARY},
        {'progressToken': 1, 'io.modelcontextprotocol/protocolVersion': CANARY}]
    with child() as (process, send, stderr):
        initialize_like_local_host(send)
        for index, metadata in enumerate(invalid, 2):
            for method, params in [
                ('tools/list', {'_meta': metadata}),
                ('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': metadata})]:
                response = send(method, params, request_id=index)
                assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
                assert CANARY not in json.dumps(response['error'])
        for method, params in [
            ('ping', {'_meta': {'progressToken': 1}}),
            ('resources/list', {'_meta': {'progressToken': 1}}),
            ('prompts/list', {'_meta': {'progressToken': 1}}),
            ('tools/call', {'name': 'workbench_status', 'arguments': {'_meta': {'progressToken': 1}}}),
            ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
                'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-flash',
                'progressToken': 1}, '_meta': {'progressToken': 1}})]:
            response = send(method, params, request_id=100)
            assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                   '_meta': {'progressToken': 1}}, request_id=101)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
    assert process.returncode == 0 and ''.join(stderr) == ''
