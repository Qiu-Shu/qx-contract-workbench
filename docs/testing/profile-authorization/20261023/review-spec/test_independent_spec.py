"""Prepared before code freeze; independent synthetic registry contract probes."""
import asyncio
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_codec, profile_preparation, registry as registry_module
from cn_contract.assistant.providers.deepseek_protocol import json_bytes
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.security import ServiceError


ROOT = Path(__file__).resolve().parents[3]
BASELINE = '60eb041536dc36dfd4133f0d09b909681146500c'


class SyntheticProvider:
    def __init__(self, config):
        self.config = config
        self.calls = []
        self.hook = lambda: None

    async def generate(self, request, *, expected_config=None):
        raise AssertionError('plain generation must not be used')

    async def generate_profile(self, request, *, expected_config=None, preflight=None):
        self.calls.append((request, expected_config, callable(preflight)))
        # Deliberately ignore preflight: wrapper must police a late response itself.
        self.hook()
        return d.MainProfileReply(state='received', provider_request_id='synthetic-profile-receipt',
            usage=d.MainUsage(prompt_tokens=7, completion_tokens=3, total_tokens=10),
            output=d.MainProfileCandidate(text='完全合成的待核回答', profile_patch=d.ProfilePatch(
                scope=request.scope, base_profile_revision=request.base_profile_revision)))


def prepare(world, basis):
    request = d.MainProfileRequest(run_id=world.run_id, message_id=world.message_id,
        scope=basis.expected_scope.model_copy(update={'input_revision': basis.expected_scope.input_revision + 1}),
        content=world.message.content, source_sha256=sha(world.message.content), source_revision=1,
        base_profile_revision=basis.base_profile_revision)
    return d.MainProfilePreparedInput(request=request, basis=basis,
        composer_revision=basis.expected_composer_revision + 1,
        wire_payload_json=json_bytes(profile_codec.build_request(request, world.config)).decode())


def policy_for(world, basis):
    return d.MainModelPolicy(policy_id=uuid4(), workspace_id=basis.expected_scope.workspace_id,
        actor_id=world.actor.user_id, config_sha256=sha(encoded(world.config)),
        allowed_content_sha256s=(profile_preparation.basis_digest(basis),), max_total_usd='1', max_calls=1,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1))


@pytest.fixture
def world():
    config = d.MainModelConfig(enabled=True, model='deepseek-flash', input_usd_per_million='0.3',
        output_usd_per_million='1.2', price_reference='independent synthetic review rates')
    actor = d.Actor(user_id=uuid4(), session_id=uuid4(), roles=frozenset())
    scope = d.ScopeSnapshot(workspace_id=uuid4(), conversation_id=uuid4(), binding_revision=1,
        input_revision=0, materials_revision=0)
    message = d.AssistantMessageInput(request_id=uuid4(), expected_scope=scope,
        expected_composer_revision=4, content='完全合成：甲自称已付款35000元，尚待核实。')
    basis = profile_preparation.build_basis(message, config, base_profile_revision=2,
        expected_intake_id=uuid4(), expected_intake_revision=1, project_intake=False)
    result = SimpleNamespace(config=config, actor=actor, message=message, basis=basis,
        run_id=uuid4(), message_id=uuid4(), provider=SyntheticProvider(config), registry=MainModelRegistry())
    result.policy = policy_for(result, basis)
    result.prepared = prepare(result, basis)
    return result


def grant(world, *, basis=None, policy=None):
    world.registry.configure(world.provider)
    world.registry.grant(policy or world.policy, world.actor.session_id, basis=basis or world.basis)
    return world.registry.resolve(world.actor, world.prepared.request.scope)


def test_valid_profile_wrapper_passes_exact_prepared_request_once(world):
    async def scenario():
        lease = grant(world)
        result = await lease.provider.generate_profile(world.prepared, expected_config=world.config)
        assert result.output is not None and result.usage.total_tokens == 10
        assert world.provider.calls == [(world.prepared.request, world.config, True)]
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['project', 'target', 'intake_revision', 'profile_revision'])
def test_identical_wire_does_not_authorize_a_different_local_save_plan(world, change):
    values = dict(base_profile_revision=2, expected_intake_id=world.basis.expected_intake_id,
        expected_intake_revision=1, project_intake=False)
    values.update({'project': {'project_intake': True}, 'target': {'expected_intake_id': uuid4()},
        'intake_revision': {'expected_intake_revision': 2},
        'profile_revision': {'base_profile_revision': 3}}[change])
    other_basis = profile_preparation.build_basis(world.message, world.config, **values)
    other = prepare(world, other_basis)
    assert other.wire_payload_json == world.prepared.wire_payload_json
    async def scenario():
        lease = grant(world)
        with pytest.raises(ServiceError):
            await lease.provider.generate_profile(other)
        assert world.provider.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('digest', ['content_sha256', 'wire_sha256'])
def test_content_or_wire_digest_is_not_a_profile_purpose_grant(world, digest):
    world.registry.configure(world.provider)
    with pytest.raises(ServiceError):
        world.registry.grant(world.policy.model_copy(update={
            'allowed_content_sha256s': (getattr(world.basis, digest),)}),
            world.actor.session_id, basis=world.basis)
    assert world.provider.calls == []


def test_self_consistent_forged_wire_cannot_bypass_current_template_rebuild(world):
    body = json.loads(world.prepared.wire_payload_json)
    body['messages'][0]['content'] = '替换后的合成system模板'
    wire = json_bytes(body)
    changed_basis = world.basis.model_copy(update={'wire_sha256': sha256(wire).hexdigest(), 'wire_bytes': len(wire)})
    changed = world.prepared.model_copy(update={'basis': changed_basis, 'wire_payload_json': wire.decode()})
    # Passes the DTO's own digest checks; current-code reconstruction must still reject it.
    changed = d.MainProfilePreparedInput.model_validate(changed.model_dump(mode='python'))
    async def scenario():
        with pytest.raises(ServiceError):
            lease = grant(world, basis=changed_basis, policy=policy_for(world, changed_basis))
            await lease.provider.generate_profile(changed)
        assert world.provider.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['revoke', 'configuration', 'replacement', 'expiry'])
def test_wrapper_preserves_late_received_usage_without_trusting_provider_preflight(world, change, monkeypatch):
    async def scenario():
        lease = grant(world)
        def invalidate():
            if change == 'revoke':
                world.registry.revoke(world.actor.session_id)
            elif change == 'configuration':
                world.provider.config = world.config.model_copy(update={'max_output_tokens': 99})
            elif change == 'replacement':
                world.registry.grant(policy_for(world, world.basis), world.actor.session_id, basis=world.basis)
            else:
                class Future(datetime):
                    @classmethod
                    def now(cls, tz=None):
                        return world.policy.expires_at + timedelta(seconds=1)
                monkeypatch.setattr(registry_module, 'datetime', Future)
        world.provider.hook = invalidate
        reply = await lease.provider.generate_profile(world.prepared)
        assert reply.state == 'received' and reply.output is None and reply.error_code == 'BLOCKED_LIVE'
        assert reply.usage.total_tokens == 10 and reply.provider_request_id == 'synthetic-profile-receipt'
        assert len(world.provider.calls) == 1
    asyncio.run(scenario())


def test_raw_profile_request_without_complete_save_plan_is_rejected(world):
    async def scenario():
        lease = grant(world)
        with pytest.raises(ServiceError):
            await lease.provider.generate_profile(world.prepared.request)
        assert world.provider.calls == []
    asyncio.run(scenario())


def test_native_http_runner_storage_and_integrity_entries_remain_at_baseline():
    paths = ['src/cn_contract/assistant/native_model_control.py',
        'src/cn_contract/assistant/task_manager.py', 'src/cn_contract/web/assistant_generation.py',
        'src/cn_contract/web/assistant.py', 'src/cn_contract/assistant/model_integrity.py',
        'src/cn_contract/assistant/providers/attempts.py', 'src/cn_contract/domain.py']
    assert subprocess.check_output(['git', 'diff', BASELINE, '--', *paths], cwd=ROOT) == b''
    assert "raise ValueError('ASSISTANT_PROFILE_MODEL_NOT_ENABLED')" in (
        ROOT / 'src/cn_contract/assistant/model_integrity.py').read_text(encoding='utf-8')
