"""Model-turn envelope, from pinned Codex source; all identifiers are fictional."""
import json

import pytest

from tests.helpers.offline_mcp_child import CANARY, child, initialize


THREAD = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
TURN = {
    'session_id': THREAD, 'thread_id': THREAD, 'turn_id': THREAD,
    'model': 'synthetic-model', 'codex_version': '0.159.0-alpha.12.1',
    'auto_review_enabled': False, 'node_repl_disabled': False,
    'turn_started_at_unix_ms': 1791493200000,
    'workspaces': {'D:/synthetic': {'latest_git_commit_hash': 'a' * 40,
                                 'has_changes': True, 'associated_remote_urls': {}}},
}
ENVELOPE = {
    'callId': 'call_synthetic_1', 'sessionId': THREAD, 'threadId': THREAD,
    'itemId': 'item_synthetic_1', 'windowId': '1',
    'plugin_id': 'qx-contract-offline-codex@qx-contract-local',
    'x-codex-turn-metadata': TURN, 'codex_bridge_mcp_call_id': 'mcp-synthetic-1',
    'traceparent': '00-' + 'a' * 32 + '-' + 'b' * 16 + '-01',
    'tracestate': 'synthetic=opaque', 'progressToken': 1,
}


@pytest.mark.parametrize('metadata', [
    {'callId': 'call_synthetic_1', 'sessionId': THREAD, 'threadId': THREAD},
    ENVELOPE,
], ids=['required-turn-fields', 'complete-turn-envelope'])
def test_model_turn_metadata_is_discarded_without_changing_either_tool(metadata):
    with child() as (process, send, stderr):
        initialize(send)
        for name, arguments in [
            ('workbench_status', {}),
            ('deepseek_offline_example', {'fixture': 'nda', 'model': 'deepseek-flash',
                                         'operation': 'review_chunk'}),
        ]:
            base = send('tools/call', {'name': name, 'arguments': arguments}, request_id=2)
            actual = send('tools/call', {'name': name, 'arguments': arguments,
                                        '_meta': metadata}, request_id=3)
            assert 'result' in actual, actual
            assert actual['result'] == base['result']
            assert 'synthetic_1' not in json.dumps(actual)
    assert process.returncode == 0 and not ''.join(stderr)


def test_chat_envelope_cannot_authorize_or_expand_tools_or_arguments():
    with child() as (process, send, stderr):
        initialize(send)
        for name, arguments in [
            ('read_case', {}), ('workbench_status', {'actor': 'admin'}),
            ('workbench_status', {'_meta': ENVELOPE}),
            ('deepseek_offline_example', {'fixture': CANARY, 'model': 'deepseek-flash',
                                         'operation': 'review_chunk'}),
        ]:
            result = send('tools/call', {'name': name, 'arguments': arguments,
                                        '_meta': ENVELOPE}, request_id=2)
            assert result['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
        for method in ('tools/list', 'ping', 'resources/list'):
            result = send(method, {'_meta': ENVELOPE}, request_id=3)
            assert result['error']['message'] == 'OFFLINE_REQUEST_REJECTED'
    assert process.returncode == 0 and not ''.join(stderr)


def test_malformed_chat_metadata_is_sanitized_and_session_recovers():
    invalid = [
        {'callId': None}, {'callId': True}, {'callId': 'x' * 257},
        {'callId': CANARY + '\n'}, {'sessionId': THREAD.upper()},
        {'plugin_id': {'text': CANARY}}, {'unknown': CANARY},
        {'x-codex-turn-metadata': CANARY},
        {'x-codex-turn-metadata': {'raw': 'x' * 8193}},
        {'x-codex-turn-metadata': {'raw': {'a': {'b': {'c': {'d': {'e': 1}}}}}}},
        {'x-codex-turn-metadata': {'raw': [0] * 257}},
        {'traceparent': CANARY}, {'traceparent': '00-' + '0' * 32 + '-' + 'b' * 16 + '-01'},
        {'tracestate': CANARY}, {'traceparent': ENVELOPE['traceparent'], 'tracestate': 'a=b\n'},
        {'x-codex-turn-metadata': {'actor': 'admin'}, 'actor': 'admin'},
    ]
    with child() as (process, send, stderr):
        initialize(send)
        for metadata in invalid:
            result = send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                        '_meta': metadata}, request_id=2)
            assert result['error'] == {'code': -32602, 'message': 'OFFLINE_REQUEST_REJECTED'}
            assert CANARY not in json.dumps(result)
        assert 'result' in send('tools/call', {'name': 'workbench_status', 'arguments': {},
                                              '_meta': ENVELOPE}, request_id=3)
    assert process.returncode == 0 and not ''.join(stderr)
