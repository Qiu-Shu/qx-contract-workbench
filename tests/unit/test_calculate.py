"""Decimal and bounded AST tests, using independently derived expected values."""
from decimal import Decimal, getcontext, localcontext, Inexact
from uuid import uuid4
import pytest
from cn_contract.domain import SafeExpression, CalculationInput, RoundingSpec, FactDecision
from test_facts import api, store, candidate


def lit(v): return {'kind':'literal','value':str(v)}
def var(n): return {'kind':'variable','name':n}
def binary(op,l,r): return {'kind':'binary','operator':op,'left':l,'right':r}
def expr(ast,unit='ratio'): return SafeExpression(ast=ast,unit=unit)
def calculate(*args,**kwargs): return api('calculate','calculate_expression')(*args,**kwargs)


def test_compound_monthly():
    result=calculate(expr(binary('subtract',binary('power',lit('1.02'),lit(12)),lit(1))),{},
        rounding=RoundingSpec(mode='ROUND_HALF_EVEN',quantum='0.00000001'),
        assumptions=('月利率2%，12期，按月复利有效年化数学口径；未判断法律效力',))
    assert result.value == Decimal('0.26824179') and result.unit=='ratio'
    assert any('月利率2%' in s for s in result.assumptions)
    exact=calculate(expr(binary('subtract',binary('power',lit('1.02'),lit(12)),lit(1))),{},
        rounding=RoundingSpec(mode='ROUND_HALF_EVEN',quantum='0.000000000000000000000001'))
    assert exact.value==Decimal('0.268241794562545318301696')
    assert any('未绑定' in s for s in exact.assumptions)


def test_payment_base_missing(tmp_path):
    payment=api('calculate','payment_base_input')
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    confirm=api('confirm','confirm_facts')
    with database.session() as db:
        confirm(matter.id,1,[FactDecision(fact_id=snap.facts[0].id,decision='confirmed',
            confirmed_value=snap.facts[0].typed_value,reason='synthetic')],actor,db=db)
        with pytest.raises(s.ServiceError) as e: payment(matter.id,actor=actor,db=db)
        assert e.value.code=='FACTS_UNCONFIRMED'


def test_renewal_direction():
    observe=api('calculate','notice_direction')
    assert observe('customer_nonrenewal',15,90,unit='calendar_day')=='shorter_customer_notice'
    assert observe('supplier_price_change',15,90,unit='calendar_day')=='shorter_customer_response_window'
    with pytest.raises(ValueError): observe('customer_nonrenewal',15,90,unit='working_hour')


def test_quantum_is_step_and_final_rounding():
    assert calculate(expr(lit('1.03'),'CNY'),{},rounding=RoundingSpec(mode='ROUND_HALF_UP',quantum='0.05')).value==Decimal('1.05')
    assert calculate(expr(binary('add',lit('0.004'),lit('0.004')),'CNY'),{},
        rounding=RoundingSpec(mode='ROUND_HALF_UP',quantum='0.01')).value==Decimal('0.01')


def test_long_decimal_and_context_unchanged():
    before=getcontext().copy()
    result=calculate(expr(binary('add',lit('123456789012345678901234567890.12'),lit('0.01')),'CNY'),{})
    assert result.value==Decimal('123456789012345678901234567890.13')
    assert getcontext().prec==before.prec and getcontext().rounding==before.rounding


@pytest.mark.parametrize('ast,values',[ (binary('divide',lit(1),lit(0)),{}),
    (binary('power',lit(0),lit(0)),{}),(binary('power',lit(2),lit('0.5')),{}),
    (binary('power',lit(2),lit(10001)),{}),(var('missing'),{}),(lit(1),{'extra':Decimal(2)}),
    (var('x'),{'x':1.2}),(var('x'),{'x':Decimal('Infinity')}),(var('x'),{'x':Decimal('1e10000')})])
def test_unsafe_math_rejected(ast,values):
    with pytest.raises(ValueError): calculate(expr(ast),values)


def test_model_copy_unknown_ast_and_depth_rejected():
    with pytest.raises(ValueError): calculate(expr(lit(1)).model_copy(update={'ast':{'kind':'call','name':'system'}}),{})
    ast=lit(1)
    for _ in range(40): ast=binary('add',ast,lit(1))
    with pytest.raises(ValueError): calculate(expr(ast),{})


def test_metadata_and_units_rejected():
    expression=expr(binary('add',var('a'),var('b')),'CNY')
    for inputs in [(CalculationInput(name='a',value='2',unit='CNY',fact_ids=()),),
        (CalculationInput(name='a',value='1',unit='CNY',fact_ids=()),CalculationInput(name='b',value='2',unit='USD',fact_ids=()))]:
        with pytest.raises(ValueError): calculate(expression,{'a':Decimal(1),'b':Decimal(2)},inputs=inputs)


def test_bound_input_requires_confirmed_values(tmp_path):
    p,s,database,actor,matter,parsed,snap=store(tmp_path)
    fact=snap.facts[0]
    inputs=[CalculationInput(name='a',value='1200',unit='CNY',fact_ids=(fact.id,))]
    with database.session() as db:
        with pytest.raises(s.ServiceError): calculate(expr(var('a'),'CNY'),{'a':Decimal(1200)},inputs=inputs,matter_id=matter.id,actor=actor,db=db)
        api('confirm','confirm_facts')(matter.id,1,[FactDecision(fact_id=fact.id,decision='confirmed',confirmed_value=fact.typed_value,reason='synthetic')],actor,db=db)
        result=calculate(expr(var('a'),'CNY'),{'a':Decimal(1200)},inputs=inputs,matter_id=matter.id,actor=actor,db=db)
        assert result.inputs[0].fact_ids==(fact.id,)
        with pytest.raises(s.ServiceError): calculate(expr(var('a'),'CNY'),{'a':Decimal(1200)},inputs=[inputs[0].model_copy(update={'fact_ids':(uuid4(),)})],matter_id=matter.id,actor=actor,db=db)


def test_actual_zero_payment_has_confirmed_period(tmp_path):
    from test_facts import setup
    from cn_contract.domain import FactSnapshot
    payment=api('calculate','payment_base_input')
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    with database.session() as db:
        facts=api('extract','build_fact_candidates')(parsed,{'facts':[
            candidate(parsed,field='prior_month_actual_paid',value='0'),
            candidate(parsed,field='prior_month_actual_paid_period',typed_value={'kind':'text','value':'2026-09'},unit=None)]},matter_id=matter.id,version=1,actor=actor,db=db)
        p.save_fact_snapshot(matter.id,FactSnapshot(version=1,facts=tuple(facts),sha256=p.fact_snapshot_sha256(facts)),actor,db)
        api('confirm','confirm_facts')(matter.id,1,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,reason='synthetic') for f in facts],actor,db=db)
        result=payment(matter.id,actor=actor,db=db)
        assert result.value==Decimal(0) and result.unit=='CNY' and result.fact_ids==(facts[0].id,)


def test_unit_bearing_products_require_interpretation():
    inputs=[CalculationInput(name='base',value='100',unit='CNY',fact_ids=()),CalculationInput(name='rate',value='0.2',unit='ratio',fact_ids=())]
    expression=expr(binary('multiply',var('base'),var('rate')),'CNY')
    with pytest.raises(ValueError): calculate(expression,{'base':Decimal(100),'rate':Decimal('0.2')},inputs=inputs)
    assert calculate(expression,{'base':Decimal(100),'rate':Decimal('0.2')},inputs=inputs,assumptions=('金额乘明确比例，仅数学口径',)).value==Decimal('20')


def test_percent_conversion_requires_explicit_hundred():
    inputs=[CalculationInput(name='r',value='0.26824179',unit='ratio',fact_ids=())]
    with pytest.raises(ValueError): calculate(expr(var('r'),'percent'),{'r':Decimal('0.26824179')},inputs=inputs)
    result=calculate(expr(binary('multiply',var('r'),lit(100)),'percent'),{'r':Decimal('0.26824179')},inputs=inputs,
        assumptions=('ratio显式乘100转percent，数学口径',))
    assert result.value==Decimal('26.824179')
    reverse=[CalculationInput(name='p',value='2',unit='percent',fact_ids=())]
    assert calculate(expr(binary('divide',var('p'),lit(100)),'ratio'),{'p':Decimal(2)},inputs=reverse,
        assumptions=('percent显式除100转ratio',)).value==Decimal('0.02')


def test_payment_period_evidence_is_available(tmp_path):
    evidence=api('calculate','payment_base_facts')
    from test_facts import setup
    from cn_contract.domain import FactSnapshot
    p,s,database,actor,matter,parsed=setup(tmp_path)
    api('storage','initialize_storage')(database)
    with database.session() as db:
        facts=api('extract','build_fact_candidates')(parsed,{'facts':[
            candidate(parsed,field='prior_month_actual_paid',value='0'),
            candidate(parsed,field='prior_month_actual_paid_period',typed_value={'kind':'text','value':'2026-09'},unit=None)]},matter_id=matter.id,version=1,actor=actor,db=db)
        p.save_fact_snapshot(matter.id,FactSnapshot(version=1,facts=tuple(facts),sha256=p.fact_snapshot_sha256(facts)),actor,db)
        api('confirm','confirm_facts')(matter.id,1,[FactDecision(fact_id=f.id,decision='confirmed',confirmed_value=f.typed_value,reason='synthetic') for f in facts],actor,db=db)
        amount,period=evidence(matter.id,actor=actor,db=db)
        assert amount.typed_value.value==0 and period.typed_value.value=='2026-09'
        assert period.anchor_ids==facts[1].anchor_ids and period.confirmation_status=='confirmed'


def test_decimal_global_traps_do_not_change_server_math():
    with localcontext() as caller:
        caller.prec=6
        caller.rounding='ROUND_FLOOR'
        caller.traps[Inexact]=True
        result=calculate(expr(binary('divide',lit(1),lit(3))),{})
        assert result.value==Decimal('0.33333333')
        assert caller.prec==6 and caller.rounding=='ROUND_FLOOR' and caller.traps[Inexact]
