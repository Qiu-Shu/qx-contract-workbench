"""Bounded DeepSeek HTTP shared by independently authorized request codecs."""
import asyncio
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutine
import logging
import re

from ... import domain as d
from .deepseek_protocol import configuration, json_bytes


_ENDPOINT = 'https://api.deepseek.com/chat/completions'
_LOOPBACK = re.compile(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})/chat/completions\Z')
_private = ContextVar('assistant_main_private_transport', default=False)


def _protect_logs():
    """Sanitize transport diagnostics in this async context, including future loggers."""
    previous=logging.getLogRecordFactory()
    if not getattr(previous,'_qx_main_private',False):
        @wraps(previous)
        def factory(*args,**kwargs):
            record=previous(*args,**kwargs)
            if _private.get() and record.name.startswith(('httpx2','httpcore2')):
                record.msg='Assistant model HTTP operation';record.args=()
                record.exc_info=None;record.exc_text=None;record.stack_info=None
            return record
        factory._qx_main_private=True
        logging.setLogRecordFactory(factory)


def _allowed(preflight):
    if preflight is None:return True
    try:
        result=preflight()
        # A mistakenly async check is refused, never scheduled as permission.
        if iscoroutine(result):result.close()
        return result is True
    except Exception:
        return False


class DeepSeekTransport:
    def __init__(self, config: d.MainModelConfig, secret_resolver):
        if type(config) is not d.MainModelConfig or not callable(secret_resolver):
            raise ValueError('validated configuration and trusted resolver required')
        self.config=configuration(config)
        self._secret_resolver=secret_resolver
        self._endpoint=_ENDPOINT
        self._synthetic=False

    @classmethod
    def for_synthetic_loopback(cls, config, secret_resolver, endpoint):
        """Trusted test assembly only; never selected from a request or environment."""
        match=_LOOPBACK.fullmatch(endpoint) if type(endpoint) is str else None
        if match is None or int(match[1])>65535:raise ValueError('exact synthetic loopback required')
        result=cls(config,secret_resolver)
        result._endpoint=endpoint;result._synthetic=True
        return result

    @property
    def is_synthetic(self):
        return self._synthetic

    async def _generate(self, request, *, expected_config=None, builder, decoder, reply_type, preflight=None):
        try:
            current=configuration(self.config)
            if expected_config is not None:
                config=configuration(expected_config)
                if current!=config:
                    return reply_type(state='failed_before_send',error_code='BLOCKED_LIVE')
            else:
                config=current
            body=builder(request,config)
            if not config.enabled:
                return reply_type(state='failed_before_send',error_code='BLOCKED_LIVE')
            match=_LOOPBACK.fullmatch(self._endpoint) if self._synthetic else None
            if (self._synthetic and (match is None or int(match[1])>65535)
                    or not self._synthetic and self._endpoint!=_ENDPOINT):
                raise ValueError('untrusted endpoint')
            if not _allowed(preflight):
                return reply_type(state='failed_before_send',error_code='BLOCKED_LIVE')
            secret=self._secret_resolver()
            if (type(secret) is not str or not 1<=len(secret)<=4096
                    or any(not 33<=ord(c)<=126 for c in secret)):
                return reply_type(state='failed_before_send',error_code='BLOCKED_LIVE')
            if not _allowed(preflight):
                return reply_type(state='failed_before_send',error_code='BLOCKED_LIVE')
            wire=json_bytes(body)
            # Lazy import: local-only startup needs no network client/dependency.
            import httpx2
        except Exception:
            return reply_type(state='failed_before_send',error_code='PROVIDER_ERROR')
        _protect_logs();token=_private.set(True)
        try:
            async with asyncio.timeout(config.timeout_seconds):
                transport=httpx2.AsyncHTTPTransport(trust_env=False,retries=0)
                async with httpx2.AsyncClient(transport=transport,trust_env=False,
                        follow_redirects=False,timeout=httpx2.Timeout(
                            config.timeout_seconds,connect=min(5,config.timeout_seconds))) as client:
                    async with client.stream('POST',self._endpoint,content=wire,headers={
                            'Authorization':'Bearer '+secret,'Content-Type':'application/json',
                            'Accept':'application/json','Accept-Encoding':'identity'}) as response:
                        if (secret in str(response.headers)
                                or response.headers.get('content-encoding','identity').lower()!='identity'):
                            return reply_type(state='received',error_code='PROVIDER_ERROR')
                        data=bytearray()
                        async for chunk in response.aiter_raw():
                            if len(data)+len(chunk)>config.max_response_bytes:
                                return reply_type(state='sent_unknown',error_code='PROVIDER_ERROR')
                            data.extend(chunk)
                        if secret.encode() in data:
                            return reply_type(state='received',error_code='PROVIDER_ERROR')
                        if response.status_code!=200:
                            return reply_type(state='received',error_code='PROVIDER_ERROR')
                        return decoder(bytes(data),request,config,secret)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Even connection errors are conservative after the caller's claim;
            # no portable HTTP exception proves that the vendor saw no request.
            return reply_type(state='sent_unknown',error_code='PROVIDER_ERROR')
        finally:
            _private.reset(token)
