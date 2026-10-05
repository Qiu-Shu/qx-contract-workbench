"""Synthetic wire reproductions of the pinned local host's metadata envelopes.

These children are the product STDIO process, not a native Codex host tool call.
"""

import json

import pytest

from tests.helpers.offline_mcp_child import CANARY, child


SYNTHETIC_THREAD_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'


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
        {'progressToken': 2**63}, {'progressToken': 1.0}, {'progressToken': CANARY + '\x00'},
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


@pytest.mark.parametrize('token', [None, 0, 1, 2**63 - 1, '', 'opaque-42', '进度令牌'],
                         ids=['thread-only', 'thread-progress-zero', 'thread-progress-one', 'thread-progress-max',
                              'thread-progress-empty', 'thread-progress-ascii', 'thread-progress-chinese'])
@pytest.mark.parametrize('thread_id', [SYNTHETIC_THREAD_ID, 'bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb'],
                         ids=['canonical-v4', 'canonical-v7'])
def test_host_thread_metadata_is_ignored_by_both_fixed_tool_results(token, thread_id):
    metadata = {'threadId': thread_id}
    if token is not None:
        metadata['progressToken'] = token
    with child() as (process, send, stderr):
        initialize_like_local_host(send)
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                    '_meta': metadata}, request_id=2)
        assert 'result' in status, status
        body = status['result']['structuredContent']
        assert body['status'] == 'OFFLINE_ONLY' and body['synthetic'] is True
        assert body['real_models_enabled'] is False and body['qcc_enabled'] is False
        example = send('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
            'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-v4-pro'},
            '_meta': metadata}, request_id=3)
        assert 'result' in example, example
        result = example['result']['structuredContent']
        assert result['legal_opinion'] is False and result['status'] == 'OFFLINE_ONLY'
        assert result['reply']['usage']['cost'] is None
        assert result['response_origin'] == 'manually_constructed_not_supplier'
        assert result['reply']['model'] == 'deepseek-v4-pro'
        for response in (status, example):
            text = json.dumps(response['result'])
            assert thread_id not in text
            assert 'threadId' not in text and 'progressToken' not in text
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_thread_metadata_rejects_types_noncanonical_values_and_other_content():
    invalid_values = [None, True, 1, 1.0, [], {}, '', CANARY,
        SYNTHETIC_THREAD_ID.upper(), SYNTHETIC_THREAD_ID.replace('-', ''),
        '{' + SYNTHETIC_THREAD_ID + '}', 'urn:uuid:' + SYNTHETIC_THREAD_ID,
        ' ' + SYNTHETIC_THREAD_ID, SYNTHETIC_THREAD_ID + ' ',
        SYNTHETIC_THREAD_ID[:-1], SYNTHETIC_THREAD_ID + 'a',
        'gggggggg-gggg-4ggg-8ggg-gggggggggggg']
    invalid = [{'threadId': value} for value in invalid_values]
    invalid += [{'threadId': SYNTHETIC_THREAD_ID, 'progressToken': value}
                for value in [None, True, -1, 2**63, 1.0, CANARY + '\x00', [], {}]]
    invalid += [{'threadId': SYNTHETIC_THREAD_ID, key: CANARY}
                for key in ['raw', 'text', 'actor', 'approval', 'traceparent', 'tracestate',
                            'io.modelcontextprotocol/protocolVersion']]
    with child() as (process, send, stderr):
        initialize_like_local_host(send)
        for index, metadata in enumerate(invalid, 2):
            for name, arguments in [
                ('workbench_status', {}),
                ('deepseek_offline_example', {'fixture': 'nda', 'operation': 'review_chunk',
                                               'model': 'deepseek-flash'})]:
                response = send('tools/call', {'name': name, 'arguments': arguments,
                                             '_meta': metadata}, request_id=index)
                assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
                text = json.dumps(response['error'])
                assert CANARY not in text and SYNTHETIC_THREAD_ID not in text
                assert 'threadId' not in text and 'progressToken' not in text
        # Refusals do not poison the already-initialized finite session.
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {}}, request_id=100)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
    assert process.returncode == 0 and ''.join(stderr) == ''


def test_thread_metadata_is_call_only_and_cannot_expand_business_arguments():
    with child() as (process, send, stderr):
        initialize_like_local_host(send)
        for index, metadata in enumerate([
            {'threadId': SYNTHETIC_THREAD_ID},
            {'threadId': SYNTHETIC_THREAD_ID, 'progressToken': 1},
            {'threadId': SYNTHETIC_THREAD_ID, 'progressToken': 'opaque-42'}], 2):
            for method in ('tools/list', 'ping', 'resources/list', 'prompts/list'):
                response = send(method, {'_meta': metadata}, request_id=index)
                assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
                assert SYNTHETIC_THREAD_ID not in json.dumps(response['error'])
        for method, params in [
            ('tools/call', {'name': 'workbench_status', 'arguments': {'threadId': SYNTHETIC_THREAD_ID}}),
            ('tools/call', {'name': 'workbench_status', 'arguments': {
                '_meta': {'threadId': SYNTHETIC_THREAD_ID}}}),
            ('tools/call', {'name': 'deepseek_offline_example', 'arguments': {
                'fixture': 'nda', 'operation': 'review_chunk', 'model': 'deepseek-flash',
                'threadId': SYNTHETIC_THREAD_ID}})]:
            response = send(method, params, request_id=50)
            assert response['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
        listing = send('tools/list', {'_meta': {'progressToken': 1}}, request_id=100)
        assert len(listing['result']['tools']) == 2
        status = send('tools/call', {'name': 'workbench_status', 'arguments': {},
            '_meta': {'progressToken': 1}}, request_id=101)
        assert status['result']['structuredContent']['status'] == 'OFFLINE_ONLY'
    assert process.returncode == 0 and ''.join(stderr) == ''
