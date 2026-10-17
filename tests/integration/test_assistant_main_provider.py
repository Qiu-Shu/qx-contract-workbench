"""Real loopback HTTP only; no credentials or remote model are used."""
import asyncio
import builtins
from contextlib import contextmanager
from decimal import Context, Inexact, Rounded, localcontext
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import logging
from threading import Event, Thread
import time
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.config import canonical_json


KEY = 'SYNTHETIC_SECRET_DO_NOT_USE_model_transport_12345'


def api():
    try:
        return importlib.import_module('cn_contract.assistant.providers.main')
    except ModuleNotFoundError:
        pytest.fail('dedicated assistant main provider is not implemented')


def config(**changes):
    return d.MainModelConfig(enabled=True, model='deepseek-flash',
        input_usd_per_million='1', output_usd_per_million='2',
        price_reference='independent synthetic test rates', **changes)


def request():
    content = '完全虚构咨询：请整理需要追问的问题。'
    return d.MainRequest(run_id=uuid4(), message_id=uuid4(), content=content,
        source_sha256=sha256(content.encode()).hexdigest(),
        scope=d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
            binding_revision=1, input_revision=1, materials_revision=0))


def envelope(value, **changes):
    result = {'id':'synthetic-response-1', 'object':'chat.completion', 'created':1,
        'model':'deepseek-flash', 'choices':[{'index':0, 'finish_reason':'stop',
        'message':{'role':'assistant', 'content':json.dumps({'text':'待核对的合成建议',
            'citations':[{'message_id':str(value.message_id), 'quote_sha256':value.source_sha256}]},
            ensure_ascii=False)}, 'logprobs':None}],
        'usage':{'prompt_tokens':30, 'completion_tokens':12, 'total_tokens':42,
                 'prompt_cache_hit_tokens':10, 'prompt_cache_miss_tokens':20}}
    result.update(changes)
    return result


@contextmanager
def server(body=b'', *, status=200, headers=None, chunks=None, pause=0, declared_length=None):
    received, seen, stopped = [], Event(), Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *_):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            received.append({'path':self.path, 'headers':dict(self.headers), 'body':raw})
            seen.set()
            try:
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                for name,value in (headers or {}).items():
                    self.send_header(name,value)
                self.send_header('Transfer-Encoding','chunked') if chunks is not None else self.send_header(
                    'Content-Length',str(len(body) if declared_length is None else declared_length))
                self.end_headers()
                if chunks is None:
                    if not stopped.wait(pause):
                        self.wfile.write(body); self.wfile.flush()
                    if declared_length is not None:self.close_connection=True
                else:
                    for chunk in chunks:
                        if stopped.wait(pause):break
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode()+chunk+b'\r\n');self.wfile.flush()
                    self.wfile.write(b'0\r\n\r\n');self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    instance = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    instance.daemon_threads = True
    thread = Thread(target=instance.serve_forever,kwargs={'poll_interval':.02},daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{instance.server_port}/chat/completions',received,seen
    finally:
        stopped.set();instance.shutdown();instance.server_close();thread.join(2)


def raw(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False).encode()


def provider(url, **changes):
    return api().DeepSeekProvider.for_synthetic_loopback(config(**changes),lambda:KEY,url)


def test_dedicated_provider_module_exists_without_changing_mock():
    assert callable(api().build_request)


def test_real_loopback_request_is_bounded_explicit_json_and_has_only_current_message(monkeypatch):
    value=request()
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
    monkeypatch.setenv('HTTPS_PROXY','http://127.0.0.1:1')
    with server(raw(envelope(value))) as (url,calls,_):
        result=asyncio.run(provider(url).generate(value))
    assert result.state=='received' and result.error_code is None
    assert result.output.text=='待核对的合成建议' and result.usage.total_tokens==42
    assert result.provider_request_id=='synthetic-response-1' and len(calls)==1
    sent=json.loads(calls[0]['body'])
    assert calls[0]['body']==canonical_json(api().build_request(value,config())).encode('utf-8')
    assert set(sent)=={'model','messages','max_tokens','stream','thinking','response_format'}
    assert sent['stream'] is False and sent['thinking']=={'type':'disabled'}
    assert sent['response_format']=={'type':'json_object'} and sent['max_tokens']==4096
    assert len(sent['messages'])==2 and [m['role'] for m in sent['messages']]==['system','user']
    assert 'json' in sent['messages'][0]['content'].lower()
    assert value.content in calls[0]['body'].decode()
    assert str(value.scope.workspace_id) not in calls[0]['body'].decode()
    assert str(value.scope.conversation_id) not in calls[0]['body'].decode()
    assert calls[0]['headers']['Authorization']=='Bearer '+KEY
    assert calls[0]['headers']['Accept-Encoding']=='identity'


def test_exact_final_wire_bytes_are_checked_before_any_network():
    value=request(); module=api()
    body=module.build_request(value,config())
    size=len(json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
    assert module.build_request(value,config(max_input_bytes=size))==body
    with pytest.raises(ValueError):module.build_request(value,config(max_input_bytes=size-1))
    with server() as (url,calls,_):
        result=asyncio.run(provider(url,max_input_bytes=size-1).generate(value))
    assert result.state=='failed_before_send' and calls==[]


@pytest.mark.parametrize('secret',[None,'','bad\r\nheader'])
def test_missing_or_invalid_credential_never_dispatches(secret):
    value=request()
    with server() as (url,calls,_):
        instance=api().DeepSeekProvider.for_synthetic_loopback(config(),lambda:secret,url)
        result=asyncio.run(instance.generate(value))
    assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE' and not calls


def test_disabled_provider_does_not_resolve_credential():
    module=api();value=request();cfg=config().model_copy(update={'enabled':False})
    def forbidden():pytest.fail('disabled provider resolved a credential')
    result=asyncio.run(module.DeepSeekProvider(cfg,forbidden).generate(value))
    assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE'


@pytest.mark.parametrize('url',['https://example.test/chat/completions','http://localhost:1234/chat/completions',
    'http://127.0.0.1:1234/other','http://user@127.0.0.1:1234/chat/completions',
    'http://127.0.0.1:1234/chat/completions?key=x'])
def test_test_seam_cannot_accept_arbitrary_destination(url):
    with pytest.raises(ValueError):api().DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)


def test_missing_usage_is_unknown_but_valid_output_is_preserved():
    value=request(); payload=envelope(value);payload.pop('usage')
    with server(raw(payload)) as (url,_,_):result=asyncio.run(provider(url).generate(value))
    assert result.state=='received' and result.output is not None and result.usage is None


@pytest.mark.parametrize('mutation',['empty','malformed','foreign_citation','approval','finish','model','tool','reasoning'])
def test_invalid_output_never_becomes_candidate_and_known_usage_is_separate(mutation):
    value=request();payload=envelope(value);message=payload['choices'][0]['message']
    if mutation=='empty':message['content']=''
    elif mutation=='malformed':message['content']='{invalid'
    elif mutation=='foreign_citation':message['content']=json.dumps({'text':'虚构建议','citations':[{'message_id':str(uuid4()),'quote_sha256':value.source_sha256}]})
    elif mutation=='approval':message['content']='{"text":"虚构建议","citations":[],"approved":true}'
    elif mutation=='finish':payload['choices'][0]['finish_reason']='length'
    elif mutation=='model':payload['model']='another-model'
    elif mutation=='tool':message['tool_calls']=[{'id':'x','type':'function','function':{'name':'shell','arguments':'{}'}}]
    elif mutation=='reasoning':message['reasoning_content']='unrequested reasoning'
    with server(raw(payload)) as (url,calls,_):result=asyncio.run(provider(url).generate(value))
    assert result.state=='received' and result.error_code=='MODEL_OUTPUT_INVALID' and result.output is None
    assert len(calls)==1
    if mutation!='model':assert result.usage is not None


@pytest.mark.parametrize('usage',[{'prompt_tokens':True,'completion_tokens':12,'total_tokens':13},
    {'prompt_tokens':30,'completion_tokens':12,'total_tokens':99},
    {'prompt_tokens':30,'completion_tokens':12,'total_tokens':42,'prompt_cache_hit_tokens':31},
    {'prompt_tokens':-1,'completion_tokens':12,'total_tokens':11}])
def test_invalid_usage_is_never_zero_or_trusted(usage):
    value=request()
    with server(raw(envelope(value,usage=usage))) as (url,_,_):result=asyncio.run(provider(url).generate(value))
    assert result.state=='received' and result.usage is None and result.error_code=='MODEL_OUTPUT_INVALID'


@pytest.mark.parametrize('status',[301,307,401,429,500])
def test_complete_error_and_redirect_response_never_retry(status):
    with server(b'{}',status=status,headers={'Location':'http://127.0.0.1:1/secret'}) as (url,calls,_):
        result=asyncio.run(provider(url).generate(request()))
    assert result.state=='received' and result.error_code=='PROVIDER_ERROR' and result.usage is None
    assert len(calls)==1


@pytest.mark.parametrize('body,headers',[(b'{"id":1,"id":2}',{}),(b'{"id":NaN}',{}),
    (b'['*1000+b']'*1000,{}),(b'x'*100,{'Content-Encoding':'gzip'})],
    ids=['duplicate-key','nonfinite','excess-depth','compressed'])
def test_malformed_or_encoded_response_is_rejected(body,headers):
    with server(body,headers=headers) as (url,calls,_):result=asyncio.run(provider(url).generate(request()))
    assert result.output is None and result.error_code is not None and len(calls)==1


def test_chunked_response_limit_counts_actual_bytes():
    with server(chunks=[b' '*128]*10) as (url,calls,_):
        result=asyncio.run(provider(url,max_response_bytes=256).generate(request()))
    assert result.output is None and result.error_code=='PROVIDER_ERROR' and len(calls)==1


def test_nonstream_keepalive_cannot_extend_total_deadline():
    with server(chunks=[b'\n']*80,pause=.04) as (url,calls,_):
        started=time.monotonic();result=asyncio.run(provider(url,timeout_seconds=1).generate(request()))
        elapsed=time.monotonic()-started
    assert result.state=='sent_unknown' and result.usage is None and len(calls)==1
    assert .7<elapsed<2


def test_cancellation_propagates_without_resending():
    async def scenario(url,seen):
        task=asyncio.create_task(provider(url).generate(request()))
        assert await asyncio.to_thread(seen.wait,2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    with server(chunks=[b'\n']*80,pause=.04) as (url,calls,seen):
        asyncio.run(scenario(url,seen))
    assert len(calls)==1


@pytest.mark.parametrize('reflection',['body','header'])
def test_secret_reflection_and_debug_logs_never_expose_credentials(caplog,reflection):
    value=request();payload=envelope(value)
    if reflection=='body':payload['id']=KEY
    headers={'X-Private-Echo':KEY} if reflection=='header' else {}
    caplog.set_level(logging.DEBUG)
    with server(raw(payload),headers=headers) as (url,_,_):
        result=asyncio.run(provider(url).generate(value))
    assert result.output is None and result.error_code=='PROVIDER_ERROR'
    assert KEY not in caplog.text and KEY not in result.model_dump_json()


def test_leading_keepalive_whitespace_is_valid_within_budget():
    value=request()
    with server(chunks=[b'\n\n',raw(envelope(value))]) as (url,_,_):
        result=asyncio.run(provider(url).generate(value))
    assert result.output is not None and result.error_code is None


@pytest.mark.parametrize('location',['request_id','candidate','nested_candidate'])
def test_json_escaped_secret_reflection_is_rejected(location,caplog):
    value=request();payload=envelope(value)
    if location=='request_id':payload['id']=KEY
    else:
        payload['choices'][0]['message']['content']=json.dumps({'text':KEY,'citations':[]})
        if location=='nested_candidate':
            payload['choices'][0]['message']['content']=payload['choices'][0]['message']['content'].replace(KEY,'\\u0053'+KEY[1:])
    encoded=raw(payload)
    if location!='nested_candidate':encoded=encoded.replace(KEY.encode(),b'\\u0053'+KEY[1:].encode())
    assert KEY.encode() not in encoded
    caplog.set_level(logging.DEBUG)
    with server(encoded) as (url,_,_):result=asyncio.run(provider(url).generate(value))
    assert result.error_code=='PROVIDER_ERROR' and result.output is None
    assert KEY not in result.model_dump_json() and KEY not in caplog.text


def test_nonfinite_exponent_in_unused_metadata_is_not_accepted():
    value=request();encoded=raw(envelope(value))
    encoded=encoded[:-1]+b',"unexpected_metadata":1e999}'
    with server(encoded) as (url,_,_):result=asyncio.run(provider(url).generate(value))
    assert result.output is None and result.error_code=='MODEL_OUTPUT_INVALID'


def test_tampered_request_hash_is_rejected_before_dispatch():
    value=request().model_copy(update={'source_sha256':'0'*64})
    with pytest.raises(ValueError):api().build_request(value,config())
    with server() as (url,calls,_):result=asyncio.run(provider(url).generate(value))
    assert result.state=='failed_before_send' and not calls


@pytest.mark.parametrize('field',['prompt','completion'])
def test_over_budget_usage_is_preserved_even_when_output_is_rejected(field):
    value=request();usage={'prompt_tokens':30,'completion_tokens':12,'total_tokens':42}
    usage[field+'_tokens']=70000 if field=='prompt' else 5000
    usage['total_tokens']=usage['prompt_tokens']+usage['completion_tokens']
    with server(raw(envelope(value,usage=usage))) as (url,_,_):
        result=asyncio.run(provider(url).generate(value))
    assert result.error_code=='MODEL_OUTPUT_INVALID' and result.output is None
    assert result.usage is not None and result.usage.total_tokens==usage['total_tokens']


def test_missing_transport_dependency_is_proven_before_send(monkeypatch):
    module=api();value=request();real_import=builtins.__import__
    def import_without_transport(name,*args,**kwargs):
        if name=='httpx2':raise ModuleNotFoundError('synthetic missing transport')
        return real_import(name,*args,**kwargs)
    with server() as (url,calls,_):
        instance=module.DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
        monkeypatch.setattr(builtins,'__import__',import_without_transport)
        result=asyncio.run(instance.generate(value))
    assert result.state=='failed_before_send' and result.error_code=='PROVIDER_ERROR' and not calls


def test_short_response_body_is_unknown_not_a_completed_success():
    value=request();body=raw(envelope(value))
    with server(body,declared_length=len(body)+100) as (url,calls,_):
        result=asyncio.run(provider(url).generate(value))
    assert result.state=='sent_unknown' and result.output is None and result.usage is None
    assert len(calls)==1


def test_oversized_content_length_does_not_replace_actual_byte_checks():
    value=request();body=raw(envelope(value))
    with server(body,declared_length=10**12) as (url,calls,_):
        result=asyncio.run(provider(url,max_response_bytes=10).generate(value))
    assert result.state=='sent_unknown' and result.error_code=='PROVIDER_ERROR' and len(calls)==1


def test_transport_logging_scope_restores_unrelated_logger(caplog):
    value=request();caplog.set_level(logging.DEBUG)
    with server(raw(envelope(value))) as (url,_,_):
        result=asyncio.run(provider(url).generate(value))
    logging.getLogger('httpx2').warning('synthetic unrelated operation marker')
    assert result.output is not None
    assert 'synthetic unrelated operation marker' in caplog.text and KEY not in caplog.text


@pytest.mark.parametrize('change', [
    {'model':'deepseek-v4-pro'}, {'max_output_tokens':8192}, {'price_reference':'different grant rates'}])
def test_claimed_configuration_mismatch_never_resolves_secret_or_dispatches(change):
    approved=config();value=request()
    def forbidden():pytest.fail('configuration mismatch must not resolve credentials')
    with server() as (url,calls,_):
        instance=api().DeepSeekProvider.for_synthetic_loopback(approved,forbidden,url)
        instance.config=d.MainModelConfig.model_validate({**approved.model_dump(mode='python'),**change})
        result=asyncio.run(instance.generate(value,expected_config=approved))
    assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE' and not calls


def test_claimed_configuration_is_used_after_runtime_configuration_changes():
    approved=config(max_output_tokens=137);value=request()
    expected=canonical_json(api().build_request(value,approved)).encode('utf-8')
    def change_runtime():
        instance.config=d.MainModelConfig.model_validate({**approved.model_dump(mode='python'),
            'model':'deepseek-v4-pro','max_output_tokens':8192})
        return KEY
    with server(raw(envelope(value))) as (url,calls,_):
        instance=api().DeepSeekProvider.for_synthetic_loopback(approved,change_runtime,url)
        result=asyncio.run(instance.generate(value,expected_config=approved))
    assert result.state=='received' and result.error_code is None and result.output is not None
    assert len(calls)==1 and calls[0]['body']==expected


def test_invalid_claimed_configuration_is_rejected_before_dispatch():
    approved=config().model_copy(update={'max_output_tokens':0})
    with server() as (url,calls,_):
        result=asyncio.run(provider(url).generate(request(),expected_config=approved))
    assert result.state=='failed_before_send' and not calls


@pytest.mark.parametrize('stage', ['build', 'construct', 'generate'])
def test_configuration_validation_is_independent_of_callers_decimal_context(stage):
    module=api();value=request()
    approved=d.MainModelConfig.model_validate({**config().model_dump(mode='python'),
        'input_usd_per_million':'1.234567', 'output_usd_per_million':'9.876543'})
    expected=module.build_request(value,approved)
    context=Context(prec=2);context.traps[Inexact]=True;context.traps[Rounded]=True
    with server(raw(envelope(value))) as (url,calls,_):
        instance=module.DeepSeekProvider.for_synthetic_loopback(approved,lambda:KEY,url)
        with localcontext(context):
            if stage=='build':
                assert module.build_request(value,approved)==expected
            elif stage=='construct':
                created=module.DeepSeekProvider(approved,lambda:KEY)
                assert created.config==approved
            else:
                result=asyncio.run(instance.generate(value,expected_config=approved))
                assert result.state=='received' and result.error_code is None
    assert len(calls)==(1 if stage=='generate' else 0)
