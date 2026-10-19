"""Local random-port HTTP and synthetic secrets only. Never calls TypeSafe."""
import asyncio
import builtins
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import logging
import subprocess
import sys
from threading import Event, Thread
import time
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.config import canonical_json
from cn_contract.assistant.providers import jev_codec as codec


KEY = 'SYNTHETIC_JEV_SECRET_DO_NOT_USE_12345'
TEXT = '完全虚构咨询标记：先回复客户，再整理附件。\n保留全部文字 😀'


def api():
    return importlib.import_module('cn_contract.assistant.providers.jev')


def config(**changes):
    return d.JevConfig(enabled=True, **changes)


def request(purpose='primary_intent', **changes):
    value = dict(local_request_id=uuid4(), scope=d.ScopeSnapshot(workspace_id=uuid4(),
        conversation_id=uuid4(), binding_revision=1, input_revision=2, materials_revision=3),
        purpose=purpose, text=TEXT)
    value.update(changes)
    return d.JudgeRequest(**value)


def envelope(value):
    question = codec.build_request(value, config())['questions'][value.purpose]
    answer = {'type': 'noul', 'noul': .8} if question['type'] == 'noul' else {
        'type': 'choice', 'choice': next(iter(question['criteria'])), 'confidence': .7,
        'probabilities': {key: int(i == 0) for i, key in enumerate(question['criteria'])}}
    return {'model': 'jev-1.13.0', 'answers': {value.purpose: answer},
            'usage': {'input_tokens': 20, 'output_tokens': 4}}


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


@contextmanager
def server(body=b'', *, status=200, headers=None, chunks=None, pause=0,
           header_pause=0, declared_length=None, content_type='application/json'):
    received, seen, stopped = [], Event(), Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def do_POST(self):
            received.append({'path': self.path, 'headers': dict(self.headers),
                'body': self.rfile.read(int(self.headers['Content-Length']))})
            seen.set()
            try:
                if stopped.wait(header_pause):
                    return
                self.send_response(status)
                if content_type is not None:
                    self.send_header('Content-Type', content_type)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                if chunks is None:
                    self.send_header('Content-Length', str(len(body) if declared_length is None else declared_length))
                else:
                    self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                if chunks is None:
                    if not stopped.wait(pause):
                        self.wfile.write(body); self.wfile.flush()
                    if declared_length is not None:
                        self.close_connection = True
                else:
                    for chunk in chunks:
                        if stopped.wait(pause):
                            return
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                        self.wfile.flush()
                    self.wfile.write(b'0\r\n\r\n'); self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    instance.daemon_threads = True
    thread = Thread(target=instance.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{instance.server_port}/v1/systemone', received, seen
    finally:
        stopped.set(); instance.shutdown(); instance.server_close(); thread.join(2)


def provider(url, **changes):
    return api().JevProvider.for_synthetic_loopback(config(**changes), lambda: KEY, url,
                                                  preflight=lambda *_: None)


@pytest.mark.parametrize('case,reason', [('disabled', 'unconfigured'), ('default', 'no_egress'),
    ('explicit', 'explicit_skill'), ('empty', 'not_needed'), ('no_budget', 'no_budget'),
    ('no_egress', 'no_egress'), ('stale_scope', 'stale_scope')])
def test_local_skip_does_not_resolve_secret_import_http_or_dispatch(monkeypatch, case, reason):
    module = api(); original = builtins.__import__; touched = []

    def importing(name, *args, **kwargs):
        if name == 'httpx2':
            touched.append('http'); raise AssertionError('local skip imported transport')
        return original(name, *args, **kwargs)

    def secret():
        touched.append('secret'); raise AssertionError('local skip read credential')

    monkeypatch.setattr(builtins, '__import__', importing)
    cfg = d.JevConfig(enabled=case != 'disabled')
    value = request(explicit_skill='client_reply' if case == 'explicit' else None,
                    text='' if case == 'empty' else TEXT)
    preflight = None if case == 'default' else lambda *_: case if case in (
        'no_budget', 'no_egress', 'stale_scope') else None
    result = asyncio.run(module.JevProvider(cfg, secret, preflight=preflight).judge(value))
    assert (result.status, result.reason_code, result.evidence) == ('skipped', reason, 'not_sent')
    assert touched == [] and result.usage is None and result.provider_request_id is None
    assert result.scope == value.scope and result.input_hash == codec.input_hash(value, cfg)
    assert result.model is None


@pytest.mark.parametrize('purpose', ['primary_intent', 'material_kind', 'possible_result_guarantee'])
def test_real_loopback_sends_one_fixed_question_once_without_identity_or_proxy(monkeypatch, purpose):
    value = request(purpose)
    monkeypatch.setenv('HTTP_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setenv('ALL_PROXY', 'http://127.0.0.1:1')
    with server(raw(envelope(value)), headers={'x-typesafe-request-id': 'synthetic-response'}) as (url, calls, _):
        instance = provider(url); result = asyncio.run(instance.judge(value))
    assert result.status == 'ok' and result.evidence == 'received' and instance.is_synthetic
    assert len(calls) == 1 and calls[0]['path'] == '/v1/systemone'
    assert calls[0]['body'] == canonical_json(codec.build_request(value, config())).encode('utf-8')
    assert calls[0]['headers']['Authorization'] == 'Bearer ' + KEY
    assert calls[0]['headers']['Accept-Encoding'] == 'identity'
    assert calls[0]['headers']['Content-Type'] == 'application/json'
    assert result.provider_request_id == 'synthetic-response' and result.usage.input_tokens == 20
    assert result.scope == value.scope and result.input_hash == codec.input_hash(value, config())
    assert result.elapsed_ms < 2000


@pytest.mark.parametrize('url', ['https://api.typesafe.ai/v1/systemone',
    'http://localhost:123/v1/systemone', 'http://127.0.0.1:0/v1/systemone',
    'http://127.0.0.1:65536/v1/systemone', 'http://127.0.0.1:0123/v1/systemone',
    'http://user@127.0.0.1:123/v1/systemone', 'http://127.0.0.1:123/v1/systemone?x=1',
    'http://127.0.0.1:123/v1/systemone/', 'http://127.0.0.2:123/v1/systemone'])
def test_synthetic_factory_cannot_point_to_arbitrary_destination(url):
    with pytest.raises(ValueError, match='exact synthetic loopback required'):
        provider(url)


@pytest.mark.parametrize('status', [301, 307, 401, 429, 529])
def test_non_200_and_redirect_have_one_post_and_no_retry(status):
    value = request()
    with server(raw(envelope(value))) as (sink, sink_calls, _):
        with server(b'{}', status=status, headers={'Location': sink, 'Retry-After': '1'}) as (url, calls, _):
            result = asyncio.run(provider(url).judge(value))
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'provider_error', 'received')
    assert len(calls) == 1 and sink_calls == [] and result.answers == {}


@pytest.mark.parametrize('mode', ['headers', 'body', 'chunks', 'truncated', 'oversize'])
def test_partial_or_late_response_is_unknown_and_never_retried(mode):
    value = request(); body = raw(envelope(value))
    options = {'header_pause': .3} if mode == 'headers' else {'pause': .3} if mode == 'body' else (
        {'chunks': [body[i:i+20] for i in range(0, len(body), 20)], 'pause': .025} if mode == 'chunks' else
        {'declared_length': len(body) + 50} if mode == 'truncated' else {})
    with server(body, **options) as (url, calls, _):
        instance = provider(url, timeout_ms=150, max_response_bytes=20 if mode == 'oversize' else 262144)
        result = asyncio.run(instance.judge(value))
    assert result.evidence == 'sent_unknown' and result.status != 'ok' and result.answers == {}
    assert result.usage is None and result.provider_request_id is None and len(calls) == 1
    if mode in ('headers', 'body', 'chunks'):
        assert result.status == 'timed_out' and result.reason_code == 'timeout'


def test_cancellation_propagates_without_background_retry():
    value = request()
    with server(raw(envelope(value)), pause=.5) as (url, calls, seen):
        async def exercise():
            task = asyncio.create_task(provider(url).judge(value))
            while not seen.is_set():
                await asyncio.sleep(.002)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(.025)
        asyncio.run(exercise())
    assert len(calls) == 1


def test_config_change_during_io_drops_answers_but_retains_received_usage():
    value = request()
    with server(raw(envelope(value)), pause=.08) as (url, calls, seen):
        instance = provider(url)
        async def exercise():
            task = asyncio.create_task(instance.judge(value))
            while not seen.is_set():
                await asyncio.sleep(.002)
            instance.config = d.JevConfig()
            return await task
        result = asyncio.run(exercise())
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'config_changed', 'received')
    assert result.answers == {} and result.usage.input_tokens == 20 and len(calls) == 1


def test_expected_config_mismatch_never_resolves_secret():
    def forbidden():
        pytest.fail('stale config resolved secret')
    result = asyncio.run(api().JevProvider(config(), forbidden, preflight=lambda *_: None).judge(
        request(), expected_config=d.JevConfig()))
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'config_changed', 'not_sent')


def test_wire_oversize_is_invalid_without_secret_or_http():
    calls = []
    result = asyncio.run(api().JevProvider(config(max_input_bytes=5), lambda: calls.append(1),
        preflight=lambda *_: None).judge(request()))
    assert (result.status, result.reason_code, result.evidence) == ('invalid', 'invalid_request', 'not_sent')
    assert not calls


@pytest.mark.parametrize('stage', ['preflight', 'secret', 'import', 'decode', 'cleanup'])
def test_one_deadline_includes_synchronous_preparation_parsing_and_cleanup(monkeypatch, stage):
    module = api(); value = request(); original_import = builtins.__import__
    import httpx2
    original_decode = codec.decode_response
    original_exit = httpx2.AsyncClient.__aexit__

    def slow():
        time.sleep(.13)

    def preflight(*_):
        if stage == 'preflight': slow()
        return None

    def secret():
        if stage == 'secret': slow()
        return KEY

    def importing(name, *args, **kwargs):
        if name == 'httpx2' and stage == 'import': slow()
        return original_import(name, *args, **kwargs)

    def decode(*args, **kwargs):
        result = original_decode(*args, **kwargs)
        if stage == 'decode': slow()
        return result

    async def cleanup(self, *args):
        result = await original_exit(self, *args)
        if stage == 'cleanup': slow()
        return result

    monkeypatch.setattr(builtins, '__import__', importing)
    monkeypatch.setattr(codec, 'decode_response', decode)
    monkeypatch.setattr(httpx2.AsyncClient, '__aexit__', cleanup)
    with server(raw(envelope(value))) as (url, calls, _):
        instance = module.JevProvider.for_synthetic_loopback(config(timeout_ms=100), secret, url,
                                                           preflight=preflight)
        result = asyncio.run(instance.judge(value))
    assert result.status == 'timed_out' and result.reason_code == 'timeout' and result.answers == {}
    assert result.elapsed_ms >= 100
    assert result.evidence == ('received' if stage in ('decode', 'cleanup') else 'not_sent')
    assert len(calls) == (1 if stage in ('decode', 'cleanup') else 0)


def test_private_transport_logs_are_sanitized_and_other_context_is_not(monkeypatch, caplog):
    import httpx2
    original = httpx2.AsyncClient.send

    async def sending(self, *args, **kwargs):
        try:
            raise ValueError(KEY + TEXT)
        except ValueError:
            logging.getLogger('httpx2.future').warning(KEY + TEXT, exc_info=True, stack_info=True)
        await asyncio.sleep(.01)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(httpx2.AsyncClient, 'send', sending)
    value = request()
    caplog.set_level(logging.DEBUG)
    with server(raw(envelope(value))) as (url, calls, _):
        async def exercise():
            task = asyncio.create_task(provider(url).judge(value))
            await asyncio.sleep(.005)
            logging.getLogger('httpx2.other').warning('outside-context-visible')
            return await task
        result = asyncio.run(exercise())
    assert result.status == 'ok' and len(calls) == 1
    assert KEY not in caplog.text and TEXT not in caplog.text and 'outside-context-visible' in caplog.text


@pytest.mark.parametrize('mode', ['invalid-answer', 'reflect-body', 'reflect-header'])
def test_invalid_or_reflected_response_contains_no_private_text(mode):
    value = request(); body = envelope(value); headers = {'x-typesafe-request-id': 'safe-id'}
    if mode == 'invalid-answer':
        body['answers']['primary_intent']['choice'] = TEXT
    elif mode == 'reflect-body':
        body[KEY] = TEXT
    else:
        headers['x-typesafe-request-id'] = KEY
    with server(raw(body), headers=headers) as (url, calls, _):
        result = asyncio.run(provider(url).judge(value))
    assert KEY not in result.model_dump_json() and TEXT not in result.model_dump_json()
    assert len(calls) == 1
    if mode == 'invalid-answer':
        assert result.status == 'invalid' and result.usage.input_tokens == 20
    elif mode == 'reflect-body':
        assert result.status == 'failed' and result.usage is None
    else:
        assert result.status == 'ok' and result.provider_request_id is None


def test_config_change_while_entering_client_stops_before_post(monkeypatch):
    import httpx2
    original = httpx2.AsyncClient.__aenter__
    value = request()
    with server(raw(envelope(value))) as (url, calls, _):
        instance = provider(url)
        async def entering(self):
            result = await original(self)
            instance.config = d.JevConfig()
            return result
        monkeypatch.setattr(httpx2.AsyncClient, '__aenter__', entering)
        result = asyncio.run(instance.judge(value))
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'config_changed', 'not_sent')
    assert calls == []


@pytest.mark.parametrize('text', [123, '中' * 32769, '\ud800'], ids=['non-string', 'oversize', 'surrogate'])
def test_forged_text_with_valid_identity_is_invalid_without_io(text):
    calls = []; value = request().model_copy(update={'text': text})
    result = asyncio.run(api().JevProvider(config(), lambda: calls.append(1),
        preflight=lambda *_: None).judge(value))
    assert (result.status, result.reason_code, result.evidence) == ('invalid', 'invalid_request', 'not_sent')
    assert result.local_request_id == value.local_request_id and not calls
    assert TEXT not in result.model_dump_json()


def test_forged_scope_has_only_fixed_exception_without_source_text():
    value = request().model_copy(update={'scope': {'workspace_id': TEXT}})
    with pytest.raises(ValueError) as caught:
        asyncio.run(api().JevProvider(config(), lambda: KEY).judge(value))
    assert str(caught.value) == 'invalid judge request identity'
    assert caught.value.__suppress_context__ is True


@pytest.mark.parametrize('secret', [None, '', 'x\ny', '汉字', 'x' * 4097],
                         ids=['missing', 'empty', 'newline', 'unicode', 'oversize'])
def test_invalid_secret_does_not_import_http_or_expose_value(monkeypatch, secret):
    original = builtins.__import__; touched = []
    def importing(name, *args, **kwargs):
        if name == 'httpx2': touched.append(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', importing)
    result = asyncio.run(api().JevProvider(config(), lambda: secret, preflight=lambda *_: None).judge(request()))
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'provider_error', 'not_sent')
    assert not touched and result.answers == {}


@pytest.mark.parametrize('stage', ['preflight', 'resolver'])
def test_callback_exception_is_fixed_and_does_not_expose_private_input(stage):
    def broken(*_):
        raise RuntimeError(KEY + TEXT)
    instance = api().JevProvider(config(), broken if stage == 'resolver' else lambda: KEY,
                                preflight=broken if stage == 'preflight' else lambda *_: None)
    result = asyncio.run(instance.judge(request()))
    assert (result.status, result.reason_code, result.evidence) == ('failed', 'provider_error', 'not_sent')
    assert KEY not in result.model_dump_json() and TEXT not in result.model_dump_json()


@pytest.mark.parametrize('answer', [True, 'ready', {}, []], ids=['bool', 'unknown', 'dict', 'list'])
def test_invalid_preflight_result_fails_closed(answer):
    calls = []
    result = asyncio.run(api().JevProvider(config(), lambda: calls.append(1),
        preflight=lambda *_: answer).judge(request()))
    assert result.status == 'failed' and result.evidence == 'not_sent' and not calls


def test_slow_connection_attempt_consumes_same_total_deadline(monkeypatch):
    import httpx2
    attempts = []
    async def connecting(self, request):
        attempts.append(1)
        await asyncio.sleep(.3)
        raise AssertionError('cancelled connection cannot finish')
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, 'handle_async_request', connecting)
    with server() as (url, calls, _):
        result = asyncio.run(provider(url, timeout_ms=100).judge(request()))
    assert (result.status, result.reason_code, result.evidence) == ('timed_out', 'timeout', 'sent_unknown')
    assert attempts == [1] and calls == []


def test_cold_process_import_is_lazy_and_first_judge_reports_actual_elapsed(record_property):
    value = request()
    script = '''import asyncio,json,sys
from cn_contract import domain as d
from cn_contract.assistant.providers.jev import JevProvider
assert "httpx2" not in sys.modules
value=d.JudgeRequest.model_validate_json(sys.argv[2])
provider=JevProvider.for_synthetic_loopback(d.JevConfig(enabled=True),lambda:"SYNTHETIC_COLD_KEY",sys.argv[1],preflight=lambda *_:None)
result=asyncio.run(provider.judge(value))
print(result.model_dump_json())
'''
    with server(raw(envelope(value))) as (url, calls, _):
        completed = subprocess.run([sys.executable, '-c', script, url, value.model_dump_json()],
                                   capture_output=True, text=True, timeout=10)
    assert completed.returncode == 0, completed.stderr
    result = d.JudgeResult.model_validate_json(completed.stdout)
    assert result.status == 'ok' and len(calls) == 1
    record_property('cold_judge_elapsed_ms', result.elapsed_ms)


@pytest.mark.parametrize('content_type', ['text/plain', 'text/html', None])
def test_only_json_media_type_can_supply_response_answers_or_model(content_type):
    value = request()
    with server(raw(envelope(value)), content_type=content_type) as (url, calls, _):
        result = asyncio.run(provider(url).judge(value))
    assert (result.status, result.reason_code, result.evidence) == ('invalid', 'invalid_response', 'received')
    assert result.model is None and result.answers == {} and result.usage is None and len(calls) == 1


def test_json_media_type_parameters_and_case_are_accepted():
    value = request()
    with server(raw(envelope(value)), content_type='Application/JSON; charset=utf-8') as (url, calls, _):
        result = asyncio.run(provider(url).judge(value))
    assert result.status == 'ok' and result.model == 'jev-1.13.0' and len(calls) == 1


@pytest.mark.parametrize('mode', ['bad-json', 'wrong-model', 'bad-answer', 'reflection'])
def test_reported_model_requires_independently_valid_response_model(mode):
    value = request(); body = envelope(value)
    if mode == 'wrong-model': body['model'] = 'jev-latest'
    elif mode == 'bad-answer': body['answers'] = {}
    elif mode == 'reflection': body[KEY] = TEXT
    with server(b'{' if mode == 'bad-json' else raw(body)) as (url, calls, _):
        result = asyncio.run(provider(url).judge(value))
    assert result.model == ('jev-1.13.0' if mode == 'bad-answer' else None)
    assert result.status != 'ok' and result.answers == {} and len(calls) == 1


def test_http_timeout_exception_is_a_timeout_even_before_outer_deadline(monkeypatch):
    import httpx2
    attempts = []
    async def timed_out(self, request):
        attempts.append(1)
        raise httpx2.ReadTimeout(KEY + TEXT)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, 'handle_async_request', timed_out)
    with server() as (url, calls, _):
        result = asyncio.run(provider(url).judge(request()))
    assert (result.status, result.reason_code, result.evidence) == ('timed_out', 'timeout', 'sent_unknown')
    assert result.model is None and attempts == [1] and calls == []


@pytest.mark.parametrize('first', ['main', 'jev'])
def test_logging_factory_composes_without_unbounded_wrapping(first):
    from cn_contract.assistant.providers import main
    module = api(); original = logging.getLogRecordFactory()
    try:
        logging.setLogRecordFactory(logging.LogRecord)
        initial, following = (main, module) if first == 'main' else (module, main)
        initial._protect_logs(); following._protect_logs()
        stable = logging.getLogRecordFactory()
        for _ in range(700):
            main._protect_logs(); module._protect_logs()
        final = logging.getLogRecordFactory()
        for owner in (main, module):
            token = owner._private.set(True)
            try:
                record = final('httpx2.test', logging.WARNING, '', 1, KEY + TEXT, (), None)
                assert KEY not in record.getMessage() and TEXT not in record.getMessage()
            finally:
                owner._private.reset(token)
        record = final('httpx2.test', logging.WARNING, '', 1, 'outside context', (), None)
        assert record.getMessage() == 'outside context'
    finally:
        logging.setLogRecordFactory(original)
    assert final is stable
