"""Independent fixed projection and receipt/answer separation probes."""
import json
from uuid import uuid4
import pytest
from cn_contract import domain as d
from cn_contract.assistant.providers import jev_codec as codec


def request(purpose='primary_intent', text='独立合成文本：先回复再整理'):
    return d.JudgeRequest(local_request_id=uuid4(), purpose=purpose, text=text,
        scope=d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
            input_revision=0, materials_revision=0))


def envelope():
    labels = ['client_reply','material_organize','contract_review','content_draft','legal_research','unknown']
    return {'model':'jev-1.13.0', 'usage':{'input_tokens':0}, 'answers':{'primary_intent':{
        'type':'choice', 'choice':'client_reply', 'probabilities':{k:int(k=='client_reply') for k in labels}, 'confidence':1}}}


def raw(value): return json.dumps(value, ensure_ascii=True).encode()


def test_local_identifiers_and_revision_only_bind_hash_never_enter_wire():
    config=d.JevConfig(enabled=True); original=request()
    body=codec.build_request(original,config); base=codec.input_hash(original,config)
    wire=json.dumps(body,ensure_ascii=False)
    assert original.text in wire
    for value in (original.local_request_id, original.scope.workspace_id, original.scope.conversation_id):
        assert str(value) not in wire
    for changed in [original.model_copy(update={'local_request_id':uuid4()}),
                    original.model_copy(update={'scope':original.scope.model_copy(update={'materials_revision':1})}),
                    original.model_copy(update={'scope':original.scope.model_copy(update={'conversation_id':uuid4()})})]:
        assert codec.build_request(changed,config)==body
        assert codec.input_hash(changed,config)!=base
    assert codec.input_hash(original,config.model_copy(update={'timeout_ms':1200}))!=base


def test_invalid_answers_keep_only_separately_validated_receipt_information():
    value=envelope(); value['answers']['primary_intent']['probabilities']['client_reply']=0.5
    out=codec.decode_response(raw(value),request(),d.JevConfig(enabled=True),'receipt-spec')
    assert out['answers']=={} and out['reason_code']=='invalid_response'
    assert out['provider_request_id']=='receipt-spec'
    assert out['usage'].input_tokens==0 and out['usage'].output_tokens is None
    value['model']='jev-preview'
    out=codec.decode_response(raw(value),request(),d.JevConfig(enabled=True),'receipt-spec')
    assert not out['answers'] and out['usage'].input_tokens==0


def test_secret_escaped_inside_unexpected_json_property_clears_all_external_metadata():
    secret='SYNTHETIC_SPEC_PRIVATE_TOKEN_4567'
    value=envelope(); value['unexpected']={'comment':secret}
    out=codec.decode_response(raw(value),request(),d.JevConfig(enabled=True),'receipt-spec',secret)
    assert out=={'answers':{},'usage':None,'provider_request_id':None,'model':None,'reason_code':'provider_error'}
    assert secret not in str(out)


@pytest.mark.parametrize('value',[True,'0.5',float('nan'),float('inf')])
def test_noul_invalid_numbers_are_unusable_but_unknown_usage_stays_unknown(value):
    data={'model':'jev-1.13.0','usage':{},'answers':{'possible_result_guarantee':{'type':'noul','noul':value}}}
    out=codec.decode_response(raw(data),request('possible_result_guarantee'),d.JevConfig(enabled=True))
    assert not out['answers'] and out['reason_code']=='invalid_response'
    assert out['usage'] is None or out['usage'].model_dump()=={'input_tokens':None,'output_tokens':None}


def test_missing_usage_cannot_be_fabricated_and_noul_needs_no_confidence():
    data={'model':'jev-1.13.0','usage':{'output_tokens':None},'answers':{'possible_result_guarantee':{'type':'noul','noul':0}}}
    req=request('possible_result_guarantee'); config=d.JevConfig(enabled=True)
    good=codec.decode_response(raw(data),req,config)
    assert good['answers']['possible_result_guarantee'].noul==0
    assert good['usage'].input_tokens is None and good['usage'].output_tokens is None
    del data['usage']
    missing=codec.decode_response(raw(data),req,config)
    assert not missing['answers'] and missing['usage'] is None


def test_invalid_tracking_id_is_dropped_without_discarding_valid_answer():
    out=codec.decode_response(raw(envelope()),request(),d.JevConfig(enabled=True),'unsafe\x85id')
    assert out['answers'] and out['provider_request_id'] is None and out['reason_code'] is None
