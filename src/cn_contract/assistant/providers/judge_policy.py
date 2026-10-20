"""Trusted Jev configuration/grants; neither HTTP nor model output grants access."""
import asyncio
from datetime import datetime, timezone
from decimal import Context, Decimal, localcontext
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from ... import domain as d
from ...config import canonical_json
from ...security import ServiceError
from .jev import JevProvider
from .jev_codec import input_hash, validated_config


def sha(value):
    return sha256(value.encode('utf-8')).hexdigest()


def encoded(value):
    return canonical_json(value.model_dump(mode='json', warnings=False))


def validated(model, value):
    try:
        with localcontext(Context(prec=60)):
            return model.model_validate(value)
    except Exception:
        raise ServiceError('BLOCKED_LIVE', 403) from None


def copy(model, value):
    if type(value) is not model:
        raise ServiceError('BLOCKED_LIVE', 403)
    return validated(model, value.model_dump(mode='python', warnings=False))


def total(values):
    with localcontext(Context(prec=60)):
        return sum(values, Decimal(0))


def require_policy(config, policy, actor, request, *, at=None):
    if (not config.enabled or policy is None or policy.actor_id != actor.user_id
            or policy.session_id != actor.session_id or policy.workspace_id != request.scope.workspace_id
            or policy.config_sha256 != sha(encoded(config))
            or policy.expires_at <= (at or datetime.now(timezone.utc))
            or not any(p.local_request_id == request.local_request_id and p.purpose == request.purpose
                       and p.input_hash == input_hash(request, config) for p in policy.permissions)):
        raise ServiceError('BLOCKED_LIVE', 403)


class JudgeRuntime:
    """Small trusted assembly seam; versions revoke queued work even across ABA."""
    def __init__(self, provider=None, policy=None):
        self._lock = RLock()
        self._loop = None
        self._provider = None; self._config = None; self._policy = None
        self._authorization_id = uuid4(); self._seen = {}
        self.configure(provider)
        if policy is not None:
            self.grant(policy)

    @property
    def provider(self):
        return self._provider

    @property
    def policy(self):
        return self._policy

    def _check_loop(self, *, bind=False):
        try:
            current = asyncio.get_running_loop()
        except RuntimeError:
            current = None
        if self._loop is None:
            if bind:
                if current is None:
                    raise ServiceError('BLOCKED_LIVE', 403)
                self._loop = current
        elif current is not self._loop:
            raise ServiceError('BLOCKED_LIVE', 403)

    def bind_execution(self):
        with self._lock:
            self._check_loop(bind=True)

    def configure(self, provider):
        with self._lock:
            self._check_loop()
            if provider is not None and type(provider) is not JevProvider:
                raise ServiceError('BLOCKED_LIVE', 403)
            try:
                config = validated_config(provider.config) if provider is not None else None
            except ValueError:
                raise ServiceError('BLOCKED_LIVE', 403) from None
            self._provider, self._config, self._policy = provider, config, None
            self._authorization_id = uuid4()

    def grant(self, policy):
        """Publish a validated policy and return its fixed authorization identity."""
        with self._lock:
            self._check_loop()
            policy = copy(d.JudgePolicy, policy)
            config = self.configuration()
            if (not config.enabled or policy.config_sha256 != sha(encoded(config))
                    or policy.expires_at <= datetime.now(timezone.utc)):
                raise ServiceError('BLOCKED_LIVE', 403)
            digest = sha(encoded(policy))
            prior = self._seen.get(policy.policy_id)
            if prior is not None and prior != digest:
                raise ServiceError('VERSION_CONFLICT', 409)
            if self._policy == policy:
                return self._authorization_id
            identity = uuid4()
            self._seen[policy.policy_id] = digest
            self._policy = policy; self._authorization_id = identity
            return identity

    def revoke(self):
        with self._lock:
            self._check_loop()
            self._policy = None; self._authorization_id = uuid4()

    def configuration(self):
        with self._lock:
            self._check_loop()
            try:
                current = validated_config(self._provider.config)
                if current != self._config:
                    raise ValueError()
                return current
            except Exception:
                raise ServiceError('BLOCKED_LIVE', 403) from None

    def snapshot_for(self, actor, request):
        with self._lock:
            actor = copy(d.Actor, actor); request = copy(d.JudgeRequest, request)
            config = self.configuration()
            policy = copy(d.JudgePolicy, self._policy) if self._policy is not None else None
            require_policy(config, policy, actor, request)
            return config, policy, self._authorization_id


def receipt(result, reserved_usd):
    return d.JudgeReceipt(result=result,
        cost_status='not_sent' if result.evidence == 'not_sent' else 'unknown',
        occupied_usd=Decimal(0) if result.evidence == 'not_sent' else reserved_usd)
