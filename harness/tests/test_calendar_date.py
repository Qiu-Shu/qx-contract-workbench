"""Calendar arithmetic is deterministic; the tool does not infer legal rules."""
import asyncio
from pathlib import Path
import sys
import anyio
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
import business_server as api


@pytest.mark.parametrize('anchor,offset,expected', [
    ('2027-12-01', -30, '2027-11-01'),
    ('2026-11-01', 15, '2026-11-16'),
    ('2028-02-28', 1, '2028-02-29'),
    ('2027-02-28', 1, '2027-03-01'),
    ('2026-12-31', 1, '2027-01-01'),
    ('2026-11-04', 0, '2026-11-04'),
])
def test_known_calendar_rule(anchor, offset, expected):
    result = api.calculate_calendar_date(anchor, offset, '合成规则，不是现行法规')
    assert result['result_date'] == expected
    assert result['base_date'] == anchor and result['offset_days'] == offset
    assert result['rule_verified'] is False
    assert result['holiday_adjusted'] is False


@pytest.mark.parametrize('anchor,offset,source', [
    ('2026-02-30', 1, 'test'), ('20261104', 1, 'test'),
    ('2026-11-04', 1, ''), ('2026-11-04', 100000, 'test'),
    ('9999-12-31', 1, 'test'),
])
def test_invalid_input_is_not_silently_guessed(anchor, offset, source):
    with pytest.raises(api.material_server.ToolError):
        api.calculate_calendar_date(anchor, offset, source)


def test_real_mcp_exposes_arithmetic_and_marks_invalid_date_error():
    async def run():
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            async with anyio.create_task_group() as tasks:
                server = api.mcp._lowlevel_server
                tasks.start_soon(server.run, *server_streams, server.create_initialization_options())
                async with ClientSession(*client_streams) as client:
                    await client.initialize()
                    names = {tool.name for tool in (await client.list_tools()).tools}
                    assert 'calculate_calendar_date' in names
                    result = await client.call_tool('calculate_calendar_date', {'base_date': '2027-12-01', 'offset_days': -30, 'rule_source': '合同假设条款：届满前30日'})
                    assert not result.is_error
                    assert '2027-11-01' in ''.join(c.text for c in result.content if c.type == 'text')
                    invalid = await client.call_tool('calculate_calendar_date', {'base_date': '未知', 'offset_days': -30, 'rule_source': '未核规则'})
                    assert invalid.is_error
                tasks.cancel_scope.cancel()
    asyncio.run(run())
