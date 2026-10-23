"""Private operation dispatch only; payload semantics remain in the native service."""
import asyncio
import json
from io import BytesIO

import pytest

from cn_contract import desktop_control as control


@pytest.mark.parametrize('operation', ['authorize_judge', 'revoke_judge'])
def test_exact_judge_authorization_operations_are_parsed(operation):
    payload = {'session_token': 'synthetic-session'}
    line = json.dumps(dict(event='model-control', protocol=control.PROTOCOL,
        nonce='synthetic', sequence=1, operation=operation, payload=payload))+'\n'
    assert control.parse_control_line(line, 'synthetic', 1) == (operation, payload)


def test_dual_dispatch_routes_authorization_without_touching_main():
    async def exercise():
        calls = []
        class Service:
            def __init__(self, name): self.name = name
            def configure(self, payload): raise AssertionError('not configuring')
            def authorize_context(self, payload): raise AssertionError('judge dispatch must not authorize main context')
            authorize_profile = authorize_context
            def disable(self): calls.append((self.name, 'disable')); return {'status':'disabled'}
            def authorize(self, payload): calls.append((self.name, 'authorize')); return {'status':'authorized'}
            def revoke(self, payload): calls.append((self.name, 'revoke')); return {'status':'revoked'}
        handler = control.NativeControlHandler(Service('main'), Service('judge'))
        channel = control.ParentControlChannel(BytesIO(), 'synthetic', lambda **kw:None, lambda:None)
        channel.bind(handler)
        for operation, status in [('authorize_judge','authorized'),('revoke_judge','revoked')]:
            assert await channel._dispatch(operation, {'session_token':'synthetic'}) == {'ok':True,'status':status}
        assert calls == [('judge','authorize'),('judge','revoke')]
        channel.close()
        assert calls[-2:] == [('main','disable'),('judge','disable')]
    asyncio.run(exercise())
