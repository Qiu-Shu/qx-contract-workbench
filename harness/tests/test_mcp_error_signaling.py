"""Exercise the real MCP protocol with a fake reader, without touching user files."""
import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import anyio
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
import server as material_api


async def call_parse():
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tasks:
            lowlevel = material_api.mcp._lowlevel_server
            tasks.start_soon(lowlevel.run, *server_streams,
                            lowlevel.create_initialization_options())
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                result = await client.call_tool('parse_material', {'path': 'synthetic.pdf'})
            tasks.cancel_scope.cancel()
    return result


@pytest.fixture
def fake_reader(monkeypatch):
    monkeypatch.setattr(material_api, 'store', SimpleNamespace(
        root=Path('synthetic-workspace'), db=lambda: nullcontext(None),
        current=lambda path, db: None))

    def install(result):
        def run(*args, **kwargs):
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(material_api.subprocess, 'run', run)
    return install


@pytest.mark.parametrize('reader_result, expected_hint', [
    (subprocess.TimeoutExpired('synthetic-reader', 600), 'PDF请减小page_count继续'),
    (SimpleNamespace(returncode=1, stdout=''), '原件保留'),
    (SimpleNamespace(returncode=0, stdout='not JSON'), '解析进程返回异常'),
    (SimpleNamespace(returncode=0, stdout=json.dumps(
        {'ok': False, 'error': '虚构解析失败，请减小读取范围继续。'})), '请减小读取范围继续'),
])
def test_reader_failure_is_an_mcp_error_with_recovery_hint(fake_reader, reader_result, expected_hint):
    fake_reader(reader_result)
    result = asyncio.run(call_parse())
    assert result.is_error is True
    assert expected_hint in '\n'.join(block.text for block in result.content if block.type == 'text')


@pytest.mark.parametrize('payload', [
    {'status': 'no_text', 'chunks': 0, 'warnings': ['需继续OCR'], 'next_page': 2},
    {'status': 'ready', 'chunks': 3, 'next_page': None},
    {'status': 'partial', 'chunks': 3, 'next_page': 4, 'warnings': ['下一批继续']},
])
def test_recoverable_and_successful_reader_results_keep_their_payload(fake_reader, payload):
    fake_reader(SimpleNamespace(returncode=0, stdout=json.dumps({'ok': True, 'result': payload})))
    result = asyncio.run(call_parse())
    assert result.is_error is False
    text = '\n'.join(block.text for block in result.content if block.type == 'text')
    assert json.loads(text) == payload
