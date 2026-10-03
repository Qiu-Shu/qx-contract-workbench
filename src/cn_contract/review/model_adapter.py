"""Static local model registry. Document text never selects tools or providers.

Mock token counts are explicit UTF-8 byte accounting units, not estimates of a
real vendor tokenizer or hidden model version. Cost is zero mock credits.
"""
from decimal import Decimal
import hashlib
import json
import re
from typing import Protocol
from uuid import uuid4
from weakref import WeakKeyDictionary

from ..domain import ModelRequest, ModelResponse, ModelUsage
from ..security import ServiceError

MAX_RAW_BYTES = 262144
MODEL = 'local-deterministic-v1'
_REGISTRY = WeakKeyDictionary()


class ModelProvider(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse: ...


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def strict_json(raw):
    if type(raw) is not str or len(raw.encode('utf-8')) > MAX_RAW_BYTES:
        raise ValueError('bounded raw text required')
    try:
        value = json.loads(raw, object_pairs_hook=_unique,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON depth/number') from exc
    if type(value) is not dict:
        raise ValueError('JSON object required')
    # json parses 1e999 as inf without parse_constant.
    stack=[(value,0)]
    while stack:
        item,depth=stack.pop()
        if depth>64:
            raise ValueError('JSON depth exceeds 64')
        if isinstance(item,float) and not Decimal(str(item)).is_finite():
            raise ValueError('nonfinite JSON')
        if isinstance(item,dict):
            stack.extend((v,depth+1) for v in item.values())
        if isinstance(item,list):
            stack.extend((v,depth+1) for v in item)
    return value


def provider_capabilities():
    return {'shell':False,'files':False,'qcc':False,'network':False}


def require_provider(model):
    # No duck typing, subclasses, instance method overrides or provider labels.
    if type(model) is not MockProvider or model not in _REGISTRY:
        raise ServiceError('DATA_POLICY_UNAPPROVED',409)
    return _REGISTRY[model]


def model_configuration(model):
    state = require_provider(model)
    return {'provider':'mock','model':MODEL,'token_accounting':'UTF-8 bytes',
        'cost':'0','unit':'mock_credit','tools':provider_capabilities(),
        'raw_script_sha256':[hashlib.sha256(x.encode()).hexdigest() for x in state['raw']],
        'statuses':list(state['statuses'])}


class RawOutputError(ValueError):
    def __init__(self, raw, usage, status='success'):
        super().__init__('MODEL_OUTPUT_INVALID')
        self.raw = raw
        self.usage = usage
        self.status = status


def candidates(package):
    """Small exact synthetic intake vocabulary; no guessed values or dates."""
    result=[]
    patterns=[('total_price',r'价款[：:]\s*([0-9]+(?:\.[0-9]+)?)元','CNY'),
        ('addendum_price',r'附件金额[：:]\s*([0-9]+(?:\.[0-9]+)?)元','CNY'),
        ('payment_ratio',r'付款比例[：:]\s*([0-9]+(?:\.[0-9]+)?)%','percent')]
    for anchor in package['anchors']:
        for field,pattern,unit in patterns:
            for match in re.finditer(pattern,anchor['quote']):
                suffix=str(len([f for f in result if f['field'].startswith(field)])+1)
                result.append({'field':field+'_'+suffix if field=='payment_ratio' else field,
                    'typed_value':{'kind':'decimal','value':match.group(1)},'unit':unit,
                    'provenance_type':'document','anchor_ids':[anchor['id']],'receipt_ids':[]})
    if not result and package['anchors']:
        result.append({'field':'synthetic_material_label','typed_value':{'kind':'text','value':package['anchors'][0]['quote']},
            'unit':None,'provenance_type':'document','anchor_ids':[package['anchors'][0]['id']],'receipt_ids':[]})
    return result


class MockProvider:
    __slots__ = ('__weakref__',)

    def __init__(self, *, raw_outputs=(), statuses=()):
        if type(raw_outputs) is not tuple or any(type(x) is not str for x in raw_outputs):
            raise ValueError('static raw text tuple required')
        if type(statuses) is not tuple or any(x not in ('success','failed','sent_unknown','blocked') for x in statuses):
            raise ValueError('static status tuple required')
        _REGISTRY[self]={'raw':raw_outputs,'statuses':statuses,'index':0,'last':None}

    def generate(self, request: ModelRequest) -> ModelResponse:
        state = require_provider(self)
        request = ModelRequest.model_validate_json(request.model_dump_json())
        if request.operation not in ('extract_facts','review_chunk','review_cross_clauses'):
            raise ServiceError('NOT_SUPPORTED',409)
        package=request.output_schema['x-input']
        index=state['index'];state['index']+=1
        payload={'examined_anchor_ids':[a['id'] for a in package['anchors']],
            'facts':candidates(package) if request.operation=='extract_facts' else [],'observations':[]}
        raw=state['raw'][index] if index<len(state['raw']) else json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        status=state['statuses'][index] if index<len(state['statuses']) else 'success'
        usage=ModelUsage(provider='mock',model=MODEL,operation=request.operation,request_id=str(uuid4()),
            input_tokens=len(request.model_dump_json().encode()),output_tokens=len(raw.encode()),cost=Decimal('0'),unit='mock_credit')
        state['last']=(raw,usage,status)
        try:
            parsed=strict_json(raw)
        except ValueError:
            raise RawOutputError(raw,usage,status) from None
        return ModelResponse(payload=parsed,usage=usage,provider='mock',model=MODEL,request_id=usage.request_id,status=status)


def dispatch(model,request):
    require_provider(model)
    # Class-owned function prevents an object's generate attribute replacing code.
    return MockProvider.generate(model,request)


def last_attempt(model):
    return require_provider(model)['last']
