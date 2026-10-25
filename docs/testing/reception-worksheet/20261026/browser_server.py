from pathlib import Path
from uuid import uuid4
import json
import uvicorn
from cn_contract import domain as d
from cn_contract.assistant import service, profile_store
from cn_contract.security import login,authenticate
from cn_contract.web.local_server import initialize_workspace,build_local_app
base=Path(Path('/tmp/qx-worksheet-browser-path').read_text().strip())
root=base/'workspaces/main'
initialize_workspace(root,'合成接待律师','fiction123',data_parent=base)
app=build_local_app(root,port=18770,data_parent=base)
with app.state.database.session() as db:
 token,_=login('合成接待律师','fiction123',db)
 actor=authenticate(token,db)
 conversation=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4(),display_title='合成借贷接待'),db)
profile_store.save_profile(actor,d.ProfileCommitInput(request_id=uuid4(),patch=d.ProfilePatch(scope=conversation.scope,
 base_profile_revision=0,changes=()),manual_edits=(d.ProfileEdit(field='internal_notes',value={'kind':'text','value':'原内部备注：谈判安排只供律师核对。'}),)),database=app.state.database)
(base/'fixture.json').write_text(json.dumps({'cid':str(conversation.scope.conversation_id),'root':str(root)},ensure_ascii=False))
uvicorn.run(app,host='127.0.0.1',port=18770,log_level='warning')
