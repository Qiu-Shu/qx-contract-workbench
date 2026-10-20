"""Reading configuration for a preview does not read or create a grant."""
import asyncio

import pytest

from cn_contract.security import ServiceError
from tests.integration.test_model_registry import world


def test_preview_configuration_is_independent_of_authority(world):
    async def scenario():
        assert world.registry.configuration() is None
        world.registry.configure(world.provider)
        assert world.registry.configuration() == world.config
        assert world.registry.resolve(world.actor, world.scope).snapshot()[1] is None
        world.registry.grant(world.policy, world.actor.session_id)
        token = world.registry.authorization_token(world.actor, world.scope)
        assert world.registry.configuration() == world.config
        assert world.registry.authorization_token(world.actor, world.scope) == token
        world.registry.revoke(world.actor.session_id)
        assert world.registry.configuration() == world.config
        assert world.registry.resolve(world.actor, world.scope).snapshot()[1] is None
        assert world.provider.calls == []
    asyncio.run(scenario())
