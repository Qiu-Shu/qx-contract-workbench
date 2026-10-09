"""Bounded opaque progress tokens on actual synthetic-only local STDIO."""

import json

import pytest

from tests.helpers.offline_mcp_child import CANARY, child, initialize


@pytest.mark.parametrize('token', [
    '', 'opaque-42', CANARY, '进度令牌', 'token with spaces', 'x' * 128, '😀' * 128,
], ids=['empty', 'ascii', 'inert-canary', 'chinese', 'spaces', 'max-ascii', 'max-utf8'])
def test_bounded_opaque_string_progress_token_allows_discovery_and_fixed_tools(token):
    with child() as (process, send, stderr):
        initialize(send)
        metadata = {'progressToken': token}
        listing = send('tools/list', {'_meta': metadata}, request_id=2)
        assert 'result' in listing, listing
        assert {item['name'] for item in listing['result']['tools']} == {
            'workbench_status', 'deepseek_offline_example', 'read_selected_case', 'submit_selected_candidates'}
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                    '_meta': metadata}, request_id=3)
        assert 'result' in status, status
        body = status['result']['structuredContent']
        assert body['status'] == 'OFFLINE_ONLY' and body['synthetic'] is True
        assert body['real_models_enabled'] is False and body['qcc_enabled'] is False
        example = send('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-flash'},
            '_meta': metadata}, request_id=4)
        assert 'result' in example, example
        result = example['result']['structuredContent']
        assert result['status'] == 'OFFLINE_ONLY' and result['legal_opinion'] is False
        assert result['reply']['usage']['cost'] is None
        for response in (listing, status, example):
            serialized = json.dumps(response['result'], ensure_ascii=False)
            assert 'progressToken' not in serialized and CANARY not in serialized
            if token:
                assert token not in serialized
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_progress_token_boundaries_and_unknown_metadata_still_reject_without_reflection():
    invalid_tokens = [None, True, False, -1, 2**63, 1.0, [], {},
        'x' * 129, '进' * 129, '😀' * 129,
        CANARY + '\x00', CANARY + '\t', CANARY + '\n', CANARY + '\r',
        CANARY + '\x1f', CANARY + '\x7f', CANARY + '\x85',
        CANARY + '\u200b', CANARY + '\u202e', CANARY + '\ufeff']
    invalid_metadata = [{'progressToken': token} for token in invalid_tokens]
    invalid_metadata += [{'progressToken': 'opaque-42', key: CANARY}
        for key in ('raw', 'text', 'actor', 'approval', 'context',
                    'traceparent', 'tracestate', 'io.modelcontextprotocol/protocolVersion')]
    with child() as (process, send, stderr):
        initialize(send)
        for index, metadata in enumerate(invalid_metadata, 2):
            for method, params in [
                ('tools/list', {'_meta': metadata}),
                ('tools/call', {'name': 'workbench_status', 'arguments': {}, '_meta': metadata}),
                ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
                    'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-flash'},
                    '_meta': metadata}),
            ]:
                response = send(method, params, request_id=index)
                assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
                assert CANARY not in json.dumps(response['error'])
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                   '_meta': {'progressToken': 'still-opaque'}}, request_id=100)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_string_progress_token_does_not_expand_other_methods_or_business_arguments():
    metadata = {'progressToken': 'opaque-42'}
    with child() as (process, send, stderr):
        initialize(send)
        requests = [(method, {'_meta': metadata})
                    for method in ('ping', 'resources/list', 'prompts/list')]
        requests += [
            ('tools/call', {'name': 'workbench_status', 'arguments': metadata}),
            ('tools/call', {'name': 'workbench_status', 'arguments': {'_meta': metadata}}),
            ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
                'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-flash',
                'progressToken': 'opaque-42'}}),
        ]
        for index, (method, params) in enumerate(requests, 2):
            response = send(method, params, request_id=index)
            assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
            assert 'opaque-42' not in json.dumps(response['error'])
        listing = send('tools/list', {'_meta': metadata}, request_id=100)
        assert len(listing['result']['tools']) == 4
    assert process.returncode == 0 and ''.join(stderr) == ''
