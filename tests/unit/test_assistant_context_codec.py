"""Explicit context input identity, with no live account or mutable database."""
import importlib
import importlib.util
import json
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.library_records import encoded, sha
from cn_contract.assistant.providers.context_preview import build_preview, project_source
from tests.unit.test_assistant_context_preview import config
from tests.unit.test_library_records import citation_container, synthetic_citation


def api():
    name = 'cn_contract.assistant.providers.context_codec'
    assert importlib.util.find_spec(name) is not None, 'context codec missing'
    return importlib.import_module(name)


def fixture(*, configured=None, records=None, question='仅整理合成资料中的待核对事项。'):
    codec = api()
    configured = config() if configured is None else configured
    records = tuple(records or (citation_container(synthetic_citation(), 'saved'),))
    scope = records[0].scope
    manifest = d.MainContextManifest(format_version='saved-library-context-v1',
        question=question, sources=tuple(project_source(item) for item in records))
    basis = codec.build_basis(uuid4(), manifest, scope, 2, configured, records)
    request = d.MainContextRequest(run_id=uuid4(), message_id=uuid4(),
        scope=d.ScopeSnapshot.model_validate(scope.model_dump() | {'input_revision':scope.input_revision+1}),
        composer_revision=3, manifest=manifest, basis=basis)
    return configured, records, request


def test_context_uses_exact_preview_wire_and_keeps_local_proofs_out_of_payload():
    codec = api()
    configured, records, request = fixture()
    prepared = codec.prepare(request, configured)
    preview = build_preview(request.manifest, request.basis.expected_scope, 2, configured)
    assert prepared.wire_payload_json == preview.wire_payload_json
    assert preview.sending_enabled is False
    assert request.basis.source_bindings[0].citation_sha256 == sha(encoded(records[0].citation))
    assert str(request.run_id) not in prepared.wire_payload_json
    assert str(request.message_id) not in prepared.wire_payload_json
    assert str(request.basis.request_id) not in prepared.wire_payload_json
    assert request.basis.source_bindings[0].citation_sha256 not in prepared.wire_payload_json
    assert codec.build_request(request, configured) == json.loads(prepared.wire_payload_json)


@pytest.mark.parametrize('changes', [
    {'config_sha256':'0'*64}, {'wire_sha256':'0'*64}, {'manifest_sha256':'0'*64},
    {'system_sha256':'0'*64}, {'template_version':'unknown-v9'}, {'input_format':'plain-text-v1'},
])
def test_forged_basis_cannot_bypass_prepare(changes):
    configured, _, request = fixture()
    forged = request.model_copy(update={'basis':request.basis.model_copy(update=changes)})
    with pytest.raises(ValueError):
        api().prepare(forged, configured)


@pytest.mark.parametrize('changes', [
    {'enabled':False}, {'model':'deepseek-v4-pro'}, {'input_usd_per_million':'1.1'},
    {'timeout_seconds':10}, {'max_input_bytes':100}, {'price_reference':'other synthetic rates'},
])
def test_complete_configuration_change_requires_new_basis(changes):
    _, _, request = fixture()
    with pytest.raises(ValueError):
        api().prepare(request, config(**changes))


@pytest.mark.parametrize('field,value', [
    ('input_revision',1), ('input_revision',3), ('materials_revision',1),
    ('binding_revision',2), ('conversation_id',uuid4()), ('workspace_id',uuid4()),
])
def test_only_exact_registered_successor_scope_is_accepted(field, value):
    configured, _, request = fixture()
    scope = request.scope.model_copy(update={field:value})
    with pytest.raises(ValueError):
        api().prepare(request.model_copy(update={'scope':scope}), configured)


@pytest.mark.parametrize('revision', [0, 2, 4])
def test_composer_revision_must_be_exact_successor(revision):
    configured, _, request = fixture()
    with pytest.raises(ValueError):
        api().prepare(request.model_copy(update={'composer_revision':revision}), configured)


def test_complete_citation_identity_not_only_outbound_projection():
    from cn_contract.assistant.citation_identity import citation_identity
    configured, records, request = fixture()
    # Metadata is intentionally absent from the wire, but changes full identity.
    citation = records[0].citation.model_dump(mode='json') | {'metadata':{'court':'另一合成法院'}}
    citation['citation_id'] = citation_identity(citation)
    changed = records[0].model_copy(update={'citation':d.CitationRef.model_validate(citation)})
    assert project_source(changed) == request.manifest.sources[0]
    with pytest.raises(ValueError):
        api().validate_sources(request.manifest, request.basis.expected_scope,
            request.basis.source_bindings, (changed,))
    api().validate_sources(request.manifest, request.basis.expected_scope,
        request.basis.source_bindings, records)
    assert api().prepare(request, configured)


@pytest.mark.parametrize('field,value', [
    ('conversation_id',uuid4()), ('workspace_id',uuid4()), ('binding_revision',2),
    ('input_revision',2), ('materials_revision',1),
])
def test_saved_source_cannot_cross_scope_or_come_from_future_revision(field, value):
    _, records, request = fixture()
    record = records[0]
    changed = record.model_copy(update={'scope':record.scope.model_copy(update={field:value})})
    with pytest.raises(ValueError):
        api().validate_sources(request.manifest, request.basis.expected_scope,
            request.basis.source_bindings, (changed,))


def test_exact_source_order_and_set_required():
    _, records, _ = fixture()
    first = records[0]
    second = first.model_copy(update={'id':uuid4()})
    configured, records, request = fixture(records=(first, second))
    api().validate_sources(request.manifest, request.basis.expected_scope,
        request.basis.source_bindings, records)
    for changed in (records[::-1], records[:1], records+records[:1]):
        with pytest.raises(ValueError):
            api().validate_sources(request.manifest, request.basis.expected_scope,
                request.basis.source_bindings, changed)
    forged = request.basis.model_copy(update={'source_bindings':request.basis.source_bindings[::-1]})
    with pytest.raises(ValueError):
        api().prepare(request.model_copy(update={'basis':forged}), configured)


def test_unicode_budget_counts_exact_wire_bytes_without_truncation():
    _, records, request = fixture(question='合成问题😀\n'*100)
    preview = build_preview(request.manifest, request.basis.expected_scope, 2, config())
    length = len(preview.wire_payload_json.encode('utf-8'))
    assert length > len(preview.wire_payload_json)
    exact, _, exact_request = fixture(configured=config(max_input_bytes=length),
        records=records, question=request.manifest.question)
    assert len(api().prepare(exact_request, exact).wire_payload_json.encode('utf-8')) == length
    with pytest.raises(ValueError):
        fixture(configured=config(max_input_bytes=length-1), records=records, question=request.manifest.question)


def test_old_v1_types_and_provider_do_not_accept_context_types():
    from cn_contract.assistant.providers.main import build_request
    configured, _, request = fixture()
    with pytest.raises(ValueError):
        build_request(request, configured)
    with pytest.raises(ValueError):
        d.MainPreparedInput.model_validate(api().prepare(request, configured))
    reply = d.MainContextReply(state='received', output=d.MainContextCandidate(text='合成回答'))
    with pytest.raises(ValueError):
        d.MainReply.model_validate(reply)


def test_new_run_ids_do_not_change_approved_wire_and_local_basis_is_not_a_grant():
    configured, _, request = fixture()
    changed = request.model_copy(update={'run_id':uuid4(), 'message_id':uuid4()})
    assert api().prepare(request, configured).wire_payload_json == api().prepare(changed, configured).wire_payload_json
    assert 'policy_id' not in type(request.basis).model_fields
    assert 'allowed' not in type(request.basis).model_fields


@pytest.mark.parametrize('field,value', [('text',' '), ('support_status','verified'),
    ('tool_calls',[]), ('citations',[{'saved_citation_id':str(uuid4()), 'quote_sha256':'0'*64}]*2)])
def test_candidate_rejects_empty_duplicate_or_extra_semantics(field, value):
    with pytest.raises(ValueError):
        d.MainContextCandidate.model_validate({'text':'合成回答', 'citations':[], field:value})


@pytest.mark.parametrize('value', [
    {'state':'received'},
    {'state':'failed_before_send', 'error_code':'BLOCKED_LIVE', 'provider_request_id':'synthetic'},
    {'state':'sent_unknown', 'error_code':'PROVIDER_ERROR', 'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}},
    {'state':'received', 'error_code':'MODEL_OUTPUT_INVALID', 'output':{'text':'合成回答'}},
])
def test_context_reply_retains_conservative_state_contract(value):
    with pytest.raises(ValueError):
        d.MainContextReply.model_validate(value)
