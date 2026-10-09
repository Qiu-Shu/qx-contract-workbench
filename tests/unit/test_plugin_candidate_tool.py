import anyio
import pytest
from cn_contract.mcp.offline_server import create_server


def test_submit_tool_is_explicit_write_and_bounded_input():
    async def listed(): return await create_server().list_tools()
    tools = anyio.run(listed)
    found = [tool for tool in tools if tool.name == 'submit_selected_candidates']
    assert len(found) == 1, 'candidate submission tool missing'
    result = found[0].model_dump(by_alias=True)
    assert result['annotations']['readOnlyHint'] is False
    assert result['annotations']['destructiveHint'] is False
    assert result['inputSchema']['additionalProperties'] is False
    assert set(result['inputSchema']['properties']) == {'candidate'}


def test_invalid_input_is_rejected_before_any_connection(monkeypatch):
    from cn_contract.mcp import case_client
    assert hasattr(case_client, 'submit_selected_candidates'), 'candidate client missing'
    monkeypatch.setattr(case_client, 'build_opener', lambda *_: pytest.fail('must not send'))
    with pytest.raises(ValueError): case_client.submit_selected_candidates({'actor_id': 'fake'})
