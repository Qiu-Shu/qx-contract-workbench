"""Fixed, project-authored Jev questions and bounded response validation.

Local identity/scope participate in the hash but never in the HTTP projection.
No model output authorizes a workflow, data access, or publication.
"""
from hashlib import sha256
import json
import math

from ... import domain as d
from ...config import canonical_json


TEMPLATE_VERSION = 'qx-jev-questions-v1'
_INTENT = {
    'client_reply': '准备给客户的回复和追问',
    'material_organize': '整理材料与资料草稿',
    'contract_review': '准备合同审查意见',
    'content_draft': '准备公开内容草稿',
    'legal_research': '查找法条案例或核对引用',
    'unknown': '没有适合项或无法确定首个流程',
}
_MATERIAL = {
    'contract': '合同或协议材料', 'chat': '聊天或通信记录',
    'transfer': '转账或付款记录', 'judgment': '裁判文书',
    'mixed': '包含多种材料', 'unknown': '无法判断材料类型',
}


def validated_config(value):
    try:
        if type(value) is not d.JevConfig:
            raise ValueError()
        return d.JevConfig.model_validate(value.model_dump(mode='python', warnings=False))
    except Exception:
        raise ValueError('invalid judge configuration') from None


def validated_request(value):
    try:
        if type(value) is not d.JudgeRequest:
            raise ValueError()
        return d.JudgeRequest.model_validate(value.model_dump(mode='python', warnings=False))
    except Exception:
        raise ValueError('invalid judge request') from None


def input_hash(request: d.JudgeRequest, config: d.JevConfig) -> str:
    request = validated_request(request); config = validated_config(config)
    return sha256(canonical_json({'template_version': TEMPLATE_VERSION,
        'request': request.model_dump(mode='json'),
        'config': config.model_dump(mode='json')}).encode('utf-8')).hexdigest()


def build_request(request: d.JudgeRequest, config: d.JevConfig) -> dict:
    request = validated_request(request); config = validated_config(config)
    if request.purpose == 'primary_intent':
        state = {'latest_request': request.text, 'selected_skill': request.explicit_skill}
        question = {'type': 'choice', 'instructions':
            '仅根据 latest_request 建议第一个工作流程。复合需求仍全部保留；无法确定首个流程时选择 unknown。'
            '不要判断事实真伪或授予权限。', 'criteria': dict(_INTENT)}
    elif request.purpose == 'material_kind':
        state = {'material_text': request.text}
        question = {'type': 'choice', 'instructions':
            '仅根据 material_text 提示材料类型。多种材料选择 mixed，无法确定选择 unknown。'
            '保留全部原文，不判断真实性、证明力或案件归属。', 'criteria': dict(_MATERIAL)}
    else:
        state = {'public_draft': request.text}
        question = {'type': 'noul', 'instructions':
            'public_draft 是否出现向读者保证案件结果的表述？只给复核提示，不作合规结论。'}
    body = {'model': config.model, 'state': state, 'questions': {request.purpose: question}}
    try:
        if len(canonical_json(body).encode('utf-8')) > config.max_input_bytes:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError('invalid judge request') from None
    return body


class _PrivateReflection(ValueError):
    pass


def _strict_json(raw, secret):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError()
            output[key] = value
        return output

    def constant(_):
        raise ValueError()

    value = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=pairs,
                       parse_constant=constant)
    if type(value) is not dict:
        raise ValueError()
    todo = [(value, 0)]; nodes = 0
    while todo:
        item, depth = todo.pop(); nodes += 1
        if depth > 32 or nodes > 20000:
            raise ValueError()
        if type(item) is dict:
            todo.extend((part, depth + 1) for pair in item.items() for part in pair)
        elif type(item) is list:
            todo.extend((part, depth + 1) for part in item)
        elif type(item) is float and not math.isfinite(item):
            raise ValueError()
        elif type(item) is str:
            item.encode('utf-8', errors='strict')
            if secret and secret in item:
                raise _PrivateReflection()
    return value


def _identifier(value, secret):
    if (type(value) is str and value.strip() and len(value) <= 256
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value)
            and not (secret and secret in value)):
        try:
            value.encode('utf-8', errors='strict')
            return value
        except UnicodeError:
            pass
    return None


def decode_response(raw: bytes, request: d.JudgeRequest, config: d.JevConfig,
                    provider_request_id=None, secret='') -> dict:
    """Return safe parsed fields; invalid answers never discard validated usage."""
    result = {'answers': {}, 'usage': None,
              'provider_request_id': _identifier(provider_request_id, secret),
              'model': None, 'reason_code': 'invalid_response'}
    try:
        request = validated_request(request); config = validated_config(config)
        if type(raw) is not bytes or len(raw) > config.max_response_bytes:
            return result
        value = _strict_json(raw, secret)
    except _PrivateReflection:
        return {'answers': {}, 'usage': None, 'provider_request_id': None, 'model': None,
                'reason_code': 'provider_error'}
    except (ValueError, TypeError, RecursionError):
        return result
    try:
        if value.get('model') == config.model:
            result['model'] = config.model
        if type(value.get('usage')) is not dict:
            return result
        result['usage'] = d.JudgeUsage.model_validate(value['usage'])
        if set(value) != {'model', 'answers', 'usage'} or value['model'] != config.model:
            return result
        answers = value['answers']
        if type(answers) is not dict or set(answers) != {request.purpose}:
            return result
        answer = answers[request.purpose]
        if type(answer) is not dict:
            return result
        if request.purpose == 'possible_result_guarantee':
            if answer.get('type') != 'noul':
                return result
            parsed = d.JudgeNoul.model_validate(answer)
        else:
            if answer.get('type') != 'choice':
                return result
            parsed = d.JudgeChoice.model_validate(answer)
            expected = _INTENT if request.purpose == 'primary_intent' else _MATERIAL
            if set(parsed.probabilities) != set(expected):
                return result
        result.update(answers={request.purpose: parsed}, reason_code=None)
    except (ValueError, KeyError, TypeError):
        pass
    return result
