"""Independent CH-05A contract boundary probes, synthetic snapshots only."""
from uuid import uuid4
import pytest
from pydantic import ValidationError
from cn_contract import domain as d
from cn_contract.assistant.routing import choose_workflow

PRIMARY = ('client_reply', 'material_organize', 'contract_review', 'content_draft', 'legal_research', 'unknown')
MATERIAL = ('contract', 'chat', 'transfer', 'judgment', 'mixed', 'unknown')


def answer(choice='client_reply', labels=PRIMARY):
    return d.JudgeChoice(choice=choice, probabilities={label: int(label == choice) for label in labels}, confidence=1)


def fields():
    return dict(status='ok', evidence='received', reason_code=None, local_request_id=uuid4(), input_hash='1'*64,
        scope=d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
            input_revision=0, materials_revision=0), elapsed_ms=10, model='jev-1.13.0',
        answers={'primary_intent': answer()})


@pytest.mark.parametrize('case', ['missing_criteria', 'extra_criteria', 'wrong_type', 'wrong_kind_options'])
def test_ok_domain_result_requires_exact_fixed_question_semantics(case):
    data = fields()
    if case == 'missing_criteria': data['answers'] = {'primary_intent': answer(labels=('client_reply',))}
    elif case == 'extra_criteria': data['answers'] = {'primary_intent': answer(labels=PRIMARY+('invented',))}
    elif case == 'wrong_type': data['answers'] = {'primary_intent': d.JudgeNoul(noul=1)}
    else: data['answers'] = {'material_kind': answer()}
    with pytest.raises(ValidationError): d.JudgeResult(**data)


@pytest.mark.parametrize('elapsed', [2001, 999999])
def test_absolute_late_ok_result_is_rejected_by_domain_and_cannot_route(elapsed):
    data = {**fields(), 'elapsed_ms': elapsed}
    forged = d.JudgeResult.model_construct(**data)
    assert choose_workflow(None, forged, set(PRIMARY)).workflow is None
    with pytest.raises(ValidationError): d.JudgeResult(**data)


def test_model_copy_missing_criteria_is_revalidated_before_routing():
    good = d.JudgeResult(**fields())
    forged = good.model_copy(update={'answers': {'primary_intent': answer(labels=('client_reply',))}})
    assert choose_workflow(None, forged, {'client_reply'}).workflow is None


@pytest.mark.parametrize('changes', [
    dict(workflow='contract_review', source='current', reason_code='no_suggestion'),
    dict(workflow=None, source='jev', reason_code='jev_suggestion'),
    dict(workflow='client_reply', source='jev', reason_code='explicit_skill'),
    dict(workflow='client_reply', source='explicit', reason_code='jev_suggestion'),
    dict(workflow=None, source='current', reason_code='explicit_skill')])
def test_route_decision_cannot_contradict_its_source(changes):
    with pytest.raises(ValidationError): d.RouteDecision(**changes)


def test_explicit_still_takes_precedence_over_invalid_auxiliary_result():
    good = d.JudgeResult(**fields())
    bad = good.model_copy(update={'elapsed_ms': 99999})
    allowed = {'client_reply', 'contract_review'}
    route = choose_workflow('contract_review', bad, allowed)
    assert (route.workflow, route.source, route.reason_code) == ('contract_review', 'explicit', 'explicit_skill')
    assert choose_workflow('unknown', good, allowed).workflow is None
    assert choose_workflow(None, good, {'legal_research'}).workflow is None


def test_all_fixed_choices_and_noul_can_be_represented_without_route_escalation():
    for label in PRIMARY:
        value = d.JudgeResult(**{**fields(), 'answers': {'primary_intent': answer(label)}})
        picked = choose_workflow(None, value, set(PRIMARY))
        assert picked.workflow == (None if label == 'unknown' else label)
    for label in MATERIAL:
        value = d.JudgeResult(**{**fields(), 'answers': {'material_kind': answer(label, MATERIAL)}})
        assert choose_workflow(None, value, set(PRIMARY)).workflow is None
    value = d.JudgeResult(**{**fields(), 'answers': {'possible_result_guarantee': d.JudgeNoul(noul=1)}})
    assert choose_workflow(None, value, set(PRIMARY)).workflow is None
