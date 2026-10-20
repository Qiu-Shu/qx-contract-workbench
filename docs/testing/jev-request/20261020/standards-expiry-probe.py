"""Independent synthetic review probe. No provider call or real material."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import MonkeyPatch
from tests.integration.test_assistant_generation import world
from tests.integration.test_native_judge_authorization import native, configuration
from cn_contract.assistant import native_judge_control
from cn_contract.assistant.providers import judge_policy
from cn_contract.security import ServiceError


async def verify(n):
    payload = configuration(n)
    payload['valid_for_seconds'] = 1
    stamp = datetime.now(timezone.utc)
    offset = [timedelta()]
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return stamp + offset[0]
    original = n.runtime.grant
    first = [True]
    def delayed_grant(*args):
        result = original(*args)
        if first[0]:
            first[0] = False
            offset[0] = timedelta(seconds=2)
        return result
    with MonkeyPatch.context() as p:
        p.setattr(native_judge_control, 'datetime', Clock)
        p.setattr(judge_policy, 'datetime', Clock)
        p.setattr(n.runtime, 'grant', delayed_grant)
        try:
            initial = n.control.authorize(payload)['status']
        except ServiceError as error:
            initial = error.code
        old_id = n.runtime.policy.policy_id
        tombstone_after_first = bool(n.control._intents)
        try:
            repeated = n.control.authorize(payload)['status']
        except ServiceError as error:
            repeated = error.code
        result = {'first': initial, 'tombstone_after_first': tombstone_after_first,
                  'repeated': repeated, 'new_policy': n.runtime.policy.policy_id != old_id}
        print(json.dumps(result))
        assert repeated == 'BLOCKED_LIVE' and not result['new_policy'], 'Same intent renewed after grant crossed expiry'


with TemporaryDirectory(prefix='standards-expiry-', dir='.local/jev-request-20261020') as directory:
    fixture = world.__wrapped__(Path(directory).resolve())
    actual = next(fixture)
    instance = native.__wrapped__(actual)
    try:
        asyncio.run(verify(instance))
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass
