import json

import pytest

from cn_contract.mcp.offline_server import _bounded_turn_metadata, _finite_tool_metadata


@pytest.mark.parametrize('value', ['\ud800', '\udfff', float('nan'), float('inf')])
def test_unencodable_or_non_json_turn_metadata_is_rejected(value):
    assert not _finite_tool_metadata({'x-codex-turn-metadata': {'value': value}},
                                     allow_thread_id=True)


def test_turn_metadata_aggregate_node_limit():
    value = {'a': [[0] * 62, [0] * 62, [0] * 62, [0] * 63]}
    assert _bounded_turn_metadata(value)  # 256 nodes including keys and containers.
    value['a'][-1].append(0)
    assert not _bounded_turn_metadata(value)


def test_turn_metadata_aggregate_utf8_byte_limit():
    value = {str(i): '中' * 682 for i in range(3)}
    value['3'] = ''
    size = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    value['3'] = 'x' * (8192 - size)
    assert _bounded_turn_metadata(value)
    value['3'] += 'x'
    assert not _bounded_turn_metadata(value)
