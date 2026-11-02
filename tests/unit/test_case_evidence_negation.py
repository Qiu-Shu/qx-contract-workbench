"""Frozen v3 compatibility; semantic negation quality needs separate content review."""
import json
from pathlib import Path

from cn_contract import domain as d
from cn_contract.assistant import case_evidence
from cn_contract.assistant.providers.policy import sha
from tests.unit.test_case_evidence_scope import frozen_fixture, manifest_for


GOLDEN = Path(__file__).parents[1] / 'fixtures' / 'case_method_v3_golden.json'
GOLDEN_SHA = '591205dbc5728bb5d00d96583742e138f7928d08ba567947d6d1adbd032f6173'


def test_saved_v3_system_snapshot_and_complete_candidate_are_unchanged():
    text = GOLDEN.read_text(encoding='utf-8')
    assert sha(text) == GOLDEN_SHA
    expected = json.loads(text)
    snapshot = d.CaseMethodSnapshot.model_validate(expected['snapshot'])
    assert case_evidence.method_system(snapshot) == expected['system']
    assert sha(expected['system']) == snapshot.method_sha256
    assert case_evidence.select_method('case', '起草文书并整理时间线', method_id='case-evidence-v3') == snapshot
    golden = frozen_fixture()
    result = case_evidence.candidate(golden['draft'], manifest_for(snapshot, golden))
    assert result.model_dump(mode='json') == expected['candidate']
    assert sha(result.text) == expected['text_sha256']
