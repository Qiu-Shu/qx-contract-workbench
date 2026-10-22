"""New protocol through actual loopback HTTP, never a real model or database."""
import asyncio
import json

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.main import DeepSeekProvider
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.unit.test_assistant_profile_codec import fixture, response


def test_one_authorized_post_returns_answer_and_unverified_archive_proposal():
    _,request=fixture()
    with server(response(request)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
        assert hasattr(provider,'generate_profile'), 'profile entry missing'
        result=asyncio.run(provider.generate_profile(request,expected_config=config(),preflight=lambda:True))
        assert type(result) is d.MainProfileReply and result.error_code is None
        assert result.output.text=='请核对借款及付款材料。'
        assert result.output.profile_patch.changes[0].verification=='unverified'
        assert len(received)==1
        wire=json.loads(received[0]['body'])
        assert json.loads(wire['messages'][1]['content'])=={'content':'甲称借款35000元。'}


@pytest.mark.parametrize('preflight',[None,lambda:False,lambda:1,lambda:[]])
def test_default_or_non_boolean_permission_cannot_read_key_or_send(preflight):
    _,request=fixture(); resolved=[]
    with server(response(request)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:resolved.append(True) or KEY,url)
        result=asyncio.run(provider.generate_profile(request,preflight=preflight))
        assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE'
        assert received==[] and resolved==[]


def test_revocation_during_key_resolution_blocks_before_post():
    _,request=fixture(); allowed=[True]
    def secret():
        allowed[0]=False
        return KEY
    with server(response(request)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),secret,url)
        result=asyncio.run(provider.generate_profile(request,preflight=lambda:allowed[0]))
        assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE'
        assert received==[] and result.usage is None


@pytest.mark.parametrize('last_check',['false','raises','async'])
def test_revocation_before_adoption_discards_output_without_erasing_actual_usage(last_check):
    _,request=fixture(); checks=[]
    async def erroneous_async(): return True
    def preflight():
        checks.append(True)
        if len(checks)<3: return True
        if last_check=='raises': raise RuntimeError('synthetic revocation')
        if last_check=='async': return erroneous_async()
        return False
    with server(response(request)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
        result=asyncio.run(provider.generate_profile(request,preflight=preflight))
        assert result.output is None and result.error_code=='BLOCKED_LIVE' and result.state=='received'
        assert result.usage.total_tokens==42 and result.provider_request_id=='synthetic-response-1'
        assert len(received)==1 and len(checks)==3


def test_invalid_output_keeps_usage_and_does_not_trigger_a_repair_call():
    from tests.unit.test_assistant_profile_codec import candidate
    _,request=fixture(); value=candidate();value['profile_changes'][0]['verification']='confirmed'
    with server(response(request,value)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
        result=asyncio.run(provider.generate_profile(request,preflight=lambda:True))
        assert result.error_code=='MODEL_OUTPUT_INVALID' and result.output is None
        assert result.usage.total_tokens==42 and len(received)==1


@pytest.mark.parametrize('mode',['timeout','truncated','oversize'])
def test_unknown_network_result_is_not_resent_or_reported_as_free(mode):
    _,request=fixture(); data=response(request)
    options={'pause':2} if mode=='timeout' else {'declared_length':len(data)+100} if mode=='truncated' else {}
    configured=config(timeout_seconds=1) if mode=='timeout' else config(max_response_bytes=256) if mode=='oversize' else config()
    with server(data,**options) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(configured,lambda:KEY,url)
        result=asyncio.run(provider.generate_profile(request,preflight=lambda:True))
        assert result.state=='sent_unknown' and result.output is None and result.usage is None
        assert len(received)==1


def test_cancellation_propagates_without_retry():
    _,request=fixture()
    with server(response(request),pause=2) as (url,received,seen):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
        async def run():
            task=asyncio.create_task(provider.generate_profile(request,preflight=lambda:True))
            for _ in range(100):
                if seen.is_set(): break
                await asyncio.sleep(.01)
            assert seen.is_set()
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
        asyncio.run(run())
        assert len(received)==1


def test_configuration_change_and_tampered_request_are_blocked_before_key_access():
    _,request=fixture(); keys=[]
    with server(response(request)) as (url,received,_):
        provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:keys.append(True) or KEY,url)
        result=asyncio.run(provider.generate_profile(request,
            expected_config=config(max_output_tokens=1000),preflight=lambda:True))
        assert result.state=='failed_before_send' and result.error_code=='BLOCKED_LIVE'
        result=asyncio.run(provider.generate_profile(request.model_copy(update={'source_sha256':'0'*64}),
                                                   preflight=lambda:True))
        assert result.state=='failed_before_send' and result.error_code=='PROVIDER_ERROR'
        assert keys==[] and received==[]
