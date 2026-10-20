"""Trusted private-pipe Jev configuration; configuration never grants egress."""
from uuid import uuid4

from .. import domain as d
from ..security import ServiceError
from .providers.jev import JevProvider
from .providers.judge_policy import copy, encoded, sha, validated


class NativeJudgeControl:
    def __init__(self, runtime, provider_factory=None):
        self._runtime = runtime
        self._provider_factory = provider_factory or JevProvider
        self._config_version = None

    def configure(self, payload):
        self._runtime.bind_execution()
        try:
            data = payload.model_dump(mode='python', warnings=False) if type(payload) is d.NativeJudgeConfigure else payload
            value = validated(d.NativeJudgeConfigure, data)
            provider = self._provider_factory(value.config, lambda secret=value.secret: secret)
            if copy(d.JevConfig, provider.config) != value.config:
                raise ServiceError('BLOCKED_LIVE', 403)
            version = uuid4()
            result = {'status': 'configured', 'config_sha256': sha(encoded(value.config)),
                      'config_version': str(version)}
            self._runtime.configure(provider)
            self._config_version = version
            return result
        except ServiceError:
            raise
        except Exception:
            raise ServiceError('BLOCKED_LIVE', 403) from None

    def disable(self):
        self._runtime.bind_execution()
        self._runtime.configure(None)
        self._config_version = None
        return {'status': 'disabled'}
