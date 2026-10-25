"""Actual persisted synthetic model answers stay internal and source-bound."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import outputs, service
from cn_contract.assistant.runner import execute_attempt
from cn_contract.security import ServiceError
from tests.integration.test_assistant_generation import world, enqueue


def completed(world):
    database, actor, conversation, _, runtime = world
    attempt = enqueue(world)
    result = asyncio.run(execute_attempt(actor,attempt.id,database,runtime))
    return database, actor, conversation, result


def test_saved_model_output_has_its_own_identity_and_internal_only_projection(world):
    database, actor, conversation, result = completed(world)
    selected = d.AssistantOutputSelection(source=d.AssistantOutputSource(kind='model',output_id=result.output.id),audience='internal')
    with database.session() as db:
        listed = outputs.list_outputs(actor,conversation.scope.conversation_id,db)
        assert listed.items[0].source.output_id == result.output.id
        assert listed.items[0].audiences == ('internal',)
        projected = outputs.preview(actor,conversation.scope.conversation_id,selected,db)
        assert projected.text == result.output.candidate.text
        assert projected.citations
        assert outputs.preview(actor,conversation.scope.conversation_id,selected,db) == projected
        with pytest.raises(ServiceError) as failure:
            outputs.preview(actor,conversation.scope.conversation_id,selected.model_copy(update={'audience':'client'}),db)
        assert failure.value.status_code == 422


@pytest.mark.parametrize('change', ['foreign','binding','incomplete'])
def test_model_source_must_belong_to_current_binding_and_completed_run(world, change):
    database, actor, conversation, result = completed(world)
    selected = d.AssistantOutputSelection(source=d.AssistantOutputSource(kind='model',output_id=result.output.id),audience='internal')
    with database.session() as db:
        cid = conversation.scope.conversation_id
        if change == 'foreign':
            cid = service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db).scope.conversation_id
        elif change == 'binding':
            db.execute(text('UPDATE assistant_conversations SET binding_revision=2 WHERE id=:id'),{'id':str(cid)})
        else:
            db.execute(text("UPDATE assistant_runs SET state='interrupted' WHERE id=:id"),{'id':str(result.run_id)})
        with pytest.raises(ServiceError):
            outputs.preview(actor,cid,selected,db)
