"""Independent synthetic public-interface probe; no persisted workspace or live provider."""
import asyncio
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from uuid import UUID

from cn_contract import domain as d
from cn_contract.assistant.profiles import merge_profile
from cn_contract.assistant.providers import profile_codec
from cn_contract.assistant.providers.main import DeepSeekProvider, build_request as build_plain


KEY = 'synthetic_spec_review_key_20261023'
TEXT = '甲称借款1元。😀\r\n乙称借款2元。'
CONFIG = d.MainModelConfig(enabled=True, model='deepseek-flash',
    input_usd_per_million='1', output_usd_per_million='2', price_reference='synthetic only')
SCOPE = d.ScopeSnapshot(workspace_id=UUID(int=101), conversation_id=UUID(int=102),
    binding_revision=1, input_revision=5, materials_revision=0)
REQUEST = d.MainProfileRequest(run_id=UUID(int=103), message_id=UUID(int=104),
    scope=SCOPE, source_revision=5, base_profile_revision=0,
    content=TEXT, source_sha256=sha256(TEXT.encode()).hexdigest())
CHECKS = []


def change(amount, start, end):
    return {'field':'principal_amount', 'value':{'kind':'money','value':amount,'unit':'CNY'},
        'origin':'user_statement', 'quotes':[{'start':start,'end':end,'quote':TEXT[start:end]}]}


def output():
    return {'text':'两项主张仍需核实。','citations':[],
        'profile_changes':[change('1',0,7),change('2',10,17)]}


def envelope(value):
    content = value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
    return json.dumps({'id':'review-response','object':'chat.completion','created':1,
        'model':'deepseek-flash','choices':[{'index':0,'finish_reason':'stop','logprobs':None,
        'message':{'role':'assistant','content':content}}],
        'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}},
        ensure_ascii=False).encode()


def decode(value):
    return profile_codec.decode_response(envelope(value),REQUEST,CONFIG,KEY)


def require_invalid(value):
    reply=decode(value)
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens==30 and reply.provider_request_id=='review-response'


def run_check(name, fn):
    fn()
    CHECKS.append({'name':name,'passed':True})


def exact_sources_and_conflicts():
    result=decode(output())
    assert result.error_code is None
    refs=[item.source_refs[0] for item in result.output.profile_patch.changes]
    assert [(r.start,r.end,r.quote) for r in refs]==[(0,7,TEXT[:7]),(10,17,TEXT[10:17])]
    assert all(r.message_id==REQUEST.message_id and r.conversation_id==SCOPE.conversation_id
        and r.source_revision==5 and r.quote_sha256==sha256(r.quote.encode()).hexdigest() for r in refs)
    source=d.ProfileSourceSnapshot(scope=SCOPE,messages=(d.AssistantMessageView(
        id=REQUEST.message_id,role='user',content=TEXT,source_revision=5,created_at='2026-10-23T00:00:00Z'),))
    merged=merge_profile(None,result.output.profile_patch,source)
    assert merged.profile.fields[0].verification=='conflicted'
    assert all(x.verification=='unverified' for x in merged.profile.fields[0].candidates)
    assert merged.projection is None


def bad_second_change_discards_all():
    value=output();value['profile_changes'][1]['quotes'][0]['start']=9
    require_invalid(value)


def all_invalid_material_states():
    for state in ('received','checked'):
        value=output();value['profile_changes'][0].update(field='materials',
            value={'kind':'materials','value':[{'name':'合成凭证','state':state}]})
        require_invalid(value)


def forbidden_wire_authority():
    for extra in ({'verification':'confirmed'},{'verification':'unverified'},
                  {'source_refs':[]},{'scope':SCOPE.model_dump(mode='json')}):
        value=output();value['profile_changes'][0].update(extra);require_invalid(value)
    value=output();value['profile_changes'][0].update(field='contact',
        value={'kind':'text','value':'合成联系人'})
    require_invalid(value)


def request_boundary():
    for delta in ({'source_revision':4},{'source_sha256':'0'*64}):
        try: profile_codec.build_request(REQUEST.model_copy(update=delta),CONFIG)
        except ValueError: pass
        else: raise AssertionError('invalid trusted request accepted')
    try: build_plain(REQUEST,CONFIG)
    except ValueError: pass
    else: raise AssertionError('new request silently used old protocol')
    wire=profile_codec.build_request(REQUEST,CONFIG)
    assert json.loads(wire['messages'][1]['content'])=={'content':TEXT}
    assert str(REQUEST.message_id) not in json.dumps(wire)


def no_citation_or_duplicate_key():
    value=output();value['citations']=[{'message_id':str(REQUEST.message_id),'quote_sha256':REQUEST.source_sha256}]
    require_invalid(value)
    require_invalid('{"text":"a","text":"b","citations":[],"profile_changes":[]}')


@contextmanager
def loopback():
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            calls.append(self.rfile.read(int(self.headers['Content-Length'])))
            body=envelope(output())
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}/chat/completions',calls
    finally: server.shutdown();server.server_close();thread.join(2)


def transport_checks():
    with loopback() as (url,calls):
        keys=[];preflights=[]
        provider=DeepSeekProvider.for_synthetic_loopback(CONFIG,lambda:keys.append(1) or KEY,url)
        denied=asyncio.run(provider.generate_profile(REQUEST))
        assert denied.state=='failed_before_send' and denied.error_code=='BLOCKED_LIVE'
        assert not calls and not keys
        CHECKS.append({'name':'default_denied_before_key_or_network','passed':True})
        def preflight():
            preflights.append(1)
            return len(preflights)<3
        revoked=asyncio.run(provider.generate_profile(REQUEST,preflight=preflight))
        assert revoked.state=='received' and revoked.output is None and revoked.error_code=='BLOCKED_LIVE'
        assert revoked.usage.total_tokens==30 and revoked.provider_request_id=='review-response'
        assert len(calls)==1 and len(keys)==1 and len(preflights)==3
        CHECKS.append({'name':'received_revocation_retains_usage','passed':True})
        valid=asyncio.run(provider.generate_profile(REQUEST,preflight=lambda:True))
        assert valid.error_code is None and valid.output is not None and len(calls)==2
        assert len(valid.output.profile_patch.changes)==2
        CHECKS.append({'name':'one_post_returns_answer_and_proposals','passed':True})


run_check('unicode_exact_source_conflicts_stay_unverified',exact_sources_and_conflicts)
run_check('invalid_second_proposal_discards_entire_candidate',bad_second_change_discards_all)
run_check('received_and_checked_are_refused',all_invalid_material_states)
run_check('model_authority_and_contact_refused',forbidden_wire_authority)
run_check('request_versions_hash_and_old_protocol_boundary',request_boundary)
run_check('nonempty_citations_and_duplicate_json_refused',no_citation_or_duplicate_key)
transport_checks()
integer=output();integer['profile_changes'][0]['value']['value']=1
integer_reply=decode(integer)
timestamp=output();timestamp['profile_changes'][0].update(field='follow_up_at',
    value={'kind':'datetime','value':'1'})
timestamp_reply=decode(timestamp)
report={'checks':CHECKS,'passed':len(CHECKS),'failed':0,
    'observation_integer_money_wire_accepted':integer_reply.output is not None,
    'observation_numeric_datetime_wire_accepted':timestamp_reply.output is not None,
    'numeric_datetime_normalized':str(timestamp_reply.output.profile_patch.changes[0].value.value)
        if timestamp_reply.output else None,
    'scope':'independent synthetic text and loopback only; no DB, real provider or desktop process'}
Path(__file__).with_name('report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
