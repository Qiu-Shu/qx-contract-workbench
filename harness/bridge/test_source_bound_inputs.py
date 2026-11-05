import pytest
from pydantic import ValidationError

from source_bound_inputs import LitigationBrief, ComplianceTracking


def test_calculation_index_is_visible_at_brief_level_and_not_an_amount():
    schema = LitigationBrief.model_json_schema()
    assert 'calculation_index' in schema['properties']
    assert set(schema['$defs']['Money']['required']) == {'citation', 'amount'}
    with pytest.raises(ValidationError, match='claim_amount'):
        LitigationBrief.model_validate({'claim_amount': {'calculation_index': 0}})
    with pytest.raises(ValidationError, match='calculation_index'):
        LitigationBrief.model_validate({'calculation_index': True})
    assert LitigationBrief.model_validate({'calculation_index': 0}).model_dump(exclude_none=True) == {
        'claim_kind': 'undetermined', 'calculation_index': 0}


def test_tracking_schema_exposes_date_basis_and_rejects_model_status():
    valid = {'as_of': '2026-11-05', 'as_of_entry': 0,
             'deadlines': [{'entry': 1, 'date': '2026-11-10', 'year_basis': 'explicit'}]}
    assert ComplianceTracking.model_validate(valid).model_dump() == valid
    with pytest.raises(ValidationError, match='submitted'):
        ComplianceTracking.model_validate({**valid, 'submitted': True})
