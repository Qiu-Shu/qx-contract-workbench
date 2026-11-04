"""Exercise the exposed MCP surface without model requests or user data."""
import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
import case_memory_server as api
from case_memory import CaseMemoryStore
from business_store import CaseStore


async def call(name, arguments):
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tasks:
            lowlevel = api.mcp._lowlevel_server
            tasks.start_soon(lowlevel.run, *server_streams, lowlevel.create_initialization_options())
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                result = await client.call_tool(name, arguments)
            tasks.cancel_scope.cancel()
    return result


def test_disabled_memory_cannot_be_read_via_listing_or_identifier(tmp_path, monkeypatch):
    monkeypatch.delenv('QX_HINDSIGHT_URL', raising=False)
    case_id = CaseStore(tmp_path).create('虚构禁用案件')['id']
    store = CaseMemoryStore(tmp_path)
    added = store.add(case_id, content='禁用后不得返回的虚构正文', source='测试', confirmed=True)['memory']
    store.settings(enabled=False, case_id=case_id)
    monkeypatch.setattr(api, 'memory', store)
    for name, args in [('list_case_memories', {'case_id': case_id}),
                       ('read_case_memory', {'case_id': case_id, 'memory_id': added['id']})]:
        result = asyncio.run(call(name, args))
        assert not result.is_error
        text = ''.join(c.text for c in result.content if c.type == 'text').lower()
        assert 'false' in text and added['content'] not in text
    assert store.read(case_id, added['id'])['content'] == added['content']


def test_unknown_case_is_protocol_error_and_does_not_expose_traceback(monkeypatch):
    def missing(**kwargs):
        raise ValueError('案件不存在。')
    monkeypatch.setattr(api, 'memory', SimpleNamespace(status=missing))
    result = asyncio.run(call('case_memory_status', {'case_id': 'other-case'}))
    assert result.is_error
    text = ''.join(c.text for c in result.content if c.type == 'text')
    assert '案件不存在' in text and 'Traceback' not in text


def test_recall_preserves_explicit_case_and_source(monkeypatch):
    calls = []
    def recall(**kwargs):
        calls.append(kwargs)
        return {'mode': 'local', 'memories': [{'id': 'm', 'source': {'note_id': 'n'}, 'revision': 2}]}
    monkeypatch.setattr(api, 'memory', SimpleNamespace(recall=recall))
    result = asyncio.run(call('recall_case_memory', {'case_id': 'case-a', 'query': '付款'}))
    assert not result.is_error
    assert calls == [{'case_id': 'case-a', 'query': '付款', 'limit': 8, 'use_hindsight': True}]
    assert 'note_id' in ''.join(c.text for c in result.content if c.type == 'text')


def test_actual_store_protocol_isolates_case_and_deleted_memory(tmp_path, monkeypatch):
    monkeypatch.delenv('QX_HINDSIGHT_URL', raising=False)
    cases = CaseStore(tmp_path)
    first, other = cases.create('同名案件')['id'], cases.create('同名案件')['id']
    note = cases.add_note(first, 'consultation', '虚构客户称已付款三万元。', source='虚构接待记录')
    memory = CaseMemoryStore(tmp_path)
    added = memory.add(first, note_id=note['id'])['memory']
    monkeypatch.setattr(api, 'memory', memory)
    result = asyncio.run(call('read_case_memory', {'case_id': other, 'memory_id': added['id']}))
    assert result.is_error
    result = asyncio.run(call('recall_case_memory', {'case_id': first, 'query': '付款'}))
    assert not result.is_error
    text = ''.join(c.text for c in result.content if c.type == 'text')
    assert note['id'] in text and 'consultation' in text and 'local_fallback' in text
    memory.delete(first, added['id'], added['revision'])
    result = asyncio.run(call('read_case_memory', {'case_id': first, 'memory_id': added['id']}))
    assert result.is_error
    assert cases.read_note(first, note['id'])['content'] == note['content']
