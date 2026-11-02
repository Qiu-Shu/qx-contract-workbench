"""Local fixed rejection reasons preserve legacy receipt bytes and never private text."""
import json
import pytest
from cn_contract import domain as d
from cn_contract.assistant.providers import deepseek_protocol as protocol
from cn_contract.assistant.providers.policy import receipt, encoded
from tests.integration.test_assistant_main_provider import config, request, envelope, raw, KEY


@pytest.mark.parametrize('error,reason', [
    ('CONTRACT_QUOTE_INVALID','quotes'), ('CONTRACT_REFERENCE_INVALID','references'),
    ('CONTRACT_STANCE_INVALID','stance'), ('CONTRACT_COVERAGE_INVALID','coverage'),
    ('CONTRACT_METHOD_INVALID','method'), ('PRIVATE_FICTIONAL_DIAGNOSTIC','schema'),
    ('MATERIAL_OUTPUT_INVALID','schema'), ('MODEL_USAGE_INVALID','usage'),
])
def test_fixed_candidate_reason_survives_receipt_without_exception_text(error, reason):
    def reject(_):
        raise ValueError(error)
    result = protocol.decode_response(raw(envelope(request())), config(), KEY,
        parse_candidate=reject, reply_type=d.MainMaterialReply)
    assert result.error_code == 'MODEL_OUTPUT_INVALID' and result.output is None
    saved = receipt(result, config())
    assert saved.rejection_reason == reason and saved.usage.total_tokens == 42
    assert d.MainReceipt.model_validate_json(encoded(saved)) == saved
    assert error not in encoded(saved) and KEY not in encoded(saved)


@pytest.mark.parametrize('mutation,reason', [('model','envelope'),('usage','usage'),('content','json'),('message','message')])
def test_protocol_reason_is_fixed_and_received_usage_is_preserved(mutation, reason):
    body = envelope(request())
    if mutation == 'model':body['model'] = 'not-our-model'
    if mutation == 'usage':body['usage']['total_tokens'] = 1
    if mutation == 'content':body['choices'][0]['message']['content'] = '{PRIVATE-FICTIONAL'
    if mutation == 'message':body['choices'][0]['message']['content'] = ' '
    result = protocol.decode_response(raw(body), config(), KEY,
        parse_candidate=lambda value:d.MainCandidate.model_validate(value), reply_type=d.MainReply)
    assert receipt(result,config()).rejection_reason == reason
    assert 'PRIVATE-FICTIONAL' not in encoded(result)


def test_legacy_receipt_roundtrip_does_not_add_null_reason_or_rewrite_old_bytes():
    old = '{"cost_status":"estimated","error_code":"MODEL_OUTPUT_INVALID","estimated_cost_usd":"0.000054","provider_request_id":"synthetic-response-1","state":"received","unit":"USD","usage":{"completion_tokens":12,"prompt_cache_hit_tokens":10,"prompt_cache_miss_tokens":20,"prompt_tokens":30,"total_tokens":42}}'
    value = d.MainReceipt.model_validate_json(old)
    assert encoded(value) == old
    assert value.rejection_reason is None


@pytest.mark.parametrize('model', [d.MainReply,d.MainContextReply,d.MainMaterialReply])
def test_reason_cannot_be_attached_to_unknown_or_unsent_response(model):
    with pytest.raises(ValueError):
        model(state='sent_unknown',error_code='MODEL_OUTPUT_INVALID',rejection_reason='quotes')
    with pytest.raises(ValueError):
        model(state='received',error_code='MODEL_OUTPUT_INVALID',rejection_reason='PRIVATE_TEXT')
