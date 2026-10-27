"""Contract method routing and old immutable wire compatibility, without network."""
import json
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant import material_codec as codec
from cn_contract.assistant.providers.policy import sha, encoded
from cn_contract.assistant.providers.deepseek_protocol import json_bytes


def sample(workflow='contract'):
    attachment_id, cid = uuid4(), uuid4()
    quote = '虚构合同：采购40件，单价25元，预付款20%，其余验收后付。'
    anchor = d.Anchor(id=uuid4(), document_version_id=attachment_id, part_name='word/document.xml',
        element_id='p0', kind='body_paragraph', quote=quote, quote_sha256=sha(quote), start=0, end=len(quote),
        table=None, row=None, cell=None, page=None, bbox=None)
    ref = d.ProfileDocumentRef(kind='document', conversation_id=cid, attachment_id=attachment_id,
        original_sha256='a'*64, parse_revision=1, result_sha256='b'*64, anchor=anchor)
    material = d.MainMaterialFile(attachment_id=attachment_id, name='合成合同.docx',
        original_sha256='a'*64, parse_revision=1, result_sha256='b'*64, reading_status='readable',
        pages=(), parts=('word/document.xml',), unread_parts=(), quality_issues=())
    parent_id = uuid4()
    manifest = d.MainMaterialManifest(workflow=workflow, stable_task_id=uuid4(), parent_business_run_id=parent_id,
        question='请核对金额、付款条件和未约定事项', materials=(material,),
        sources=(d.MainMaterialSource(source_id=sha(encoded(ref)), reference=ref),))
    selection = d.MainMaterialSelection(request_id=uuid4(), expected_scope=d.ScopeSnapshot(workspace_id=uuid4(),
        conversation_id=cid, binding_revision=1, input_revision=0, materials_revision=1),
        expected_composer_revision=0, parent_business_run_id=parent_id)
    config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.30',
        output_usd_per_million='1.20', price_reference='synthetic test rates')
    return manifest, selection, config


def legacy_basis(manifest, selection, config):
    # Reproduce the exact pre-C4 wire, rather than calling new routing code.
    body = dict(model=config.model, messages=[dict(role='system', content=codec.SYSTEM),
        dict(role='user', content=json_bytes(manifest.model_dump(mode='json')).decode('utf-8'))],
        max_tokens=config.max_output_tokens, stream=False, thinking={'type':'disabled'},
        response_format={'type':'json_object'})
    wire = json_bytes(body)
    basis = d.MainMaterialSendBasis(**selection.model_dump(mode='python'), manifest=manifest,
        manifest_sha256=sha(encoded(manifest)), system_sha256=sha(codec.SYSTEM), config_sha256=sha(encoded(config)),
        wire_sha256=sha(wire.decode('utf-8')), wire_bytes=len(wire))
    return basis, body


def request(basis):
    return d.MainMaterialRequest(run_id=uuid4(), message_id=uuid4(),
        scope=basis.expected_scope.model_copy(update={'input_revision':basis.expected_scope.input_revision+1}), basis=basis)


def test_contract_uses_c4_method_in_bound_wire():
    manifest, selection, config = sample()
    basis = codec.build_basis(selection, manifest, config)
    wire = codec.build_request(request(basis), config)
    assert 'C4材料草稿适配版' in wire['messages'][0]['content']
    assert basis.system_sha256 == sha(wire['messages'][0]['content'])
    assert basis.system_sha256 != sha(codec.SYSTEM)
    assert set(wire['messages'][1]) == {'role', 'content'}
    assert json.loads(wire['messages'][1]['content']) == manifest.model_dump(mode='json')


@pytest.mark.parametrize('workflow', ['sales', 'case', 'court'])
def test_other_workflows_keep_exact_previous_wire(workflow):
    manifest, selection, config = sample(workflow)
    old, wire = legacy_basis(manifest, selection, config)
    assert codec.build_basis(selection, manifest, config) == old
    assert codec.build_request(request(old), config) == wire


def test_legacy_contract_basis_rebuilds_exactly_for_history():
    manifest, selection, config = sample()
    old, wire = legacy_basis(manifest, selection, config)
    assert codec.rebuild_basis(old, config) == old
    assert codec.build_request(request(old), config) == wire
    assert codec.prepare(request(old), config).wire_payload_json == json_bytes(wire).decode('utf-8')


@pytest.mark.parametrize('field', ['system_sha256', 'wire_sha256', 'manifest_sha256', 'config_sha256'])
def test_tampered_basis_fails_closed(field):
    manifest, selection, config = sample()
    basis = codec.build_basis(selection, manifest, config).model_copy(update={field:'f'*64})
    with pytest.raises(ValueError): codec.build_request(request(basis), config)


def test_method_bytes_count_toward_preflight_budget():
    manifest, selection, config = sample()
    old, _ = legacy_basis(manifest, selection, config)
    config = config.model_copy(update={'max_input_bytes':old.wire_bytes})
    with pytest.raises(ValueError, match='MATERIAL_INPUT_TOO_LARGE'):
        codec.build_basis(selection, manifest, config)
