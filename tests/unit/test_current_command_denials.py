"""Current denial scope must not depend on the length of an intervening phrase."""
import pytest
import json
from pathlib import Path
from cn_contract.assistant import business, trademark_triage

CASES=json.loads((Path(__file__).parents[1]/'fixtures/current-command-denials-synthetic.json').read_bytes())
@pytest.mark.parametrize('case',CASES)
def test_current_denial_or_separate_request_controls(case):
    assert business.classify(case['text'])==case['workflow']
    assert business.negative_only(case['text']) is case['blocked']
    if case['blocked']:
        assert trademark_triage.select_method('case',case['text']) is None

def test_old_method_retains_frozen_long_prefix_interpretation():
    text='不要在这个案子里做任何形式的商标初筛'
    for mid in ('trademark-triage-v1','trademark-triage-v2'):
        assert trademark_triage.select_method('case',text,method_id=mid).method_id==mid
