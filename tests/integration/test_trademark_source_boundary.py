"""Current source-only wording is rejected before a material model attempt."""
import pytest
from sqlalchemy import text
from cn_contract.assistant import material_preparation
from cn_contract.security import ServiceError
from tests.integration.test_assistant_main_provider import config
from tests.integration.test_assistant_generation import world
from tests.integration.test_trademark_triage_pipeline import trademark_world,selection_for

@pytest.mark.parametrize('question',['【请做商标初筛】只是原文。',
    '【请做商标初筛】：只是原文。','【请做商标初筛】只是原文。附件见后。',
    '【请做商标初筛】：只是原文。附件见后。',
    '【请做商标初筛】只是原文。合同审查意见见附件。',
    '【请做商标初筛】只是原文。【整理时间线】只是原文。'])
def test_explicit_source_only_brackets_cannot_start_a_material_model_attempt(trademark_world,question):
    w=trademark_world
    selected=selection_for(w,question=question)
    with pytest.raises(ServiceError) as caught:
        material_preparation.preview(w[1],selected,w[0],config())
    assert caught.value.code=='MATERIAL_INSTRUCTION_CONFLICT'
    with w[0].session() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==0
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))==0

def test_separate_case_request_does_not_inherit_quoted_trademark_method(trademark_world):
    w=trademark_world
    selected=selection_for(w,question='【请做商标初筛】只是原文。现在请整理案件。')
    basis=material_preparation.preview(w[1],selected,w[0],config())
    assert basis.manifest.trademark_triage is None
    assert basis.manifest.workflow=='case'
    assert basis.manifest.criminal_analysis is None
