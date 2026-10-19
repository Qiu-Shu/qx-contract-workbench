"""Independent test-only network counter audit; no socket is opened."""
import asyncio
import ast
import importlib.util
import json
import os
from pathlib import Path
import runpy
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT/'tests/helpers/synthetic_native_approval_entry.py'
COUNTER = Path(__file__).with_name('review-frontend-network.json')
URL = 'http://127.0.0.1:34567/chat/completions'
called = []


def transport(*args, **kwargs):
    called.append('sync')
    return 'synthetic response'


async def async_transport(*args, **kwargs):
    called.append('async')
    return 'synthetic async response'


httpx.Client.send = transport
httpx.AsyncClient.send = async_transport
entries = []
runpy.run_path = lambda path, **kwargs: entries.append(Path(path).name)
sys.argv = [str(HELPER), URL]
os.environ['QX_PROBE_SETTINGS_NETWORK'] = str(COUNTER)
spec = importlib.util.spec_from_file_location('independent_approval_tripwire', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert entries == ['synthetic_native_control_entry.py']
assert json.loads(COUNTER.read_text()) == {'loopback_calls': 0, 'external_requests': 0}
assert httpx.Client.send(None, httpx.Request('POST', URL)) == 'synthetic response'
assert asyncio.run(httpx.AsyncClient.send(None, httpx.Request('POST', URL))) == 'synthetic async response'
assert called == ['sync', 'async']
assert json.loads(COUNTER.read_text()) == {'loopback_calls': 2, 'external_requests': 0}
print('PASS sync and async allowed-loopback calls counted exactly before transport')
try:
    httpx.Client.send(None, httpx.Request('POST', 'https://example.invalid/chat/completions'))
except RuntimeError as error:
    assert str(error) == 'TEST_EXTERNAL_NETWORK_BLOCKED'
else:
    raise AssertionError('external request reached transport')
assert called == ['sync', 'async']
assert json.loads(COUNTER.read_text()) == {'loopback_calls': 2, 'external_requests': 1}
print('PASS unexpected URL counted and blocked without executing transport')

source = (ROOT/'desktop/tests/model-approval-acceptance.py').read_text('utf-8')
tree = ast.parse(source)
branches = [node for node in ast.walk(tree) if isinstance(node, ast.If)
    and isinstance(node.test, ast.Name) and node.test.id == 'frozen']
branch = next(node for node in branches if 'probeApproval' in ast.get_source_segment(source, node))
frozen_text = '\n'.join(ast.get_source_segment(source, child) for child in branch.body)
assert 'authorizeGeneration' in frozen_text and 'model-disable' in frozen_text
assert "locator('#send').click()" not in frozen_text
assert "method:'POST'" not in frozen_text and 'submitGeneration' not in frozen_text
assert "assert len(posts) == 1" in ast.get_source_segment(source, branch.orelse[0]) or 'len(posts) == 1' in '\n'.join(
    ast.get_source_segment(source, child) for child in branch.orelse)
print('PASS static frozen branch uses native approval and disable; source branch alone clicks final send')
print('3 independent audit groups passed; no socket or actual Electron process used')
