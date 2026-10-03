"""Independent T07 synthetic fixtures; no official QCC schema or account."""
import importlib
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from cn_contract.domain import BindingInput, ProviderConfig, Role
from tests.helpers.synthetic_documents import world


def api():
    try:
        result = importlib.import_module('cn_contract.providers.qcc_registry')
    except ModuleNotFoundError as exc:
        assert exc.name != 'cn_contract.providers', 'T07 authorized provider registry must exist'
        assert exc.name != 'cn_contract.providers.qcc_registry', 'T07 authorized provider registry must exist'
        raise
    assert callable(getattr(result, 'bind_capability', None)), 'T07 binding service required'
    return result


def setup(tmp_path, *, grant=True):
    p, s, a, database, actor, matter = world(tmp_path)
    from cn_contract.persistence import UserRow
    r = api()
    r.initialize_storage(database)
    with database.session() as db:
        user = db.get(UserRow, str(actor.user_id))
        user.roles = '["admin", "handling_lawyer"]'
        if grant:
            r.provision_binding_manager(actor.user_id, db=db)
    return database, actor, matter, r


def config(endpoint='mock://synthetic-t07', transport='mock', secret_ref=None):
    return ProviderConfig(endpoint=endpoint, transport=transport, secret_ref=secret_ref,
                          approved_by=None, approved_at=None)


async def ready(database, actor, matter, r, *, cfg=None):
    with database.session() as db:
        selected = cfg or config()
        ref = (r.provision_synthetic_endpoint(selected, actor=actor, db=db) if selected.transport == 'streamable_http'
               else r.register_endpoint(selected, actor=actor, db=db))
        catalog = await r.discover_tools(ref, actor=actor, matter_id=matter.id, db=db)
        price = r.register_synthetic_price(ref, actor=actor, db=db)
        tool = catalog.tools[0]
        value = BindingInput(capability_key='synthetic.identity', provider=catalog.provider, tool_name=tool.name,
            input_schema_snapshot=tool.input_schema_snapshot, output_schema_snapshot=tool.output_schema_snapshot,
            schema_hash=r.schema_hash(tool), endpoint_config_ref=ref, unit_price=Decimal('0'),
            price_unit='synthetic_credit/call', price_snapshot_id=price, approved_by=None, approved_at=None)
        pending = r.bind_capability(value, actor=actor, db=db)
        binding_ref = r.binding_reference(pending, actor=actor, db=db)
        r.approve_binding(binding_ref, actor=actor, db=db)
        binding = r.read_binding(binding_ref, actor=actor, db=db)
    return ref, binding_ref, binding, value


def run(coroutine):
    import asyncio
    return asyncio.run(coroutine)


from contextlib import contextmanager


@contextmanager
def sdk_server(*, redirect=None, reflect=None, escaped=False, state='unknown', pages_complete=False, reflect_header_on=None):
    """Installed SDK server in a local thread; no subprocess, shell or outer net."""
    import socket
    import threading
    import time
    import uvicorn
    from mcp.server import MCPServer
    from starlette.responses import RedirectResponse
    counts = {'initialize': 0, 'list': 0, 'call': 0, 'http': 0}
    server = MCPServer('Independent fictional T07 test server', log_level='ERROR')

    @server.tool(name='synthetic_identity', structured_output=True)
    def identity(name: str) -> dict[str, str | bool]:
        counts['call'] += 1
        return {'synthetic': True, 'state': state, 'pages_complete': pages_complete,
                'trace': 'e36d2f04-0319-4da5-8a9c-f6c771cd7655', 'echo': reflect or 'SYNTHETIC'}

    sdk_app = server.streamable_http_app(json_response=True, stateless_http=True)

    async def app(scope, receive, send):
        if scope['type'] != 'http':
            return await sdk_app(scope, receive, send)
        counts['http'] += 1
        if redirect:
            return await RedirectResponse(redirect, status_code=307)(scope, receive, send)
        method_seen = None
        async def counted_receive():
            nonlocal method_seen
            message = await receive()
            if message.get('body'):
                import json
                try:
                    method = json.loads(message['body']).get('method')
                    method_seen = method
                    if method == 'initialize': counts['initialize'] += 1
                    elif method == 'tools/list': counts['list'] += 1
                except (ValueError, AttributeError):
                    pass
            return message
        async def protected_test_send(message):
            if reflect_header_on == method_seen and reflect and message['type'] == 'http.response.start':
                message = {**message, 'headers': [*message['headers'], (b'x-synthetic-private', reflect.encode())]}
            if escaped and message['type'] == 'http.response.start':
                message = {**message, 'headers': [(key, value) for key, value in message['headers']
                                                  if key.lower() != b'content-length']}
            if escaped and reflect and message.get('body'):
                message = {**message, 'body': message['body'].replace(reflect.encode(),
                    ''.join('\\u%04x' % ord(letter) for letter in reflect).encode())}
            await send(message)
        await sdk_app(scope, counted_receive, protected_test_send)

    sock = socket.socket(); sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    runtime = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, log_level='critical', access_log=False,
        timeout_keep_alive=1, timeout_graceful_shutdown=1))
    thread = threading.Thread(target=lambda: runtime.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not runtime.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        assert runtime.started, 'local SDK server must actually start'
        yield config(f'http://127.0.0.1:{port}/mcp', 'streamable_http'), counts, server
    finally:
        runtime.should_exit = True; thread.join(timeout=5); sock.close()
        assert not thread.is_alive(), 'synthetic server must shut down'
