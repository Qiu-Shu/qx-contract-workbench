"""Explicit unlimited grants preserve finite historical policy bytes."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from cn_contract import domain as d
from cn_contract.assistant.providers.policy import budget_exceeded, encoded, sha
from cn_contract.config import canonical_json


def policy_data():
    return dict(policy_id=str(UUID(int=1)), workspace_id=str(UUID(int=2)),
        actor_id=str(UUID(int=3)), config_sha256='a'*64, allowed_content_sha256s=['b'*64],
        max_total_usd='1.00', max_calls=1, expires_at='2999-01-01T00:00:00Z')


def test_finite_policy_roundtrip_retains_canonical_bytes_and_hash():
    data = policy_data()
    historical = canonical_json(data)
    restored = d.MainModelPolicy.model_validate_json(historical)
    assert encoded(restored) == historical
    assert sha(encoded(restored)) == sha(historical)
    assert restored.max_total_usd == Decimal('1.00')
    assert budget_exceeded(Decimal('1.000001'), restored.max_total_usd)


def test_null_is_required_explicitly_and_preserves_all_other_grant_limits():
    data = policy_data()
    data['max_total_usd'] = None
    policy = d.MainModelPolicy.model_validate(data)
    assert '"max_total_usd":null' in encoded(policy)
    assert not budget_exceeded(Decimal('1000000000'), policy.max_total_usd)
    assert policy.max_calls == 1 and policy.expires_at > datetime.now(timezone.utc)
    del data['max_total_usd']
    with pytest.raises(ValidationError):
        d.MainModelPolicy.model_validate(data)


@pytest.mark.parametrize('budget', ['0', '-1', 'NaN', 'Infinity', 0.1, True])
def test_invalid_finite_limits_are_not_treated_as_unlimited(budget):
    with pytest.raises(ValidationError):
        d.MainModelPolicy.model_validate({**policy_data(), 'max_total_usd': budget})
