"""Frozen historical candidates and source binding, not semantic accuracy."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cn_contract import domain as d
from cn_contract.assistant import case_evidence
from cn_contract.assistant.providers.policy import sha


GOLDEN = Path(__file__).parents[1] / 'fixtures' / 'case_method_scope_golden.json'
GOLDEN_SHA = '20287a79effe2f76ab4bdcd53b24dcbe8e1ab807e6fcfe1b389ccceb58bf1401'


def frozen_fixture():
    text = GOLDEN.read_text(encoding='utf-8')
    assert sha(text) == GOLDEN_SHA
    return json.loads(text)


def manifest_for(snapshot, golden):
    return SimpleNamespace(case_method=snapshot, knowledge=None, sources=tuple(
        SimpleNamespace(source_id=source['source_id'],
            reference=SimpleNamespace(kind='message', quote=source['text']))
        for source in golden['sources']))


@pytest.mark.parametrize('method_id', ['case-evidence-v1', 'case-evidence-v2'])
def test_saved_historical_system_snapshot_and_complete_candidate_are_unchanged(method_id):
    golden = frozen_fixture()
    expected = golden['versions'][method_id]
    # Reconstruct the saved snapshot; selecting the new default would hide a fallback.
    snapshot = d.CaseMethodSnapshot.model_validate(expected['snapshot'])
    assert case_evidence.method_system(snapshot) == expected['system']
    assert sha(expected['system']) == snapshot.method_sha256
    assert case_evidence.select_method('case', '起草文书并整理时间线', method_id=method_id) == snapshot
    result = case_evidence.candidate(golden['draft'], manifest_for(snapshot, golden))
    assert result.model_dump(mode='json') == expected['candidate']
    assert sha(result.text) == expected['text_sha256']


def test_new_case_request_uses_v5_with_existing_evidence_format_and_rendering():
    golden = frozen_fixture()
    snapshot = case_evidence.select_method('case', '起草文书并整理时间线')
    assert snapshot.method_id == 'case-evidence-v5'
    assert snapshot == case_evidence.select_method('case', '起草文书并整理时间线', method_id='case-evidence-v5')
    assert d.CaseMethodSnapshot.model_validate(snapshot.model_dump(mode='json')) == snapshot
    assert sha(case_evidence.method_system(snapshot)) == snapshot.method_sha256
    result = case_evidence.candidate(golden['draft'], manifest_for(snapshot, golden))
    assert result.case_evidence.format_version == 'case-evidence-v1'
    assert result.model_dump(mode='json') == golden['versions']['case-evidence-v2']['candidate']


@pytest.mark.parametrize('method_id', ['case-evidence-v1', 'case-evidence-v2', 'case-evidence-v3', 'case-evidence-v4', 'case-evidence-v5'])
def test_saved_method_digest_tampering_is_rejected(method_id):
    snapshot = case_evidence.select_method('case', '整理时间线', method_id=method_id)
    bad = snapshot.model_copy(update={'method_sha256': 'f' * 64})
    golden = frozen_fixture()
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.candidate(golden['draft'], manifest_for(bad, golden))


@pytest.mark.parametrize('mutation', ['source', 'quote', 'offset', 'reference'])
@pytest.mark.parametrize('method_id', ['case-evidence-v3', 'case-evidence-v4', 'case-evidence-v5'])
def test_source_or_structured_reference_tampering_is_rejected(mutation, method_id):
    golden = frozen_fixture()
    snapshot = case_evidence.select_method('case', '整理时间线', method_id=method_id)
    data = golden['draft']
    if mutation == 'source':
        data['quotes'][0]['source_id'] = 'f' * 64
    elif mutation == 'quote':
        data['quotes'][0]['exact_quote'] = '日期栏明确为空。'
    elif mutation == 'offset':
        data['quotes'][0]['start'] = 1
    else:
        data['statements'][0]['support'] = ['absent']
    with pytest.raises(ValueError):
        case_evidence.candidate(data, manifest_for(snapshot, golden))


def test_unknown_future_revision_cannot_be_selected_or_reconstructed():
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.select_method('case', '整理时间线', method_id='case-evidence-v6')
    golden = frozen_fixture()
    snapshot = d.CaseMethodSnapshot.model_validate(golden['versions']['case-evidence-v2']['snapshot'])
    with pytest.raises(ValueError):
        d.CaseMethodSnapshot.model_validate(dict(method_id='case-evidence-v6',
            method_sha256=snapshot.method_sha256))
    unknown = snapshot.model_copy(update={'method_id': 'case-evidence-v6'})
    with pytest.raises(ValueError, match='CASE_METHOD_INVALID'):
        case_evidence.candidate(golden['draft'], manifest_for(unknown, golden))


@pytest.mark.parametrize('workflow', ['sales', 'contract', 'court'])
def test_case_method_is_not_selected_for_another_workflow(workflow):
    assert case_evidence.select_method(workflow, '起草文书并整理时间线') is None
