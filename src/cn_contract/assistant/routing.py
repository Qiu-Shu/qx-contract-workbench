"""Workflow advice only; caller retains the complete request and owns permission."""
from typing import get_args

from .. import domain as d


def choose_workflow(explicit_skill, judge_result, allowed_skills):
    available = set(get_args(d.AssistantSkill)).intersection(allowed_skills)
    if explicit_skill is not None:
        if type(explicit_skill) is str and explicit_skill in available:
            return d.RouteDecision(workflow=explicit_skill, source='explicit', reason_code='explicit_skill')
        return d.RouteDecision(workflow=None, source='current', reason_code='explicit_unavailable')
    try:
        if type(judge_result) is not d.JudgeResult:
            raise ValueError
        value = d.JudgeResult.model_validate(judge_result.model_dump(mode='python'))
    except (ValueError, TypeError):
        return d.RouteDecision(workflow=None, source='current', reason_code='no_suggestion')
    answer = value.answers.get('primary_intent') if value.status == 'ok' else None
    if type(answer) is not d.JudgeChoice or answer.choice == 'unknown':
        return d.RouteDecision(workflow=None, source='current', reason_code='no_suggestion')
    if answer.choice not in available:
        return d.RouteDecision(workflow=None, source='current', reason_code='unavailable_suggestion')
    return d.RouteDecision(workflow=answer.choice, source='jev', reason_code='jev_suggestion')
