"""Offline arithmetic/evidence gate for synthetic outputs and trusted curated plans.

Source substring matches bind a plan to text; they do NOT prove its interpretation.
This module neither extracts plans from models nor changes answers or authorizes use.
Reports are engineering dictionaries, not new business DTOs.
"""
from decimal import Decimal
import operator

from cn_contract.acceptance.contract_scoring import fingerprint
from cn_contract.domain import CalculationInput, RoundingSpec, SafeExpression
from cn_contract.facts.calculate import calculate_expression

VERSION = 'curated-calculation-gate-v1'
RELATIONS = {'eq': operator.eq, 'gt': operator.gt, 'ge': operator.ge,
             'lt': operator.lt, 'le': operator.le}
UNITS = {'CNY', 'ratio', 'percent'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _fields(value, names):
    _require(isinstance(value, dict) and set(value) == set(names.split()), 'invalid fields')


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 16000


def _list(value, limit=256, empty=False):
    _require(isinstance(value, list) and (0 if empty else 1) <= len(value) <= limit, 'invalid list')
    return value


def _ids(value, empty=False):
    _list(value, empty=empty)
    _require(all(_text(v) for v in value) and len(value) == len(set(value)), 'invalid ids')
    return set(value)


def _bounded(value):
    """Reject cycles, oversized trees and non-JSON values before hashing or parsing."""
    stack, count, chars = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        count += 1
        _require(count <= 30000 and depth <= 64, 'JSON tree exceeds limit')
        if isinstance(item, dict):
            _require(len(item) <= 512 and all(isinstance(k, str) for k in item), 'invalid object')
            stack.extend((v, depth + 1) for v in item.values())
            stack.extend((k, depth + 1) for k in item)
        elif isinstance(item, list):
            _require(len(item) <= 512, 'array exceeds limit')
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, str):
            chars += len(item)
            _require(len(item) <= 16000 and chars <= 1000000, 'text exceeds limit')
        else:
            _require(item is None or type(item) in (bool, int), 'non-exact JSON scalar')
            if type(item) is int:
                _require(item.bit_length() <= 512, 'integer exceeds limit')


def _number(value):
    _require(isinstance(value, str) and 0 < len(value) <= 140, 'decimal string required')
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError('invalid decimal') from exc
    _require(result.is_finite(), 'finite decimal required')
    _require(len(result.as_tuple().digits) <= 128 and abs(result.as_tuple().exponent) <= 128
             and abs(result.adjusted()) <= 128, 'decimal exceeds limit')
    return result


def _ast(ast):
    stack, count = [(ast, 1)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        _require(count <= 128 and depth <= 32 and isinstance(node, dict), 'invalid bounded AST')
        kind = node.get('kind')
        if kind == 'literal':
            _fields(node, 'kind value')
            _require(_number(node['value']) in (Decimal(0), Decimal(1), Decimal(100)), 'unbound literal')
        elif kind == 'variable':
            _fields(node, 'kind name')
            _require(_text(node['name']), 'variable name required')
        elif kind == 'binary':
            _fields(node, 'kind operator left right')
            _require(isinstance(node['operator'], str) and node['operator'] in
                     {'add', 'subtract', 'multiply', 'divide'}, 'invalid operator')
            stack.extend([(node['left'], depth + 1), (node['right'], depth + 1)])
        else:
            raise ValueError('unknown AST kind')


def _case_sources(case):
    _bounded(case)
    _require(isinstance(case, dict) and _text(case.get('id')), 'case id required')
    anchors, claims = {}, {}
    for item in _list(case.get('anchors')):
        _fields(item, 'id quote')
        _require(_text(item['id']) and _text(item['quote']) and item['id'] not in anchors, 'invalid anchor')
        anchors[item['id']] = item['quote']
    for item in _list(case.get('checks'), 64):
        _fields(item, 'id claim')
        _require(_text(item['id']) and _text(item['claim']) and item['id'] not in claims, 'invalid claim')
        claims[item['id']] = item['claim']
    return anchors, claims


def _comparison(comp, claim, anchors, options):
    _fields(comp, 'formula inputs rounding assumptions bindings relation target')
    _fields(comp['formula'], 'ast unit')
    _ast(comp['formula']['ast'])
    _require(isinstance(comp['formula']['unit'], str) and comp['formula']['unit'] in UNITS, 'unsupported unit')
    _fields(comp['rounding'], 'mode quantum')
    _require(_number(comp['rounding']['quantum']) > 0, 'positive rounding quantum required')
    assumptions = _list(comp['assumptions'], 32)
    _require(all(_text(a) for a in assumptions), 'explicit assumptions required')
    inputs, values = [], {}
    for item in _list(comp['inputs'], 32):
        _fields(item, 'name value unit fact_ids')
        _require(_text(item['name']) and item['name'] not in values and item['fact_ids'] == []
                 and isinstance(item['unit'], str) and item['unit'] in UNITS, 'invalid offline input')
        values[item['name']] = _number(item['value'])
        inputs.append(CalculationInput.model_validate(item))
    bindings = comp['bindings']
    _require(isinstance(bindings, dict) and set(bindings) == set(values), 'all inputs need bindings')
    for locations in bindings.values():
        valid = set()
        for loc in _list(locations, 32):
            _fields(loc, 'id text')
            _require(_text(loc['id']) and loc['id'] in anchors and _text(loc['text'])
                     and loc['text'] in anchors[loc['id']], 'binding does not match source')
            valid.add(loc['id'])
        _require(all(option & valid for option in options), 'evidence option omits a variable')
    target = comp['target']
    _fields(target, 'value unit location text')
    number = _number(target['value'])
    _require(target['unit'] == comp['formula']['unit'], 'target unit mismatch')
    _require(_text(target['location']) and _text(target['text']), 'target source required')
    target_source = claim if target['location'] == 'claim' else anchors.get(target['location'], '')
    _require(target['text'] in target_source, 'target does not match source')
    if target['location'] != 'claim':
        _require(all(target['location'] in option for option in options), 'target evidence missing')
    _require(isinstance(comp['relation'], str) and comp['relation'] in RELATIONS, 'invalid comparison')
    try:
        result = calculate_expression(SafeExpression.model_validate(comp['formula']), values,
                                      inputs=tuple(inputs), rounding=RoundingSpec.model_validate(comp['rounding']),
                                      assumptions=tuple(assumptions))
    except (ArithmeticError, ValueError) as exc:
        raise ValueError('curated calculation invalid') from exc
    return {'value': str(result.value), 'unit': result.unit, 'relation': comp['relation'],
            'target': str(number), 'comparison_holds': RELATIONS[comp['relation']](result.value, number),
            'precision_limited': '中间运算达到有限Decimal精度，不能视为无限精确值' in result.assumptions,
            'assumptions': list(result.assumptions)}


def _plan_calculations(case, plan, anchors, claims):
    if plan is None:
        return {}
    _bounded(plan)
    _fields(plan, 'case_sha256 checks')
    _require(plan['case_sha256'] == fingerprint(case), 'case fingerprint mismatch')
    computed = {}
    for check in _list(plan['checks'], 64, empty=True):
        _fields(check, 'id claim_quote comparisons evidence_options')
        cid = check['id']
        _require(_text(cid) and cid in claims and cid not in computed and
                 check['claim_quote'] == claims[cid], 'claim binding mismatch')
        options = [_ids(ids) for ids in _list(check['evidence_options'], 32)]
        _require(all(ids <= anchors.keys() for ids in options), 'unknown evidence anchor')
        calculations = [_comparison(comp, claims[cid], anchors, options)
                        for comp in _list(check['comparisons'], 16)]
        computed[cid] = (calculations, options)
    return computed


def _answer_checks(answer, anchors, claims):
    _bounded(answer)
    _fields(answer, 'examined_anchor_ids formal_signoff legal_status checks')
    _require(answer['formal_signoff'] is False and answer['legal_status'] == 'not_verified', 'unsafe status')
    _require(_ids(answer['examined_anchor_ids']) == anchors.keys(), 'source coverage incomplete')
    checks = {}
    for check in _list(answer['checks'], 64):
        _fields(check, 'id verdict citations explanation')
        cid = check['id']
        _require(_text(cid) and cid in claims and cid not in checks and _text(check['explanation'])
                 and isinstance(check['verdict'], str) and check['verdict'] in
                 {'supported', 'refuted', 'not_stated'}, 'invalid check')
        seen = set()
        for citation in _list(check['citations'], empty=True):
            _fields(citation, 'id quote')
            aid = citation['id']
            _require(_text(aid) and aid in anchors and aid not in seen and
                     citation['quote'] == anchors[aid], 'invalid citation')
            seen.add(aid)
        checks[cid] = (check['verdict'], seen)
    _require(checks.keys() == claims.keys(), 'check coverage incomplete')
    return checks


def check_calculations(case, answer, plan=None):
    """Raise ValueError for invalid trusted inputs; report bad model answers as blocked.

    math_stage_passed concerns ONLY planned checks. Even if true, narrative semantics,
    unplanned checks, plan interpretation and legal review remain unverified.
    """
    anchors, claims = _case_sources(case)
    computed = _plan_calculations(case, plan, anchors, claims)
    errors, answer_hash = [], None
    try:
        _bounded(answer)
        answer_hash = fingerprint(answer)
        checks = _answer_checks(answer, anchors, claims)
    except ValueError:
        errors, checks = ['answer_schema'], {}
    reports = {}
    for cid in claims:
        if cid not in computed:
            reports[cid] = {'status': 'not_covered', 'errors': [], 'calculations': []}
            continue
        calculations, options = computed[cid]
        verdict = 'supported' if all(c['comparison_holds'] for c in calculations) else 'refuted'
        problems = list(errors)
        if any(c['precision_limited'] for c in calculations):
            problems.append('calculation_precision_limited')
            verdict = None
        if cid in checks:
            observed, cited = checks[cid]
            if verdict is not None and observed != verdict:
                problems.append('verdict_mismatch')
            if not any(option <= cited for option in options):
                problems.append('evidence_incomplete')
        reports[cid] = {'status': 'blocked' if problems else 'consistent', 'errors': problems,
                        'computed_verdict': verdict, 'calculations': calculations}
    return {'version': VERSION, 'case_id': case['id'], 'case_sha256': fingerprint(case),
            'answer_sha256': answer_hash, 'plan_sha256': fingerprint(plan), 'checks': reports,
            'errors': errors, 'covered_checks': len(computed),
            'math_stage_passed': bool(computed) and not errors and all(
                reports[cid]['status'] == 'consistent' for cid in computed),
            'manual_review_required': True, 'reasoning_status': 'pending_manual_review',
            'promotion_allowed': False}
