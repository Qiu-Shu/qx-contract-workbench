"""Check the actual stdio servers; public sample only, no model or personal data."""
import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'docs/checks/web-tools'


async def main():
    report = {}
    servers = {
        'bb_browser': ('D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe', [str(ROOT/'bridge/browser.py')]),
        'scrapling': ('C:/Users/Lenovo/.codex/tools/scrapling/venv/Scripts/scrapling.exe', ['mcp', '--executable-path', 'C:/Program Files/Google/Chrome/Application/chrome.exe']),
        'windows': ('C:/Users/Lenovo/.codex/tools/windows-mcp/venv/Scripts/windows-mcp.exe', ['serve', '--transport', 'stdio']),
    }
    for name, (command, args) in servers.items():
        async with stdio_client(StdioServerParameters(command=command, args=args)) as streams:
            async with ClientSession(*streams, read_timeout_seconds=120) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                print(json.dumps({'server': name, 'tools': names}), flush=True)
                report[name] = {'tools': names}
                if name == 'scrapling':
                    result = await session.call_tool('make_request', {'url': 'https://example.com', 'extraction_type': 'text', 'main_content_only': False, 'timeout': 25})
                    report[name]['publicPage'] = result.model_dump(mode='json')
                    print(json.dumps(report[name]['publicPage'], ensure_ascii=False), flush=True)
                    assert not result.is_error and 'Example Domain' in str(result), 'Public HTTP fetch failed'
                elif name == 'bb_browser':
                    result = await session.call_tool('browser', {'arguments': ['status']})
                    report[name]['status'] = result.model_dump(mode='json')
                    assert not result.is_error
                else:
                    result = await session.call_tool('ControlStatus', {})
                    report[name]['status'] = result.model_dump(mode='json')
                    assert not result.is_error
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT/'stdio.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('All three MCP handshakes and public fetch passed', flush=True)


asyncio.run(main())
