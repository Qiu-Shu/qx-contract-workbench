import pytest
from cn_contract import domain as d
from cn_contract.weixin_inbox.service_routing import decide,control,readiness


@pytest.mark.parametrize('message',[
    '现在还不可以开始','尚未发送完毕','还没有发送完毕','不可以现在开始',
    '等我发送完毕后再开始','如果材料发送完毕就可以开始','发送完毕后才能开始',
    '可以开始了吗？','对方说可以开始','明天可以开始',
    '等材料到齐，可以开始','材料发送完毕后，可以开始',
    '等我发完，再开始',
])
def test_negative_conditional_or_quoted_start_is_not_permission(message):
    assert control(d.TaskInboxEventInput(event_id='control',text=message))=='paused'
    assert readiness('可以开始\n'+message)=='paused'
    assert readiness(message+'\n可以开始')=='collecting'


@pytest.mark.parametrize('message',['可以开始','现在可以开始','开始','开始处理','发送完毕',
    '材料发完了','我已发送完毕','新事项：请审查合同，可以开始'])
def test_explicit_affirmative_readiness_is_supported(message):
    assert control(d.TaskInboxEventInput(event_id='control',text=message))=='collecting'


def test_two_matters_explicit_title_beats_recent_and_capability_change_reuses():
    candidates = [{'id':'a','title':'甲租赁事项'}, {'id':'b','title':'乙买卖事项'}]
    assert decide('甲租赁事项做庭审准备', candidates).conversation_id == 'a'
    assert decide('继续整理这个案件', candidates).action == 'clarify'
    assert decide('新事项：丙公司客户咨询', candidates).relation == 'new'


@pytest.mark.parametrize('message,workflow',[
    ('新事项：请理清诉求，准备下一步','sales'),
    ('新事项：案件整理，梳理事实与材料线索','case'),
    ('新事项：审查合同，核对原文，准备修改建议','contract'),
    ('新事项：庭审准备，从不同视角准备追问','court'),
])
def test_weixin_clear_function_labels_automatically_select_workflow(message,workflow):
    decision=decide(message,[])
    assert decision.action=='start'
    assert decision.relation=='new'
    assert decision.workflow==workflow


@pytest.mark.parametrize('message',[
    '不需要理清诉求','无需案件整理','不要审查合同','取消庭审准备',
    '请理清诉求\n不需要理清诉求','整理材料\n无需案件整理',
    '审查合同\n不要审查合同','庭审准备\n取消庭审准备',
])
def test_weixin_negative_function_instruction_waits_without_workflow(message):
    decision=decide(message,[])
    assert decision.action=='wait'
    assert decision.workflow is None


def test_single_matter_continue_then_release_keeps_same_matter():
    decision=decide('继续\n可以开始',[{'id':'a','title':'甲事项'}])
    assert decision.conversation_id=='a'


def test_hold_greeting_and_file_only_never_start():
    assert decide('还有附件，稍等', []).action == 'wait'
    assert decide('测试', []).action == 'ack'
    assert decide('', []).action == 'wait'


def test_clear_followup_uses_only_single_candidate():
    assert decide('继续补充', [{'id':'a','title':'甲事项'}]).conversation_id == 'a'
    assert decide('补充：合同金额120000元', [{'id':'a','title':'甲事项'}]).conversation_id == 'a'
    assert decide('新事项：乙客户咨询', [{'id':'a','title':'甲事项'}]).relation == 'new'


def test_release_and_batch_internal_supplement_do_not_select_an_old_matter():
    content='验收A：虚构合同审查，材料还没发完\n验收A补充：总额120000元\n验收A：附件已发完，可以开始'
    decision=decide(content,[{'id':'old','title':'既有事项'}])
    assert decision.action=='clarify'
    assert decision.conversation_id is None
