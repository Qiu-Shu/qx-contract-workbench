"""Independent local-loopback Jev transport spec probes."""
import asyncio
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Event, Thread
import time
from uuid import uuid4
import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import jev_codec as codec
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.assistant.routing import choose_workflow

SECRET='SYNTHETIC_SPEC_JEV_ONLY_KEY_8912'


def req():
    return d.JudgeRequest(local_request_id=uuid4(),purpose='primary_intent',text='独立合成：整理材料。',
        scope=d.ScopeSnapshot(workspace_id=uuid4(),conversation_id=uuid4(),binding_revision=1,input_revision=0,materials_revision=0))


def body(model='jev-1.13.0'):
    labels=['client_reply','material_organize','contract_review','content_draft','legal_research','unknown']
    return json.dumps({'model':model,'answers':{'primary_intent':{'type':'choice','choice':'material_organize',
        'probabilities':{k:int(k=='material_organize') for k in labels},'confidence':1}},
        'usage':{'input_tokens':3,'output_tokens':1}}).encode()


@contextmanager
def endpoint(content_type='application/json',status=200,delay=0,model='jev-1.13.0'):
    calls=[]; received=Event(); shutdown=Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            calls.append({'path':self.path,'body':json.loads(self.rfile.read(int(self.headers['Content-Length']))),
                'auth_ok':self.headers.get('Authorization')=='Bearer '+SECRET})
            received.set()
            if shutdown.wait(delay):return
            try:
                self.send_response(status)
                if content_type is not None:self.send_header('Content-Type',content_type)
                data=body(model); self.send_header('Content-Length',str(len(data)))
                self.send_header('x-typesafe-request-id','independent-receipt')
                self.send_header('Retry-After','0')
                self.end_headers();self.wfile.write(data)
            except OSError:pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    worker=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);worker.start()
    try:yield f'http://127.0.0.1:{server.server_port}/v1/systemone',calls,received
    finally:
        shutdown.set();server.shutdown();server.server_close();worker.join(2)


def provider(url,config=None,**kwargs):
    return JevProvider.for_synthetic_loopback(config or d.JevConfig(enabled=True),lambda:SECRET,url,
        preflight=kwargs.get('preflight',lambda *_:None))


@pytest.mark.parametrize('content_type',['text/plain','text/html',None])
def test_non_json_content_type_never_supplies_adoptable_answer(content_type):
    with endpoint(content_type) as (url,calls,_):
        result=asyncio.run(provider(url).judge(req()))
    assert result.status=='invalid' and result.evidence=='received' and not result.answers
    assert len(calls)==1
    assert choose_workflow(None,result,{'material_organize'}).workflow is None


def test_good_wire_has_no_scope_and_gives_only_allowed_advice():
    value=req()
    with endpoint('application/json; charset=utf-8') as (url,calls,_):
        result=asyncio.run(provider(url).judge(value))
    assert result.status=='ok' and len(calls)==1
    wire=json.dumps(calls[0]['body'],ensure_ascii=False)
    assert value.text in wire and str(value.scope.workspace_id) not in wire and str(value.local_request_id) not in wire
    assert calls[0]['auth_ok'] and calls[0]['path']=='/v1/systemone'
    assert choose_workflow(None,result,{'material_organize'}).workflow=='material_organize'
    assert choose_workflow(None,result,{'client_reply'}).workflow is None


def test_even_well_formed_429_envelope_never_adopts_or_retries():
    with endpoint(status=429) as (url,calls,_):result=asyncio.run(provider(url).judge(req()))
    assert result.status=='failed' and result.evidence=='received' and not result.answers
    assert result.usage.input_tokens==3 and result.provider_request_id=='independent-receipt'
    assert len(calls)==1


def test_synchronous_decode_time_is_inside_deadline_and_usage_is_accounting_only(monkeypatch):
    import httpx2
    original=codec.decode_response
    def slow(*args,**kwargs):
        time.sleep(.25)
        return original(*args,**kwargs)
    monkeypatch.setattr(codec,'decode_response',slow)
    with endpoint() as (url,calls,_):
        result=asyncio.run(provider(url,d.JevConfig(enabled=True,timeout_ms=200)).judge(req()))
    assert result.status=='timed_out' and result.evidence=='received' and not result.answers
    assert result.usage.input_tokens==3 and result.elapsed_ms>=250
    assert choose_workflow(None,result,{'material_organize'}).workflow is None
    assert len(calls)==1


def test_cancelled_request_propagates_cancellation_and_does_not_retry():
    async def run(url,received):
        task=asyncio.create_task(provider(url).judge(req()))
        deadline=asyncio.get_running_loop().time()+2
        while not received.is_set():
            assert asyncio.get_running_loop().time()<deadline
            await asyncio.sleep(.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        await asyncio.sleep(.03)
    with endpoint(delay=.8) as (url,calls,received):asyncio.run(run(url,received))
    assert len(calls)==1


def test_no_egress_cannot_claim_reported_model_or_read_secret():
    touched=[]
    def forbidden_secret():
        touched.append(True)
        raise AssertionError('No permission must not resolve synthetic key')
    value=JevProvider(d.JevConfig(enabled=True),forbidden_secret)
    result=asyncio.run(value.judge(req()))
    assert result.status=='skipped' and result.reason_code=='no_egress'
    assert result.evidence=='not_sent' and result.model is None
    assert result.usage is None and result.provider_request_id is None and touched==[]


def test_wrong_reported_model_is_not_replaced_with_requested_model():
    with endpoint(model='jev-preview') as (url,calls,_):
        result=asyncio.run(provider(url).judge(req()))
    assert result.status=='invalid' and result.evidence=='received'
    assert result.model is None and not result.answers and len(calls)==1
    assert result.usage.input_tokens==3
