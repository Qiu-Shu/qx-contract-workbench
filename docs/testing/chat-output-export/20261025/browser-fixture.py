from pathlib import Path
import json, sys
from uuid import uuid4
import uvicorn
from cn_contract import domain as d
from cn_contract.assistant import service, profile_store
from cn_contract.security import login, authenticate
from cn_contract.web.local_server import initialize_workspace, build_local_app
from sqlalchemy import text
base=Path('/tmp/qx-ch08-browser-path').read_text().strip()
out=Path(base)
root=out/'workspaces/main'
if not root.exists(): initialize_workspace(root,'合成导出律师','fiction123',data_parent=out)
app=build_local_app(root,port=18769,data_parent=out)
database=app.state.database
with database.session() as db:
 token,_=login('合成导出律师','fiction123',db)
 actor=authenticate(token,db)
 view=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4(),display_title='合成咨询 · 成果导出验证'),db)
 view2=service.create_conversation(actor,d.AssistantConversationCreateInput(request_id=uuid4(),display_title='另一合成对话'),db)
public='您好，关于您提到的款项问题，我们建议先核对以下材料。\n\n一、请提供合同、付款凭证及相关沟通记录。\n二、请确认约定的付款日期、实际已付款金额和未付款金额。\n三、材料核对后，我们将整理可行的处理方案供您确认。\n\n目前信息仍待核实，以上是沟通草稿，不代表已确认对方违约或形成正式法律意见。'
private='内部哨兵：最低和解底线777元，不得发客户。\n需内部讨论证据不足、诉讼成本和谈判安排。'
request=d.ProfileCommitInput(request_id=uuid4(),patch=d.ProfilePatch(scope=view.scope,base_profile_revision=0,changes=()),manual_edits=(
 d.ProfileEdit(field='client_reply',value={'kind':'text','value':public}),
 d.ProfileEdit(field='internal_notes',value={'kind':'text','value':private}),
 d.ProfileEdit(field='title',value={'kind':'text','value':'内部标题哨兵-只给律师'})),project_intake=False)
profile_store.save_profile(actor,request,database=database)
old_public=public
public+='\n后续补充：请确认联系人。'
profile_store.save_profile(actor,d.ProfileCommitInput(request_id=uuid4(),patch=d.ProfilePatch(scope=view.scope,base_profile_revision=1,changes=()),manual_edits=(d.ProfileEdit(field='client_reply',value={'kind':'text','value':public}),),project_intake=False),database=database)
(out/'fixture.json').write_text(json.dumps({'cid':str(view.scope.conversation_id),'other':str(view2.scope.conversation_id),'public':public,'old_public':old_public,'private':private},ensure_ascii=False,indent=2))
uvicorn.run(app,host='127.0.0.1',port=18769,log_level='warning')
