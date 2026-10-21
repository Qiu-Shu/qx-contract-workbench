"""Shared DeepSeek envelope; callers validate their own candidate sources."""
from decimal import Context, localcontext
import json
import math

from ... import domain as d
from ...config import canonical_json


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
    except (ValueError,KeyError,TypeError,RecursionError):
        return reply_type(state='received',error_code='MODEL_OUTPUT_INVALID')
    try:
        usage=_usage(value.get('usage'))
        if usage is not None and (usage.prompt_tokens>config.max_input_bytes
                or usage.completion_tokens>config.max_output_tokens):
            raise ValueError('reported usage exceeds request caps')
        choices=value['choices']
        if type(choices) is not list or len(choices)!=1:raise ValueError('single choice required')
        choice=choices[0]
        if (type(choice) is not dict or type(choice['index']) is not int or choice['index']!=0
                or choice['finish_reason']!='stop' or choice.get('logprobs') is not None):
            raise ValueError('incomplete or unsupported response')
        message=choice['message']
        if (type(message) is not dict or message['role']!='assistant'
                or type(message['content']) is not str or not message['content'].strip()
                or message.get('tool_calls') not in (None,[])
                or message.get('reasoning_content') not in (None,'')):
            raise ValueError('unsupported message')
        candidate=parse_candidate(strict_json(message['content'],secret))
        return reply_type(state='received',provider_request_id=identifier,usage=usage,output=candidate)
    except PrivateReflection:
        return reply_type(state='received',error_code='PROVIDER_ERROR')
    except (ValueError,KeyError,TypeError,RecursionError):
        return reply_type(state='received',provider_request_id=identifier,usage=usage,
                           error_code='MODEL_OUTPUT_INVALID')
