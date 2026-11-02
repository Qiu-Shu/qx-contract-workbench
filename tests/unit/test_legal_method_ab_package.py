"""Offline comparison inputs must stay paired, traceable and unscored."""
import copy
import importlib.util
import json
from hashlib import sha256
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('legal_method_ab', ROOT / 'scripts/prepare_legal_method_ab.py')
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


@pytest.mark.parametrize('case_id', package.CASE_IDS)
def test_pairs_keep_identical_facts_and_current_method_selection(case_id):
    case = next(case for case in package.load_cases() if case['id'] == case_id)
    pair = package.prepare_pair(case)
    left, right = pair['A'], pair['B']
    a, b = (json.loads(wire['messages'][1]['content']) for wire in (left, right))
    selected = [field for field in package.METHOD_FIELDS if field in b]
    assert len(selected) == 1
    assert b.pop(selected[0])['method_id'] == case['expected_method']
    assert a == b
    assert left['messages'][0] != right['messages'][0]
    assert {k: v for k, v in left.items() if k != 'messages'} == {
        k: v for k, v in right.items() if k != 'messages'}
    assert pair == package.prepare_pair(case)
    if case_id == 'criminal_case':
        snap = json.loads(right['messages'][1]['content'])['criminal_analysis']
        assert snap['stage'] == 'investigation'
        assert [m['method_id'] for m in snap['method_sources']] == ['case_analysis']
    if case_id == 'defense_strategy':
        snap = json.loads(right['messages'][1]['content'])['criminal_analysis']
        assert snap['stage'] == 'prosecution'
        assert [m['method_id'] for m in snap['method_sources']] == ['case_analysis', 'defense_strategy']
    if case_id == 'commercial_review':
        snap = json.loads(right['messages'][1]['content'])['contract_review']
        assert {'nda', 'vendor'} <= {method for route in snap['routes'] for method in route['methods']}
        assert 'dpa' in {kind for route in snap['routes'] for kind in route['uncovered']}
        assert 'C4材料草稿适配版' in left['messages'][0]['content']


@pytest.mark.parametrize('bad_ref', [
    {'document_id': 'missing'}, {'paragraph': 0}, {'paragraph': True},
    {'exact_quote': '材料中没有的引文'}, {'exact_quote': ''},
])
def test_checkpoints_cannot_invent_sources(bad_ref):
    case = copy.deepcopy(package.load_cases()[0])
    case['checkpoints'][0]['refs'][0].update(bad_ref)
    with pytest.raises(ValueError, match='CHECKPOINT_INVALID'):
        package.prepare_pair(case)


def test_package_contains_no_results_and_will_not_overwrite(tmp_path, monkeypatch):
    import socket
    import httpx

    def forbidden(*args, **kwargs):
        pytest.fail('Offline preparation attempted network access')

    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(httpx.Client, 'send', forbidden)
    first, second = tmp_path / 'first', tmp_path / 'second'
    package.write_package(first)
    package.write_package(second)
    inventory = json.loads((first / 'sha256.json').read_text(encoding='utf-8'))
    assert inventory == json.loads((second / 'sha256.json').read_text(encoding='utf-8'))
    for path, digest in inventory.items():
        assert sha256((first / path).read_bytes()).hexdigest() == digest
    status = json.loads((first / 'status.json').read_text(encoding='utf-8'))
    assert status['case_count'] == 6 and status['request_count'] == 12
    assert status['model_calls'] == 0
    assert status['model_evaluation'] == status['lawyer_evaluation'] == 'NOT_RUN'
    assert status['scores'] is None and status['quality_decision'] == 'PENDING'
    for item in status['cases']:
        assert item['baseline'] == item['enhanced'] == 'NOT_RUN'
        assert item['legal_gold'] == 'UNAPPROVED'
    before = {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}
    with pytest.raises(FileExistsError):
        package.write_package(first)
    assert before == {p.relative_to(first): p.read_bytes() for p in first.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case_id', package.CASE_IDS)
def test_reviewer_keys_never_enter_model_requests(case_id):
    case = next(case for case in package.load_cases() if case['id'] == case_id)
    for arm in ('A', 'B'):
        wire = json.dumps(package.prepare_pair(case)[arm], ensure_ascii=False)
        assert 'checkpoints' not in wire
        for checkpoint in case['checkpoints']:
            assert checkpoint['text'] not in wire
        assert 'quality_decision' not in wire


def test_exported_requests_bind_actual_material_bytes(tmp_path):
    root = tmp_path / 'package'
    package.write_package(root)
    for case_id in package.CASE_IDS:
        wire = json.loads((root / 'coordinator/requests' / case_id / 'B.json').read_bytes())
        manifest = json.loads(wire['messages'][1]['content'])
        index = json.loads((root / 'inputs' / case_id / 'source-index.json').read_bytes())
        for source in manifest['sources']:
            ref = source['reference']
            if ref['kind'] != 'document':
                continue
            locator = index['sources'][source['source_id']]
            path = root / 'inputs' / case_id / (locator['document_id'] + '.json')
            document = json.loads(path.read_bytes())
            assert ref['original_sha256'] == sha256(path.read_bytes()).hexdigest()
            assert ref['anchor']['quote'] == locator['quote'] == document['paragraphs'][locator['paragraph'] - 1]
