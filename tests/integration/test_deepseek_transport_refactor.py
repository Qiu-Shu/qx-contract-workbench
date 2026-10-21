"""Shared DeepSeek boundaries keep V1 semantics and enforce optional preflight."""
import asyncio
import builtins
import importlib
import importlib.util

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import main
from tests.integration.test_assistant_main_provider import config, request, envelope, raw, server, KEY


def transport_api():
    name = 'cn_contract.assistant.providers.deepseek_transport'
    assert importlib.util.find_spec(name) is not None, 'shared DeepSeek transport is missing'
    return importlib.import_module(name)


@pytest.mark.parametrize('refusal', ['false','none','zero','one','text','exception','coroutine','awaitable'])
def test_refused_preflight_does_not_resolve_secret_or_import_http(monkeypatch, refusal):
    module = transport_api()
    seen = []
    real_import = builtins.__import__
    def capture_import(name, *args, **kwargs):
        if name == 'httpx2':
            seen.append('http')
            raise AssertionError('refused request imported network client')
        return real_import(name, *args, **kwargs)
    def secret():
        seen.append('secret')
        return 'SYNTHETIC_UNUSED_SECRET'
    async def async_check():
        seen.append('async_body')
        return True
    class Deferred:
        def __await__(self):
            raise AssertionError('permission awaitable was executed')
    def preflight():
        if refusal == 'exception':raise RuntimeError(KEY)
        if refusal == 'coroutine':return async_check()
        if refusal == 'awaitable':return Deferred()
        return {'false':False,'none':None,'zero':0,'one':1,'text':'approved'}[refusal]
    provider = module.DeepSeekTransport(config(), secret)
    monkeypatch.setattr(builtins, '__import__', capture_import)
    result = asyncio.run(provider._generate(request(), builder=main.build_request,
        decoder=main._decode, reply_type=d.MainReply, preflight=preflight))
    assert result.state == 'failed_before_send' and result.error_code == 'BLOCKED_LIVE'
    assert seen == [] and KEY not in result.model_dump_json()


@pytest.mark.parametrize('refusal', ['false','exception','coroutine'])
def test_preflight_is_checked_again_after_secret_before_import_or_send(monkeypatch, refusal):
    module = transport_api()
    seen = []
    real_import = builtins.__import__
    def capture_import(name, *args, **kwargs):
        if name == 'httpx2':
            seen.append('http')
            raise AssertionError('revoked request imported network client')
        return real_import(name, *args, **kwargs)
    def secret():
        seen.append('secret')
        return KEY
    async def async_check():return True
    def preflight():
        seen.append('preflight')
        if len(seen) == 1:return True
        if refusal == 'exception':raise RuntimeError(KEY)
        return async_check() if refusal == 'coroutine' else False
    provider = module.DeepSeekTransport(config(), secret)
    monkeypatch.setattr(builtins, '__import__', capture_import)
    result = asyncio.run(provider._generate(request(), builder=main.build_request,
        decoder=main._decode, reply_type=d.MainReply, preflight=preflight))
    assert result.state == 'failed_before_send' and result.error_code == 'BLOCKED_LIVE'
    assert seen == ['preflight','secret','preflight'] and KEY not in result.model_dump_json()


def test_explicit_true_preflight_sends_one_exact_request():
    module = transport_api()
    value = request()
    seen = []
    def preflight():
        seen.append('preflight')
        return True
    def secret():
        seen.append('secret')
        return KEY
    with server(raw(envelope(value))) as (url, calls, _):
        provider = module.DeepSeekTransport.for_synthetic_loopback(config(), secret, url)
        result = asyncio.run(provider._generate(value, expected_config=config(), builder=main.build_request,
            decoder=main._decode, reply_type=d.MainReply, preflight=preflight))
    assert seen == ['preflight','secret','preflight']
    assert result.output is not None and result.usage.total_tokens == 42
    assert len(calls) == 1 and calls[0]['body'] == main._json_bytes(main.build_request(value, config()))


def test_shared_envelope_uses_the_callers_candidate_and_reply_contract():
    from cn_contract.assistant.providers import deepseek_protocol as protocol
    payload = envelope(request())
    seen = []
    def candidate(value):
        seen.append(value)
        return {'selected_saved_sources':('independent-test-identifier',)}
    result = protocol.decode_response(raw(payload), config(), KEY, parse_candidate=candidate, reply_type=dict)
    assert seen[0]['text'] == '待核对的合成建议'
    assert result['output'] == {'selected_saved_sources':('independent-test-identifier',)}
    assert result['usage'].total_tokens == 42 and result['provider_request_id'] == 'synthetic-response-1'


def test_candidate_rejection_preserves_received_usage_and_fixed_error():
    from cn_contract.assistant.providers import deepseek_protocol as protocol
    def candidate(_):raise ValueError('untrusted private candidate detail')
    result = protocol.decode_response(raw(envelope(request())), config(), KEY,
        parse_candidate=candidate, reply_type=d.MainReply)
    assert result.error_code == 'MODEL_OUTPUT_INVALID' and result.output is None
    assert result.usage.total_tokens == 42 and result.provider_request_id == 'synthetic-response-1'
    assert 'untrusted private candidate detail' not in result.model_dump_json()
