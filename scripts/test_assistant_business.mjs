import assert from 'node:assert/strict';
import test from 'node:test';
import {createBusinessController,businessWorkflow} from '../src/cn_contract/web/static/assistant-business.mjs';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

test('clear intents route without a module selection; ordinary chat stays ordinary',()=>{
  assert.equal(businessWorkflow({text:'帮我审查这个合同'}),'contract');
  assert.equal(businessWorkflow({text:'整理这个案件'}),'case');
  assert.equal(businessWorkflow({text:'站在对方律师和法官角度模拟'}),'court');
  assert.equal(businessWorkflow({text:'客户咨询：这是虚构客户的情况'}),'sales');
  assert.equal(businessWorkflow({text:'你好'}),null);
  assert.equal(businessWorkflow({text:'你好',business:{items:[{task_id:'old'}]}}),null);
  assert.equal(businessWorkflow({text:'整理这个案件并进行模拟法庭',business:{items:[{task_id:'old'}]}}),'clarify');
  assert.equal(businessWorkflow({text:'再补充一份材料',business:{items:[{task_id:'old'}]}}),'continue');
});

test('unknown write is recovered only by GET and keeps one request identity',async()=>{
  const scope={conversation_id:'c',input_revision:0};
  const state={id:'c',text:'客户咨询：合成内容',savedText:'客户咨询：合成内容',view:{scope,composer_revision:0},status:'saved'};
  let writes=0,reads=0;
  const result={run_id:'r',request_id:'key',task_id:'t',workflow:'sales',scope:{...scope,input_revision:1}};
  const api={submitBusiness:async()=>{writes++;throw {code:'NETWORK_UNKNOWN',status:0};},
    findBusiness:async()=>{reads++;return result;},getBusinessHistory:async()=>[]};
  const host={state,readonly:false,uuid:()=> 'key',notify:()=>{},token:()=>1,current:()=>true,
    blocked:()=>false,saveDraft:async()=>true,refreshDraft:async()=>true,
    accept:()=>{state.text='';state.savedText='';},fail:()=>false};
  const work=createBusinessController(api,host);
  assert.equal(await work.send(),false);
  assert.equal(state.business.phase,'unknown');
  assert.equal(writes,1);
  await work.send();
  assert.equal(writes,1);assert.equal(reads,1);assert.equal(state.text,'');
});

test('selected task follows an explicit restart and subsequent continuation',async()=>{
  const scope={conversation_id:'c',input_revision:0};
  const state={id:'c',text:'重新审查合同',view:{scope,composer_revision:0},status:'saved'};
  const bodies=[];
  const api={submitBusiness:async(cid,body)=>{bodies.push(body);return {run_id:'run-'+bodies.length,
    request_id:body.request_id,task_id:'new-task',workflow:'contract',scope:{...scope,input_revision:1}};}};
  const work=createBusinessController(api,{state,readonly:false,uuid:()=> 'key-'+bodies.length,
    notify:()=>{},token:()=>1,current:()=>true,blocked:()=>false,saveDraft:async()=>true,
    refreshDraft:async()=>true,accept:()=>{state.text='';},fail:()=>false});
  state.business.items=[{task_id:'old-task',workflow:'contract'}];work.select('old-task');
  assert.equal(await work.send(),true);
  assert.equal(bodies[0].new_task,true);assert.equal(bodies[0].task_id,undefined);
  state.text='继续补充';assert.equal(await work.send(),true);
  assert.equal(bodies[1].task_id,'new-task');
});

test('refresh after an unknown business write preserves new typing without inventing a conflict',async()=>{
  let view={scope:{workspace_id:'w',conversation_id:'c',scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:0},composer_revision:0,draft_input:'',messages:[]};
  let result,writes=0,lookups=0,seq=0;
  const api={getConversation:async()=>structuredClone(view),
    saveDraft:async(cid,body)=>{view={...view,draft_input:body.content,composer_revision:view.composer_revision+1};return structuredClone(view);},
    submitBusiness:async(cid,body)=>{
      writes++;view={...view,scope:{...view.scope,input_revision:view.scope.input_revision+1},
        composer_revision:view.composer_revision+1,draft_input:'',messages:[{id:'input',role:'user',content:body.content}]};
      result={request_id:body.request_id,run_id:'run',message_id:'input',task_id:'task',workflow:'sales',scope:view.scope};
      throw {code:'NETWORK_UNKNOWN',status:0};
    },findBusiness:async()=>{lookups++;return structuredClone(result);}};
  const controller=createDraftController(api,{uuid:()=>String(++seq)});
  await controller.open('c');controller.edit('客户咨询：独立虚构事项');
  assert.equal(await controller.send(),false);
  controller.edit('等待期间的新输入');
  assert.equal(await controller.refresh(),false);
  assert.equal(controller.state.conflict,null);
  assert.equal(await controller.refreshGeneration(),true);
  assert.equal(controller.state.conflict,null);
  assert.equal(controller.state.text,'等待期间的新输入');
  assert.equal(writes,1);assert.equal(lookups,1);
});
