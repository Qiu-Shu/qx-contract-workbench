import * as api from './assistant-api.mjs';
import {createDraftController} from './assistant-state.mjs';
import {createRenderer,errorText} from './assistant-render.mjs';
import {bindComposer} from './assistant-composer.mjs';

const byId=id=>document.getElementById(id);
const readonly=document.body.dataset.readonly==='true';
let composer, timer, listCursor=null, listEpoch=0, closed=false;
let pendingRoute=document.body.dataset.conversationId || null;
const renderer=createRenderer(document,{isComposing:()=>composer?.isComposing()});
const controller=createDraftController(api,{readonly,
  onChange:state=>{
    drawState(state);
    renderer.selected(state.id);
    if(state.status==='revoked') {
      ++listEpoch;
      byId('conversation-list').replaceChildren();
      byId('more-conversations').hidden=true;
    }
  },
  onConversation:id=>{
    history.replaceState(null,'',id?'/assistant/'+encodeURIComponent(id):'/assistant');
    void loadList();
  },
});

function drawState(state) {
  renderer.state(state,readonly);
  if(pendingRoute && !state.id && state.status!=='revoked') {
    byId('composer').disabled=true;byId('save-draft').disabled=true;
    document.querySelectorAll('[data-skill]').forEach(button=>button.disabled=true);
    byId('refresh-run').hidden=state.status!=='error';
    byId('refresh-run').textContent='重新读取记录';
  } else byId('refresh-run').textContent='刷新状态';
}
function closeMenu() {
  document.body.classList.remove('sidebar-open');byId('nav-toggle').setAttribute('aria-expanded','false');
}
function notice(text){byId('notice').textContent=text;}
function failure(error) {if(!controller.revoke(error))notice(errorText(error));}
async function safely(action) {
  try { return await action(); }
  catch(error) { failure(error); return false; }
}
async function loadList(append=false) {
  if(closed || controller.state.status==='revoked')return;
  const epoch=++listEpoch;
  byId('more-conversations').disabled=true;
  try {
    const page=await api.listConversations(append?listCursor:null);
    if(epoch!==listEpoch || closed || controller.state.status==='revoked')return;
    listCursor=page.next_cursor;
    renderer.conversations(page,{append,selected:controller.state.id,onSelect:id=>void open(id)});
  } catch(error) { if(epoch===listEpoch)failure(error); }
  finally { if(epoch===listEpoch)byId('more-conversations').disabled=false; }
}
async function open(id) {
  clearTimeout(timer);
  pendingRoute=id;
  const done=await safely(()=>controller.open(id));
  if(done || controller.state.id)pendingRoute=null;
  drawState(controller.state);
  if(done)closeMenu();
}
composer=bindComposer({input:byId('composer'),form:byId('composer-form'),
  onEdit:text=>{
    controller.edit(text); clearTimeout(timer);
    if(!readonly)timer=setTimeout(()=>void safely(()=>controller.save()),650);
  },
  onSend:()=>notice('模型对话尚未接入。输入可以保存为草稿；现有业务请从工作区进入。'),
});

const examples={client_reply:'这是客户的咨询，帮我理清诉求并起草回复：',
  material_organize:'请帮我整理这次咨询的事实线索和待补材料：',
  contract_review:'请帮我核对这份合同需要重点审查的问题：',
  content_draft:'请围绕这个法律主题起草一段文案：',
  legal_research:'请帮我检索与这个问题相关的法律资料：'};
document.querySelectorAll('[data-skill]').forEach(button=>button.addEventListener('click',()=>{
  controller.selectSkill(button.dataset.skill);
  if(!controller.state.text && !composer.isComposing()) {
    controller.edit(examples[button.dataset.skill]);
    clearTimeout(timer);timer=setTimeout(()=>void safely(()=>controller.save()),650);
  }
  closeMenu();byId('composer').focus();
}));
byId('clear-skill').addEventListener('click',()=>{controller.selectSkill(null);byId('composer').focus();});
byId('save-draft').addEventListener('click',()=>{clearTimeout(timer);void safely(()=>
  controller.state.status==='error'?controller.retry():controller.save());});
byId('new-conversation').addEventListener('click',async()=>{
  clearTimeout(timer);
  if(await safely(()=>controller.newConversation())) {
    pendingRoute=null;drawState(controller.state);closeMenu();byId('composer').focus();
  }
});
byId('more-conversations').addEventListener('click',()=>void loadList(true));
byId('older-messages').addEventListener('click',async()=>{
  const height=document.documentElement.scrollHeight,scroll=window.scrollY;
  if(await safely(()=>controller.loadEarlier()))window.scrollTo(0,scroll+document.documentElement.scrollHeight-height);
});
byId('refresh-run').addEventListener('click',()=>void (pendingRoute?open(pendingRoute):safely(()=>controller.refresh())));
byId('cancel-run').addEventListener('click',()=>void safely(()=>controller.cancel()));
for(const [id,choice] of [['keep-local','local'],['use-server','server']])
  byId(id).addEventListener('click',()=>void safely(()=>controller.resolveConflict(choice)));
byId('nav-toggle').addEventListener('click',()=>{
  const expanded=document.body.classList.toggle('sidebar-open');
  byId('nav-toggle').setAttribute('aria-expanded',String(expanded));
  if(expanded)byId('sidebar').querySelector('a,button:not(:disabled)').focus();
});
document.addEventListener('focusin',event=>{
  if(document.body.classList.contains('sidebar-open') && !byId('sidebar').contains(event.target)
      && event.target!==byId('nav-toggle'))closeMenu();
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape' && document.body.classList.contains('sidebar-open')) {
    closeMenu();byId('nav-toggle').focus();
  }
});
byId('body-size').addEventListener('change',event=>{
  document.body.classList.toggle('read-large',event.target.value==='18');
  document.body.classList.toggle('read-largest',event.target.value==='20');
});
byId('logout').addEventListener('click',async()=>{
  clearTimeout(timer);
  if(!await safely(()=>controller.save()) || !controller.canLeave())return;
  if(await safely(()=>api.request('/api/logout',{method:'POST'}))) {
    closed=true;controller.close();window.location.assign('/login');
  }
});
window.addEventListener('beforeunload',event=>{
  if(!controller.canLeave() || composer.isComposing()) {event.preventDefault();event.returnValue='';}
});
window.addEventListener('pagehide',()=>{closed=true;++listEpoch;clearTimeout(timer);composer.dispose();controller.close();});

drawState(controller.state);
await safely(async()=>{
  const identifier=document.body.dataset.conversationId;
  const opening=identifier?open(identifier):Promise.resolve(true);
  const metadata=Promise.allSettled([api.session(),api.skills()]);
  await opening;
  const [session,catalog]=await metadata;
  if(session.status==='fulfilled')byId('account-name').textContent=session.value.username;
  else failure(session.reason);
  if(catalog.status==='fulfilled')renderer.capability(catalog.value);
  else failure(catalog.reason);
  await loadList();
});
