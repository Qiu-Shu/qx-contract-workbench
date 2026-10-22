"""Synthetic protocol behavior; no database, account, files or live model."""
import importlib
import importlib.util
import json
from decimal import Decimal
from uuid import UUID

import pytest

from cn_contract import domain as d
from tests.unit.test_assistant_profiles import source, digest
from tests.integration.test_assistant_main_provider import config, envelope, raw, KEY


def api():
    name='cn_contract.assistant.providers.profile_codec'
    assert importlib.util.find_spec(name) is not None, 'profile codec missing'
    return importlib.import_module(name)


def fixture(text='甲称借款35000元。'):
    snapshot=source(text)
    request=d.MainProfileRequest(run_id=UUID(int=4),scope=snapshot.scope,
        message_id=snapshot.messages[0].id,content=text,source_sha256=digest(text),
        source_revision=snapshot.messages[0].source_revision,base_profile_revision=0)
    return snapshot,request


def candidate():
    return {'text':'请核对借款及付款材料。','citations':[], 'profile_changes':[
        {'field':'principal_amount','value':{'kind':'money','value':'35000','unit':'CNY'},
         'origin':'user_statement','quotes':[{'start':0,'end':10,'quote':'甲称借款35000元'}]}]}


def response(request,value=None):
    body=envelope(request)
    body['choices'][0]['message']['content']=json.dumps(candidate() if value is None else value,ensure_ascii=False)
    return raw(body)


def test_same_response_builds_unverified_patch_with_server_owned_source_identity():
    codec=api()
    snapshot,request=fixture()
    result=codec.decode_response(response(request),request,config(),KEY)
    assert result.error_code is None and result.usage.total_tokens==42
    assert result.output.text=='请核对借款及付款材料。'
    patch=result.output.profile_patch
    assert patch.scope==snapshot.scope and patch.base_profile_revision==0
    item=patch.changes[0]
    assert item.verification=='unverified' and item.value.value==Decimal('35000')
    ref=item.source_refs[0]
    assert (ref.conversation_id,ref.message_id,ref.source_revision)==(UUID(int=2),UUID(int=3),1)
    assert (ref.start,ref.end,ref.quote)==(0,10,'甲称借款35000元')
    assert ref.quote_sha256=='d8b391254fb1d76c5b490cf2140c29065bf83dfeeff93a07503c65e97090dcd0'


def test_no_changes_and_unknown_are_explicit_without_inventing_data():
    snapshot,request=fixture()
    body=candidate() | {'profile_changes':[]}
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.output.profile_patch.changes==()
    body['profile_changes']=[{'field':'contact','value':{'kind':'null','value':None},
                             'origin':'model_inference','quotes':[]}]
    reply=api().decode_response(response(request,body),request,config(),KEY)
    from cn_contract.assistant.profiles import merge_profile
    merged=merge_profile(None,reply.output.profile_patch,snapshot)
    assert merged.profile.fields[0].verification=='unknown' and merged.projection is None


def test_needed_material_is_only_a_request_not_an_attached_document():
    snapshot,request=fixture('还需借款凭证。')
    body=candidate() | {'profile_changes':[{'field':'materials',
        'value':{'kind':'materials','value':[{'name':'借款凭证','state':'needed'}]},
        'origin':'user_statement','quotes':[{'start':0,'end':7,'quote':'还需借款凭证。'}]}]}
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.error_code is None
    from cn_contract.assistant.profiles import merge_profile
    merged=merge_profile(None,reply.output.profile_patch,snapshot,project_intake=True)
    assert merged.projection.materials[0].state=='needed'


@pytest.mark.parametrize('value', [35000,35000.0,True,'-1','NaN','Infinity','0.000000001','1e16'])
def test_inexact_or_unbounded_amounts_are_rejected_but_usage_is_retained(value):
    _,request=fixture()
    body=candidate(); body['profile_changes'][0]['value']['value']=value
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.error_code=='MODEL_OUTPUT_INVALID' and reply.output is None
    assert reply.usage.total_tokens==42 and reply.provider_request_id=='synthetic-response-1'


@pytest.mark.parametrize('value',[1,True,'1','20261024','1792803600.5','2026-10-24','2026-10-24T09:00:00'])
def test_follow_up_time_cannot_be_guessed_from_epoch_or_missing_timezone(value):
    _,request=fixture(); body=candidate()
    body['profile_changes'][0].update(field='follow_up_at',value={'kind':'datetime','value':value})
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens==42


def test_explicit_follow_up_time_preserves_instant_without_claiming_legal_deadline():
    _,request=fixture('请于2026-10-24T09:00:00+08:00跟进。'); body=candidate()
    body['profile_changes']=[{'field':'follow_up_at','value':{'kind':'datetime','value':'2026-10-24T09:00:00+08:00'},
        'origin':'user_statement','quotes':[{'start':0,'end':30,'quote':'请于2026-10-24T09:00:00+08:00跟进。'}]}]
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.error_code is None
    item=reply.output.profile_patch.changes[0]
    assert item.value.value.isoformat()=='2026-10-24T01:00:00+00:00'
    assert item.verification=='unverified'


@pytest.mark.parametrize('changes', [
    {'verification':'confirmed'}, {'verification':'unverified'}, {'scope':{}}, {'source_refs':[]},
    {'reviewer':'lawyer'}, {'origin':'document_statement'}, {'field':'status'},
    {'field':'contact','value':{'kind':'text','value':'合成联系人'}},
    {'field':'questions','value':{'kind':'text','value':'合成问题'}},
    {'quotes':[]}, {'value':{'kind':'text','value':'35000'}},
    {'field':'materials','value':{'kind':'materials','value':[{'name':'凭证','state':'received'}]}},
    {'field':'materials','value':{'kind':'materials','value':[{'name':'凭证','state':'checked'}]}},
])
def test_model_cannot_supply_authority_or_source_identity(changes):
    _,request=fixture(); body=candidate(); body['profile_changes'][0].update(changes)
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens==42


@pytest.mark.parametrize('changes', [
    {'start':True},{'start':'0'},{'start':-1},{'start':1,'end':11},
    {'end':999},{'quote':'甲称借款99999元'}, {'quote':''},
    {'message_id':str(UUID(int=99))},{'quote_sha256':'0'*64},{'source_revision':1},
])
def test_quote_is_exact_at_its_position_without_search_or_cross_source_fallback(changes):
    _,request=fixture(); body=candidate(); body['profile_changes'][0]['quotes'][0].update(changes)
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.error_code=='MODEL_OUTPUT_INVALID' and reply.output is None


def test_unicode_quotes_and_conflicting_proposals_remain_distinct_and_unverified():
    snapshot,request=fixture('😀甲称1元\r\n乙称2元')
    body=candidate(); body['profile_changes']=[
        {'field':'principal_amount','value':{'kind':'money','value':'1','unit':'CNY'},
         'origin':'user_statement','quotes':[{'start':1,'end':5,'quote':'甲称1元'}]},
        {'field':'principal_amount','value':{'kind':'money','value':'2','unit':'CNY'},
         'origin':'user_statement','quotes':[{'start':7,'end':11,'quote':'乙称2元'}]}]
    reply=api().decode_response(response(request,body),request,config(),KEY)
    from cn_contract.assistant.profiles import merge_profile
    merged=merge_profile(None,reply.output.profile_patch,snapshot)
    field=merged.profile.fields[0]
    assert field.verification=='conflicted' and len(field.candidates)==2
    assert [x.source_refs[0].start for x in field.candidates]==[1,7]


@pytest.mark.parametrize('mode',['missing_changes','missing_citations','old_citation','extra',
                                 'too_many_changes','too_many_quotes','empty_text'])
def test_wire_shape_and_bounds_do_not_accept_old_output_implicitly(mode):
    _,request=fixture(); body=candidate()
    if mode=='missing_changes': del body['profile_changes']
    if mode=='missing_citations': del body['citations']
    if mode=='old_citation': body['citations']=[{'message_id':str(request.message_id), 'quote_sha256':request.source_sha256}]
    if mode=='extra': body['profile_patch']={}
    if mode=='too_many_changes': body['profile_changes']*=61
    if mode=='too_many_quotes': body['profile_changes'][0]['quotes']*=41
    if mode=='empty_text': body['text']=' '
    reply=api().decode_response(response(request,body),request,config(),KEY)
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'


@pytest.mark.parametrize('text',[
    '{"text":"合成回答","text":"替换","citations":[],"profile_changes":[]}',
    '```json\n{"text":"合成回答","citations":[],"profile_changes":[]}\n```',
    '{"text":"合成回答","citations":[],"profile_changes":[],"other":NaN}',
])
def test_no_json_scraping_or_duplicate_key_acceptance(text):
    _,request=fixture(); body=envelope(request); body['choices'][0]['message']['content']=text
    reply=api().decode_response(raw(body),request,config(),KEY)
    assert reply.error_code=='MODEL_OUTPUT_INVALID' and reply.usage.total_tokens==42


@pytest.mark.parametrize('changes',[
    {'source_sha256':'0'*64},{'source_revision':0},{'source_revision':2},
    {'base_profile_revision':True},{'input_format':'plain-text-v1'},
    {'template_version':'other-template'},
])
def test_bypassed_request_construction_is_revalidated(changes):
    _,request=fixture()
    with pytest.raises(ValueError): api().build_request(request.model_copy(update=changes),config())


def test_nested_scope_revalidation_and_exact_request_type_prevent_implicit_upgrade():
    _,request=fixture()
    with pytest.raises(ValueError): api().build_request(request.model_copy(
        update={'scope':request.scope.model_copy(update={'input_revision':True})}),config())
    from cn_contract.assistant.providers.main import build_request
    with pytest.raises(ValueError): build_request(request,config())
    plain=d.MainRequest.model_validate({k:getattr(request,k) for k in d.MainRequest.model_fields})
    with pytest.raises(ValueError): api().build_request(plain,config())


def test_wire_omits_local_ids_and_bounds_complete_utf8_including_system():
    _,request=fixture(); body=api().build_request(request,config())
    assert set(body)=={'model','messages','max_tokens','stream','thinking','response_format'}
    assert json.loads(body['messages'][1]['content'])=={'content':'甲称借款35000元。'}
    from cn_contract.config import canonical_json
    wire=canonical_json(body).encode('utf-8')
    assert str(request.message_id).encode() not in wire and request.source_sha256.encode() not in wire
    assert len(wire)>len(request.content.encode('utf-8'))
    assert api().build_request(request,config(max_input_bytes=len(wire)))==body
    with pytest.raises(ValueError): api().build_request(request,config(max_input_bytes=len(wire)-1))
