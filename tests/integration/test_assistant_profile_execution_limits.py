"""Expanded source references must fit the existing persistent output reader."""
import asyncio

from sqlalchemy import text

from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.integration.test_assistant_profile_execution import profile_world, authorize, enqueue, no_archive
from tests.unit.test_assistant_profile_codec import fixture, response, candidate as wire_candidate


def test_expanded_oversize_output_is_rejected_before_persistence_but_usage_is_saved(profile_world):
    database, actor, _, _ = profile_world
    payload = wire_candidate()
    payload['profile_changes'][0]['quotes'] *= 40
    payload['profile_changes'] *= 60
    raw = response(fixture()[1], payload)
    assert len(raw) < config().max_response_bytes
    with server(raw) as (url, received, _):
        async def scenario():
            provider = DeepSeekProvider.for_synthetic_loopback(config(), lambda: KEY, url)
            _, runtime, _, _ = authorize(profile_world, provider)
            first = enqueue(profile_world, runtime)
            result = await execute_attempt(actor, first.id, database, runtime)
            assert result.output is None and result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
            assert result.state == 'received' and result.receipt.usage.total_tokens == 42
            no_archive(database)
            with database.session() as db:
                assert db.scalar(text('SELECT count(*) FROM assistant_model_receipts')) == 1
                assert db.scalar(text('SELECT count(*) FROM assistant_model_outputs')) == 0
                validate_model_records(db)
        asyncio.run(scenario())
        assert len(received) == 1
