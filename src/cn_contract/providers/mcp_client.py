"""Installed MCP v2 SDK, restricted to explicitly provisioned synthetic loopback.

No stdio, auth discovery, redirects, proxy environment, external references or
automatic business retry. JSON-response StreamableHTTP is the supported subset.
"""
import asyncio
from contextvars import ContextVar
import logging
import json
import math
from contextlib import asynccontextmanager
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from ..domain import ToolCatalog, ToolDefinition
from ..security import ServiceError

_private_operation = ContextVar('t07_private_sdk_operation', default=False)


class _PrivateLogFilter(logging.Filter):
    def filter(self, record):
        if _private_operation.get():
            record.msg = 'T07 controlled SDK operation'
            record.args = (); record.exc_info = None; record.exc_text = None; record.stack_info = None
        return True


_log_filter = _PrivateLogFilter()


def _check_private_response(data, secret):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        def constant(_):
            raise ValueError('nonfinite JSON')
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
        stack = [(value, 0)]; count = 0
        while stack:
            item, depth = stack.pop(); count += 1
            if depth > 32 or count > 20000:
                raise ValueError('response bounds')
            if isinstance(item, str) and secret and secret in item:
                raise ValueError('private reflection')
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError('nonfinite JSON number')
            if isinstance(item, dict):
                stack.extend((part, depth+1) for pair in item.items() for part in pair)
            elif isinstance(item, list):
                stack.extend((part, depth+1) for part in item)
    except Exception:
        raise ServiceError('PROVIDER_ERROR', 502) from None


def _protect_logs():
    # Context-local sanitization: independent requests outside this operation
    # retain their logs. SDK bodies/arguments/exceptions never reach log handlers.
    previous = logging.getLogRecordFactory()
    if not getattr(previous, '_t07_private_factory', False):
        def factory(*args, **kwargs):
            record = previous(*args, **kwargs)
            if record.name.startswith(('mcp.', 'httpx2', 'httpcore2')):
                _log_filter.filter(record)
            return record
        factory._t07_private_factory = True
        # ContextVar confines sanitization to this request, while the factory
        # sees future lazy SDK/HTTP loggers before any handler gets their record.
        logging.setLogRecordFactory(factory)
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith(('mcp.', 'httpx2', 'httpcore2')):
            logger = logging.getLogger(name)
            if _log_filter not in logger.filters:
                logger.addFilter(_log_filter)


def _service_error(exception):
    stack = [exception]
    while stack:
        error = stack.pop()
        if isinstance(error, ServiceError):
            return ServiceError(error.code, error.status_code)
        if isinstance(error, BaseExceptionGroup):
            stack.extend(error.exceptions)
    return ServiceError('PROVIDER_ERROR', 502)


class SecretStore:
    """Explicit server-owned ephemeral secret map, never a config serializer."""
    def __init__(self):
        self.__values = {}

    def register(self, ref, value):
        if not isinstance(ref, str) or not ref.startswith('synthetic-secret:') or len(ref) > 128:
            raise ServiceError('BLOCKED_LIVE', 403)
        if not isinstance(value, str) or not 16 <= len(value) <= 256 or not value.isascii() or not value.isalnum():
            raise ServiceError('BLOCKED_LIVE', 403)
        self.__values[ref] = value

    def _resolve(self, ref):
        if ref not in self.__values:
            raise ServiceError('BLOCKED_LIVE', 403)
        return self.__values[ref]


class _GuardedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, endpoint, secret, capture=None):
        self.endpoint = endpoint; self.secret = secret
        self.capture = capture
        self.inner = httpx2.AsyncHTTPTransport(retries=0, trust_env=False)

    async def handle_async_request(self, request):
        if str(request.url) != self.endpoint or request.method != 'POST':
            raise ServiceError('BLOCKED_LIVE', 403)
        response = await self.inner.handle_async_request(request)
        try:
            if 300 <= response.status_code < 400:
                raise ServiceError('BLOCKED_LIVE', 403)
            if response.status_code == 202:
                return httpx2.Response(202, content=b'')
            if response.headers.get('content-type', '').split(';')[0] != 'application/json':
                raise ServiceError('PROVIDER_ERROR', 502)
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > 1048576:
                    raise ServiceError('PROVIDER_ERROR', 502)
            if self.secret and self.secret.encode() in bytes(data):
                raise ServiceError('PROVIDER_ERROR', 502)
            _check_private_response(bytes(data), self.secret)
            # Header reflection also cannot become SDK session IDs or log text.
            if self.secret and any(self.secret in v for v in response.headers.values()):
                raise ServiceError('PROVIDER_ERROR', 502)
            if self.capture is not None:
                # Capture protected actual HTTP JSON evidence before SDK output
                # validation. This does not implement/dispatch the MCP protocol.
                try:
                    method = json.loads(request.content).get('method')
                except (ValueError, AttributeError):
                    method = None
                if method == 'tools/call':
                    self.capture.append(json.loads(data))
            headers = [(key, value) for key, value in response.headers.multi_items()
                       if key.lower() not in {'content-length', 'content-encoding', 'transfer-encoding'}]
            return httpx2.Response(response.status_code, headers=headers, content=bytes(data))
        finally:
            await response.aclose()

    async def aclose(self):
        await self.inner.aclose()


@asynccontextmanager
async def _session(config, secrets=None, capture=None):
    from .qcc_registry import allowed_synthetic_endpoint
    if config.transport != 'streamable_http' or not allowed_synthetic_endpoint(config.endpoint):
        raise ServiceError('BLOCKED_LIVE', 403)
    secret = None
    if config.secret_ref:
        if type(secrets) is not SecretStore:
            raise ServiceError('BLOCKED_LIVE', 403)
        secret = secrets._resolve(config.secret_ref)
    _protect_logs()
    token = _private_operation.set(True)
    try:
        async with asyncio.timeout(5):
            async with httpx2.AsyncClient(transport=_GuardedTransport(config.endpoint, secret, capture), trust_env=False,
                follow_redirects=False, timeout=3, headers={'Authorization': 'Bearer '+secret} if secret else {}) as client:
                async with streamable_http_client(config.endpoint, http_client=client, terminate_on_close=False) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=3.0) as session:
                        await session.initialize()
                        yield session
    except Exception as error:
        safe = _service_error(error)
        if capture:
            safe._protected_raw = {'wire_response': capture[-1]}
        raise safe from None
    finally:
        _private_operation.reset(token)


async def _catalog(session):
    result = await session.list_tools()
    if result.next_cursor is not None:
        # Never represent a partial discovered catalog as complete.
        raise ServiceError('TOOL_UNBOUND', 422)
    return ToolCatalog(provider='synthetic_mcp_loopback', tools=tuple(ToolDefinition(name=t.name,
        input_schema_snapshot=t.input_schema, output_schema_snapshot=t.output_schema or {}) for t in result.tools))


async def discover(config, *, secrets=None):
    async with _session(config, secrets) as session:
        return await _catalog(session)


async def invoke(config, binding, arguments, *, secrets=None, before_dispatch=None, on_catalog=None):
    from .qcc_registry import schema_hash
    capture = []
    async with _session(config, secrets, capture) as session:
        catalog = await _catalog(session)
        if on_catalog:
            on_catalog(catalog)
        matches = [t for t in catalog.tools if t.name == binding.tool_name]
        if len(matches) != 1 or schema_hash(matches[0]) != binding.schema_hash:
            raise ServiceError('TOOL_UNBOUND', 403)
        if before_dispatch:
            before_dispatch()
        result = await session.call_tool(binding.tool_name, arguments, read_timeout_seconds=3.0)
        return {'structured': result.structured_content, 'is_error': result.is_error,
                'content': [c.model_dump(mode='json') for c in result.content],
                'wire_response': capture[-1] if capture else None}
