import pytest
import json
from pathlib import Path
from cn_contract.assistant import business
CASES=json.loads((Path(__file__).parents[1]/'fixtures/current-command-data-synthetic.json').read_bytes())
@pytest.mark.parametrize('case',CASES)
def test_current_data_is_not_a_command(case):
    assert business.classify(case['text'])==case['workflow']
    assert business.negative_only(case['text']) is case['blocked']
