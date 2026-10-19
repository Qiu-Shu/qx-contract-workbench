"""Bounded private parent pipe; application authority stays on its event loop."""
import asyncio
from contextlib import asynccontextmanager
import json
import math
import os
import re
from threading import Event
from uuid import UUID

PROTOCOL = 'qx-model-control-v1'
MAX_BYTES = 32768
MAX_SEQUENCE = 9007199254740991
_OPERATIONS = {'configure', 'disable', 'authorize', 'revoke'}
_CODES = {'BLOCKED_LIVE', 'VERSION_CONFLICT', 'STATE_CONFLICT', 'BUDGET_EXCEEDED', 'CROSS_MATTER_DENIED'}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('CONTROL_REJECTED')
        value[key] = item
    return value


def _constant(value):
    raise ValueError('CONTROL_REJECTED')


def parse_control_line(line, nonce, sequence):
    try:
        if type(line) is bytes:
            if len(line) > MAX_BYTES:
                raise ValueError
            line = line.decode('utf-8')
        if type(line) is not str:
            raise ValueError
        if not line.endswith('\n') or len(line.encode('utf-8')) > MAX_BYTES:
            raise ValueError
        value = json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
        if (type(value) is not dict or set(value) != {'event','protocol','nonce','sequence','operation','payload'}
                or value['event'] != 'model-control' or value['protocol'] != PROTOCOL
                or value['nonce'] != nonce or type(value['sequence']) is not int
                or not 1 <= value['sequence'] <= MAX_SEQUENCE or value['sequence'] != sequence
                or type(value['operation']) is not str or value['operation'] not in _OPERATIONS
                or type(value['payload']) is not dict):
            raise ValueError
        pending = [(value['payload'], 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 16 or (type(item) is float and not math.isfinite(item)):
                raise ValueError
            if type(item) is dict:
                pending.extend((part, depth+1) for part in item.values())
            elif type(item) is list:
                pending.extend((part, depth+1) for part in item)
        return value['operation'], value['payload']
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ValueError('CONTROL_REJECTED') from None


class ParentControlChannel:
    def __init__(self, stream, nonce, emit, on_eof, *, fatal=os._exit, timeout=10):
        self._stream, self._nonce = stream, nonce
        self._emit, self._on_eof, self._fatal = emit, on_eof, fatal
        self._timeout = timeout
        self._closed = Event()
        self._loop = self._handler = None

    def bind(self, handler):
        if self._closed.is_set() or self._loop is not None:
            raise ValueError('CONTROL_REJECTED')
        self._handler = handler
        self._loop = asyncio.get_running_loop()

    def close(self):
        self._closed.set()
        if self._handler is not None:
            self._handler.disable()

    def _request_close(self):
        self._closed.set()
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self.close)
            except RuntimeError:
                pass

    def _fail(self):
        self._closed.set()
        self._fatal(2)

    async def _dispatch(self, operation, payload):
        from .security import ServiceError
        if self._closed.is_set() or asyncio.get_running_loop() is not self._loop:
            raise ValueError('CONTROL_REJECTED')
        try:
            if operation == 'disable':
                if payload:
                    raise ServiceError('BLOCKED_LIVE', 403)
                result = self._handler.disable()
            else:
                result = getattr(self._handler, operation)(payload)
        except ServiceError as error:
            return {'ok':False, 'code':error.code if error.code in _CODES else 'BLOCKED_LIVE'}
        except Exception:
            self._handler.disable()
            return {'ok':False, 'code':'BLOCKED_LIVE'}
        expected = {'configure':{'configured'}, 'disable':{'disabled'},
                    'authorize':{'authorized','existing'}, 'revoke':{'revoked'}}[operation]
        if type(result) is not dict or result.get('status') not in expected:
            raise ValueError('CONTROL_REJECTED')
        keys = {'status','config_sha256','config_version'} if operation == 'configure' else {'status'}
        if set(result) != keys:
            raise ValueError('CONTROL_REJECTED')
        if operation == 'configure':
            if (type(result['config_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', result['config_sha256'])
                    or type(result['config_version']) is not str
                    or str(UUID(result['config_version'])) != result['config_version']):
                raise ValueError('CONTROL_REJECTED')
        return {'ok':True, **result}

    def watch(self):
        sequence = 1
        while not self._closed.is_set():
            future = None
            try:
                line = self._stream.readline(MAX_BYTES+1)
                if line == b'':
                    self._request_close()
                    self._on_eof()
                    return
                operation, payload = parse_control_line(line, self._nonce, sequence)
                if self._loop is None or self._closed.is_set():
                    raise ValueError('CONTROL_REJECTED')
                coroutine = self._dispatch(operation, payload)
                try:
                    future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
                except RuntimeError:
                    coroutine.close()
                    raise
                result = future.result(timeout=self._timeout)
                if self._closed.is_set():
                    return
                self._emit(event='model-control-result', protocol=PROTOCOL,
                           nonce=self._nonce, sequence=sequence, **result)
                sequence += 1
                # References are released, not a claim to erase immutable strings.
                line = payload = result = None
            except Exception:
                if future is not None:
                    future.cancel()
                self._fail()
                return


def attach_control(app, channel, handler):
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            channel.bind(handler)
            try:
                yield
            finally:
                channel.close()

    app.router.lifespan_context = lifespan
