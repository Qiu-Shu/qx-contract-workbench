"""Exact independent policy bounds, never a TypeSafe price quotation."""
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, Inexact, Rounded, localcontext
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.judge_policy import copy, total
from cn_contract.security import ServiceError


def policy(**patch):
    fields=dict(policy_id=uuid4(),workspace_id=uuid4(),actor_id=uuid4(),session_id=uuid4(),
        config_sha256='a'*64,permissions=(d.JudgePermission(local_request_id=uuid4(),purpose='primary_intent',input_hash='b'*64),),
        reserved_usd='0.02',max_total_usd='0.04',max_calls=2,
        expires_at=datetime.now(timezone.utc)+timedelta(minutes=5))
    fields.update(patch)
    return d.JudgePolicy(**fields)


@pytest.mark.parametrize('patch',[{'reserved_usd':0.02},{'max_total_usd':True},{'reserved_usd':'0'},
    {'reserved_usd':'0.05'},{'max_calls':True},{'max_calls':0},{'recipient':'https://other.invalid'},
    {'permissions':()},{'expires_at':datetime.now()}])
def test_policy_rejects_inexact_unscoped_or_invalid_approval(patch):
    with pytest.raises(ValueError):policy(**patch)


def test_policy_cannot_have_two_allowances_for_the_same_exact_request_and_purpose():
    first=policy(); permission=first.permissions[0]
    with pytest.raises(ValueError):policy(permissions=(permission,permission.model_copy(update={'input_hash':'c'*64})))


def test_budget_arithmetic_and_validation_ignore_ambient_decimal_rounding():
    original=policy(reserved_usd='0.123456789123',max_total_usd='1')
    with localcontext(Context(prec=2,traps=[Inexact,Rounded])):
        assert copy(d.JudgePolicy,original)==original
        assert total([Decimal('0.123456789123')]*3)==Decimal('0.370370367369')


def test_counterfeit_dto_is_revalidated_with_fixed_error():
    value=policy().model_copy(update={'reserved_usd':'PRIVATE-INVALID'})
    with pytest.raises(ServiceError) as failure:copy(d.JudgePolicy,value)
    assert failure.value.code=='BLOCKED_LIVE' and 'PRIVATE-INVALID' not in str(failure.value)
