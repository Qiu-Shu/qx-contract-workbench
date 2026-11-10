"""Shared DeepSeek envelope; callers validate their own candidate sources."""
from decimal import Context, localcontext
from hashlib import sha256
import json
import logging
import math
import re
from unicodedata import category

from pydantic import ValidationError

from ... import domain as d
from ...config import canonical_json


_logger = logging.getLogger(__name__)


_LOGGED_FIELDS = d.MAIN_REJECTION_FIELDS
_LOGGED_ERROR_TYPES = d.MAIN_REJECTION_ERROR_TYPES
_LOGGED_CODES = d.MAIN_REJECTION_CODES


def rejection_reason(stage, error):
    # Only fixed identifiers cross the receipt boundary, never exception text or inputs.
    if stage != 'candidate':
        return {'usage':'usage', 'choice':'completion', 'message':'message',
                'content_json':'json'}.get(stage, 'envelope')
    code = error.args[0] if error.args and type(error.args[0]) is str else ''
    return {'CONTRACT_QUOTE_INVALID':'quotes', 'CONTRACT_REFERENCE_INVALID':'references',
            'CONTRACT_STANCE_INVALID':'stance', 'CONTRACT_COVERAGE_INVALID':'coverage',
            'CONTRACT_METHOD_INVALID':'method', 'MODEL_USAGE_INVALID':'usage',
            'CASE_EVIDENCE_QUOTE_INVALID':'quotes', 'CASE_EVIDENCE_INLINE_INVALID':'quotes',
            'TRADEMARK_QUOTE_INVALID':'quotes', 'CRIMINAL_QUOTE_INVALID':'quotes',
            'CASE_EVIDENCE_FACT_SOURCE_INVALID':'references',
            'TRADEMARK_REFERENCE_INVALID':'references', 'CRIMINAL_REFERENCE_INVALID':'references',
            'TRADEMARK_METHOD_INVALID':'method', 'CASE_METHOD_INVALID':'method',
            'CRIMINAL_METHOD_INVALID':'method'}.get(code, 'schema')


def rejected_detail(error):
    """Return (fields, kinds) from closed vocabularies, joined in complaint order.

    The first three distinct complaints are kept: a lone leading error can point at a
    field that is merely unexpected while the real cause sits one entry later.
    """
    if isinstance(error, ValidationError):
        pairs = []
        for item in error.errors()[:3]:
            loc = item.get('loc') or ()
            name = next((part for part in loc
                         if isinstance(part, str) and part in _LOGGED_FIELDS), 'other')
            kind = item.get('type')
            pair = (name, kind if kind in _LOGGED_ERROR_TYPES else 'other')
            if pair not in pairs:
                pairs.append(pair)
        if not pairs:
            return 'other', 'other'
        return '|'.join(pair[0] for pair in pairs), '|'.join(pair[1] for pair in pairs)
    # ServiceError keeps its fixed code as an attribute; args[0] is a generic sentence.
    code = getattr(error, 'code', None)
    if type(code) is not str:
        code = error.args[0] if error.args and type(error.args[0]) is str else ''
    return 'other', code if code in _LOGGED_CODES else 'other'


def rejection_diagnostic(stage, error):
    """Persist only bounded source-defined paths and kinds, never exception inputs."""
    issues = []
    if isinstance(error, ValidationError):
        for item in error.errors(include_input=False, include_context=False, include_url=False):
            path = tuple(part if part in _LOGGED_FIELDS else 'other'
                         for part in (item.get('loc') or ()) if isinstance(part, str))[:6] or ('other',)
            kind = item.get('type')
            issue = d.MainRejectionIssue(path=path, kind=kind if kind in _LOGGED_ERROR_TYPES else 'other')
            if issue not in issues:
                issues.append(issue)
            if len(issues) == 3:
                break
    if not issues:
        _, kind = rejected_detail(error)
        issues.append(d.MainRejectionIssue(path=('other',), kind=kind))
    return d.MainRejectionDiagnostic(stage=stage, issues=tuple(issues))


def candidate_json(content, secret):
    # Accept only a complete JSON code block; never extract, repair or merge model text.
    fenced = re.fullmatch(r'\s*```(?:json)?\r?\n(.*?)\r?\n```\s*', content, re.DOTALL)
    return strict_json(fenced.group(1) if fenced else content, secret)


def unvalidated_response(content, secret):
    """Retain a bounded literal response, never reasoning, tools or secret reflection."""
    try:
        raw = content.encode('utf-8')
        escaped = re.sub(r'\\u([0-9a-fA-F]{4})', lambda match: chr(int(match[1], 16)), content)
        if (not raw or len(raw) > 8388608 or secret and (secret in content or secret in escaped)
                or any(category(char) in {'Cc', 'Cf', 'Cs'} and char not in '\t\r\n' for char in content)):
            return None
        lower, upper = 0, min(len(content), d.UNVALIDATED_RESPONSE_MAX_JSON_BYTES)
        while lower < upper:
            middle = (lower + upper + 1) // 2
            if len(json.dumps(content[:middle], ensure_ascii=False).encode('utf-8')) <= d.UNVALIDATED_RESPONSE_MAX_JSON_BYTES:
                lower = middle
            else:
                upper = middle - 1
        return d.MainUnvalidatedResponse(text=content[:lower], truncated=lower < len(content),
            original_utf8_bytes=len(raw), sha256=sha256(raw).hexdigest())
    except (ValueError, UnicodeError):
        return None


def json_bytes(value):
    return canonical_json(value).encode('utf-8')


def configuration(value):
    if type(value) is not d.MainModelConfig:
        raise ValueError('validated main configuration required')
    with localcontext(Context(prec=60)):
        return d.MainModelConfig.model_validate(value.model_dump(mode='python'))


class PrivateReflection(ValueError):
    pass


def strict_json(raw, secret=''):
    def pairs(items):
        output={}
        for key,value in items:
            if key in output:raise ValueError('duplicate JSON key')
            output[key]=value
        return output
    def constant(_):raise ValueError('nonfinite JSON number')
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
    if type(value) is not dict:raise ValueError('JSON object required')
    todo=[(value,0)];nodes=0
    while todo:
        item,depth=todo.pop();nodes+=1
        if depth>32 or nodes>20000:raise ValueError('JSON resource bound')
        if type(item) is dict:todo.extend((part,depth+1) for pair in item.items() for part in pair)
        elif type(item) is list:todo.extend((part,depth+1) for part in item)
        elif type(item) is float and not math.isfinite(item):raise ValueError('nonfinite number')
        elif type(item) is str and secret and secret in item:raise PrivateReflection()
    return value


def _usage(value):
    if value is None:return None
    if type(value) is not dict:raise ValueError('usage object required')
    fields=('prompt_tokens','completion_tokens','total_tokens',
            'prompt_cache_hit_tokens','prompt_cache_miss_tokens')
    usage=d.MainUsage.model_validate({name:value[name] for name in fields if name in value})
    for name,field,expected in (
            ('prompt_tokens_details','cached_tokens',usage.prompt_cache_hit_tokens),
            ('completion_tokens_details','reasoning_tokens',0)):
        details=value.get(name)
        if details is not None:
            if type(details) is not dict:raise ValueError('usage detail object required')
            if field in details:
                count=details[field]
                if type(count) is not int or count<0 or (expected is not None and count!=expected):
                    raise ValueError('usage detail mismatch')
                if name=='prompt_tokens_details' and count>usage.prompt_tokens:
                    raise ValueError('cache count exceeds input')
    return usage


def decode_response(raw, config, secret, *, parse_candidate, reply_type):
    identifier=None;usage=None
    try:
        value=strict_json(raw,secret)
        identifier=value['id']
        if (type(identifier) is not str or not identifier.strip() or len(identifier)>256
                or any(ord(c)<32 for c in identifier) or value['model']!=config.model
                or value['object']!='chat.completion' or type(value['created']) is not int
                or value['created']<0):
            raise ValueError('response identity mismatch')
    except PrivateReflection:
        return reply_type(state='received',error_code='PROVIDER_ERROR')
    except (ValueError,KeyError,TypeError,RecursionError) as error:
        _logger.warning('model_response_rejected stage=envelope')
        return reply_type(state='received',error_code='MODEL_OUTPUT_INVALID',rejection_reason='envelope',
                          rejection_diagnostic=rejection_diagnostic('envelope', error))
    stage='usage'
    try:
        usage=_usage(value.get('usage'))
        if usage is not None and (usage.prompt_tokens>config.max_input_bytes
                or usage.completion_tokens>config.max_output_tokens):
            raise ValueError('reported usage exceeds request caps')
        stage='choice'
        choices=value['choices']
        if type(choices) is not list or len(choices)!=1:raise ValueError('single choice required')
        choice=choices[0]
        if (type(choice) is not dict or type(choice['index']) is not int or choice['index']!=0
                or choice.get('logprobs') is not None):
            raise ValueError('incomplete or unsupported response')
        if choice['finish_reason']=='length':
            _logger.warning('model_response_rejected stage=choice')
            return reply_type(state='received',provider_request_id=identifier,usage=usage,
                              error_code='MODEL_OUTPUT_TRUNCATED')
        if choice['finish_reason']!='stop':
            raise ValueError('incomplete or unsupported response')
        stage='message'
        message=choice['message']
        if (type(message) is not dict or message['role']!='assistant'
                or type(message['content']) is not str or not message['content'].strip()
                or message.get('tool_calls') not in (None,[])
                or message.get('reasoning_content') not in (None,'')):
            raise ValueError('unsupported message')
        stage='content_json'
        content=candidate_json(message['content'],secret)
        stage='candidate'
        candidate=parse_candidate(content)
        if isinstance(candidate, d.MainContextToolPlan):
            return reply_type(state='received',provider_request_id=identifier,usage=usage,
                              tool_plan=candidate)
        return reply_type(state='received',provider_request_id=identifier,usage=usage,output=candidate)
    except PrivateReflection:
        return reply_type(state='received',error_code='PROVIDER_ERROR')
    except (ValueError,KeyError,TypeError,RecursionError) as error:
        # Fixed stages, fields and error kinds only: exception details and response text
        # can contain private data, so both detail values come from closed vocabularies.
        field,kind=rejected_detail(error)
        _logger.warning('model_response_rejected stage=%s field=%s error=%s',stage,field,kind)
        return reply_type(state='received',provider_request_id=identifier,usage=usage,
                           error_code='MODEL_OUTPUT_INVALID',rejection_reason=rejection_reason(stage,error),
                           rejection_diagnostic=rejection_diagnostic(stage,error),
                           unvalidated_response=unvalidated_response(message['content'], secret)
                               if stage in {'content_json', 'candidate'} else None)
