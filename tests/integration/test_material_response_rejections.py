"""Fictional received-response probes; no socket, credentials or user workspace."""
import asyncio
import json
import logging

import pytest
from sqlalchemy import text

from cn_contract.assistant import material_codec
from cn_contract.assistant.model_integrity import validate_model_records
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.runner import execute_attempt
from tests.integration.test_contract_c4_material_flow import (
    configure_and_preview, enqueue, material_flow, world,
)


def mutate_response(raw, failure):
    value = json.loads(raw)
    choice = value['choices'][0]
    message = choice['message']
    candidate = json.loads(message['content'])
    if failure == 'envelope':
        value['model'] = 'unsupported-fictional-model'
    elif failure == 'usage':
        value['usage']['total_tokens'] += 1
    elif failure == 'choice':
        choice['finish_reason'] = 'length'
    elif failure == 'message':
        message['reasoning_content'] = 'PRIVATE-FICTIONAL-REASONING'
    elif failure == 'content_json':
        message['content'] = '{PRIVATE-FICTIONAL-INCOMPLETE'
    elif failure == 'candidate_schema':
        candidate['citations'] = []
    elif failure == 'material_sources':
        candidate['citations'] = ['a' * 64]
    elif failure == 'unsupported_business_output':
        candidate['workflow'] = 'unsupported-fictional-workflow'
    if failure not in ('content_json',):
        message['content'] = json.dumps(candidate)
    return json.dumps(value).encode()


@pytest.mark.parametrize('failure', [
    'envelope', 'usage', 'choice', 'message', 'content_json', 'candidate_schema',
    'material_sources', 'unsupported_business_output',
])
def test_material_received_rejection_preserves_ledger_without_resending(
        material_flow, monkeypatch, caplog, failure):
    f = material_flow
    caplog.set_level(logging.WARNING)
    original_decode = material_codec.decode

    def decode(raw, request, config, secret):
        return original_decode(mutate_response(raw, failure), request, config, secret)

    monkeypatch.setattr(material_codec, 'decode', decode)

    async def scenario():
        payload = configure_and_preview(f)
        f.control.authorize_material(payload)
        lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
        queued = enqueue(f, payload['basis'], lease)
        result = await execute_attempt(f.actor, queued.id, f.database, lease)
        assert result.state == 'received'
        assert result.receipt.error_code == 'MODEL_OUTPUT_INVALID'
        assert result.output is None
        if failure in ('envelope', 'usage'):
            assert result.receipt.usage is None
            assert result.receipt.cost_status == 'unknown'
        else:
            assert result.receipt.usage.total_tokens == 30
            assert result.receipt.cost_status == 'estimated'
        assert await execute_attempt(f.actor, queued.id, f.database, lease) == result
        with f.database.session() as db:
            assert attempts.read_attempt(f.actor, queued.id, db) == result
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_attempts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
            assert db.scalar(text('SELECT state FROM assistant_runs WHERE id=:id'),
                {'id': str(result.run_id)}) == 'failed'
            validate_model_records(db)
        assert len(f.providers[0].calls) == 1

    asyncio.run(scenario())
    stage = {'unsupported_business_output': 'candidate', 'candidate_schema': 'candidate',
        'material_sources': 'candidate'}.get(failure, failure)
    messages = [record.getMessage() for record in caplog.records
        if record.name.startswith('cn_contract.assistant.')]
    assert 'model_response_rejected stage=' + stage in messages
    if failure == 'material_sources':
        assert 'model_response_rejected stage=material_sources' in messages
    assert all(message.startswith('model_response_rejected stage=') for message in messages)
    assert not any(marker in '\n'.join(messages) for marker in (
        'PRIVATE-', 'synthetic-material-response', 'a' * 64, '合成待核草稿', 'SYNTHETIC_MATERIAL_FLOW'))


@pytest.mark.parametrize('failure', ['candidate', 'current'])
def test_material_settlement_discard_is_distinguishable_from_provider_rejection(
        material_flow, monkeypatch, caplog, failure):
    f = material_flow
    caplog.set_level(logging.WARNING)
    original_decode = material_codec.decode

    def decode(raw, request, config, secret):
        reply = original_decode(raw, request, config, secret)
        assert reply.output is not None
        if failure == 'candidate':
            return reply.model_copy(update={'output': reply.output.model_copy(
                update={'citations': ('a' * 64,)})})
        return reply

    monkeypatch.setattr(material_codec, 'decode', decode)
    original_settle = attempts.settle

    def settle(*args, **kwargs):
        if failure == 'current':
            f.control.revoke({'session_token': f.token})
        return original_settle(*args, **kwargs)

    monkeypatch.setattr(attempts, 'settle', settle)

    async def scenario():
        payload = configure_and_preview(f)
        f.control.authorize_material(payload)
        lease = f.registry.resolve(f.actor, payload['basis'].expected_scope)
        queued = enqueue(f, payload['basis'], lease)
        result = await execute_attempt(f.actor, queued.id, f.database, lease)
        assert result.state == 'received' and result.output is None
        assert result.receipt.usage.total_tokens == 30
        assert result.receipt.error_code == ('MODEL_OUTPUT_INVALID' if failure == 'candidate' else None)
        assert await execute_attempt(f.actor, queued.id, f.database, lease) == result
        with f.database.session() as db:
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_receipts')) == 1
            assert db.scalar(text('SELECT COUNT(*) FROM assistant_model_outputs')) == 0
            validate_model_records(db)
        assert len(f.providers[0].calls) == 1

    asyncio.run(scenario())
    assert 'model_response_rejected stage=material_settle_' + failure in caplog.messages
