"""Synthetic judge snapshots and routing advice; no authorization or I/O."""
from importlib import import_module
from typing import get_args
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d


def scope():
    return d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(),
        binding_revision=1, input_revision=0, materials_revision=0)


def result(choice='client_reply', **changes):
    options = set(get_args(d.AssistantSkill)) | {'unknown'}
    fields = dict(status='ok', evidence='received', reason_code=None, local_request_id=uuid4(),
        input_hash='1'*64, scope=scope(), elapsed_ms=10, model='jev-1.13.0',
        answers={'primary_intent': d.JudgeChoice(choice=choice,
            probabilities={key: int(key == choice) for key in options}, confidence=1)})
    fields.update(changes)
    return d.JudgeResult(**fields)


def choose(*args):
    return import_module('cn_contract.assistant.routing').choose_workflow(*args)


def test_default_disabled_fixed_model_and_bounded_request():
    config = d.JevConfig()
    assert not config.enabled and config.model == 'jev-1.13.0' and config.timeout_ms == 2000
    for change in ({'model': 'jev-latest'}, {'timeout_ms': 2001}, {'enabled': 1},
                   {'max_input_bytes': 65537}, {'endpoint': 'https://invalid.example'}):
        with pytest.raises(ValidationError): d.JevConfig(**change)
    request = d.JudgeRequest(local_request_id=uuid4(), scope=scope(), purpose='primary_intent',
        text=' 第一件合成诉求\n第二件合成诉求 ')
    assert request.text == ' 第一件合成诉求\n第二件合成诉求 '
    with pytest.raises(ValidationError):
        d.JudgeRequest(**{**request.model_dump(), 'approved': True})


@pytest.mark.parametrize('value', [True, False, '0.5', -0.01, 1.01, float('nan'), float('inf')])
def test_probabilities_are_numbers_not_truth_or_strings(value):
    with pytest.raises(ValidationError): d.JudgeNoul(noul=value)
    with pytest.raises(ValidationError): d.JudgeChoice(choice='a', probabilities={'a': value}, confidence=1)


@pytest.mark.parametrize('choice, probabilities', [('a', {}), ('a', {'b': 1}),
    ('a', {'a': 0.4, 'b': 0.6}), ('a', {'a': 0.8, 'b': 0.8})])
def test_choice_does_not_repair_invalid_probability_distribution(choice, probabilities):
    with pytest.raises(ValidationError): d.JudgeChoice(choice=choice, probabilities=probabilities, confidence=0.4)


def test_tied_choice_and_unknown_usage_remain_distinct_from_zero():
    value = d.JudgeChoice(choice='a', probabilities={'a': 0.5, 'b': 0.5}, confidence=0)
    with pytest.raises(TypeError): value.probabilities['a'] = 1
    assert d.JudgeNoul(noul=0).noul == 0
    assert d.JudgeUsage().input_tokens is None and d.JudgeUsage(input_tokens=0).input_tokens == 0
    with pytest.raises(ValidationError): d.JudgeUsage(output_tokens=True)


@pytest.mark.parametrize('changes', [dict(status='timed_out', reason_code='timeout'),
    dict(evidence='not_sent'), dict(evidence='sent_unknown'), dict(model=None), dict(answers={})])
def test_result_cannot_mix_usable_answers_with_unknown_or_unsent_state(changes):
    with pytest.raises(ValidationError): result(**changes)


def test_timed_out_received_metadata_is_accounting_only():
    value = result(status='timed_out', reason_code='timeout', answers={},
        usage=d.JudgeUsage(input_tokens=3), provider_request_id='synthetic-receipt')
    assert choose(None, value, {'client_reply'}).workflow is None


def test_explicit_skill_always_wins_without_mutating_full_request_or_judge():
    original = d.JudgeRequest(local_request_id=uuid4(), scope=scope(), purpose='primary_intent',
        text='先回复虚构客户，再整理全部合成附件；最后查法条。', explicit_skill='material_organize')
    snapshot = original.model_dump_json()
    judge = result(); before = judge.model_dump_json()
    decision = choose(original.explicit_skill, judge, {'client_reply', 'material_organize'})
    assert (decision.workflow, decision.source) == ('material_organize', 'explicit')
    assert original.model_dump_json() == snapshot and judge.model_dump_json() == before
    assert set(decision.model_dump()) == {'workflow', 'source', 'reason_code'}


@pytest.mark.parametrize('explicit', ['not_registered', 'contract_review', ''])
def test_unavailable_explicit_choice_never_falls_back_to_judge(explicit):
    decision = choose(explicit, result(), {'client_reply'})
    assert decision.workflow is None and decision.reason_code == 'explicit_unavailable'


def test_valid_advice_only_selects_whitelisted_existing_workflow():
    assert choose(None, result(), {'client_reply'}).workflow == 'client_reply'
    assert choose(None, result(), {'material_organize'}).workflow is None
    forged = result().model_copy(update={'answers': {'primary_intent': d.JudgeChoice(
        choice='not_registered', probabilities={'not_registered': 1}, confidence=1)}})
    assert choose(None, forged, {'not_registered'}).workflow is None
    assert choose(None, result('unknown'), {'unknown'}).workflow is None


def test_material_mix_and_absent_or_forged_judge_do_not_replace_current_flow():
    mixed = result(answers={'material_kind': d.JudgeChoice(choice='mixed',
        probabilities={key: int(key == 'mixed') for key in get_args(d.JudgeMaterialKind)}, confidence=1)})
    assert choose(None, mixed, {'client_reply'}).workflow is None
    assert choose(None, None, {'client_reply'}).workflow is None
    forged = result().model_copy(update={'status': 'timed_out'})
    assert choose(None, forged, {'client_reply'}).workflow is None


@pytest.mark.parametrize('elapsed_ms', [2000, 3000])
def test_late_judge_is_never_a_usable_result(elapsed_ms):
    with pytest.raises(ValidationError): result(elapsed_ms=elapsed_ms)


def test_incomplete_options_and_contradictory_route_cannot_be_valid_snapshots():
    with pytest.raises(ValidationError):
        result(answers={'primary_intent': d.JudgeChoice(choice='client_reply',
            probabilities={'client_reply': 1}, confidence=1)})
    with pytest.raises(ValidationError):
        d.RouteDecision(workflow='contract_review', source='current', reason_code='no_suggestion')


@pytest.mark.parametrize('evidence', ['not_sent', 'sent_unknown'])
def test_configured_model_is_not_a_received_model_receipt(evidence):
    with pytest.raises(ValidationError):
        result(status='failed', reason_code='provider_error', evidence=evidence, answers={})
