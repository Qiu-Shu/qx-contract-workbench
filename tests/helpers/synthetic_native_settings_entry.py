"""Test-only network tripwire around the real desktop entry; never packaged."""
import json
import os
from pathlib import Path

import httpx

from cn_contract.desktop_entry import main

report = Path(os.environ['QX_PROBE_SETTINGS_NETWORK'])
calls = json.loads(report.read_text('utf-8'))['httpx_calls'] if report.exists() else 0


def forbidden(*args, **kwargs):
    global calls
    calls += 1
    report.write_text(json.dumps({'httpx_calls': calls, 'external_requests': 0}), encoding='utf-8')
    raise RuntimeError('SYNTHETIC_NETWORK_TRIPWIRE')


async def async_forbidden(*args, **kwargs):
    return forbidden()


report.write_text(json.dumps({'httpx_calls': calls, 'external_requests': 0}), encoding='utf-8')
httpx.Client.send = forbidden
httpx.AsyncClient.send = async_forbidden
if __name__ == '__main__':
    raise SystemExit(main())
