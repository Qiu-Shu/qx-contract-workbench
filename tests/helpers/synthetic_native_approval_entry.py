"""Test-only loopback provider plus a hard external-network tripwire."""
import json
import os
from pathlib import Path
import runpy
import sys

import httpx
import httpx2

counts = {'loopback_calls': 0, 'external_requests': 0}
target = Path(os.environ['QX_PROBE_SETTINGS_NETWORK'])
target.write_text(json.dumps(counts), encoding='utf-8')


def check(request):
    if str(request.url) != sys.argv[1]:
        counts['external_requests'] += 1
        target.write_text(json.dumps(counts), encoding='utf-8')
        raise RuntimeError('TEST_EXTERNAL_NETWORK_BLOCKED')
    counts['loopback_calls'] += 1
    target.write_text(json.dumps(counts), encoding='utf-8')


def wrap_sync(original):
    def send(self, request, *args, **kwargs):
        check(request)
        return original(self, request, *args, **kwargs)
    return send


def wrap_async(original):
    async def send(self, request, *args, **kwargs):
        check(request)
        return await original(self, request, *args, **kwargs)
    return send


for module in (httpx, httpx2):
    module.Client.send = wrap_sync(module.Client.send)
    module.AsyncClient.send = wrap_async(module.AsyncClient.send)
runpy.run_path(str(Path(__file__).with_name('synthetic_native_control_entry.py')), run_name='__main__')
