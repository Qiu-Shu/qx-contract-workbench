"""Synthetic boundary tests: each rejection protects a v2.0 domain invariant."""

import copy
import hashlib
import importlib
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
U = '11111111-1111-4111-8111-111111111111'
V = '22222222-2222-4222-8222-222222222222'
W = '33333333-3333-4333-8333-333333333333'
H = 'a' * 64
NOW = '2026-10-02T10:00:00+08:00'


def domain():
    location = ROOT / 'src' / 'cn_contract' / 'domain.py'
    assert location.is_file(), 'T01 domain implementation missing'
    sys.path.insert(0, str(ROOT / 'src')) if str(ROOT / 'src') not in sys.path else None
    return importlib.import_module('cn_contract.domain')


def matter(contract_type='sales'):
    return dict(id=U, client_ref='SYNTHETIC-CLIENT', title='虚构合同', jurisdiction='CN',
                contract_type=contract_type, review_mode='pre_sign', position='buyer',
                objectives=['核对交付'], member_ids=[V], status='intake',
                active_fact_version=None, active_policy_version=None, gate_issues=[])


def manifest():
    return dict(schema_version='2.0', contract_type='sales', document_hashes={V: H}, fact_snapshot_sha256=H,
                rules_sha256=H, policy_sha256=H, model_config_sha256=H,
                config_sha256=H, model_provider='mock')


def review():
    return dict(id=U, matter_id=W, manifest=manifest(), status='completed',
                coverage=[dict(coverage_id=f'C{i:02}', status='reviewed_no_issue',
                               examined_anchor_ids=[], rule_ids=[],
                               rationale='虚构材料检查：无该事项', finding_ids=[])
                          for i in range(1, 19)],
                findings=[], limitations=['虚构演示，不能签发'], model_usage=[],
                started_at=NOW, finished_at=NOW, error_code=None)


def anchor(kind='body_paragraph'):
    return dict(id=U, document_version_id=V, part_name='word/document.xml',
                element_id='p:1', kind=kind, quote='虚构条款',
                quote_sha256=hashlib.sha256('虚构条款'.encode()).hexdigest(),
                start=0, end=4, table=None, row=None, cell=None, page=None, bbox=None)


def finding():
    return dict(id=V, run_id=U, coverage_ids=['C01'], issue_type='identity',
                severity='high', evidence_state='unconfirmed', anchor_ids=[W],
                cross_anchor_ids=[], rule_ids=[], authority_ids=[], analysis='虚构分析',
                business_effect='身份尚未核对', recommendation='补充证明',
                replacement_text=None, fallback=None, human_decision=None)


def assert_invalid(model, payload):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize('kind', ['sales', 'service', 'lease', 'nda'])
def test_four_contract_types_remain_supported_and_full(kind):
    result = domain().Matter.model_validate(matter(kind))
    assert result.contract_type.value == kind
    assert result.review_route.value == 'full'


def test_unknown_contract_routes_to_specialist():
    result = domain().Matter.model_validate(matter('unknown'))
    assert result.review_route.value == 'specialist'
    assert_invalid(domain().Matter, matter('general'))


def test_missing_position_is_not_defaulted_to_party_a():
    payload = matter()
    payload.pop('position')
    assert_invalid(domain().Matter, payload)


def test_explicit_unconfirmed_position_is_allowed_during_intake():
    payload = matter()
    payload['position'] = None
    assert domain().Matter.model_validate(payload).position is None


def test_coverage_exact18_accepts_valid_run():
    result = domain().validate_review(review())
    assert len(result.coverage) == 18
    assert result.coverage[17].coverage_id.value == 'C18'


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'unknown', 'extra'])
def test_coverage_exact18_rejects_invalid_dimensions(mutation):
    payload = review()
    if mutation == 'missing':
        payload['coverage'].pop()
    elif mutation == 'duplicate':
        payload['coverage'][-1]['coverage_id'] = 'C01'
    elif mutation == 'unknown':
        payload['coverage'][-1]['coverage_id'] = 'C99'
    else:
        payload['coverage'].append(copy.deepcopy(payload['coverage'][0]))
    assert_invalid(domain().ReviewRun, payload)


@pytest.mark.parametrize('status', ['not_applicable', 'reviewed_no_issue'])
@pytest.mark.parametrize('rationale', [None, '', '   '])
def test_no_issue_and_not_applicable_require_reason(status, rationale):
    payload = review()['coverage'][0]
    payload.update(status=status, rationale=rationale)
    assert_invalid(domain().CoverageItem, payload)


@pytest.mark.parametrize('location', ['run', 'manifest', 'coverage', 'finding'])
def test_forbid_extra_fields_in_nested_model_output(location):
    payload = review()
    if location == 'run':
        payload['safe_to_sign'] = True
    elif location == 'manifest':
        payload['manifest']['unapproved_key'] = 'value'
    elif location == 'coverage':
        payload['coverage'][0]['score'] = 99
    else:
        payload['findings'] = [finding()]
        payload['coverage'][0].update(status='reviewed_issue', finding_ids=[V])
        payload['findings'][0]['secret'] = 'not-a-real-secret'
    assert_invalid(domain().ReviewRun, payload)


def test_issue_coverage_and_finding_bidirectional_link():
    payload = review()
    payload['findings'] = [finding()]
    payload['coverage'][0].update(status='reviewed_issue', finding_ids=[V])
    result = domain().validate_review(payload)
    assert result.findings[0].run_id == result.id


@pytest.mark.parametrize('mutation', ['dangling', 'wrong_run', 'unlinked', 'wrong_dimension', 'duplicate_finding', 'false_no_issue'])
def test_review_rejects_broken_finding_links(mutation):
    payload = review()
    payload['findings'] = [finding()]
    payload['coverage'][0].update(status='reviewed_issue', finding_ids=[V])
    if mutation == 'dangling':
        payload['coverage'][0]['finding_ids'] = [W]
    elif mutation == 'wrong_run':
        payload['findings'][0]['run_id'] = W
    elif mutation == 'unlinked':
        payload['coverage'][0]['finding_ids'] = []
    elif mutation == 'wrong_dimension':
        payload['findings'][0]['coverage_ids'] = ['C02']
    elif mutation == 'duplicate_finding':
        payload['findings'].append(copy.deepcopy(payload['findings'][0]))
    else:
        payload['coverage'][0]['status'] = 'reviewed_no_issue'
    assert_invalid(domain().ReviewRun, payload)


def test_decimal_preserves_exact_credits_and_string_serialization():
    result = domain().Reservation.model_validate(dict(ledger_id=U, credits='0.123456789012345678901',
                                                     calls=1, idempotency_key='synthetic-key', status='reserved'))
    assert result.credits == Decimal('0.123456789012345678901')
    assert result.model_dump(mode='json')['credits'] == '0.123456789012345678901'


@pytest.mark.parametrize('credits', [0.1, True, '-0.01', 'NaN', 'Infinity'])
def test_credits_reject_float_bool_negative_and_nonfinite(credits):
    assert_invalid(domain().Reservation, dict(ledger_id=U, credits=credits, calls=1,
                                             idempotency_key='synthetic-key', status='reserved'))


def test_datetime_normalizes_timezone_to_utc():
    result = domain().validate_review(review())
    assert result.started_at == datetime(2026, 10, 2, 2, tzinfo=timezone.utc)
    assert result.started_at.utcoffset() == timedelta(0)


def test_datetime_rejects_naive_input():
    payload = review()
    payload['started_at'] = '2026-10-02T10:00:00'
    assert_invalid(domain().ReviewRun, payload)


def test_finish_cannot_precede_start():
    payload = review()
    payload['finished_at'] = '2026-10-01T00:00:00Z'
    assert_invalid(domain().ReviewRun, payload)


def test_document_version_is_frozen_and_lists_are_immutable():
    result = domain().DocumentVersion.model_validate(dict(
        id=U, matter_id=V, original_name='synthetic.docx', mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        sha256=H, storage_ref='synthetic/original', byte_size=12, uploaded_by=W,
        created_at=NOW, baseline_view='original', part_inventory=[], page_count=None,
        parse_status='pending', unsupported_parts=[], supersedes_id=None))
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        result.sha256 = 'b' * 64
    assert isinstance(result.part_inventory, tuple)


def test_manifest_document_hashes_are_immutable():
    result = domain().RunManifest.model_validate(manifest())
    with pytest.raises(TypeError):
        result.document_hashes[UUID(V)] = 'b' * 64
    assert result.model_dump(mode='json')['document_hashes'] == {V: H}


@pytest.mark.parametrize('mutation', ['hash', 'range', 'length', 'table_missing', 'pdf_missing', 'pdf_zero', 'bbox_reversed'])
def test_anchor_rejects_ambiguous_or_corrupt_location(mutation):
    payload = anchor()
    if mutation == 'hash':
        payload['quote_sha256'] = H
    elif mutation == 'range':
        payload['start'] = 5
    elif mutation == 'length':
        payload['end'] = 20
    elif mutation == 'table_missing':
        payload['kind'] = 'table_cell'
    elif mutation == 'pdf_missing':
        payload['kind'] = 'pdf_span'
    elif mutation == 'pdf_zero':
        payload.update(kind='pdf_span', page=0, bbox=[0, 0, 20, 10])
    else:
        payload.update(kind='pdf_span', page=1, bbox=[20, 0, 0, 10])
    assert_invalid(domain().Anchor, payload)


def test_anchor_table_and_pdf_location_are_explicit():
    table = anchor('table_cell')
    table.update(table=0, row=2, cell=1)
    assert domain().Anchor.model_validate(table).row == 2
    pdf = anchor('pdf_span')
    pdf.update(part_name='pdf/page/1', page=1, bbox=[0, 0, 20, 10])
    assert domain().Anchor.model_validate(pdf).page == 1


def test_rule_cannot_be_approved_without_lawyer_and_authority():
    payload = dict(id=U, version=1, contract_types=['sales'], positions=['buyer'],
                   trigger_facts=['price'], exception_facts=[], basis_kind='law', authority_ids=[],
                   finding_template='虚构规则', coverage_ids=['C06'], status='approved',
                   approved_by=None, approved_at=None)
    assert_invalid(domain().Rule, payload)
    payload.update(approved_by=V, approved_at=NOW)
    assert_invalid(domain().Rule, payload)
    payload['authority_ids'] = [W]
    assert domain().Rule.model_validate(payload).status.value == 'approved'


def test_approved_export_requires_approval_reference():
    payload = dict(id=U, matter_id=V, run_id=W, audience='client', type='docx',
                   content_sha256=H, storage_ref='synthetic/report', mode='approved',
                   approval_id=None, created_at=NOW, superseded=False)
    assert_invalid(domain().ExportArtifact, payload)
    payload['approval_id'] = U
    assert domain().ExportArtifact.model_validate(payload).approval_id == UUID(U)


def test_fact_confirmation_requires_actor_and_timestamp():
    payload = dict(id=U, matter_id=V, version=1, field='price', typed_value={'kind': 'decimal', 'value': Decimal('0.10')},
                   unit='CNY', provenance_type='document', anchor_ids=[W], receipt_ids=[],
                   confirmation_status='confirmed', confirmed_by=None, confirmed_at=None)
    assert_invalid(domain().Fact, payload)
    payload.update(confirmed_by=W, confirmed_at=NOW)
    assert domain().Fact.model_validate(payload).typed_value.value == Decimal('0.10')
    payload['typed_value'] = {'kind': 'decimal', 'value': 0.1}
    assert_invalid(domain().Fact, payload)


def test_actor_does_not_accept_client_supplied_memberships():
    payload = dict(user_id=U, roles=['handling_lawyer'], session_id=V, matter_ids=[W])
    assert_invalid(domain().Actor, payload)


def test_safe_expression_ast_rejects_calls_and_requires_whitelisted_nodes():
    allowed = dict(ast=dict(kind='binary', operator='add', left=dict(kind='variable', name='paid'),
                           right=dict(kind='literal', value='1')), unit='CNY')
    assert domain().SafeExpression.model_validate(allowed).ast.operator.value == 'add'
    disallowed = dict(ast=dict(kind='call', name='exec', arguments=[]), unit='CNY')
    assert_invalid(domain().SafeExpression, disallowed)


def test_auxiliary_dtos_reject_untyped_query_item_and_false_readiness_go():
    query = dict(matter_id=U, party_id=V, purpose='虚构核验', items=[dict(capability_key='party.registration', pages=0)],
                 authorization_id=W, scope='Q1')
    assert_invalid(domain().QueryPlanInput, query)
    readiness = dict(decision='GO', reasons={'rules': '尚未批准'}, evidence=None)
    assert_invalid(domain().ReadinessDecision, readiness)


def test_review_schema_contains_closed_objects_and_all_coverage_ids():
    schema = domain().ReviewRun.model_json_schema()
    assert schema['additionalProperties'] is False
    assert schema['$defs']['Finding']['additionalProperties'] is False
    assert schema['$defs']['CoverageId']['enum'] == [f'C{i:02}' for i in range(1, 19)]
    assert schema['properties']['coverage']['minItems'] == 18
    assert schema['properties']['coverage']['maxItems'] == 18


def test_all_required_entity_and_dto_types_exist():
    names = ('Matter DocumentVersion Anchor Fact Party Authority Rule Finding CoverageItem ReviewRun RunManifest '
             'ToolBinding QueryPlan QueryReceipt Patch Approval ExportArtifact AuditEvent GateIssue Actor '
             'VersionInput UploadMeta ParseResult AnchoredSpan FactDecision FactSnapshot SafeExpression CalculationResult '
             'PartyCandidate PartyDecision ReviewContext EvidenceBundle RuleSnapshot RuleSelection AuthorityInput ApprovalEvidence '
             'ModelRequest ModelResponse ProviderConfig ToolCatalog BindingInput ProviderResult BillingEvidence QueryPlanInput Reservation '
             'BudgetEntry PatchResult ArtifactBundle VerificationResult ValidationResult JobInput JobStatus AcceptanceCase EvaluationReport '
             'ReleaseConfig ReleaseManifest EgressPolicy BackupConfig BackupReport ReadinessEvidence ReadinessDecision').split()
    missing = [name for name in names if not hasattr(domain(), name)]
    assert missing == []


def test_manifest_binds_contract_type_and_unknown_route():
    payload = manifest()
    payload['contract_type'] = 'unknown'
    result = domain().RunManifest.model_validate(payload)
    assert result.review_route.value == 'specialist'
    assert domain().ReviewRun.model_json_schema()['$defs']['ContractType']['enum'] == [
        'sales', 'service', 'lease', 'nda', 'unknown']


def test_query_plan_item_freezes_nested_parameters():
    payload = dict(id=U, capability_key='party.registration', pages=1,
                   tool_binding_ref='synthetic/binding', parameters={'filter': {'codes': ['SYNTHETIC']}},
                   max_credits='1.00', price_snapshot_id=V)
    item = domain().QueryPlanItem.model_validate(payload)
    with pytest.raises(TypeError):
        item.parameters['filter']['codes'].append('OTHER')
    with pytest.raises(TypeError):
        item.parameters['filter']['added'] = 'OTHER'
    assert item.model_dump(mode='json')['parameters'] == {'filter': {'codes': ['SYNTHETIC']}}


def test_parse_result_rejects_anchor_from_another_version():
    payload = dict(version_id=W, anchors=[anchor()], pages=[], parts=['word/document.xml'],
                   unsupported_parts=[], quality_issues=[])
    assert_invalid(domain().ParseResult, payload)


def test_evidence_mapping_rejects_mismatched_uuid_key():
    payload = dict(anchors={V: anchor()}, authorities={}, receipts={})
    assert_invalid(domain().EvidenceBundle, payload)


def test_fact_snapshot_rejects_duplicate_fact_and_other_version():
    fact = dict(id=U, matter_id=V, version=1, field='price', typed_value={'kind': 'decimal', 'value': Decimal('0.10')},
                unit='CNY', provenance_type='document', anchor_ids=[W], receipt_ids=[],
                confirmation_status='unconfirmed', confirmed_by=None, confirmed_at=None)
    assert_invalid(domain().FactSnapshot, dict(version=2, facts=[fact], sha256=H))
    assert_invalid(domain().FactSnapshot, dict(version=1, facts=[fact, fact], sha256=H))


def test_validation_cannot_claim_ok_with_errors():
    assert_invalid(domain().ValidationResult, dict(ok=True, errors=['缺少资料'], warnings=[], checked=[]))


def test_authority_keeps_source_dates_separate_from_acquisition_time():
    source = '独立虚构法源，仅测试'
    payload = dict(title='虚构来源', issuer='虚构发布方', url='https://example.invalid/synthetic',
                   article='测试条款', text_snapshot=source, snapshot_sha256=hashlib.sha256(source.encode()).hexdigest(),
                   promulgated_at='2026-09-01', effective_from='2026-10-01', effective_to=None,
                   jurisdiction='CN', legal_rank='synthetic', fetch_status='fetched', fetched_at=NOW,
                   verification_status='verified', verified_by=U, verified_at=NOW)
    result = domain().AuthorityInput.model_validate(payload)
    assert result.promulgated_at.isoformat() == '2026-09-01'
    assert result.fetched_at.isoformat() == '2026-10-02T02:00:00+00:00'
    payload['fetched_at'] = None
    assert_invalid(domain().AuthorityInput, payload)


@pytest.mark.parametrize('role', ['admin', 'handling_lawyer', 'reviewing_lawyer', 'assistant'])
def test_actor_accepts_only_spec_roles(role):
    actor = domain().Actor.model_validate(dict(user_id=U, roles=[role], session_id=V))
    assert {item.value for item in actor.roles} == {role}


@pytest.mark.parametrize('role', ['intake', 'lawyer', 'reviewer', 'approver', 'query_proposer',
                                  'query_approver', 'query_executor', 'operator'])
def test_actor_rejects_unapproved_role_vocabulary(role):
    assert_invalid(domain().Actor, dict(user_id=U, roles=[role], session_id=V))


FACT_VALUE_CASES = [
    ('text', '0.1000', None, str, '0.1000'),
    ('bool', True, None, bool, True),
    ('integer', 42, 'items', int, 42),
    ('decimal', Decimal('0.1000'), 'CNY', Decimal, Decimal('0.1000')),
    ('date', date(2026, 10, 2), None, date, date(2026, 10, 2)),
    ('datetime', NOW, None, datetime, datetime(2026, 10, 2, 2, tzinfo=timezone.utc)),
    ('null', None, None, type(None), None),
]


@pytest.mark.parametrize('kind,value,unit,want_type,want_value', FACT_VALUE_CASES)
def test_fact_tag_preserves_value_type_through_json_roundtrip(kind, value, unit, want_type, want_value):
    payload = dict(id=U, matter_id=V, version=1, field='synthetic_value', typed_value={'kind': kind, 'value': value},
                   unit=unit, provenance_type='client_statement', anchor_ids=[], receipt_ids=[],
                   confirmation_status='unconfirmed', confirmed_by=None, confirmed_at=None)
    fact = domain().Fact.model_validate(payload)
    restored = domain().Fact.model_validate_json(fact.model_dump_json())
    assert restored.typed_value.kind == kind
    assert type(restored.typed_value.value) is want_type
    assert restored.typed_value.value == want_value
    if kind == 'decimal':
        assert str(restored.typed_value.value) == '0.1000'
        assert restored.unit == 'CNY'
    if kind == 'datetime':
        assert restored.typed_value.value.utcoffset() == timedelta(0)


@pytest.mark.parametrize('kind,value,unit,want_type,want_value', FACT_VALUE_CASES)
def test_fact_decision_tag_preserves_value_type_through_json_roundtrip(kind, value, unit, want_type, want_value):
    decision = domain().FactDecision.model_validate(dict(fact_id=U, decision='corrected',
                                                        confirmed_value={'kind': kind, 'value': value}, reason='虚构更正'))
    restored = domain().FactDecision.model_validate_json(decision.model_dump_json())
    assert restored.confirmed_value.kind == kind
    assert type(restored.confirmed_value.value) is want_type
    assert restored.confirmed_value.value == want_value


@pytest.mark.parametrize('unit', [None, '', '   '])
def test_decimal_fact_requires_explicit_unit(unit):
    payload = dict(id=U, matter_id=V, version=1, field='price', typed_value={'kind': 'decimal', 'value': '0.1'},
                   unit=unit, provenance_type='assumption', anchor_ids=[], receipt_ids=[],
                   confirmation_status='unconfirmed', confirmed_by=None, confirmed_at=None)
    assert_invalid(domain().Fact, payload)


@pytest.mark.parametrize('value', [Decimal('0.1'), '0.1', 1, True, None])
def test_fact_decision_rejects_untagged_values(value):
    assert_invalid(domain().FactDecision, dict(fact_id=U, decision='confirmed', confirmed_value=value, reason='虚构确认'))


@pytest.mark.parametrize('value', [
    {'kind': 'text', 'value': 1},
    {'kind': 'bool', 'value': 1},
    {'kind': 'integer', 'value': True},
    {'kind': 'integer', 'value': 1.1},
    {'kind': 'integer', 'value': '1'},
    {'kind': 'decimal', 'value': 0.1},
    {'kind': 'decimal', 'value': True},
    {'kind': 'decimal', 'value': 'NaN'},
    {'kind': 'date', 'value': '2026-10-02T00:00:00'},
    {'kind': 'datetime', 'value': '2026-10-02T00:00:00'},
    {'kind': 'null', 'value': 'null'},
    {'kind': 'unknown', 'value': '0.1'},
    {'kind': 'text', 'value': 'synthetic', 'run_tool': 'forbidden'},
])
def test_fact_decision_rejects_invalid_tagged_values(value):
    assert_invalid(domain().FactDecision, dict(fact_id=U, decision='confirmed', confirmed_value=value, reason='虚构确认'))


def test_model_request_standard_json_roundtrip_keeps_external_schema_alias():
    context = dict(matter=matter(), document_versions=[], fact_snapshot=dict(version=1, facts=[], sha256=H),
                   position='buyer', rules=[],
                   policy=dict(client_ref='SYNTHETIC-CLIENT', version=1, sha256=H,
                               preferences=[], approved_by=None, approved_at=None),
                   authority_ids=[], allowed_scope=['C01'])
    request = domain().ModelRequest.model_validate(dict(
        operation='synthetic_review', context=context, schema={'type': 'object', 'properties': {}},
        budget_approval_id=None, usage_limit=dict(max_input_tokens=1000, max_output_tokens=1000, max_cost='0', unit='CNY')))
    serialized = request.model_dump_json()
    restored = domain().ModelRequest.model_validate_json(serialized)
    assert restored.output_schema == {'type': 'object', 'properties': {}}
    assert restored.context.matter.id == UUID(U)
    assert 'schema' in json.loads(serialized)
    assert 'output_schema' not in json.loads(serialized)
