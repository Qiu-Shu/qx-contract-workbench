"""Synthetic wire fixtures; no vendor account or legal source material."""
from copy import deepcopy
import importlib
import json
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.config import canonical_json


OPTIONS = {
    'primary_intent': ('client_reply', 'material_organize', 'contract_review',
                       'content_draft', 'legal_research', 'unknown'),
    'material_kind': ('contract', 'chat', 'transfer', 'judgment', 'mixed', 'unknown'),
}
SECRET = 'SYNTHETIC_JEV_SECRET_12345'


def api():
    return importlib.import_module('cn_contract.assistant.providers.jev_codec')


def request(purpose='primary_intent', **changes):
    fields = dict(local_request_id=uuid4(), scope=d.ScopeSnapshot(
        workspace_id=uuid4(), conversation_id=uuid4(), scope_kind='matter',
        scope_ref=uuid4(), binding_revision=2, input_revision=3, materials_revision=4),
        purpose=purpose, text='合成多诉求：先答复客户，再整理附件。\n保留原文 😀', explicit_skill=None)
    fields.update(changes)
    return d.JudgeRequest(**fields)


def envelope(purpose='primary_intent'):
    answer = {'type': 'noul', 'noul': .95} if purpose not in OPTIONS else {
        'type': 'choice', 'choice': OPTIONS[purpose][0],
        'probabilities': {key: (1 if index == 0 else 0) for index, key in enumerate(OPTIONS[purpose])},
        'confidence': .7}
    return {'model': 'jev-1.13.0', 'answers': {purpose: answer},
            'usage': {'input_tokens': 20, 'output_tokens': 5}}


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


@pytest.mark.parametrize('purpose,state_key', [('primary_intent', 'latest_request'),
    ('material_kind', 'material_text'), ('possible_result_guarantee', 'public_draft')])
def test_fixed_single_question_preserves_unicode_and_omits_local_identity(purpose, state_key):
    value = request(purpose); cfg = d.JevConfig()
    body = api().build_request(value, cfg)
    assert set(body) == {'model', 'state', 'questions'}
    assert body['model'] == cfg.model and set(body['questions']) == {purpose}
    assert body['state'][state_key] == value.text
    assert set(body['state']) == ({state_key, 'selected_skill'} if purpose == 'primary_intent' else {state_key})
    if purpose in OPTIONS:
        assert set(body['questions'][purpose]['criteria']) == set(OPTIONS[purpose])
    else:
        assert body['questions'][purpose]['type'] == 'noul'
    encoded = canonical_json(body)
    assert value.text in json.loads(encoded)['state'][state_key]
    for identifier in (value.local_request_id, value.scope.workspace_id, value.scope.conversation_id,
                       value.scope.scope_ref):
        assert str(identifier) not in encoded


def test_wire_byte_limit_includes_fixed_template_overhead_and_never_truncates():
    value = request(); body = api().build_request(value, d.JevConfig())
    size = len(canonical_json(body).encode('utf-8'))
    assert api().build_request(value, d.JevConfig(max_input_bytes=size)) == body
    with pytest.raises(ValueError, match='invalid judge request'):
        api().build_request(value, d.JevConfig(max_input_bytes=size - 1))
    with pytest.raises(ValueError):
        api().build_request(request(text='中' * 32768), d.JevConfig())


def test_hash_binds_full_request_config_and_template_version(monkeypatch):
    value = request(); cfg = d.JevConfig(); module = api()
    baseline = module.input_hash(value, cfg)
    assert len(baseline) == 64 and module.input_hash(deepcopy(value), deepcopy(cfg)) == baseline
    for field in type(value.scope).model_fields:
        old = getattr(value.scope, field)
        replacement = ('intake' if field == 'scope_kind' else
                       uuid4() if old is None or hasattr(old, 'hex') else old + 1)
        changed = value.model_copy(update={'scope': value.scope.model_copy(update={field: replacement})})
        assert module.input_hash(changed, cfg) != baseline
    for field, replacement in [('local_request_id', uuid4()), ('text', value.text + ' '),
                               ('explicit_skill', 'client_reply'), ('purpose', 'material_kind')]:
        assert module.input_hash(value.model_copy(update={field: replacement}), cfg) != baseline
    for field, replacement in [('enabled', True), ('timeout_ms', 1000),
                               ('max_input_bytes', 60000), ('max_response_bytes', 60000)]:
        assert module.input_hash(value, cfg.model_copy(update={field: replacement})) != baseline
    monkeypatch.setattr(module, 'TEMPLATE_VERSION', 'synthetic-template-v2')
    assert module.input_hash(value, cfg) != baseline


@pytest.mark.parametrize('purpose', list(OPTIONS) + ['possible_result_guarantee'])
def test_valid_response_keeps_reported_confidence_or_noul(purpose):
    decoded = api().decode_response(raw(envelope(purpose)), request(purpose), d.JevConfig(), 'synthetic-id')
    assert decoded['reason_code'] is None and decoded['provider_request_id'] == 'synthetic-id'
    assert decoded['usage'] == d.JudgeUsage(input_tokens=20, output_tokens=5)
    answer = decoded['answers'][purpose]
    if purpose in OPTIONS:
        assert answer.confidence == .7
    else:
        assert answer.noul == .95 and 'confidence' not in answer.model_dump()


@pytest.mark.parametrize('usage', [{}, {'input_tokens': None}, {'output_tokens': None},
                                  {'input_tokens': 0, 'output_tokens': 0}])
def test_missing_counts_remain_unknown_and_real_zero_remains_zero(usage):
    body = envelope(); body['usage'] = usage
    decoded = api().decode_response(raw(body), request(), d.JevConfig())
    assert decoded['reason_code'] is None
    assert decoded['usage'].input_tokens == usage.get('input_tokens')
    assert decoded['usage'].output_tokens == usage.get('output_tokens')


def mutations():
    yield 'missing question', lambda b: b['answers'].clear()
    yield 'extra question', lambda b: b['answers'].update(other={'type': 'noul', 'noul': .5})
    yield 'wrong type', lambda b: b['answers'].update(primary_intent={'type': 'noul', 'noul': .5})
    yield 'wrong model', lambda b: b.update(model='jev-latest')
    yield 'extra envelope', lambda b: b.update(untrusted='ignored?')
    yield 'missing option', lambda b: b['answers']['primary_intent']['probabilities'].pop('unknown')
    yield 'extra option', lambda b: b['answers']['primary_intent']['probabilities'].update(other=0)
    yield 'unknown choice', lambda b: b['answers']['primary_intent'].update(choice='other')
    yield 'not maximum', lambda b: b['answers']['primary_intent'].update(choice='unknown')
    yield 'bool confidence', lambda b: b['answers']['primary_intent'].update(confidence=True)
    yield 'bool probability', lambda b: b['answers']['primary_intent']['probabilities'].update(unknown=False)
    yield 'negative probability', lambda b: b['answers']['primary_intent']['probabilities'].update(unknown=-.1)
    yield 'sum not one', lambda b: b['answers']['primary_intent']['probabilities'].update(unknown=.2)
    yield 'nonfinite', lambda b: b['answers']['primary_intent'].update(confidence=float('nan'))
    yield 'extra answer field', lambda b: b['answers']['primary_intent'].update(text='arbitrary')


@pytest.mark.parametrize('name,mutate', list(mutations()), ids=lambda value: value if isinstance(value, str) else '')
def test_invalid_answers_or_envelope_preserve_only_safe_metadata(name, mutate):
    body = envelope(); mutate(body)
    decoded = api().decode_response(raw(body), request(), d.JevConfig(), 'safe-id')
    assert decoded['reason_code'] == 'invalid_response' and decoded['answers'] == {}
    assert decoded['provider_request_id'] == 'safe-id'
    # A syntactically invalid/nonfinite document has no independently parsed usage.
    if name != 'nonfinite':
        assert decoded['usage'] == d.JudgeUsage(input_tokens=20, output_tokens=5)


@pytest.mark.parametrize('usage', [None, [], {'input_tokens': True}, {'output_tokens': -1},
    {'input_tokens': 1.5}, {'input_tokens': 2**31}, {'input_tokens': '2'}, {'extra': 1}])
def test_invalid_usage_is_not_replaced_by_zero(usage):
    body = envelope(); body['usage'] = usage
    decoded = api().decode_response(raw(body), request(), d.JevConfig(), 'safe-id')
    assert decoded['reason_code'] == 'invalid_response' and decoded['usage'] is None


def test_missing_usage_envelope_is_invalid():
    body = envelope(); del body['usage']
    assert api().decode_response(raw(body), request(), d.JevConfig())['reason_code'] == 'invalid_response'


@pytest.mark.parametrize('body', [b'[]', b'{}{}', b'{"model":1,"model":2}', b'{"x":1e999}',
    b'{"x":Infinity}', b'{"x":"\xff"}', '{}'.encode('utf-16'),
    ('{"x":' + '[' * 34 + '0' + ']' * 34 + '}').encode(),
    raw({'x': [0] * 20001})], ids=['array', 'trailing', 'duplicate', 'overflow',
        'infinity', 'bad-utf8', 'utf16', 'depth', 'nodes'])
def test_strict_json_resource_and_encoding_bounds(body):
    decoded = api().decode_response(body, request(), d.JevConfig())
    assert decoded['reason_code'] == 'invalid_response' and decoded['answers'] == {}


@pytest.mark.parametrize('identifier', ['', 'x' * 257, 'bad\nvalue', 'bad\x7fvalue', SECRET])
def test_unsafe_request_id_is_discarded_without_invalidating_answer(identifier):
    decoded = api().decode_response(raw(envelope()), request(), d.JevConfig(), identifier, SECRET)
    assert decoded['reason_code'] is None and decoded['provider_request_id'] is None


@pytest.mark.parametrize('escaped', [False, True])
def test_secret_reflection_in_any_json_string_or_key_is_never_returned(escaped):
    body = raw({**envelope(), SECRET: 'synthetic'})
    if escaped:
        body = body.replace(SECRET.encode(), ''.join('\\u%04x' % ord(c) for c in SECRET).encode())
    decoded = api().decode_response(body, request(), d.JevConfig(), 'safe-id', SECRET)
    assert decoded == {'answers': {}, 'usage': None, 'provider_request_id': None, 'model': None,
                       'reason_code': 'provider_error'}


def test_tied_maximum_choice_is_legal():
    body = envelope(); probabilities = body['answers']['primary_intent']['probabilities']
    probabilities.update(client_reply=.5, unknown=.5)
    assert api().decode_response(raw(body), request(), d.JevConfig())['reason_code'] is None
