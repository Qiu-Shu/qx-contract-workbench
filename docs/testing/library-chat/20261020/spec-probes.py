"""Independent CH-06B2a spec probes; synthetic sources only."""
import asyncio
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import text

from cn_contract import domain as d
from cn_contract.assistant import research, service
from cn_contract.assistant.library_handlers import read_saved_citation
from cn_contract.assistant.task_manager import GenerationTasks
from cn_contract.assistant.tools.library import LegalLibraryAdapter
from cn_contract.security import ServiceError, remove_membership
from tests.integration.test_assistant_generation import world
from tests.integration.test_assistant_library_adapter import library
from tests.integration.test_assistant_storage import add_matter


@pytest.mark.parametrize('revoked_scope', ['current','historical'])
def test_rebound_research_requires_both_current_and_historical_permissions(world,library,revoked_scope):
    database, actor, _, _, _ = world
    old, new = add_matter(database,actor), add_matter(database,actor)
    with database.session() as db:
        view=service.create_conversation(actor,d.AssistantConversationCreateInput(
            request_id=uuid4(),scope_kind='matter',scope_ref=old),db)
        registered=research.enqueue_research(actor,view.scope.conversation_id,d.AssistantMessageInput(
            request_id=uuid4(),expected_scope=view.scope,expected_composer_revision=0,
            content='目标租赁',requested_skill='legal_research'),db)
    completed=research.execute_research(actor,registered.run.id,database,LegalLibraryAdapter(library[0]))
    saved=completed.receipts[0].result.citation_ids[0]
    with database.session() as db:
        db.execute(text('UPDATE assistant_conversations SET scope_ref=:new,binding_revision=binding_revision+1 WHERE id=:id'),
            {'new':str(new),'id':str(view.scope.conversation_id)})
        current=service._owned(actor,view.scope.conversation_id,db)
        query=d.MainGenerationHistoryQuery(message_ids=(completed.run.message_id,))
        assert research.read_history(actor,current,query,db).items[0].research == completed
        assert read_saved_citation(actor,saved,db).scope.scope_ref == old
        remove_membership(new if revoked_scope=='current' else old,actor.user_id,db)
    with database.session() as db:
        for read in [lambda: research.read_history(actor,current,query,db),
                     lambda: research.find_research(actor,view.scope.conversation_id,completed.run.request_id,db),
                     lambda: read_saved_citation(actor,saved,db)]:
            with pytest.raises(ServiceError) as failure: read()
            assert failure.value.code=='CROSS_MATTER_DENIED'


def test_repeated_close_cancellation_still_drains_worker_and_refuses_late_receipt(world):
    database,actor,view,request,_=world
    entered,release=Event(),Event()
    class Adapter:
        def search(self,query):
            entered.set()
            assert release.wait(5)
            return d.LibraryCitationPage(query=query,state='not_configured')
    manager=GenerationTasks(database,None,library_adapter=Adapter())
    request=request.model_copy(update={'content':'合成关键词','requested_skill':'legal_research'})
    async def scenario():
        manager.start()
        registered=manager.submit_research(actor,view.scope.conversation_id,request)
        assert await asyncio.to_thread(entered.wait,3)
        closing=asyncio.create_task(manager.close())
        try:
            await asyncio.sleep(.03)
            closing.cancel()
            await asyncio.sleep(.03)
            closing.cancel()
            await asyncio.sleep(.03)
            assert not closing.done() and manager.active_count==1 and not manager.accepting
            with database.session() as db:
                result=research.read_research(actor,registered.run.id,db)
                assert result.run.state=='interrupted' and not result.receipts
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError): await closing
        assert manager.active_count==0
        with database.session() as db:
            assert not research.read_research(actor,registered.run.id,db).receipts
        await manager.close()
    asyncio.run(scenario())
