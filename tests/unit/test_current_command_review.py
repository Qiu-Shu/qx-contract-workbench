"""Independent review examples shared with the current desktop router."""
import json
from pathlib import Path
import pytest
from cn_contract.assistant import business, trademark_triage

CASES=json.loads((Path(__file__).parents[1]/'fixtures/current-command-review-synthetic.json').read_bytes())
@pytest.mark.parametrize('case',CASES)
def test_review_boundary(case):
    assert business.classify(case['text'])==case['workflow']
    assert business.negative_only(case['text']) is case['blocked']
    if case['blocked']:
        assert trademark_triage.select_method('case',case['text']) is None

@pytest.mark.parametrize('text',['客户说“继续”。','对方说“这个任务继续”。','若收到材料，再继续。'])
def test_quoted_or_conditional_continuation_is_not_authorization(text):
    assert not business.continuing(text)
