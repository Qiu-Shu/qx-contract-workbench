import sys
sys.path.insert(0, '/Users/molin/Project/qx-contract-workbench/tests/integration')
from test_assistant_output_models import world, completed
from cn_contract import domain as d
from cn_contract.assistant import outputs, service, profile_store
from cn_contract.security import ServiceError
from sqlalchemy import text
from uuid import uuid4
import pytest

@pytest.mark.parametrize('count',[19,20,21,40,41])
def test_profiles_to_model_boundary_without_loss_or_duplicates(world,count):
    database, actor, conversation, result = completed(world)
    cid = conversation.scope.conversation_id
    with database.session() as db:
        scope = service.read_conversation(actor,cid,db).scope
    for revision in range(count):
        profile_store.save_profile(actor,d.ProfileCommitInput(request_id=uuid4(), patch=d.ProfilePatch(scope=scope,base_profile_revision=revision),manual_edits=(d.ProfileEdit(field='client_reply',value={'kind':'text','value':f'回复{revision}'}),),project_intake=False),database=database)
    seen=[];cursor=None;pages=0
    while True:
        with database.session() as db:
            page=outputs.list_outputs(actor,cid,db,before=cursor)
        assert len(page.items)<=20
        seen.extend(item.source for item in page.items)
        pages+=1
        assert pages<=4
        cursor=page.next_before
        if cursor is None:break
    assert [x.profile_revision for x in seen if x.kind=='profile']==list(range(count,0,-1))
    assert [x.output_id for x in seen if x.kind=='model']==[result.output.id]
    assert len(seen)==count+1


def test_foreign_model_cursor_and_changed_binding_remain_closed(world):
    database, actor, conversation, result = completed(world)
    cid=conversation.scope.conversation_id
    with database.session() as db:
        other=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4()),db)
        with pytest.raises(ServiceError) as error:
            outputs.list_outputs(actor,other.scope.conversation_id,db,before=d.AssistantOutputSource(kind='model',output_id=result.output.id))
        assert error.value.status_code==403
        db.execute(text('UPDATE assistant_conversations SET binding_revision=2 WHERE id=:id'),{'id':str(cid)})
        listing=outputs.list_outputs(actor,cid,db)
        assert not listing.items
        with pytest.raises(ServiceError):
            outputs.preview(actor,cid,d.AssistantOutputSelection(source=d.AssistantOutputSource(kind='model',output_id=result.output.id),audience='internal'),db)
