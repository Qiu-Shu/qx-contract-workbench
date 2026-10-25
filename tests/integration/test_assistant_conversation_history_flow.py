"""Actual two-turn loopback requests and their immutable archive, synthetic only."""
import asyncio
import json
from uuid import uuid4

import pytest
from cn_contract import domain as d
from cn_contract.assistant import service, profile_preparation_service
from cn_contract.assistant.providers import attempts
from cn_contract.assistant.providers.main import DeepSeekProvider
from cn_contract.assistant.runner import execute_attempt
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_profile_execution import profile_world, authorize, enqueue
from tests.integration.test_assistant_main_provider import config, server, KEY
from tests.unit.test_assistant_profile_codec import fixture, response


def next_turn(state, text):
    database,actor,conversation,_=state
    with database.session() as db:
        current=service.read_conversation(actor,conversation.scope.conversation_id,db)
        current=service.save_draft(actor,current.scope.conversation_id,d.AssistantDraftInput(
            expected_scope=current.scope,expected_composer_revision=current.composer_revision,content=text),db)
    request=d.AssistantMessageInput(request_id=uuid4(),expected_scope=current.scope,
        expected_composer_revision=current.composer_revision,content=text)
    return database,actor,current,request


def test_two_turn_wire_contains_only_own_completed_context_and_archive_rebuilds(profile_world):
    raw=response(fixture()[1],{'text':'请补充还款日期。','citations':[],'profile_changes':[]})
    database,actor,_,_=profile_world
    with server(raw) as (url,received,_):
        async def scenario():
            provider=DeepSeekProvider.for_synthetic_loopback(config(),lambda:KEY,url)
            _,runtime,_,_=authorize(profile_world,provider)
            first=enqueue(profile_world,runtime)
            await execute_attempt(actor,first.id,database,runtime)
            state=next_turn(profile_world,'约定月底，继续刚才的问题。')
            _,runtime,basis,_=authorize(state,provider)
            assert basis.template_version=='profile-text-system-v2'
            assert [m.role for m in basis.conversation_history]==['user','assistant']
            second=enqueue(state,runtime)
            result=await execute_attempt(actor,second.id,database,runtime)
            assert result.output is not None
            assert await execute_attempt(actor,second.id,database,runtime)==result
            from cn_contract.assistant.model_integrity import validate_model_records
            with database.session() as db:
                validate_model_records(db)
            wire=json.loads(received[-1]['body'])
            assert len(received)==2
            assert [m['role'] for m in wire['messages']]==['system','user','assistant','user']
            assert '35000' in wire['messages'][1]['content']
            assert '还款日期' in wire['messages'][2]['content']
            assert '月底' in wire['messages'][-1]['content']
        asyncio.run(scenario())
