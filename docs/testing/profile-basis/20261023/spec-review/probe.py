"""Independent CH-07C2a offline public-interface checks, synthetic data only."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_codec, profile_preparation as api
from cn_contract.assistant.providers.deepseek_protocol import json_bytes
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.providers.attempts import _input
from cn_contract.assistant.providers.main import build_request as old_plain_builder
from cn_contract.security import ServiceError

BASE='37773d92f08e0b3bc2fed27064ceb011e8a72cd6'
TEXT='合成原话：甲🙂称借款5元。\r\n尚待核实。'
CONFIG=d.MainModelConfig(enabled=True,model='deepseek-flash',input_usd_per_million='1.25',
    output_usd_per_million='2.5',price_reference='independent synthetic review')
BEFORE=d.ScopeSnapshot(workspace_id=UUID(int=101),conversation_id=UUID(int=102),
    binding_revision=2,input_revision=7,materials_revision=0)
SUBMIT=d.AssistantMessageInput(request_id=UUID(int=103),expected_scope=BEFORE,
    expected_composer_revision=9,content=TEXT)
SCOPE=BEFORE.model_copy(update={'input_revision':8})
MESSAGE=d.AssistantMessageView(id=UUID(int=104),role='user',content=TEXT,source_revision=8,
    created_at='2026-10-23T01:00:00Z')
RUN=d.AssistantRunView(id=UUID(int=105),message_id=MESSAGE.id,request_id=SUBMIT.request_id,
    request_sha256='0'*64,scope=SCOPE,state='queued',requested_skill=None,selected_provider=None,
    selected_model=None,cancel_requested=False,created_at=MESSAGE.created_at,events=())
CHECKS=[]


def check(name,fn):
    fn();CHECKS.append({'name':name,'passed':True})


def refused(fn):
    try:fn()
    except (ValueError,ServiceError):return
    raise AssertionError('expected boundary rejection')


def basis(**plan):
    return api.build_basis(SUBMIT,CONFIG,base_profile_revision=4,**plan)


def prepare(value=None,config=CONFIG,run=RUN,message=MESSAGE,composer=10):
    return api.prepare(run,message,value or basis(),config,composer_revision=composer)


def complete_binding():
    b=basis(expected_intake_id=UUID(int=106),expected_intake_revision=3,project_intake=True)
    prepared=prepare(b)
    assert b.purpose=='reply_and_profile_draft' and b.handler_id=='profile.save' and b.handler_version=='1'
    assert prepared.request.scope==SCOPE and prepared.request.source_revision==8
    assert prepared.request.message_id==MESSAGE.id and prepared.request.run_id==RUN.id
    assert prepared.request.base_profile_revision==4 and prepared.composer_revision==10
    wire=prepared.wire_payload_json.encode('utf-8')
    assert b.wire_bytes==len(wire) and b.wire_sha256==sha256(wire).hexdigest()
    assert b.content_sha256==sha256(TEXT.encode()).hexdigest()
    assert b.config_sha256==sha256(json_bytes(CONFIG.model_dump(mode='json'))).hexdigest()
    assert json.loads(json.loads(wire)['messages'][1]['content'])=={'content':TEXT}
    assert str(b.expected_intake_id) not in prepared.wire_payload_json
    assert 'project_intake' not in prepared.wire_payload_json


def exact_prior_c1_bytes():
    source=subprocess.run(['git','show',BASE+':src/cn_contract/assistant/providers/profile_codec.py'],
        check=True,capture_output=True).stdout.decode('utf-8')
    prior=ModuleType('cn_contract.assistant.providers._spec_baseline')
    prior.__package__='cn_contract.assistant.providers'
    exec(compile(source,'<fixed-C1-baseline>','exec'),prior.__dict__)
    p=prepare()
    assert p.wire_payload_json.encode()==json_bytes(prior.build_request(p.request,CONFIG))
    assert profile_codec._SYSTEM==prior._SYSTEM


def whole_basis_plan_digest():
    original=basis();digests={api.basis_digest(original)}
    variants=[{'project_intake':True},{'base_profile_revision':5},
        {'expected_intake_id':UUID(int=106),'expected_intake_revision':3},
        {'expected_intake_id':UUID(int=106),'expected_intake_revision':4},
        {'expected_intake_id':UUID(int=107),'expected_intake_revision':3}]
    for delta in variants:
        revised=d.MainProfileSendBasis.model_validate(original.model_dump(mode='python')|delta)
        assert revised.wire_sha256==original.wire_sha256
        digests.add(api.basis_digest(revised))
    assert len(digests)==6
    assert api.basis_digest(d.MainProfileSendBasis.model_validate_json(original.model_dump_json())) in digests


def run_and_message_identity():
    for delta in ({'request_id':UUID(int=999)},{'message_id':UUID(int=999)},
                  {'requested_skill':'client_reply'}):
        refused(lambda delta=delta:prepare(run=RUN.model_copy(update=delta)))
    for delta in ({'role':'assistant'},{'source_revision':7},{'content':'不同合成原话'}):
        refused(lambda delta=delta:prepare(message=MESSAGE.model_copy(update=delta)))


def scope_composer_bridge():
    for field,value in (('workspace_id',UUID(int=999)),('conversation_id',UUID(int=999)),
                        ('binding_revision',3),('input_revision',7),('materials_revision',1)):
        run=RUN.model_copy(update={'scope':SCOPE.model_copy(update={field:value})})
        refused(lambda run=run:prepare(run=run))
    for composer in (9,11,True):refused(lambda composer=composer:prepare(composer=composer))


def constructed_invalid_basis():
    raw=basis().model_dump(mode='python')
    for field,value in (('purpose','reply_only'),('input_format','plain-text-v1'),
                        ('handler_id','legal_library.search'),('handler_version','2'),
                        ('template_version','other'),('project_intake',1),
                        ('base_profile_revision',True),('wire_bytes',True),
                        ('expected_intake_id',UUID(int=999)),('expected_intake_revision',1)):
        b=d.MainProfileSendBasis.model_construct(**(raw|{field:value}))
        refused(lambda b=b:prepare(b))
        refused(lambda b=b:api.basis_digest(b))
    bad=basis().model_copy(update={'expected_scope':BEFORE.model_copy(update={'input_revision':True})})
    refused(lambda:api.basis_digest(bad))


def plan_cannot_gain_manual_edits():
    refused(lambda:d.MainProfileSendBasis.model_validate(basis().model_dump(mode='python')|{'manual_edits':[]}))


def selected_input_boundary():
    for delta in ({'attachment_ids':(UUID(int=999),)},{'requested_skill':'content_draft'},
                  {'content':' '},{'content':123}):
        refused(lambda delta=delta:api.build_basis(SUBMIT.model_copy(update=delta),CONFIG,base_profile_revision=4))


def config_and_template_binding():
    b=basis()
    for delta in ({'max_output_tokens':1000},{'input_usd_per_million':Decimal('1.3')},
                  {'model':'deepseek-v4-pro'},{'timeout_seconds':40},{'max_input_bytes':65535}):
        refused(lambda delta=delta:prepare(b,config=CONFIG.model_copy(update=delta)))
    with patch.object(profile_codec,'_SYSTEM',profile_codec._SYSTEM+' synthetic changed'):
        refused(lambda:prepare(b))


def exact_utf8_limit():
    n=basis().wire_bytes
    exact=CONFIG.model_copy(update={'max_input_bytes':n})
    b=api.build_basis(SUBMIT,exact,base_profile_revision=4)
    assert prepare(b,config=exact).basis.wire_bytes==n
    refused(lambda:api.build_basis(SUBMIT,exact.model_copy(update={'max_input_bytes':n-1}),base_profile_revision=4))


def serialized_wire_tamper():
    p=prepare();raw=p.model_dump(mode='python');raw['wire_payload_json']+=' '
    refused(lambda:d.MainProfilePreparedInput.model_validate(raw))
    raw=p.model_dump(mode='python');raw['request']['source_revision']=7
    refused(lambda:d.MainProfilePreparedInput.model_validate(raw))


def old_runtime_permission_rejection():
    b=basis();registry=MainModelRegistry();calls=[]
    registry.configure(SimpleNamespace(config=CONFIG,generate=lambda *args:calls.append(args)))
    policy=d.MainModelPolicy(policy_id=UUID(int=111),workspace_id=BEFORE.workspace_id,actor_id=UUID(int=112),
        config_sha256=b.config_sha256,allowed_content_sha256s=(api.basis_digest(b),),
        max_total_usd='1',max_calls=1,expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
    try:registry.grant(policy,UUID(int=113),basis=b)
    except ServiceError as error:assert error.code=='BLOCKED_LIVE'
    else:raise AssertionError('old registry accepted new basis')
    refused(lambda:old_plain_builder(prepare().request,CONFIG))
    refused(lambda:_input({'input_format':'profile-text-v1','input_json':prepare().model_dump_json()}))
    assert calls==[]


with patch('socket.socket',side_effect=AssertionError('offline probe attempted network')):
    check('complete_local_plan_and_wire_identity',complete_binding)
    check('byte_for_byte_fixed_prior_C1_builder',exact_prior_c1_bytes)
    check('same_wire_distinct_save_plan_distinct_digest',whole_basis_plan_digest)
    check('run_message_request_identity_rejection',run_and_message_identity)
    check('scope_and_composer_bridge_rejection',scope_composer_bridge)
    check('constructed_and_nested_invalid_basis_rejected',constructed_invalid_basis)
    check('manual_edits_not_part_of_prepare_plan',plan_cannot_gain_manual_edits)
    check('attachment_skill_and_empty_input_rejected',selected_input_boundary)
    check('config_and_template_changes_invalidate_basis',config_and_template_binding)
    check('exact_utf8_limit_and_one_byte_over',exact_utf8_limit)
    check('serialized_wire_and_source_revision_tamper_rejected',serialized_wire_tamper)
    check('old_runtime_grants_format_and_plain_builder_refuse',old_runtime_permission_rejection)
report={'baseline':BASE,'checks':CHECKS,'passed':len(CHECKS),'failed':0,
    'scope':'pure offline synthetic values, socket creation blocked; no DB or running process access',
    'limits':'does not establish DB membership/current authority/current attachments or current profile versions'}
Path(__file__).with_name('report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
