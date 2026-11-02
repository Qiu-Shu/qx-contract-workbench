"""Shared desktop/backend command examples; all text is synthetic."""
import json
from pathlib import Path
import pytest
from cn_contract.assistant import business
from cn_contract.weixin_inbox.service_routing import decide

CASES = json.loads((Path(__file__).parents[1] / 'fixtures/business-intent-synthetic.json').read_text(encoding='utf8'))


@pytest.mark.parametrize('example', CASES)
def test_command_boundaries(example):
    assert business.classify(example['text']) == example['workflow']
    assert business.negative_only(example['text']) == example['blocked']


@pytest.mark.parametrize('content', [
    '继续整理材料\n可以开始',
    '继续整理材料\n虚构补充事实：交货日期待核\n可以开始',
    '继续整理材料\n附件已经上传\n发送完毕',
])
def test_release_preserves_explicit_continuation(content):
    decision = decide(content, [{'id':'matter-a','title':'虚构甲事项'}])
    assert decision.action == 'start'
    assert decision.conversation_id == 'matter-a'
    assert decision.workflow == 'case'


def test_multiple_candidates_and_cancel_do_not_guess_matter():
    candidates = [{'id':'matter-a','title':'虚构甲事项'}, {'id':'matter-b','title':'虚构乙事项'}]
    assert decide('继续整理材料\n可以开始', candidates).action == 'clarify'
    assert decide('虚构甲事项停止处理', candidates).action == 'wait'
    assert decide('虚构乙事项继续整理材料\n可以开始', candidates).conversation_id == 'matter-b'


def test_cancel_between_continuation_and_release_does_not_revive_task():
    assert decide('继续整理材料\n停止处理\n可以开始', [{'id':'matter-a','title':'虚构甲事项'}]).action == 'wait'
