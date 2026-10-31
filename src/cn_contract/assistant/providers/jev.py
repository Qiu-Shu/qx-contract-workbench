"""Bounded Jev transport; unconnected and denied by default.

The trusted caller must claim its durable attempt and check independent egress,
scope and budget before allowing preflight. No retry or persistence lives here.
"""
import asyncio
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256
import inspect
import logging
import re
from typing import get_args

from ... import domain as d
from ...config import canonical_json
from . import jev_codec as codec


_ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
_LOOPBACK = re.compile(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/v1/systemone\Z')
_private = ContextVar('assistant_jev_private_transport', default=False)


def _protect_logs():
    """Suppress HTTP diagnostics only in the current private async context."""
    previous = logging.getLogRecordFactory()
    if not getattr(previous, '_qx_jev_private', False):
        # Preserve earlier privacy markers so alternating providers stabilize.
        @wraps(previous)
        def factory(*args, **kwargs):
            record = previous(*args, **kwargs)
            if _private.get() and record.name.startswith(('httpx2', 'httpcore2')):
                record.msg = 'Assistant judge HTTP operation'; record.args = ()
                record.exc_info = None; record.exc_text = None; record.stack_info = None
            return record
        factory._qx_jev_private = True
        logging.setLogRecordFactory(factory)


class _InvalidResponse(ValueError):
    pass


class _ConfigurationChanged(ValueError):
    pass


class _PreflightDenied(ValueError):
    def __init__(self, reason):
        self.reason = reason


class JevCancelledError(asyncio.CancelledError):
    """Cancellation carrying only an already parsed, safe accounting receipt."""

    def __init__(self, result: d.JudgeResult):
        super().__init__()
        self.result = result


def _preflight(callback, request, config):
    reason = 'no_egress' if callback is None else callback(request, config)
    if inspect.iscoroutine(reason):
        reason.close()
        raise ValueError()
    if reason is not None and (type(reason) is not str or reason not in get_args(d.JudgeSkipReason)):
        raise ValueError()
    return reason


class JevProvider:
    def __init__(self, config: d.JevConfig, secret_resolver, *, preflight=None):
        self.config = codec.validated_config(config)
        if not callable(secret_resolver) or (preflight is not None and not callable(preflight)):
            raise ValueError('trusted resolver and preflight required')
        self._initial_config = self.config
        self._secret_resolver = secret_resolver
        self._preflight = preflight
        self._endpoint = _ENDPOINT
        self._synthetic = False

    @classmethod
    def for_synthetic_loopback(cls, config, secret_resolver, endpoint, *, preflight=None):
        """Trusted test assembly only, never a destination from user material."""
        match = _LOOPBACK.fullmatch(endpoint) if type(endpoint) is str else None
        if match is None or int(match[1]) > 65535:
            raise ValueError('exact synthetic loopback required')
        instance = cls(config, secret_resolver, preflight=preflight)
        instance._endpoint = endpoint; instance._synthetic = True
        return instance

    @property
    def is_synthetic(self):
        return self._synthetic

    def _unchanged(self, config):
        try:
            return codec.validated_config(self.config) == config
        except ValueError:
            return False

    async def judge(self, request: d.JudgeRequest, *,
                    expected_config: d.JevConfig | None = None, preflight=None) -> d.JudgeResult:
        loop = asyncio.get_running_loop(); started = loop.time()
        config_invalid = False
        try:
            config = codec.validated_config(self.config if expected_config is None else expected_config)
        except ValueError:
            config = self._initial_config; config_invalid = True
        deadline = started + config.timeout_ms / 1000
        invalid_request = False
        try:
            value = codec.validated_request(request)
            digest = codec.input_hash(value, config)
        except ValueError:
            # A forged DTO may still have a valid receipt identity. Never return
            # a Pydantic exception (which embeds the consultation) to a caller.
            try:
                if type(request) is not d.JudgeRequest:
                    raise ValueError()
                fields = request.model_dump(mode='python', warnings=False)
                value = d.JudgeRequest.model_validate({**fields, 'purpose': 'primary_intent',
                    'text': '', 'explicit_skill': None})
                digest = sha256(canonical_json({'template_version': codec.TEMPLATE_VERSION,
                    'request': request.model_dump(mode='json', warnings=False),
                    'config': config.model_dump(mode='json')}).encode('utf-8', errors='surrogatepass')).hexdigest()
                invalid_request = True
            except Exception:
                raise ValueError('invalid judge request identity') from None
        evidence = 'not_sent'
        decoded = {'answers': {}, 'usage': None, 'provider_request_id': None, 'model': None}

        def check_deadline():
            if loop.time() >= deadline:
                raise TimeoutError()

        def finish(status, reason=None):
            if config_invalid or not self._unchanged(config):
                status, reason = 'failed', 'config_changed'
            if loop.time() >= deadline:
                status, reason = 'timed_out', 'timeout'
            result_type = d.ServiceJudgeResult if type(value) is d.ServiceJudgeRequest else d.JudgeResult
            result = result_type(status=status, reason_code=reason, evidence=evidence,
                local_request_id=value.local_request_id, scope=value.scope, input_hash=digest,
                elapsed_ms=max(0, int((loop.time() - started) * 1000)),
                model=decoded['model'] if evidence == 'received' else None,
                answers=decoded['answers'] if status == 'ok' else {},
                usage=decoded['usage'] if evidence == 'received' else None,
                provider_request_id=decoded['provider_request_id'] if evidence == 'received' else None)
            if status == 'ok' and loop.time() >= deadline:
                return result_type.model_validate({**result.model_dump(mode='python'),
                    'status': 'timed_out', 'reason_code': 'timeout', 'answers': {},
                    'elapsed_ms': max(0, int((loop.time() - started) * 1000))})
            return result

        if config_invalid or not self._unchanged(config):
            return finish('failed', 'config_changed')
        if invalid_request:
            return finish('invalid', 'invalid_request')
        _protect_logs(); token = _private.set(True)
        try:
            check_deadline()
            if not config.enabled:
                return finish('skipped', 'unconfigured')
            if value.purpose == 'primary_intent' and value.explicit_skill is not None:
                return finish('skipped', 'explicit_skill')
            if not value.text.strip():
                return finish('skipped', 'not_needed')
            callback = self._preflight if preflight is None else preflight
            reason = _preflight(callback, value, config)
            check_deadline()
            if reason is not None:
                return finish('skipped', reason)
            try:
                body = codec.build_request(value, config)
            except ValueError:
                return finish('invalid', 'invalid_request')
            check_deadline()
            match = _LOOPBACK.fullmatch(self._endpoint) if self._synthetic else None
            if ((self._synthetic and (match is None or int(match[1]) > 65535))
                    or (not self._synthetic and self._endpoint != _ENDPOINT)):
                raise ValueError()
            secret = self._secret_resolver()
            check_deadline()
            if (type(secret) is not str or not 1 <= len(secret) <= 4096
                    or any(not 33 <= ord(c) <= 126 for c in secret)):
                raise ValueError()
            wire = canonical_json(body).encode('utf-8')
            check_deadline()
            # Local skip paths never import a network dependency.
            import httpx2
            check_deadline()
            if not self._unchanged(config):
                return finish('failed', 'config_changed')
            async with asyncio.timeout_at(deadline):
                remaining = deadline - loop.time()
                transport = httpx2.AsyncHTTPTransport(trust_env=False, retries=0)
                async with httpx2.AsyncClient(transport=transport, trust_env=False,
                        follow_redirects=False, timeout=httpx2.Timeout(remaining)) as client:
                    check_deadline()
                    if not self._unchanged(config):
                        raise _ConfigurationChanged()
                    reason = _preflight(callback, value, config)
                    check_deadline()
                    if reason is not None:
                        raise _PreflightDenied(reason)
                    if not self._unchanged(config):
                        raise _ConfigurationChanged()
                    evidence = 'sent_unknown'
                    async with client.stream('POST', self._endpoint, content=wire, headers={
                            'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json',
                            'Accept': 'application/json', 'Accept-Encoding': 'identity'}) as response:
                        data = bytearray()
                        async for chunk in response.aiter_raw():
                            if len(data) + len(chunk) > config.max_response_bytes:
                                raise _InvalidResponse()
                            data.extend(chunk)
                        evidence = 'received'
                        supported = (response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
                                     == 'application/json' and
                                     response.headers.get('content-encoding', 'identity').lower() == 'identity')
                        decoded = codec.decode_response(bytes(data) if supported else b'', value, config,
                            response.headers.get('x-typesafe-request-id'), secret)
                        if response.status_code != 200 or decoded.get('reason_code') == 'provider_error':
                            status, reason = 'failed', 'provider_error'
                        elif decoded.get('reason_code') is not None:
                            status, reason = 'invalid', 'invalid_response'
                        else:
                            status, reason = 'ok', None
            # Context cleanup and synchronous parsing consume the same deadline.
            return finish(status, reason)
        except asyncio.CancelledError:
            if evidence == 'received':
                # Cleanup cancellation must not discard already received usage.
                # Non-ok status removes all answers; cancellation still propagates.
                raise JevCancelledError(finish('failed', 'provider_error')) from None
            raise
        except TimeoutError:
            return finish('timed_out', 'timeout')
        except _InvalidResponse:
            return finish('invalid', 'invalid_response')
        except _ConfigurationChanged:
            return finish('failed', 'config_changed')
        except _PreflightDenied as failure:
            return finish('skipped', failure.reason)
        except Exception as error:
            if 'httpx2' in locals() and isinstance(error, httpx2.TimeoutException):
                return finish('timed_out', 'timeout')
            return finish('failed', 'provider_error')
        finally:
            _private.reset(token)
