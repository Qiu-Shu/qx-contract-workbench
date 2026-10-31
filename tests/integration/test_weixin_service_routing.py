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


def test_hold_greeting_and_file_only_never_start():
    assert decide('还有附件，稍等', []).action == 'wait'
    assert decide('测试', []).action == 'ack'
    assert decide('', []).action == 'wait'


def test_clear_followup_uses_only_single_candidate():
    assert decide('继续补充', [{'id':'a','title':'甲事项'}]).conversation_id == 'a'
    assert decide('新事项：乙客户咨询', [{'id':'a','title':'甲事项'}]).relation == 'new'
