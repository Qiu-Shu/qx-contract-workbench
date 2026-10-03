"""Bounded Decimal AST interpreter. No expression strings, calls, eval or exec."""
from decimal import Decimal, DecimalException, Context, Inexact, Rounded, localcontext
from ..domain import (SafeExpression, LiteralExpression, VariableExpression, BinaryExpression,
    CalculationInput, RoundingSpec, CalculationResult)
from ..persistence import read_matter, get_fact_snapshot
from ..security import ServiceError

_MAX_NODES = 128
_MAX_DEPTH = 32
_PRECISION = 512


def _decimal(value, *, input_value=False):
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError('finite Decimal required')
    digits = len(value.as_tuple().digits)
    bound = 128 if input_value else _PRECISION
    if digits > bound or abs(value.as_tuple().exponent)>bound or (value and abs(value.adjusted())>bound):
        raise ValueError('Decimal resource limit')
    return value


def _inspect(ast):
    stack = [(ast,1)]
    names = set()
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count>_MAX_NODES or depth>_MAX_DEPTH:
            raise ValueError('AST resource limit')
        if isinstance(node,LiteralExpression):
            _decimal(node.value,input_value=True)
        elif isinstance(node,VariableExpression):
            names.add(node.name)
        elif isinstance(node,BinaryExpression):
            stack.extend(((node.left,depth+1),(node.right,depth+1)))
        else:
            raise ValueError('only approved AST nodes accepted')
    return names


def _unit(unit):
    return {} if unit=='ratio' else {unit:1}


def calculate_expression(expr, values, *, inputs=None, rounding=None, assumptions=(),
                         matter_id=None, fact_version=None, actor=None, db=None):
    """Interpret approved AST and round only the complete result.

    128 nodes / depth 32 / 128 input digits / 512 working digits / integer
    powers [-100,100]. Unit-bearing products/quotients require an explicit
    caller assumption describing their business interpretation.
    Bare mathematics records unbound-source and caller-declared-unit limits.
    """
    if not isinstance(expr,SafeExpression):
        raise ValueError('SafeExpression required')
    _inspect(expr.ast)  # bound traversal before recursive serialization/validation
    expr = SafeExpression.model_validate(expr.model_dump(mode='python'))
    names = _inspect(expr.ast)
    if type(values) is not dict or set(values)!=names:
        raise ValueError('exact referenced variables required')
    values = {name:_decimal(value,input_value=True) for name,value in values.items()}
    notes = tuple(assumptions)
    if any(type(note) is not str or not note.strip() for note in notes):
        raise ValueError('nonempty assumptions required')
    explicit_inputs = inputs is not None
    metadata = tuple(CalculationInput.model_validate(i.model_dump(mode='python')) for i in (inputs or ()))
    if explicit_inputs:
        if len({i.name for i in metadata})!=len(metadata) or {i.name for i in metadata}!=names:
            raise ValueError('metadata must match variable names exactly')
        for item in metadata:
            _decimal(item.value,input_value=True)
            if item.value != values[item.name] or len(set(item.fact_ids))!=len(item.fact_ids):
                raise ValueError('metadata value/IDs inconsistent')
    else:
        metadata = tuple(CalculationInput(name=n,value=values[n],unit='unspecified',fact_ids=()) for n in sorted(names))
    bound = [i for i in metadata if i.fact_ids]
    if bound:
        if matter_id is None or db is None or actor is None:
            raise ValueError('fact binding requires explicit authorized case context')
        matter = read_matter(matter_id,actor,db)
        version = matter.active_fact_version if fact_version is None else fact_version
        if type(version) is not int or version<1 or version>(matter.active_fact_version or 0):
            raise ServiceError('FACTS_UNCONFIRMED',409)
        snapshot = get_fact_snapshot(matter_id,version,actor,db)
        facts = {f.id:f for f in snapshot.facts}
        for item in bound:
            for identifier in item.fact_ids:
                fact = facts.get(identifier)
                if (fact is None or fact.matter_id!=matter_id or fact.version!=version
                    or fact.confirmation_status not in {'confirmed','corrected'}
                    or fact.typed_value.kind!='decimal' or fact.unit!=item.unit
                    or fact.typed_value.value!=item.value):
                    raise ServiceError('FACTS_UNCONFIRMED',409)
        notes += (f'输入事实快照版本{version}，sha256={snapshot.sha256}',)
    if not metadata or any(not i.fact_ids for i in metadata):
        notes += ('未绑定全部已确认事实；数学结果不能直接作为合同结论；输出单位由调用者声明',)
    rounding = (RoundingSpec(mode='ROUND_HALF_EVEN',quantum='0.01' if expr.unit=='CNY' else '0.00000001')
        if rounding is None else RoundingSpec.model_validate(rounding.model_dump(mode='python')))
    _decimal(rounding.quantum,input_value=True)
    units = {i.name:_unit(i.unit) for i in metadata}

    def compute(node):
        if isinstance(node,LiteralExpression):
            return node.value, {}
        if isinstance(node,VariableExpression):
            return values[node.name], units[node.name]
        left,lu = compute(node.left)
        right,ru = compute(node.right)
        op = node.operator
        if op in {'add','subtract'}:
            if explicit_inputs and lu!=ru:
                raise ValueError('addition/subtraction requires matching units')
            result = left+right if op=='add' else left-right
            unit = lu
        elif op in {'multiply','divide'}:
            if op=='divide' and not right:
                raise ValueError('division by zero')
            if explicit_inputs and (lu or ru) and not assumptions:
                raise ValueError('unit-bearing multiplication/division requires explicit interpretation')
            result = left*right if op=='multiply' else left/right
            unit = dict(lu)
            for name,power in ru.items():
                unit[name] = unit.get(name,0)+power*(1 if op=='multiply' else -1)
            unit = {name:power for name,power in unit.items() if power}
            # Unit conversion is explicit arithmetic, never a relabel. Percent
            # -> ratio is /100; ratio -> percent is a final *100 operation.
            hundred_right = isinstance(node.right,LiteralExpression) and right==100
            hundred_left = isinstance(node.left,LiteralExpression) and left==100
            if explicit_inputs and op=='divide' and lu=={'percent':1} and hundred_right:
                unit = {}
            elif (explicit_inputs and op=='multiply' and node is expr.ast and expr.unit=='percent'
                  and not lu and not ru and (hundred_right or hundred_left)):
                if not assumptions:
                    raise ValueError('percent conversion requires explicit interpretation')
                unit = {'percent':1}
        elif op=='power':
            if ru or right != right.to_integral_value() or abs(right)>100 or (not left and right<=0):
                raise ValueError('bounded integer exponent required; zero power invalid')
            if explicit_inputs and lu and not assumptions:
                raise ValueError('unit-bearing power requires explicit interpretation')
            exponent = int(right)
            result = left**exponent
            unit = {name:power*exponent for name,power in lu.items() if power*exponent}
        else:
            raise ValueError('unsupported operator')
        return _decimal(result),unit

    try:
        with localcontext(Context(prec=_PRECISION,rounding='ROUND_HALF_EVEN',Emax=1024,Emin=-1024)) as context:
            context.clear_flags()
            value,result_unit = compute(expr.ast)
            if explicit_inputs and names and result_unit!=_unit(expr.unit):
                raise ValueError('output unit does not match input dimensional arithmetic')
            limited = context.flags[Inexact] or context.flags[Rounded]
            # quantum is a true step (including 0.05), not a decimal-place hint.
            value = (value/rounding.quantum).to_integral_value(rounding=rounding.mode)*rounding.quantum
            _decimal(value)
    except DecimalException:
        raise ValueError('Decimal calculation blocked') from None
    notes += (f'Decimal工作精度{_PRECISION}位；最终按{rounding.quantum}步长舍入',)
    if limited:
        notes += ('中间运算达到有限Decimal精度，不能视为无限精确值',)
    return CalculationResult(value=value,unit=expr.unit,formula=expr,inputs=metadata,rounding=rounding,assumptions=notes)


def payment_base_facts(matter_id, *, actor, db, fact_version=None):
    """Return the confirmed amount AND period evidence; never annual/12."""
    matter = read_matter(matter_id,actor,db)
    version = matter.active_fact_version if fact_version is None else fact_version
    if type(version) is not int or version<1 or version>(matter.active_fact_version or 0):
        raise ServiceError('FACTS_UNCONFIRMED',409)
    snapshot = get_fact_snapshot(matter_id,version,actor,db)
    paid = [f for f in snapshot.facts if f.field=='prior_month_actual_paid']
    periods = [f for f in snapshot.facts if f.field=='prior_month_actual_paid_period']
    if len(paid)!=1 or len(periods)!=1:
        raise ServiceError('FACTS_UNCONFIRMED',409)
    amount,period = paid[0],periods[0]
    if (any(f.confirmation_status not in {'confirmed','corrected'} for f in (amount,period))
        or amount.typed_value.kind!='decimal' or amount.unit!='CNY' or amount.typed_value.value<0
        or period.typed_value.kind not in {'text','date'} or not period.typed_value.value):
        raise ServiceError('FACTS_UNCONFIRMED',409)
    _decimal(amount.typed_value.value,input_value=True)
    return amount,period


def payment_base_input(matter_id, *, actor, db, fact_version=None):
    """Numeric input convenience; preserve payment_base_facts period for review."""
    amount,_ = payment_base_facts(matter_id,actor=actor,db=db,fact_version=fact_version)
    return CalculationInput(name='prior_month_actual_paid',value=amount.typed_value.value,unit=amount.unit,fact_ids=(amount.id,))


def notice_direction(event, shorter, longer, *, unit):
    """Factual directional observation only; no risk rank or legal threshold."""
    if unit!='calendar_day' or type(shorter) is not int or type(longer) is not int or not 0<=shorter<longer:
        raise ValueError('ordered natural-calendar-day periods required')
    if event=='customer_nonrenewal':
        return 'shorter_customer_notice'
    if event=='supplier_price_change':
        return 'shorter_customer_response_window'
    raise ValueError('explicit notice obligor/event required')
