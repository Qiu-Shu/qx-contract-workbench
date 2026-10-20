"""Native Jev configuration is local, independent and never an egress grant."""
import asyncio
from datetime import datetime, timedelta, timezone
import gc
import subprocess
import sys
import weakref
from uuid import UUID, uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers.judge_policy import JudgeRuntime
from cn_contract.assistant.native_judge_control import NativeJudgeControl
from cn_contract.assistant.providers.jev import JevProvider
from cn_contract.security import ServiceError


SECRET = 'SYNTHETIC_TYPESAFE_NATIVE_TOKEN_ONLY'


def test_configuration_returns_only_safe_new_identity_and_never_grants():
    runtime = JudgeRuntime()
    control = NativeJudgeControl(runtime)
    async def scenario():
        config = d.JevConfig(enabled=True)
        first = control.configure({'config': config, 'secret': SECRET})
        assert set(first) == {'status', 'config_sha256', 'config_version'}
        assert first['status'] == 'configured' and len(first['config_sha256']) == 64
        assert str(UUID(first['config_version'])) == first['config_version']
        assert runtime.configuration() == config and runtime.policy is None
        second = control.configure({'config': config, 'secret': SECRET})
        assert second['config_sha256'] == first['config_sha256']
        assert second['config_version'] != first['config_version']
        assert runtime.policy is None and SECRET not in repr(first)
        assert control.disable() == {'status': 'disabled'}
        assert runtime.provider is None and runtime.policy is None
    asyncio.run(scenario())


def policy(config_sha256):
    return d.JudgePolicy(policy_id=uuid4(), workspace_id=uuid4(), actor_id=uuid4(), session_id=uuid4(),
        config_sha256=config_sha256, permissions=(d.JudgePermission(local_request_id=uuid4(),
            purpose='primary_intent', input_hash='a'*64),), reserved_usd='0.01', max_total_usd='0.01',
        max_calls=1, expires_at=datetime.now(timezone.utc)+timedelta(minutes=1))


@pytest.mark.parametrize('change', [
    {'secret': 'short'}, {'secret': 'x'*513}, {'secret': ' x'*20}, {'secret': 'x'*20+'\n'},
    {'secret': 'x'*20+'\x00'}, {'secret': '汉'*20}, {'secret': 1234567890123456},
    {'config': {'enabled': 'true'}}, {'config': {'enabled': True, 'model': 'other'}},
    {'config': {'enabled': True, 'endpoint': 'https://untrusted.invalid'}},
    {'config': {'enabled': True, 'timeout_ms': 2001}}, {'url': 'https://untrusted.invalid'},
], ids=['short', 'long', 'space', 'newline', 'nul', 'unicode', 'number',
        'coercion', 'model', 'endpoint', 'deadline', 'extra-field'])
def test_invalid_configuration_is_fixed_error_and_preserves_current_identity(change):
    runtime = JudgeRuntime()
    control = NativeJudgeControl(runtime)
    async def scenario():
        payload = {'config': {'enabled': True}, 'secret': SECRET}
        first = control.configure(payload)
        runtime.grant(policy(first['config_sha256']))
        current, permission = runtime.provider, runtime.policy
        with pytest.raises(ServiceError) as failure:
            control.configure({**payload, **change})
        assert failure.value.code == 'BLOCKED_LIVE'
        assert str(failure.value) == 'request not authorized'
        assert runtime.provider is current and runtime.policy == permission
        control.disable()
    asyncio.run(scenario())


def test_replacement_and_disable_clear_grants_and_release_retired_providers():
    runtime = JudgeRuntime()
    control = NativeJudgeControl(runtime)
    async def scenario():
        first = control.configure({'config': {'enabled': True}, 'secret': SECRET})
        runtime.grant(policy(first['config_sha256']))
        old = weakref.ref(runtime.provider)
        second = control.configure({'config': {'enabled': True}, 'secret': SECRET+'REPLACED'})
        gc.collect()
        assert old() is None and runtime.policy is None
        assert first['config_version'] != second['config_version']
        current = weakref.ref(runtime.provider)
        runtime.grant(policy(second['config_sha256']))
        control.disable(); gc.collect()
        assert current() is None and runtime.policy is None
        assert control.disable() == {'status': 'disabled'}
    asyncio.run(scenario())


def test_control_requires_the_same_running_loop_including_runtime_mutations():
    runtime = JudgeRuntime()
    control = NativeJudgeControl(runtime)
    with pytest.raises(ServiceError): control.disable()
    async def scenario():
        control.configure({'config': {'enabled': True}, 'secret': SECRET})
        current = runtime.provider
        def wrong_thread():
            for action in (control.disable, lambda: runtime.configure(None)):
                with pytest.raises(ServiceError): action()
        await asyncio.to_thread(wrong_thread)
        assert runtime.provider is current
        control.disable()
    asyncio.run(scenario())
    async def other_loop():
        with pytest.raises(ServiceError):
            control.configure({'config': {'enabled': True}, 'secret': SECRET})
        with pytest.raises(ServiceError): control.disable()
    asyncio.run(other_loop())


@pytest.mark.parametrize('failure', ['exception', 'changed-config', 'wrong-provider'])
def test_factory_failure_is_sanitized_and_does_not_replace_valid_configuration(failure):
    runtime = JudgeRuntime()
    fail = False
    def factory(config, resolver):
        if fail:
            if failure == 'exception': raise RuntimeError(SECRET)
            if failure == 'wrong-provider': return object()
            config = config.model_copy(update={'timeout_ms': 1000})
        return JevProvider(config, resolver)
    control = NativeJudgeControl(runtime, provider_factory=factory)
    async def scenario():
        nonlocal fail
        control.configure({'config': {'enabled': True}, 'secret': SECRET})
        current = runtime.provider
        fail = True
        with pytest.raises(ServiceError) as error:
            control.configure({'config': {'enabled': True}, 'secret': SECRET+'NEW'})
        assert error.value.code == 'BLOCKED_LIVE' and SECRET not in str(error.value)
        assert runtime.provider is current
        control.disable()
    asyncio.run(scenario())


def test_secret_is_not_in_dto_repr_and_configuration_cold_path_loads_no_http_client():
    value = d.NativeJudgeConfigure(config=d.JevConfig(), secret=SECRET)
    assert SECRET not in repr(value)
    code = '''import asyncio, sys
from cn_contract.assistant.providers.judge_policy import JudgeRuntime
from cn_contract.assistant.native_judge_control import NativeJudgeControl
assert 'httpx2' not in sys.modules
async def check():
 control = NativeJudgeControl(JudgeRuntime())
 control.configure({'config': {'enabled': True}, 'secret': 'SYNTHETIC_COLD_JUDGE_TOKEN_ONLY'})
 control.disable()
 assert 'httpx2' not in sys.modules
asyncio.run(check())
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ''
