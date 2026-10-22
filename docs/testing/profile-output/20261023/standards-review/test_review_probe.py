"""Independent synthetic review probes; no application database or real provider."""
import json
import hashlib
import subprocess
import sys
from uuid import UUID

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.profile_codec import decode_response


TEXT = '合成预约：2026-10-24T09:00:00+08:00；😀资料待补。'
CONFIG = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='1',
    output_usd_per_million='1', price_reference='synthetic review only')
REQUEST = d.MainProfileRequest(run_id=UUID(int=104), message_id=UUID(int=103),
    content=TEXT, source_sha256=hashlib.sha256(TEXT.encode()).hexdigest(),
    scope=d.ScopeSnapshot(workspace_id=UUID(int=101), conversation_id=UUID(int=102),
        binding_revision=1, input_revision=3, materials_revision=0),
    source_revision=3, base_profile_revision=2)


def decode(change):
    candidate = {'text':'合成待核回答', 'citations':[], 'profile_changes':[change]}
    envelope = {'id':'synthetic-standards-review', 'object':'chat.completion', 'created':1,
        'model':'deepseek-flash', 'usage':{'prompt_tokens':25,'completion_tokens':13,'total_tokens':38},
        'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant',
            'content':json.dumps(candidate, ensure_ascii=False)}}]}
    return decode_response(json.dumps(envelope, ensure_ascii=False).encode(), REQUEST, CONFIG, '')


def proposal(field, value):
    return {'field':field, 'value':value, 'origin':'user_statement',
        'quotes':[{'start':0,'end':len(TEXT),'quote':TEXT}]}


@pytest.mark.parametrize('value', ['20261024','1792803600','1792803600.5'])
def test_wire_datetime_must_not_guess_epoch_from_numeric_string(value):
    reply=decode(proposal('follow_up_at', {'kind':'datetime','value':value}))
    actual = None if reply.output is None else reply.output.profile_patch.changes[0].value.value
    assert reply.output is None, f'bare numeric timestamp accepted as {actual!r}'
    assert reply.error_code=='MODEL_OUTPUT_INVALID' and reply.usage.total_tokens==38


def test_explicit_datetime_normalizes_timezone_and_keeps_unverified_source():
    reply=decode(proposal('follow_up_at', {'kind':'datetime','value':'2026-10-24T09:00:00+08:00'}))
    item=reply.output.profile_patch.changes[0]
    assert item.value.value.isoformat()=='2026-10-24T01:00:00+00:00'
    assert item.verification=='unverified' and item.source_refs[0].source_revision==3
    assert item.source_refs[0].conversation_id==UUID(int=102)


@pytest.mark.parametrize('value', ['unsafe\u0000text','x'*12001])
def test_model_text_respects_export_alphabet_and_field_cap(value):
    reply=decode(proposal('consultation', {'kind':'text','value':value}))
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens==38


def test_utf16_surrogate_unit_offsets_cannot_be_used_as_codepoint_offsets():
    item=proposal('consultation', {'kind':'text','value':'资料待补'})
    start=TEXT.index('资料')
    item['quotes']=[{'start':start+1,'end':start+5,'quote':'资料待补'}]
    reply=decode(item)
    assert reply.output is None and reply.error_code=='MODEL_OUTPUT_INVALID'
    assert reply.usage.total_tokens==38


def test_plain_provider_import_does_not_load_profile_codec_or_http_client():
    completed=subprocess.run([sys.executable,'-X','utf8','-c',
        "import sys; from cn_contract.assistant.providers.main import DeepSeekProvider; "
        "assert 'cn_contract.assistant.providers.profile_codec' not in sys.modules; "
        "assert 'httpx2' not in sys.modules"],capture_output=True,text=True,check=False)
    assert completed.returncode==0,completed.stderr
