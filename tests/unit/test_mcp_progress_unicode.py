"""Strict UTF-8 metadata validation before inert tokens reach SDK callbacks."""

import pytest

from cn_contract.mcp.offline_server import _finite_tool_metadata


@pytest.mark.parametrize('token', ['\ud800', '\udfff', '\ud83d\ude00', 'opaque\ud800'])
@pytest.mark.parametrize('with_thread', [False, True])
def test_progress_token_rejects_surrogate_sequences_without_raising(token, with_thread):
    metadata = {'progressToken': token}
    if with_thread:
        metadata['threadId'] = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    assert _finite_tool_metadata(metadata, allow_thread_id=with_thread) is False
