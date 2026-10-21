"""Compare frozen V1 request AST and exact reply JSON without any network."""
import ast
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

BASE=Path(__file__).resolve().parent
ROOT=BASE.parent.parent
sys.path.insert(0,str(ROOT))
from cn_contract.assistant.providers import main, deepseek_protocol, deepseek_transport
from tests.integration.test_assistant_main_provider import config, request, envelope, raw, KEY

snapshot=BASE/'transport-main-baseline.py'
spec=importlib.util.spec_from_file_location('cn_contract.assistant.providers._legacy_snapshot',snapshot)
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
current=ROOT/'src/cn_contract/assistant/providers/main.py'
def node(path,name):
    return next(item for item in ast.parse(path.read_text('utf-8')).body if getattr(item,'name',None)==name)
assert ast.dump(node(snapshot,'build_request'))==ast.dump(node(current,'build_request'))
assert legacy._SYSTEM==main._SYSTEM
assert main._strict_json is deepseek_protocol.strict_json
assert main._protect_logs is deepseek_transport._protect_logs
value=request();cfg=config();wire=[]
for content in ('纯合成问题。','合成多行\n第二行\t原样','合成😀'*100,'合成'*10000):
    selected=value.model_copy(update={'content':content,'source_sha256':sha256(content.encode()).hexdigest()})
    old=legacy._json_bytes(legacy.build_request(selected,cfg))
    new=main._json_bytes(main.build_request(selected,cfg))
    assert old==new
    wire.append({'bytes':len(new),'sha256':sha256(new).hexdigest()})
responses=[('valid',raw(envelope(value))),('empty',b''),('not_json',b'invalid'),
    ('duplicate',b'{"id":1,"id":2}'),('nonfinite',b'{"id":NaN}'),('nonobject',b'[]'),
    ('depth',b'['*1100+b']'*1100)]
for name,change in [('id_empty',{'id':''}),('id_secret',{'id':KEY}),('wrong_model',{'model':'foreign'}),
    ('created_bool',{'created':True}),('object',{'object':'wrong'}),('missing_usage',{'usage':None}),
    ('usage_bool',{'usage':{'prompt_tokens':True,'completion_tokens':12,'total_tokens':13}}),
    ('usage_over_budget',{'usage':{'prompt_tokens':70000,'completion_tokens':12,'total_tokens':70012}}),
    ('choices_empty',{'choices':[]}),('unknown_metadata',{'unknown':{'safe':'preserved behavior'}})]:
    responses.append((name,raw(envelope(value,**change))))
for name,change in [('empty_content',{'content':''}),('bad_content',{'content':'{invalid'}),
    ('foreign_source',{'content':'{"text":"合成","citations":[{"message_id":"00000000-0000-0000-0000-000000000001","quote_sha256":"'+'0'*64+'"}]}'}),
    ('candidate_extra',{'content':'{"text":"合成","citations":[],"approved":true}'}),
    ('tool',{'tool_calls':[{'id':'synthetic'}]}),('reasoning',{'reasoning_content':'unrequested'}),
    ('escaped_secret',{'content':json.dumps({'text':KEY,'citations':[]}).replace(KEY,'\\u0053'+KEY[1:])})]:
    payload=envelope(value);payload['choices'][0]['message'].update(change)
    responses.append((name,raw(payload)))
payload=envelope(value);payload['choices'][0]['finish_reason']='length';responses.append(('finish',raw(payload)))
checks=[]
for name,data in responses:
    old=legacy._decode(data,value,cfg,KEY).model_dump_json()
    new=main._decode(data,value,cfg,KEY).model_dump_json()
    assert old==new,name
    assert KEY not in new
    checks.append({'name':name,'reply_sha256':sha256(new.encode()).hexdigest()})
result={'build_request_ast_unchanged':True,'system_text_unchanged':True,'compatibility_aliases':True,
    'wire_cases':wire,'reply_cases':checks,'baseline_sha256':sha256(snapshot.read_bytes()).hexdigest(),
    'main_sha256':sha256(current.read_bytes()).hexdigest(),'network_used':False}
(BASE/'transport-compat.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'wire_cases':len(wire),'reply_cases':len(checks),'all_exactly_equal':True}))
