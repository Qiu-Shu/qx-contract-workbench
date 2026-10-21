"""Independent bounded Standards probes: synthetic local loopback only."""
import asyncio
import builtins
import logging

import pytest

from cn_contract.assistant.providers.context import DeepSeekContextProvider
from cn_contract.assistant.providers.deepseek_transport import _private
from tests.integration.test_assistant_main_provider import KEY, server
from tests.unit.test_assistant_context_codec import fixture


def test_context_cancellation_keeps_shared_log_scope_and_never_retries(caplog):
    configured, _, request = fixture()
    caplog.set_level(logging.DEBUG)

    async def scenario(endpoint, seen):
        provider = DeepSeekContextProvider.for_synthetic_loopback(configured, lambda: KEY, endpoint)
        task = asyncio.create_task(provider.generate(request, preflight=lambda: True))
        assert await asyncio.to_thread(seen.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert _private.get() is False
        logging.getLogger('httpx2').warning('independent synthetic after-cancel marker')

    with server(chunks=[b'\n'] * 80, pause=.04) as (endpoint, calls, seen):
        asyncio.run(scenario(endpoint, seen))
    assert len(calls) == 1
    assert KEY not in caplog.text
    assert 'independent synthetic after-cancel marker' in caplog.text


def test_context_default_refusal_never_reaches_secret_or_http_import(monkeypatch):
    configured, _, request = fixture()
    events = []
    original = builtins.__import__

    def audited_import(name, *args, **kwargs):
        if name == 'httpx2':
            events.append('http')
            raise AssertionError('default-refused context imported HTTP')
        return original(name, *args, **kwargs)

    def secret():
        events.append('secret')
        return KEY

    provider = DeepSeekContextProvider(configured, secret)
    monkeypatch.setattr(builtins, '__import__', audited_import)
    result = asyncio.run(provider.generate(request))
    assert events == []
    assert result.state == 'failed_before_send'
    assert result.error_code == 'BLOCKED_LIVE'
    assert result.usage is None and result.provider_request_id is None
