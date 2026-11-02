"""Rejection diagnostics must locate a failure without carrying private material.

Every assertion here is about closed vocabularies: the helper may name fields and error
kinds, but it must never echo model-supplied text or field names back out.
"""

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.assistant.providers.deepseek_protocol import rejected_detail, rejection_reason
from cn_contract.security import ServiceError


CITATION = 'a' * 64
PRIVATE_FIELD = 'secret_material_body'
PRIVATE_VALUE = 'PRIVATE-SYNTHETIC-BODY-110101199001011234'


def payload(**overrides):
    """Minimal fictional candidate source; overrides replace single fields."""
    value = {'text': '合成待核草稿', 'citations': (CITATION,)}
    value.update(overrides)
    return value


def test_string_too_long_on_text_names_the_field_and_the_kind():
    with pytest.raises(ValidationError) as caught:
        d.MainMaterialCandidate.model_validate(payload(text='合' * 20001))
    assert rejected_detail(caught.value) == ('text', 'string_too_long')


def test_model_invented_extra_field_is_reduced_to_other():
    with pytest.raises(ValidationError) as caught:
        d.MainMaterialCandidate.model_validate(payload(**{PRIVATE_FIELD: PRIVATE_VALUE}))
    fields, kinds = rejected_detail(caught.value)
    assert fields == 'other'
    assert 'extra_forbidden' in kinds.split('|')
    assert all(PRIVATE_FIELD not in part and PRIVATE_VALUE not in part for part in (fields, kinds))


def test_several_complaints_are_joined_so_the_real_cause_is_visible():
    with pytest.raises(ValidationError) as caught:
        d.MainMaterialCandidate.model_validate(payload(text='合' * 20001, citations=('not-a-hash',)))
    fields, kinds = rejected_detail(caught.value)
    assert set(fields.split('|')) == {'text', 'citations'}
    assert 'string_too_long' in kinds.split('|')
    assert 'string_pattern_mismatch' in kinds.split('|')


def test_identical_complaints_on_one_field_collapse_to_a_single_pair():
    with pytest.raises(ValidationError) as caught:
        d.MainMaterialCandidate.model_validate(payload(citations=('not-a-hash', 'also-not-a-hash')))
    fields, kinds = rejected_detail(caught.value)
    assert set(fields.split('|')) == {'citations'}
    assert kinds.split('|').count('string_pattern_mismatch') == 1


def test_known_business_code_is_the_error_kind_only():
    assert rejected_detail(ValueError('CONTRACT_QUOTE_INVALID')) == ('other', 'CONTRACT_QUOTE_INVALID')


def test_service_error_exposes_only_its_whitelisted_code():
    assert rejected_detail(ServiceError('VERSION_CONFLICT', 409)) == ('other', 'VERSION_CONFLICT')
    assert rejected_detail(ServiceError('PRIVATE_SYNTHETIC_CODE', 409)) == ('other', 'other')


def test_unknown_exception_text_never_reaches_the_detail():
    message = '客户身份证号110101199001011234'
    fields, kinds = rejected_detail(ValueError(message))
    assert (fields, kinds) == ('other', 'other')
    assert all(message not in part for part in (fields, kinds))


def test_rejection_reason_maps_quote_reference_and_method_codes():
    assert rejection_reason('candidate', ValueError('CASE_EVIDENCE_QUOTE_INVALID')) == 'quotes'
    assert rejection_reason('candidate', ValueError('TRADEMARK_METHOD_INVALID')) == 'method'
    assert rejection_reason('candidate', ValueError('HEARING_OUTPUT_INVALID')) == 'schema'


def test_missing_citations_is_located_at_the_citations_field():
    with pytest.raises(ValidationError) as caught:
        d.MainMaterialCandidate.model_validate(payload(citations=()))
    fields, kinds = rejected_detail(caught.value)
    assert fields == 'citations'
    assert kinds != 'other'
