"""New contract protocol is opt-in by a host snapshot; old wires stay exact."""
import importlib
import json

import pytest

from cn_contract import domain as d
from cn_contract.assistant import material_codec as codec
from tests.unit.test_contract_live_method import sample, request, legacy_basis


def current():
    method = importlib.import_module('cn_contract.assistant.contract_review')
    manifest, selection, config = sample()
    manifest = manifest.model_copy(update={'contract_review':method.select_method(
        manifest.workflow, manifest.materials, manifest.sources)})
    return manifest, selection, config


def test_new_contract_method_is_bound_to_request_but_not_legacy_c4():
    old, selection, config = sample()
    old_basis = codec.build_basis(selection, old, config)
    old_wire = codec.prepare(request(old_basis), config).wire_payload_json
    legacy, legacy_wire = legacy_basis(old, selection, config)
    manifest, selection, config = current()
    basis = codec.build_basis(selection, manifest, config)
    wire = codec.build_request(request(basis), config)
    assert 'contract-review-v1' in wire['messages'][0]['content']
    assert basis.system_sha256 == manifest.contract_review.method_sha256
    assert json.loads(wire['messages'][1]['content'])['contract_review'] == manifest.contract_review.model_dump(mode='json')
    assert codec.prepare(request(old_basis), config).wire_payload_json == old_wire
    assert codec.build_request(request(legacy), config) == legacy_wire
    assert 'contract_review' not in old.model_dump(mode='json')


@pytest.mark.parametrize('field', ['method_sha256','method_id','playbook_status'])
def test_forged_method_or_approval_is_rejected(field):
    manifest, selection, config = current()
    snapshot = manifest.contract_review.model_dump(mode='python')
    snapshot[field] = {'method_sha256':'f'*64, 'method_id':'unregistered', 'playbook_status':'approved'}[field]
    with pytest.raises(ValueError):
        forged = manifest.model_dump(mode='python') | {'contract_review':snapshot}
        codec.build_basis(selection, d.MainMaterialManifest.model_validate(forged), config)


def test_contract_snapshot_cannot_move_to_other_workflow():
    manifest, _, _ = current()
    with pytest.raises(ValueError):
        d.MainMaterialManifest.model_validate(manifest.model_dump(mode='python') | {'workflow':'case'})


def test_current_contract_cannot_accept_legacy_candidate():
    manifest, _, _ = current()
    candidate = d.MainMaterialCandidate(text='旧格式草稿', citations=(manifest.sources[0].source_id,))
    with pytest.raises(ValueError):
        codec.validate_manifest_candidate(candidate, manifest)


def test_method_routes_cannot_describe_a_different_material_selection():
    from uuid import uuid4
    manifest, selection, config = current()
    snapshot = manifest.contract_review
    route = snapshot.routes[0].model_copy(update={'attachment_id':uuid4()})
    forged = manifest.model_copy(update={'contract_review':snapshot.model_copy(update={'routes':(route,)})})
    with pytest.raises(ValueError):
        codec.build_basis(selection, forged, config)


def test_method_snapshot_bytes_count_towards_existing_wire_limit():
    manifest, selection, config = current()
    basis = codec.build_basis(selection, manifest, config)
    with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
        codec.build_basis(selection, manifest, config.model_copy(update={'max_input_bytes':basis.wire_bytes-1}))
