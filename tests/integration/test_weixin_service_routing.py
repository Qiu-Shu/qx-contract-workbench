import pytest
from cn_contract.weixin_inbox.service_routing import decide


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
