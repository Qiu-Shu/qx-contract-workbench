"""Test-only network tripwire around the real desktop entry; never packaged."""
import json
import os
from pathlib import Path

import httpx
import httpx2

from cn_contract.desktop_entry import main

report = Path(os.environ['QX_PROBE_SETTINGS_NETWORK'])
previous = json.loads(report.read_text('utf-8')) if report.exists() else {}
calls = {name: previous.get(name, 0) for name in ('httpx_calls', 'httpx2_calls')}


def save():
    report.write_text(json.dumps({**calls, 'blocked_send_attempts': sum(calls.values()),
        'scope': 'source backend httpx/httpx2 Client.send and AsyncClient.send only; not process-wide networking'}), encoding='utf-8')


def intercept(name):
    def forbidden(*args, **kwargs):
        calls[name] += 1
        save()
        raise RuntimeError('SYNTHETIC_NETWORK_TRIPWIRE')

    async def async_forbidden(*args, **kwargs):
        return forbidden()

    return forbidden, async_forbidden


save()
httpx.Client.send, httpx.AsyncClient.send = intercept('httpx_calls')
httpx2.Client.send, httpx2.AsyncClient.send = intercept('httpx2_calls')
if __name__ == '__main__':
    raise SystemExit(main())
