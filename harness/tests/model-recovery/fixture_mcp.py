"""Synthetic side effects for the isolated Harness recovery test."""
import json
from pathlib import Path
import sys
from mcp.server.mcpserver import MCPServer

root = Path(sys.argv[1])
mcp = MCPServer('recovery', log_level='WARNING')


def record(name):
    with (root / 'effects.jsonl').open('a', encoding='utf-8') as file:
        file.write(json.dumps({'tool': name}) + '\n')


@mcp.tool()
def write_file() -> dict:
    """Write a synthetic result file once."""
    record('write_file')
    target = root / 'result.txt'
    target.write_bytes(b'SYNTHETIC SAVED RESULT\n')
    return {'path': str(target), 'saved': True}


@mcp.tool()
def present() -> dict:
    """Record a synthetic presentation side effect."""
    record('present')
    return {'presented': True}


@mcp.tool()
def record_case_note() -> dict:
    """Record a synthetic case note side effect."""
    record('record_case_note')
    return {'note_id': 'synthetic-note-1', 'saved': True}


if __name__ == '__main__':
    mcp.run(transport='stdio')
