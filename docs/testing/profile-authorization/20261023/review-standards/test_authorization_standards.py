"""Independent authorization edge probes; synthetic in-memory provider only."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Inexact, Rounded, localcontext
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest

from cn_contract import domain as d
from cn_contract.assistant.providers import profile_preparation, profile_codec
from cn_contract.assistant.providers.registry import MainModelRegistry
from cn_contract.assistant.providers.policy import encoded, sha
from cn_contract.security import ServiceError
from tests.integration.test_assistant_main_provider import config, KEY
from tests.unit.test_assistant_profile_codec import response
from tests.unit.test_assistant_profile_preparation import draft, basis, saved

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = '60eb041536dc36dfd4133f0d09b909681146500c'


def value(approval=None):
    return profile_preparation.prepare(*saved(),approval or basis(),config(),composer_revision=4)


class Provider:
    def __init__(self):
        self.config = config()
        self.calls = 0
        self.action = lambda: None

    async def generate(self, request, **kwargs):
        pytest.fail('plain provider must not be used')

    async def generate_profile(self, request, *, expected_config, preflight):
        self.calls += 1
        assert preflight() is True
        await asyncio.sleep(0)
        self.action()
        return profile_codec.decode_response(response(request),request,expected_config,KEY)


def setup(approval=None):
    approval = approval or basis()
    actor = d.Actor(user_id=uuid4(),session_id=uuid4(),roles=frozenset())
    provider = Provider()
    registry = MainModelRegistry()
    registry.configure(provider)
    policy = d.MainModelPolicy(policy_id=uuid4(),workspace_id=approval.expected_scope.workspace_id,
        actor_id=actor.user_id,config_sha256=sha(encoded(provider.config)),
        allowed_content_sha256s=(profile_preparation.basis_digest(approval),),
        max_total_usd='1',max_calls=1,expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
    registry.grant(policy,actor.session_id,basis=approval)
    return registry,provider,actor,policy


def test_cold_registry_import_keeps_baseline_dependency_set():
    baseline_path = HERE/'baseline_registry.py'
    baseline_path.write_bytes(subprocess.check_output(['git','show',BASE+':src/cn_contract/assistant/providers/registry.py'],cwd=ROOT))
    script = '''import importlib, json, sys, types
from pathlib import Path
if sys.argv[1] == 'baseline':
    importlib.import_module('cn_contract.assistant.providers')
    module=types.ModuleType('cn_contract.assistant.providers.registry')
    module.__package__='cn_contract.assistant.providers'
    sys.modules[module.__name__]=module
    exec(compile(Path(sys.argv[2]).read_text('utf-8'),sys.argv[2],'exec'),module.__dict__)
else:
    importlib.import_module('cn_contract.assistant.providers.registry')
project=sorted(n for n in sys.modules if n=='cn_contract' or n.startswith('cn_contract.'))
prefixes=('cn_contract.assistant.providers.profile_codec','cn_contract.assistant.providers.profile_preparation',
          'cn_contract.web','cn_contract.desktop','fitz','pypdf','PyPDF2')
forbidden=sorted(n for n in sys.modules if any(n==p or n.startswith(p+'.') for p in prefixes))
print(json.dumps({'project_modules':project,'forbidden_modules':forbidden},sort_keys=True))
'''
    observed={}
    for mode in ('baseline','current'):
        result=subprocess.run([sys.executable,'-X','utf8','-c',script,mode,str(baseline_path)],
            cwd=ROOT,capture_output=True,text=True,timeout=45)
        assert result.returncode == 0, result.stderr
        observed[mode]=json.loads(result.stdout)
    observed['new_project_modules']=sorted(set(observed['current']['project_modules'])-set(observed['baseline']['project_modules']))
    (HERE/'cold-import.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2),'utf-8')
    assert observed['new_project_modules'] == []
    assert observed['current']['project_modules'] == observed['baseline']['project_modules']
    assert observed['baseline']['forbidden_modules'] == observed['current']['forbidden_modules'] == []


def test_self_consistent_noncanonical_wire_still_requires_exact_current_bytes():
    original=value()
    wire=json.dumps(json.loads(original.wire_payload_json),ensure_ascii=False,indent=2)
    approval=original.basis.model_copy(update={'wire_sha256':hashlib.sha256(wire.encode()).hexdigest(),'wire_bytes':len(wire.encode())})
    forged=d.MainProfilePreparedInput.model_validate(original.model_dump(mode='python')|{'basis':approval,'wire_payload_json':wire})
    async def scenario():
        registry,provider,actor,_=setup(approval)
        lease=registry.resolve(actor,forged.request.scope)
        with pytest.raises(ServiceError) as error:
            await lease.provider.generate_profile(forged)
        assert error.value.code == 'BLOCKED_LIVE'
        assert provider.calls == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('change',['replacement_grant','removed_method'])
def test_inflight_plan_replacement_or_capability_loss_discards_only_candidate(change):
    async def scenario():
        registry,provider,actor,policy=setup()
        lease=registry.resolve(actor,basis().expected_scope)
        if change == 'replacement_grant':
            replacement=basis(project_intake=True)
            new_policy=policy.model_copy(update={'policy_id':uuid4(),
                'allowed_content_sha256s':(profile_preparation.basis_digest(replacement),)})
            provider.action=lambda: registry.grant(new_policy,actor.session_id,basis=replacement)
        else:
            provider.action=lambda: setattr(provider,'generate_profile',None)
        reply=await lease.provider.generate_profile(value())
        assert reply.state == 'received' and reply.error_code == 'BLOCKED_LIVE'
        assert reply.output is None and reply.usage.total_tokens == 42
        assert reply.provider_request_id == 'synthetic-response-1' and provider.calls == 1
    asyncio.run(scenario())


def test_profile_authorization_does_not_inherit_hostile_decimal_context():
    async def scenario():
        with localcontext() as context:
            context.prec=1
            context.traps[Inexact]=True
            context.traps[Rounded]=True
            registry,provider,actor,_=setup()
            lease=registry.resolve(actor,basis().expected_scope)
            lease.check_profile_submission(actor,draft(),basis())
            lease.check_profile_execution(actor,basis().request_id,value())
            reply=await lease.provider.generate_profile(value())
            assert reply.output is not None and provider.calls == 1
    asyncio.run(scenario())


def test_permission_is_expired_at_exact_deadline(monkeypatch):
    from cn_contract.assistant.providers import registry as module
    async def scenario():
        registry,provider,actor,policy=setup()
        lease=registry.resolve(actor,basis().expected_scope)
        class Clock:
            @staticmethod
            def now(_timezone):
                return policy.expires_at
        monkeypatch.setattr(module,'datetime',Clock)
        with pytest.raises(ServiceError) as error:
            await lease.provider.generate_profile(value())
        assert error.value.code == 'BLOCKED_LIVE' and provider.calls == 0
    asyncio.run(scenario())
