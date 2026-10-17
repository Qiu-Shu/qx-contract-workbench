"""Trusted runtime policy; neither model data nor HTTP input creates grants."""
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
import hashlib

from ... import domain as d
from ...config import canonical_json
from ...security import ServiceError
from .main import build_request


def sha(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def encoded(value):
    return canonical_json(value.model_dump(mode='json'))


class MainModelRuntime:
    def __init__(self, provider, policy=None):
        self.provider = provider
        self.policy = policy

    def snapshot(self):
        config = validated(d.MainModelConfig, self.provider.config.model_dump(mode='python'))
        policy = (validated(d.MainModelPolicy, self.policy.model_dump(mode='python'))
                  if self.policy is not None else None)
        return config, policy


def validated(model, data):
    with localcontext(Context(prec=60)):
        return model.model_validate(data)


def require_policy(config, policy, actor, scope, source_hash):
    if (not config.enabled or policy is None or policy.actor_id != actor.user_id
            or policy.workspace_id != scope.workspace_id or policy.config_sha256 != sha(encoded(config))
            or policy.expires_at <= datetime.now(timezone.utc)
            or source_hash not in policy.allowed_content_sha256s):
        raise ServiceError('BLOCKED_LIVE', 403)


def prepare(request, config):
    payload = canonical_json(build_request(request, config))
    return d.MainPreparedInput(request=request, wire_payload_json=payload)


def reservation(config):
    return estimated_cost(config.max_input_bytes, config.max_output_tokens, config)


def estimated_cost(prompt_tokens, completion_tokens, config):
    # DTO limits bound all operands; never inherit caller precision or traps.
    with localcontext(Context(prec=60)):
        return (Decimal(prompt_tokens)*config.input_usd_per_million
                + Decimal(completion_tokens)*config.output_usd_per_million)/Decimal(1000000)


def add_costs(values):
    with localcontext(Context(prec=60)):
        return sum(values, Decimal(0))


def receipt(reply, config):
    cost = None
    status = 'unknown'
    if reply.state == 'failed_before_send':
        cost, status = Decimal(0), 'not_sent'
    elif reply.usage is not None:
        cost = estimated_cost(reply.usage.prompt_tokens, reply.usage.completion_tokens, config)
        status = 'estimated'
    with localcontext(Context(prec=60)):
        return d.MainReceipt(state=reply.state, provider_request_id=reply.provider_request_id,
            usage=reply.usage, cost_status=status, estimated_cost_usd=cost, error_code=reply.error_code)
