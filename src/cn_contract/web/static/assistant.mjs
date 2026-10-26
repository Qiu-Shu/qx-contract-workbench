import * as api from './assistant-api.mjs';
import {createDraftController} from './assistant-state.mjs';
import {createRenderer,errorText} from './assistant-render.mjs';
import {bindComposer} from './assistant-composer.mjs';
import {bindMaterials} from './assistant-materials.mjs';
import {bindCitations} from './assistant-citations.mjs';
import {bindProfile} from './assistant-profile.mjs';
import {bindTaskDrafts} from './assistant-tasks.mjs';
import {bindWeixinAuthorization} from './assistant-weixin.mjs';
import {bindWeixinGenerations} from './assistant-weixin-generations.mjs';
import {bindOutputs} from './assistant-outputs.mjs';
import {bindEvidenceWorksheet} from './evidence-worksheet.mjs';
import {bindReceptionWorksheet} from './reception-worksheet.mjs';

const byId=id=>document.getElementById(id);
const readonly=document.body.dataset.readonly==='true';
let composer, materials, citations, profile, outputs, worksheet, evidence, tasks, weixin, weixinHistory, timer, listCursor=null, listEpoch=0, closed=false;
let generationTimer, pollTimer, generationKey=null;
let pendingRoute=document.body.dataset.conversationId || null;
const renderer=createRenderer(document,{isComposing:()=>composer?.isComposing(),onCitation:(id,trigger)=>void citations.open(id,trigger),
  onToggleCitation:id=>controller.toggleContextCitation(id),
  onPreviewContext:()=>void safely(()=>controller.previewContext())});
const controller=createDraftController(api,{readonly,
  nativeAuthorization:typeof window.desktopAssistant?.authorizeGeneration==='function'
    ?value=>window.desktopAssistant.authorizeGeneration(value):null,
  nativeContextAuthorization:typeof window.desktopAssistant?.authorizeContext==='function'
    ?value=>window.desktopAssistant.authorizeContext(value):null,
  nativeProfileAuthorization:typeof window.desktopAssistant?.authorizeProfile==='function'
    ?value=>window.desktopAssistant.authorizeProfile(value):null,
  onChange:state=>{
    drawState(state);
    renderer.selected(state.id);
    coordinateGeneration(state);
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
  materials?.state(state);citations?.state(state);profile?.state(state);tasks?.state(state);
  outputs?.state(state);
  worksheet?.state(state);evidence?.state(state);
  weixin?.state(state);
  weixinHistory?.state(state);
  if(pendingRoute && !state.id && state.status!=='revoked') {
    byId('composer').disabled=true;byId('save-draft').disabled=true;byId('send').disabled=true;
    byId('add-material').disabled=true;
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
// Read only after a stable saved snapshot; draft edits never dispatch a model call.
function coordinateGeneration(state) {
  clearTimeout(generationTimer);
  if(closed || !state.id || !state.view || state.status==='revoked') {
    generationKey=null;clearTimeout(pollTimer);pollTimer=null;return;
  }
  if(state.generation.phase!=='tracking' && state.research?.phase!=='tracking' && state.context?.phase!=='tracking') {clearTimeout(pollTimer);pollTimer=null;}
  else if(!pollTimer)pollTimer=setTimeout(async()=>{
    pollTimer=null;
    if(closed)return;
    if(document.hidden) {coordinateGeneration(controller.state);return;}
    const id=controller.state.id;
    await safely(()=>controller.refresh());
    if(!closed && id===controller.state.id)await safely(()=>controller.refreshGeneration());
    if(!closed)coordinateGeneration(controller.state);
  },2000);
  // Editing and then undoing can restore the same text after invalidating its capability.
  if(!state.generation.capability && ['idle','tracking'].includes(state.generation.phase))generationKey=null;
  if(state.loading || state.dirty || state.conflict || state.materialAction ||
      ['saving','error'].includes(state.status) ||
      ['checking','confirming','submitting','unknown'].includes(state.generation.phase) ||
      ['checking','submitting','unknown'].includes(state.research?.phase) ||
      ['checking','confirming','submitting','unknown'].includes(state.context?.phase))return;
  const key=JSON.stringify([state.view.scope,state.view.composer_revision,state.savedText,
    state.skill,state.view.messages.map(message=>message.id)]);
  if(key!==generationKey)generationTimer=setTimeout(()=>{
    generationKey=key;void safely(()=>controller.refreshGeneration());
  },0);
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
  if(evidence?.hasPending()||worksheet?.hasPending()||tasks?.hasPending()||weixin?.hasPending()||weixinHistory?.hasPending()){notice('请先保存或清空本次内容；结果未知时请先查询，再切换对话。');return;}
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
  onSend:()=>{clearTimeout(timer);void safely(()=>controller.send());},
});
materials=bindMaterials({controller,readonly,onPreview:()=>{citations?.close();profile?.close();outputs?.close();}});
citations=bindCitations({controller,onOpen:()=>{materials.close();profile?.close();outputs?.close();}});
profile=bindProfile({controller,api,readonly,onOpen:()=>{materials.close();citations.close();outputs?.close();}});
outputs=bindOutputs({controller,api,readonly,onOpen:()=>{materials.close();citations.close();profile.close();}});
evidence=bindEvidenceWorksheet({controller,api,readonly});
worksheet=bindReceptionWorksheet({controller,api,readonly,onPrepared:()=>{clearTimeout(timer);byId('composer').focus();}});
tasks=bindTaskDrafts({controller,api,readonly});
const updateWeixinControls=()=>{weixin?.updateControls();weixinHistory?.updateControls();};
weixin=bindWeixinAuthorization({controller,api,readonly,isBlocked:()=>weixinHistory?.hasPending(),onActivityChange:updateWeixinControls});
weixinHistory=bindWeixinGenerations({controller,api,readonly,getAuthorization:()=>weixin.projection(),
  isBlocked:()=>weixin.hasPending(),onActivityChange:updateWeixinControls,onSaved:()=>weixin.refresh()});

const examples={client_reply:'这是客户的咨询，帮我理清诉求并起草回复：',
  material_organize:'请帮我整理这次咨询的事实线索和待补材料：',
  contract_review:'请帮我核对这份合同需要重点审查的问题：',
  content_draft:'请围绕这个法律主题起草一段文案：',
  legal_research:''};
document.querySelectorAll('[data-skill]').forEach(button=>button.addEventListener('click',()=>{
  if(button.dataset.skill==='contract_review'){closeMenu();tasks.open();return;}
  controller.selectSkill(button.dataset.skill);
  if(examples[button.dataset.skill] && !controller.state.text && !composer.isComposing()) {
    controller.edit(examples[button.dataset.skill]);
    clearTimeout(timer);timer=setTimeout(()=>void safely(()=>controller.save()),650);
  }
  closeMenu();byId('composer').focus();
}));
byId('clear-skill').addEventListener('click',()=>{controller.selectSkill(null);byId('composer').focus();});
byId('save-draft').addEventListener('click',()=>{clearTimeout(timer);void safely(()=>
  controller.state.status==='error'?controller.retry():controller.save());});
byId('new-conversation').addEventListener('click',async()=>{
  if(evidence.hasPending()||worksheet.hasPending()||tasks.hasPending()||weixin.hasPending()||weixinHistory.hasPending()){notice('请先保存或清空本次内容；结果未知时请先查询，再新建对话。');return;}
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
byId('refresh-run').addEventListener('click',()=>void (pendingRoute?open(pendingRoute):safely(async()=>{
  const id=controller.state.id;
  await controller.refresh();
  if(id===controller.state.id)await controller.refreshGeneration();
})));
byId('recover-generation').addEventListener('click',()=>void safely(()=>controller.refreshGeneration()));
byId('preview-context').addEventListener('click',()=>void safely(()=>controller.previewContext()));
byId('cancel-run').addEventListener('click',()=>void safely(()=>controller.cancel()));
// Desktop model switch: a saved credential can flip Flash/V4 Pro in place.
const desktopBridge=window.desktopAssistant;
function setDesktopModel(next){controller.state.desktopModel=next;drawState(controller.state);}
async function refreshModelInfo(){
  if(typeof desktopBridge?.modelStatus!=='function')return;
  try{
    const result=await desktopBridge.modelStatus();
    if(closed||!result?.ok)return;
    const runtime=result.runtime;
    setDesktopModel({available:true,busy:false,
      model:runtime?.state==='configured'?runtime.model:null});
  }catch{/* the button simply stays hidden */}
}
void refreshModelInfo();
byId('switch-model').addEventListener('click',async()=>{
  if(typeof desktopBridge?.modelSwitch!=='function'||!controller.state.desktopModel?.available)return;
  setDesktopModel({...controller.state.desktopModel,busy:true});
  const fail=code=>{
    if(closed)return;
    setDesktopModel({available:true,busy:false,model:controller.state.desktopModel?.model??null});
    byId('generation-status').dataset.kind='error';
    byId('generation-status').textContent=code==='UNCONFIGURED'
      ?'尚未配置本次运行的模型。请从菜单打开“主模型设置”完成配置。'
      :'模型切换未完成。请稍后重试，或从菜单打开“主模型设置”。';
  };
  try{
    const result=await desktopBridge.modelSwitch();
    if(closed)return;
    if(result?.ok===true&&result.runtime?.state==='configured'){
      setDesktopModel({available:true,busy:false,model:result.runtime.model});
      await safely(()=>controller.refreshGeneration());
    }else fail(result?.code);
  }catch{fail();}
});
// Returning from the desktop settings page can change the model runtime;
// re-check the saved draft's generation conditions on focus.
window.addEventListener('focus',()=>{
  if(!closed&&controller.state.id&&!controller.state.loading)
    void safely(()=>controller.refreshGeneration());
});
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
  if(evidence.hasPending()||worksheet.hasPending()||tasks.hasPending()||weixin.hasPending()||weixinHistory.hasPending()){notice('仍有未保存内容或未查明的结果，请先处理后退出。');return;}
  clearTimeout(timer);
  if(!await safely(()=>controller.save()) || !controller.canLeave())return;
  if(await safely(()=>api.request('/api/logout',{method:'POST'}))) {
    closed=true;weixin.dispose();weixinHistory.dispose();controller.close();window.location.assign('/login');
  }
});
window.addEventListener('beforeunload',event=>{
  if(!controller.canLeave() || composer.isComposing() || materials.hasSelection() || evidence.hasPending() || worksheet.hasPending() || tasks.hasPending() || weixin.hasPending() || weixinHistory.hasPending()) {event.preventDefault();event.returnValue='';}
});
window.addEventListener('pagehide',()=>{
  closed=true;++listEpoch;clearTimeout(timer);clearTimeout(generationTimer);clearTimeout(pollTimer);
  composer.dispose();materials.dispose();citations.dispose();profile.close();outputs.dispose();worksheet.dispose();evidence.dispose();tasks.dispose();weixin.dispose();weixinHistory.dispose();controller.close();
});

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
