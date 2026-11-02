"""Current request scope through real persistence, synthetic loopback transport only."""
import pytest
from sqlalchemy import text
from cn_contract.assistant import business, material_preparation
from cn_contract.security import ServiceError
from tests.helpers.case_evidence import add_document
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config
from tests.integration.test_trademark_triage_pipeline import trademark_world, execute
from tests.integration.test_material_followup_history import followup

# Exact failed preflight question; preserve the separate experiment and its failure.
QUESTION='请做商标初筛。请基于本组两份材料，就涉案文字标识做商标使用与权属的初步筛查：分别梳理我方委托人与对方各自可核的因素、双方在标识与商品渠道上的重合处和不同处，并列出当前材料的缺口与需补凭证。本轮结论仅用于内部初筛，不作侵权是否成立的判断；若后续补充材料到达，应在同一案件卷宗内续办，不另立案。'

def test_unconditional_request_with_future_condition_saves_and_continues_same_task(trademark_world):
    w=trademark_world
    chosen=followup(w,None,QUESTION,new_task=True,workflow=None)
    first,basis=execute(w,chosen)
    assert basis.manifest.question==QUESTION
    assert basis.manifest.trademark_triage.method_id=='trademark-triage-v5'
    with w[0].session() as db:
        original=db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),{'id':str(first.id)})
    add_document(w,['独立虚构补件：仅为展位询问，没有销售记录，仍待核。'])
    q2='请继续商标初筛。若再有材料，再整理。'
    second,updated=execute(w,followup(w,basis.manifest.stable_task_id,q2,workflow=None))
    assert second.output is not None
    assert updated.manifest.stable_task_id==basis.manifest.stable_task_id
    assert len(updated.manifest.materials)==len(basis.manifest.materials)+1
    assert [m.content for m in updated.manifest.conversation_history]==[QUESTION,first.output.candidate.text]
    with w[0].session() as db:
        assert db.scalar(text('SELECT output_json FROM assistant_model_outputs WHERE attempt_id=:id'),{'id':str(first.id)})==original
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==2
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs'))==2

@pytest.mark.parametrize('question',[
    '如果客户授权，请做商标初筛。','若收到材料；请做商标初筛。',
    '请做商标初筛。若收到材料，再整理。暂停。',
    '请做商标初筛。若收到材料，再整理。只接收材料。',
    '客户说“请做商标初筛。请审查合同”。',
    '不要在这个案子里做任何形式的商标初筛',
    '请做商标初筛。不做商标。',
    '如果客户在2026.10.01前未授权，请做商标初筛。',
    '请做商标初筛，暂停。',
    '请做商标初筛。请先暂停。',
    '客户说“继续”。',
    '请审查合同。不审查合同。',
    '【请做商标初筛】只是原文。暂时不分析，只接收材料。',
])
def test_pending_or_withdrawn_instruction_cannot_use_explicit_workflow_or_old_task(trademark_world,question):
    w=trademark_world
    chosen=followup(w,None,'请做商标初筛。',new_task=True)
    basis=material_preparation.preview(w[1],chosen,w[0],config())
    blocked=followup(w,basis.manifest.stable_task_id,question,workflow='case')
    with w[0].session() as db:
        rows=business.history(w[1],w[2],db)
        latest=next(row for row in rows if row.run_id==blocked.parent_business_run_id)
        assert latest.workflow is None and latest.task_id is None
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==0
    with pytest.raises(ServiceError):
        material_preparation.preview(w[1],blocked,w[0],config())

@pytest.mark.parametrize('question,explicit,fresh',[
    ('不要新建任务，请整理材料。',False,False),
    ('不要新建任务，请整理材料。',True,False),
    ('客户说“开始新任务”。请整理材料。',False,False),
    ('若以后有需要，再新建任务。请整理材料。',False,False),
    ('请新建任务整理材料。',False,True),
    ('请整理材料。',True,True),
])
def test_new_task_requires_current_unconditional_nonnegated_request(trademark_world,question,explicit,fresh):
    w=trademark_world
    first=followup(w,None,'请整理材料。',new_task=True)
    basis=material_preparation.preview(w[1],first,w[0],config())
    next_selection=followup(w,basis.manifest.stable_task_id,question,new_task=explicit)
    with w[0].session() as db:
        result=next(row for row in business.history(w[1],w[2],db) if row.run_id==next_selection.parent_business_run_id)
        assert (result.task_id!=basis.manifest.stable_task_id) is fresh
        assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts'))==0
