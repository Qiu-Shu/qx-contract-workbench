"""Frozen v4 compatibility; role and scope quality require separate content review."""
import json
from pathlib import Path

import pytest

from cn_contract import domain as d
from cn_contract.assistant import case_evidence
from cn_contract.assistant.providers.policy import sha
from tests.unit.test_case_evidence_scope import frozen_fixture, manifest_for


GOLDEN = Path(__file__).parents[1] / 'fixtures' / 'case_method_v4_golden.json'
GOLDEN_SHA = '60f8b6eaaaccc74756236d0181dbec3575d1306de923d1b902de319899bf331b'


def test_saved_v4_system_snapshot_and_complete_candidate_are_unchanged():
    text = GOLDEN.read_text(encoding='utf-8')
    assert sha(text) == GOLDEN_SHA
    expected = json.loads(text)
    snapshot = d.CaseMethodSnapshot.model_validate(expected['snapshot'])
    assert case_evidence.method_system(snapshot) == expected['system']
    assert sha(expected['system']) == snapshot.method_sha256
    assert case_evidence.select_method('case', '起草文书并整理时间线', method_id='case-evidence-v4') == snapshot
    golden = frozen_fixture()
    result = case_evidence.candidate(golden['draft'], manifest_for(snapshot, golden))
    assert result.model_dump(mode='json') == expected['candidate']
    assert sha(result.text) == expected['text_sha256']


@pytest.mark.parametrize('method_id', [f'case-evidence-v{version}' for version in range(1, 6)])
def test_known_revision_can_be_selected_and_reconstructed_without_changing_id(method_id):
    selected = case_evidence.select_method('case', '起草文书并整理时间线', method_id=method_id)
    assert selected.method_id == method_id
    saved = d.CaseMethodSnapshot.model_validate(selected.model_dump(mode='json'))
    assert saved == selected
    assert sha(case_evidence.method_system(saved)) == saved.method_sha256


@pytest.mark.parametrize('method_id,other_id', [
    ('case-evidence-v4', 'case-evidence-v5'),
    ('case-evidence-v5', 'case-evidence-v4'),
])
def test_v4_and_v5_cannot_borrow_each_others_method_digest(method_id, other_id):
    selected = case_evidence.select_method('case', '整理时间线', method_id=method_id)
    other = case_evidence.select_method('case', '整理时间线', method_id=other_id)
    swapped = selected.model_copy(update={'method_sha256': other.method_sha256})
    golden = frozen_fixture()
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.candidate(golden['draft'], manifest_for(swapped, golden))
