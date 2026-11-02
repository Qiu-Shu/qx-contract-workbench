"""Synthetic desktop configuration and single-request output-limit regressions."""
import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import main, deepseek_protocol
from cn_contract.assistant.providers.policy import receipt
from tests.integration.test_assistant_main_provider import config, request, envelope, raw, server, KEY


def desktop_config(model='deepseek-flash'):
    root = Path(__file__).resolve().parents[2]
    script = """
const {createModelSession}=require('./desktop/model-session.cjs');
const backend={closing:false,disableModel:async()=>({ok:true,status:'disabled'}),stop:async()=>{},
 configureModel:async value=>{process.stdout.write(JSON.stringify(value.config));
 return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'11111111-2222-4333-8444-555555555555'};}};
const session=createModelSession({store:{withSecret:async fn=>{await fn('SYNTHETIC_OUTPUT_CAPACITY_KEY');return {status:'saved'};}},getBackend:()=>backend});
session.configure(process.argv[1]).then(result=>{if(!result.ok)process.exitCode=1;});
"""
    result = subprocess.run(['C:/Program Files/nodejs/node.exe', '-e', script, model],
                            cwd=root, capture_output=True, check=True)
    return json.loads(result.stdout)


@pytest.mark.parametrize('model', ['deepseek-flash', 'deepseek-v4-pro'])
def test_desktop_requests_provider_maximum_not_local_4096_or_8192(model):
    value = desktop_config(model)
    assert value['max_output_tokens'] == 393216
    assert value['max_response_bytes'] == 8388608
    assert value['timeout_seconds'] == 600
    configured = d.MainModelConfig.model_validate(value)
    assert main.build_request(request(), configured)['max_tokens'] == 393216


@pytest.mark.parametrize('reply_type', [d.MainReply, d.MainMaterialReply, d.MainContextReply])
def test_length_rejection_is_saved_with_usage_without_parsing_partial_content(reply_type):
    body = envelope(request())
    body['choices'][0]['finish_reason'] = 'length'
    body['choices'][0]['message']['content'] = '{"text":"unfinished synthetic draft'
    def no_candidate(_):
        pytest.fail('truncated text must never become a draft')
    reply = deepseek_protocol.decode_response(raw(body), config(), KEY,
        parse_candidate=no_candidate, reply_type=reply_type)
    assert reply.error_code == 'MODEL_OUTPUT_TRUNCATED' and reply.output is None
    saved = receipt(reply, config())
    assert d.MainReceipt.model_validate_json(saved.model_dump_json()) == saved
    assert saved.usage.total_tokens == 42 and saved.cost_status == 'estimated'
    assert saved.provider_request_id == 'synthetic-response-1'


@pytest.mark.parametrize('finish', ['stop', 'length'])
def test_desktop_capacity_flows_through_loopback_once_without_retry(finish):
    configured = d.MainModelConfig.model_validate(desktop_config())
    value = request(); body = envelope(value)
    body['usage'].update(completion_tokens=9000, total_tokens=9030)
    body['choices'][0]['finish_reason'] = finish
    with server(raw(body)) as (url, calls, _):
        provider = main.DeepSeekProvider.for_synthetic_loopback(configured, lambda: KEY, url)
        reply = asyncio.run(provider.generate(value, expected_config=configured))
    assert len(calls) == 1
    wire = json.loads(calls[0]['body'])
    assert wire['max_tokens'] == 393216 and wire['thinking'] == {'type': 'disabled'}
    assert reply.usage.completion_tokens == 9000
    assert (reply.output is not None) == (finish == 'stop')
    assert reply.error_code == (None if finish == 'stop' else 'MODEL_OUTPUT_TRUNCATED')


@pytest.mark.parametrize('field,value', [('max_output_tokens',393217), ('max_response_bytes',8388609), ('timeout_seconds',601)])
def test_provider_and_resource_bounds_remain_enforced(field, value):
    with pytest.raises(ValueError):
        config(**{field: value})


def test_library_preview_uses_provider_maximum_without_authorizing_send():
    from tests.unit.test_assistant_context_preview import api, manifest, scope
    configured = d.MainModelConfig.model_validate(desktop_config())
    preview = api().build_preview(manifest(), scope(), 2, configured)
    assert preview.state == 'ready' and preview.sending_enabled is False
    assert json.loads(preview.wire_payload_json)['max_tokens'] == 393216
