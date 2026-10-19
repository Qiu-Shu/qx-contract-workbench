import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createDraftController} from '../../src/cn_contract/web/static/assistant-state.mjs';
const clone=value=>structuredClone(value);
const sha=value=>createHash('sha256').update(value).digest('hex');
const gate=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const failure=()=>Object.assign(new Error('synthetic unknown response'),{status:0,code:'NETWORK_UNKNOWN'});
function fixture({mode='ready',readonly=false}={}) {
  let server={scope:{workspace_id:'workspace-A',conversation_id:'conversation-A',scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0},draft_input:'原始合成草稿',composer_revision:3,
    messages:[],latest_run:null,next_before:null};
  const calls={approvals:[],submissions:[],lookups:[],saves:0};let number=0;
  const dialog=gate(),opened=gate();let selected=[];
  const api={
    async getConversation(){return clone(server);},
    async getMaterials(){return {scope:clone(server.scope),items:clone(selected),attachments:[]};},
    async saveDraft(_id,body){calls.saves++;server={...server,draft_input:body.content,composer_revision:server.composer_revision+1};return clone(server);},
    async getGenerationCapability(){return {scope:clone(server.scope),composer_revision:server.composer_revision,
      basis:'saved_draft',content_sha256:server.draft_input.trim()?sha(server.draft_input):null,state:mode};},
    async submitGeneration(id,body){calls.submissions.push(clone({id,body}));throw failure();},
    async findGenerationRequest(id,request){calls.lookups.push({id,request});return null;},
  };
  const controller=createDraftController(api,{readonly,uuid:()=>`synthetic-request-${++number}`,
    nativeAuthorization:async input=>{calls.approvals.push(clone(input));opened.resolve();return dialog.promise;}});
  return {controller,calls,api,dialog,opened,get server(){return server;},set server(value){server=value;},
    materials(value){selected=value;},async start(){await controller.open(server.scope.conversation_id);return controller;}};
}
test('independent: ready never bypasses confirmation and repeated clicks share it',async()=>{
  const f=fixture(),c=await f.start();await c.refreshGeneration();assert.equal(c.state.generation.canSend,true);
  const sending=c.send();await f.opened.promise;assert.equal(c.send(),sending);
  assert.equal(f.calls.submissions.length,0);assert.equal(f.calls.approvals.length,1);
  f.dialog.resolve({ok:true});await sending;
  assert.equal(f.calls.submissions.length,1);
  assert.equal(f.calls.submissions[0].body.request_id,f.calls.approvals[0].request_id);
});
test('independent: cancellation preserves saved input and refresh cannot reopen or submit',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
  f.dialog.resolve({ok:false,canceled:true});assert.equal(await sending,false);
  await c.refreshGeneration();assert.equal(c.state.generation.phase,'idle');assert.equal(c.state.generation.error,null);
  assert.equal(c.state.text,'原始合成草稿');assert.equal(c.state.generation.canSend,true);
  assert.equal(f.calls.approvals.length,1);assert.equal(f.calls.submissions.length,0);
});
test('independent: each scope dimension invalidates approval after a fresh backend read',async()=>{
  for(const [field,value] of [['workspace_id','workspace-B'],['conversation_id','conversation-B'],
    ['scope_kind','matter'],['scope_ref','matter-A'],['binding_revision',2],['input_revision',1],['materials_revision',1]]){
    const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
    f.server={...f.server,scope:{...f.server.scope,[field]:value}};
    await c.refresh();f.dialog.resolve({ok:true});await sending;
    assert.equal(f.calls.submissions.length,0,field);
  }
});
test('independent: composer-only revision movement invalidates an otherwise identical draft',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
  f.server={...f.server,composer_revision:4};await c.refresh();f.dialog.resolve({ok:true});await sending;
  assert.equal(f.calls.submissions.length,0);
});
test('independent: text and skill ABA edits cannot reuse the approved snapshot',async()=>{
  for(const kind of ['text','skill']){
    const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
    if(kind==='text'){c.edit('临时修改');c.edit('原始合成草稿');}
    else {c.selectSkill('contract_review');c.selectSkill(null);}
    f.dialog.resolve({ok:true});await sending;assert.equal(f.calls.submissions.length,0,kind);
  }
});
test('independent: selected material blocks approval consumption even if capability incorrectly stays ready',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
  f.materials([{attachment_id:'synthetic-material'}]);await c.refresh();f.dialog.resolve({ok:true});await sending;
  assert.equal(f.calls.submissions.length,0);
});
test('independent: new page, close and revoked ownership discard late approval',async()=>{
  for(const action of ['new','close','revoke']){
    const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
    if(action==='new')await c.newConversation();
    else if(action==='close')c.close();
    else c.revoke({status:401,code:'AUTHORIZATION_REQUIRED'});
    f.dialog.resolve({ok:true});await sending;
    assert.equal(f.calls.submissions.length,0,action);assert.equal(c.state.id,null);
  }
});
test('independent: unknown POST is only looked up by its fixed original request',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;f.dialog.resolve({ok:true});await sending;
  assert.equal(c.state.generation.phase,'unknown');
  for(let i=0;i<3;i++){await c.send();await c.refreshGeneration();}
  assert.equal(f.calls.submissions.length,1);assert.equal(f.calls.approvals.length,1);
  assert.equal(f.calls.lookups.length,6);
  assert.equal(f.calls.lookups.every(value=>value.request===f.calls.approvals[0].request_id),true);
});
test('independent: a draft edited during confirmation waits to save and does not send the old version',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;c.edit('确认期间的新草稿');
  const saving=c.save();assert.equal(f.calls.saves,0);f.dialog.resolve({ok:true});await sending;
  assert.equal(await saving,true);assert.equal(f.calls.saves,1);assert.equal(f.calls.submissions.length,0);
  assert.equal(c.state.savedText,'确认期间的新草稿');
});
test('independent: readonly mode never invokes native confirmation despite ready capability',async()=>{
  const f=fixture({readonly:true}),c=await f.start();await c.refreshGeneration();await c.send();
  assert.equal(c.state.generation.canSend,false);assert.equal(f.calls.approvals.length,0);assert.equal(f.calls.submissions.length,0);
});
test('independent: malformed native approval becomes fixed pre-submit failure, not unknown POST',async()=>{
  const f=fixture(),c=await f.start(),sending=c.send();await f.opened.promise;
  f.dialog.resolve({ok:'true',message:'synthetic-private-detail'});await sending;
  assert.equal(c.state.generation.phase,'error');assert.equal(c.state.generation.error.code,'NATIVE_CONFIRMATION_FAILED');
  assert.equal(JSON.stringify(c.state).includes('synthetic-private-detail'),false);
  await c.refreshGeneration();assert.equal(f.calls.approvals.length,1);assert.equal(f.calls.submissions.length,0);
});
