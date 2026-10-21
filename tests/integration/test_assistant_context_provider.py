"""Actual loopback HTTP only; no account, live model, app grant or database."""
import asyncio
import json
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.context import DeepSeekContextProvider
from cn_contract.assistant.providers.context_codec import prepare, decode_response
from cn_contract.assistant.providers.policy import receipt
from tests.unit.test_assistant_context_codec import fixture
from tests.unit.test_assistant_context_preview import config
from tests.integration.test_assistant_main_provider import KEY, envelope as old_envelope, raw, server, request as old_request


def envelope(request, **candidate_changes):
    value = old_envelope(old_request())
    value['choices'][0]['message']['content'] = json.dumps(dict(text='合成回答，引用仍待律师核验。',
        citations=[{'saved_citation_id':str(request.manifest.sources[0].saved_citation_id),
            'quote_sha256':request.manifest.sources[0].quote_sha256}]) | candidate_changes, ensure_ascii=False)
    return value


def provider(configured, endpoint, resolver=None):
    return DeepSeekContextProvider.for_synthetic_loopback(configured, resolver or (lambda:KEY), endpoint)


def test_exact_context_wire_and_received_candidate_keep_unverified_citations():
    configured, _, request = fixture()
    with server(raw(envelope(request))) as (url, received, _):
        result = asyncio.run(provider(configured, url).generate(request, preflight=lambda:True))
    assert type(result) is d.MainContextReply and result.state == 'received' and result.error_code is None
    assert len(received) == 1
    assert received[0]['body'] == prepare(request, configured).wire_payload_json.encode('utf-8')
    assert result.output.citations[0].saved_citation_id == request.manifest.sources[0].saved_citation_id
    assert result.usage.total_tokens == 42
    assert receipt(result, configured).cost_status == 'estimated'


@pytest.mark.parametrize('preflight', [None, lambda:False, lambda:1, lambda:[]])
def test_context_adapter_defaults_closed_and_does_not_resolve_secret(preflight):
    configured, _, request = fixture()
    resolved = []
    with server(raw(envelope(request))) as (url, received, _):
        result = asyncio.run(provider(configured, url, lambda:resolved.append(True) or KEY)
            .generate(request, preflight=preflight))
    assert result.state == 'failed_before_send' and result.error_code == 'BLOCKED_LIVE'
    assert not received and not resolved


def test_permission_rechecked_after_secret_resolution():
    configured, _, request = fixture()
    allowed = [True]
    calls = []
    def resolve():
        allowed[0] = False
        return KEY
    def preflight():
        calls.append(allowed[0])
        return allowed[0]
    with server(raw(envelope(request))) as (url, received, _):
        result = asyncio.run(provider(configured, url, resolve).generate(request, preflight=preflight))
    assert result.error_code == 'BLOCKED_LIVE' and calls == [True, False] and not received


@pytest.mark.parametrize('candidate', [
    {'citations':[{'saved_citation_id':str(uuid4()), 'quote_sha256':'0'*64}]},
    {'support_status':'verified'}, {'tool_calls':[]}, {'text':' '},
])
def test_invalid_candidate_retains_received_usage_for_cost_accounting(candidate):
    configured, _, request = fixture()
    with server(raw(envelope(request, **candidate))) as (url, received, _):
        result = asyncio.run(provider(configured, url).generate(request, preflight=lambda:True))
    assert len(received) == 1 and result.state == 'received' and result.error_code == 'MODEL_OUTPUT_INVALID'
    assert result.output is None and result.usage.total_tokens == 42
    assert receipt(result, configured).cost_status == 'estimated'


@pytest.mark.parametrize('mutation', ['wrong_hash', 'duplicate', 'duplicate_key', 'tool', 'reasoning', 'secret'])
def test_strict_context_decode_reuses_transport_envelope_rules(mutation):
    configured, _, request = fixture()
    body = envelope(request)
    message = body['choices'][0]['message']
    candidate = json.loads(message['content'])
    if mutation == 'wrong_hash':candidate['citations'][0]['quote_sha256'] = '0'*64
    elif mutation == 'duplicate':candidate['citations'] *= 2
    elif mutation == 'tool':message['tool_calls'] = [{'id':'forbidden'}]
    elif mutation == 'reasoning':message['reasoning_content'] = '合成私有内容'
    elif mutation == 'secret':candidate['text'] = KEY
    message['content'] = json.dumps(candidate)
    if mutation == 'duplicate_key':message['content'] = '{"text":"甲","text":"乙","citations":[]}'
    result = decode_response(raw(body), request, configured, KEY)
    assert result.output is None and result.state == 'received'
    if mutation == 'secret':
        assert result.usage is None and result.provider_request_id is None
    else:
        assert result.usage.total_tokens == 42 and result.error_code == 'MODEL_OUTPUT_INVALID'


@pytest.mark.parametrize('mutation', ['basis', 'config', 'disabled', 'v1'])
def test_invalid_input_is_blocked_before_secret_or_network(mutation):
    configured, _, request = fixture()
    if mutation == 'basis':request = request.model_copy(update={'basis':request.basis.model_copy(update={'wire_sha256':'0'*64})})
    elif mutation == 'config':configured = config(price_reference='changed synthetic price')
    elif mutation == 'disabled':configured = config(enabled=False)
    elif mutation == 'v1':request = old_request()
    resolved = []
    with server() as (url, received, _):
        result = asyncio.run(provider(configured, url, lambda:resolved.append(True) or KEY)
            .generate(request, preflight=lambda:True))
    assert result.state == 'failed_before_send' and not received and not resolved


def test_truncated_transport_stays_unknown_without_retry():
    configured, _, request = fixture()
    with server(b'{', declared_length=100) as (url, received, _):
        result = asyncio.run(provider(configured, url).generate(request, preflight=lambda:True))
    assert result.state == 'sent_unknown' and result.usage is None and len(received) == 1
    assert receipt(result, configured).cost_status == 'unknown'
