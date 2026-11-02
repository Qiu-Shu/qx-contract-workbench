"""Current commands respect sentence scope while saved method ids retain their meaning."""
import json
from pathlib import Path
import pytest
from cn_contract.assistant import business, trademark_triage as method

CASES=json.loads((Path(__file__).parents[1]/'fixtures/current-command-scope-synthetic.json').read_bytes())

@pytest.mark.parametrize('case',CASES)
def test_current_business_does_not_drop_an_unconditional_instruction(case):
    assert business.classify(case['text'])==case['workflow']
    assert business.negative_only(case['text']) is case['blocked']

@pytest.mark.parametrize('question',[
    '请做商标初筛。若后续补充材料到达，应在同一案件卷宗内续办。',
    '请做商标初筛；若后续材料到达，再整理。',
    '暂停。请做商标初筛。若后续材料到达，再整理。',
])
def test_new_trademark_method_selects_current_request_without_reinterpreting_old_ids(question):
    selected=method.select_method('case',question)
    assert selected is not None and selected.method_id=='trademark-triage-v5'
    for legacy in ('trademark-triage-v1','trademark-triage-v2'):
        assert method.select_method('case',question,method_id=legacy) is None

@pytest.mark.parametrize('question',[
    '如果客户授权，请做商标初筛。','若收到材料；请做商标初筛。',
    '请做商标初筛。若后续材料到达，再整理。不做商标初筛。',
    '客户说“请做商标初筛”。若后续材料到达，再整理。',
])
def test_new_trademark_method_never_promotes_conditional_denied_or_quoted_work(question):
    assert method.select_method('case',question) is None

def test_legacy_command_helpers_keep_original_line_scope():
    text='请做商标初筛；若后续材料到达，再整理。'
    assert business._command_text(text)==''
    assert business.execution_hold(text) is True
    assert business._latest_command(text,('商标初筛',)) is None
