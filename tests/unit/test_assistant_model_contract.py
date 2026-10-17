from decimal import Decimal, Inexact, localcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cn_contract import domain as d


def test_main_configuration_is_disabled_and_prices_are_exact():
    config = d.MainModelConfig(model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='synthetic-test-ceiling')
    assert config.enabled is False
    assert config.input_usd_per_million == Decimal('0.3')
    with pytest.raises(ValidationError):
        d.MainModelConfig(model='deepseek-flash', input_usd_per_million=0.3,
            output_usd_per_million='1.2', price_reference='synthetic-test-ceiling')


def test_usage_has_a_bounded_exact_accounting_range():
    with pytest.raises(ValidationError):
        d.MainUsage(prompt_tokens=2**31, completion_tokens=0, total_tokens=2**31)


def test_cost_arithmetic_is_independent_of_callers_decimal_context():
    from cn_contract.assistant.providers.policy import receipt, reservation
    config=d.MainModelConfig(model='deepseek-flash',input_usd_per_million='0.3',
        output_usd_per_million='1.2',price_reference='synthetic-ceiling')
    reply=d.MainReply(state='received',usage=d.MainUsage(prompt_tokens=12345,completion_tokens=1000,total_tokens=13345),
        error_code='MODEL_OUTPUT_INVALID')
    with localcontext() as context:
        context.prec=3
        context.traps[Inexact]=True
        assert reservation(config) == Decimal('0.024576')
        assert receipt(reply,config).estimated_cost_usd == Decimal('0.0049035')
