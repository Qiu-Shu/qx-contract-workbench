"""A reported fact does not absorb its outer instruction or authorize its own action."""
import json
from hashlib import sha256
from pathlib import Path

import pytest
from cn_contract.assistant import business
from cn_contract import domain as d
from cn_contract.assistant import material_codec, trademark_triage
from cn_contract.assistant.providers.policy import encoded
from cn_contract.review.model_adapter import strict_json

CASES = json.loads((Path(__file__).parents[1] / 'fixtures/current-command-reported-prefix-synthetic.json').read_bytes())


@pytest.mark.parametrize('example', CASES, ids=lambda example: example['text'])
def test_current_reported_prefix_boundary(example):
    assert business.classify(example['text']) == example['workflow']
    assert business.negative_only(example['text']) is example['blocked']
    if 'continuing' in example:
        assert business.continuing(example['text']) is example['continuing']


def test_legacy_reported_clause_interpretation_is_unchanged():
    text = '补充：客户说明已收到五千元，银行凭证待核。'
    assert business._command_text(text) == '银行凭证待核\n'
    assert business.execution_hold(text) is False
    assert business.execution_hold('请继续客户接待：客户说明已收到五千元。') is True


FROZEN = json.loads((Path(__file__).parents[1] / 'fixtures/trademark-reported-scope-prepared.json').read_bytes())


@pytest.mark.parametrize('row', FROZEN['rows'], ids=lambda row: row['id'])
def test_frozen_trademark_prepared_keeps_method_and_exact_wire(row):
    assert sha256(row['prepared_json'].encode('utf-8')).hexdigest() == row['prepared_sha256']
    prepared = d.MainMaterialPreparedInput.model_validate(strict_json(row['prepared_json']))
    config = d.MainModelConfig.model_validate_json(row['config_json'])
    manifest = prepared.request.basis.manifest
    trademark_triage.validate_snapshot(manifest)
    assert trademark_triage.select_method(manifest.workflow, manifest.question,
        method_id=manifest.trademark_triage.method_id) == manifest.trademark_triage
    assert material_codec.rebuild_basis(prepared.request.basis, config) == prepared.request.basis
    rebuilt = material_codec.prepare(prepared.request, config)
    assert encoded(rebuilt) == row['prepared_json']
    assert sha256(rebuilt.wire_payload_json.encode('utf-8')).hexdigest() == row['wire_sha256']
