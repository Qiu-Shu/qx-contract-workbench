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
  assert.equal(businessWorkflow({text:'我是甲方，帮我审查并给出最小修改建议',materials:{items:[{}]}}),'contract');
  assert.equal(businessWorkflow({text:'整理这个案件并起草起诉状'}),'case');
  assert.equal(businessWorkflow({text:'根据现有材料模拟开庭'}),'court');
});

function directFixture({unknown=false,canceled=false,onSave=null,onAuthorize=null,cancelledParent=false}={}) {
  let view={scope:{workspace_id:'w',conversation_id:'c',scope_kind:'conversation',scope_ref:null,
    binding_revision:1,input_revision:0,materials_revision:1},composer_revision:0,draft_input:'',messages:[]};
  let sequence=0,receipt,submitted,businessBody,automatic=false;
  const calls=[],items=[];
  const bump=()=>{view={...view,scope:{...view.scope,input_revision:view.scope.input_revision+1},
    composer_revision:view.composer_revision+1,draft_input:''};};
  const api={getConversation:async()=>structuredClone(view),
    getMaterials:async()=>({scope:structuredClone(view.scope),items:[{attachment_id:'file',parse_revision:1}]}),
    saveDraft:async(cid,body)=>{view={...view,draft_input:body.content,composer_revision:view.composer_revision+1};
      onSave?.(controller,body);return structuredClone(view);},
    getBusinessHistory:async()=>structuredClone(items),
    cancelRun:async()=>{calls.push('cancel');view.latest_run={id:'parent',state:'cancelled',cancel_requested:true};},
    submitBusiness:async(cid,body)=>{businessBody=body;calls.push('business');bump();
      view.latest_run={id:'parent',state:cancelledParent?'cancelled':'awaiting_input',cancel_requested:cancelledParent};
      receipt={request_id:body.request_id,run_id:'parent',message_id:'input',task_id:'task',workflow:body.workflow,
        scope:structuredClone(view.scope)};items.push(receipt);return receipt;},
    submitMaterialGeneration:async(cid,body)=>{calls.push('model');submitted=body;bump();
      if(unknown)throw {code:'NETWORK_UNKNOWN',status:0};
      return {request_id:body.request_id,input_format:'material-business-v1',scope:structuredClone(view.scope)};},
    findGenerationRequest:async(cid,id)=>{calls.push('lookup');assert.equal(id,submitted.request_id);
      return {request_id:id,input_format:'material-business-v1',scope:structuredClone(view.scope)};}};
  const controller=createDraftController(api,{automaticIntake:async()=>automatic,uuid:()=>String(++sequence),nativeMaterialAuthorization:async value=>{
    calls.push('authorize');assert.equal(value.parent_business_run_id,'parent');await onAuthorize?.(controller);return {ok:!canceled};}});
  return {controller,calls,api,setAutomatic:value=>automatic=value,get businessBody(){return businessBody;},get submitted(){return submitted;}};
}

test('one chat send chains contract preparation and native material execution without a second action',async()=>{
  const f=directFixture(),c=f.controller;await c.open('c');
  c.edit('我是甲方，帮我审查并给出最小修改建议');
  assert.equal(await c.send(),true);
  assert.deepEqual(f.calls,['business','authorize','model']);
  assert.equal(f.submitted.parent_business_run_id,'parent');assert.equal(c.state.text,'');
  await c.refreshGeneration();assert.equal(f.calls.filter(x=>x==='model').length,1);
});

test('automatic material send honors native cancellation and explicit wait instructions',async()=>{
  for(const [options,prompt,expected] of [
    [{canceled:true},'审查合同',['business','authorize']],
    [{},'审查合同，还有附件，稍等上传完再开始',['business']],
  ]){
    const f=directFixture(options);await f.controller.open('c');f.controller.edit(prompt);
    await f.controller.send();assert.deepEqual(f.calls,expected);
  }
});

test('unknown automatic material submission is only looked up with its original identity',async()=>{
  const f=directFixture({unknown:true}),c=f.controller;await c.open('c');c.edit('审查合同');
  assert.equal(await c.send(),false);assert.equal(c.state.materialGeneration.phase,'unknown');
  assert.equal(await c.send(),true);
  assert.deepEqual(f.calls,['business','authorize','model','lookup']);
});

test('cancelled parent cannot continue before or during native authorization',async()=>{
  const before=directFixture({cancelledParent:true});await before.controller.open('c');before.controller.edit('审查合同');
  await before.controller.send();assert.deepEqual(before.calls,['business']);
  const during=directFixture({onAuthorize:async c=>{assert.equal(await c.cancel(),true);}});
  await during.controller.open('c');during.controller.edit('审查合同');await during.controller.send();
  assert.deepEqual(during.calls,['business','authorize','cancel']);
});

test('text-only sales acknowledgements keep a single task for natural follow-ups',async()=>{
  const state={id:'c',text:'客户咨询：借款纠纷',view:{scope:{conversation_id:'c',input_revision:0},composer_revision:0},status:'saved'};
  const bodies=[];
  const work=createBusinessController({submitBusiness:async(cid,body)=>{bodies.push(body);return {request_id:body.request_id,
    task_id:'sales-task',workflow:'sales',run_id:'r'+bodies.length,scope:{conversation_id:'c',input_revision:1}};}},
  {state,readonly:false,uuid:()=> 'key'+bodies.length,notify:()=>{},token:()=>1,current:()=>true,blocked:()=>false,
    saveDraft:async()=>true,refreshDraft:async()=>true,accept:()=>{state.text='';},fail:()=>false});
  assert.equal(await work.send(),true);
  for(const text of ['客户叫张三，借款已经到期，对方未还','请把给客户的回复缩短到两句话']){
    state.text=text;assert.equal(businessWorkflow(state),'continue');assert.equal(await work.send(),true);
    assert.equal(bodies.at(-1).task_id,'sales-task');
  }
});

test('wait instruction added during draft saving governs the actually submitted task',async()=>{
  let changed=false;
  const f=directFixture({onSave:c=>{if(!changed){changed=true;c.edit('审查合同，还有附件，稍等');}}});
  await f.controller.open('c');f.controller.edit('审查合同');
  assert.equal(await f.controller.send(),true);
  assert.deepEqual(f.calls,['business']);
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

test('attachment follow-up uses the only task and never chooses among several by recency',async()=>{
  for(const count of [1,2]){
    const state={id:'c',text:'把第二条修改得更简洁',view:{scope:{conversation_id:'c',input_revision:0},composer_revision:0},
      status:'saved',materials:{items:[{}]}};let submitted;
    const work=createBusinessController({submitBusiness:async(cid,body)=>{submitted=body;return {request_id:body.request_id,
      run_id:'r',scope:{conversation_id:'c',input_revision:1}};}},{state,readonly:false,uuid:()=> 'key',notify:()=>{},
      token:()=>1,current:()=>true,blocked:()=>false,saveDraft:async()=>true,refreshDraft:async()=>true,accept:()=>{},fail:()=>false});
    state.business.items=Array.from({length:count},(_,i)=>({task_id:'t'+i,workflow:'contract'}));
    await work.send();assert.equal(submitted.task_id,count===1?'t0':undefined);
  }
});

test('automatic task inference cannot override ambiguous intent or survive multiple tasks',async()=>{
  const state={id:'c',text:'',view:{scope:{conversation_id:'c',input_revision:0},composer_revision:0},status:'saved'};
  let items=[{task_id:'a',workflow:'sales',scope:{conversation_id:'c'}}],submitted;
  const work=createBusinessController({getBusinessHistory:async()=>items,submitBusiness:async(cid,body)=>{
    submitted=body;return {request_id:body.request_id,run_id:'clarify',scope:{conversation_id:'c',input_revision:1}};}},
  {state,readonly:false,uuid:()=> 'key',notify:()=>{},token:()=>1,current:()=>true,blocked:()=>false,
    saveDraft:async()=>true,refreshDraft:async()=>true,accept:()=>{},fail:()=>false});
  await work.refresh();assert.equal(state.business.selectedTask,'a');
  state.text='整理这个案件并进行模拟法庭';await work.send();assert.equal(submitted.task_id,undefined);
  await work.refresh();assert.equal(state.business.selectedTask,'a');
  items=[...items,{task_id:'b',workflow:'sales',scope:{conversation_id:'c'}}];await work.refresh();
  assert.equal(state.business.selectedTask,null);
  work.select('a');await work.refresh();assert.equal(state.business.selectedTask,'a');
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


test('desktop explicit send consumes four-workflow intake without readiness delay',async()=>{
  const f=directFixture();const c=f.controller;await c.open('c');
  c.edit('请推演举证和质证的应对');
  f.api.assistJudge=async body=>{assert.equal(body.purpose,'service_intake');return {available:true,result:{status:'ok',scope:body.expected_scope,
    answers:{readiness:{choice:'wait',confidence:1},workflow:{choice:'court',confidence:.95},material_kind:{choice:'judgment',confidence:.95}}}};};
  f.setAutomatic(true);assert.equal(await c.send(),true);
  assert.equal(f.businessBody.workflow,'court');assert.equal(c.state.intakeSuggestion.material_kind,'judgment');
});
test('desktop automatic OFF never calls Jev; explicit choice wins and late text edits discard assistance',async()=>{
  for(const automatic of [false,true]){
    const f=directFixture();await f.controller.open('c');f.setAutomatic(automatic);f.controller.edit('准备庭审应对');f.controller.selectSkill('contract_review');
    let calls=0;f.api.assistJudge=async body=>{calls++;return {available:true,result:{status:'ok',scope:body.expected_scope,
      answers:{workflow:{choice:'court',confidence:.99},material_kind:{choice:'judgment',confidence:.99}}}};};
    await f.controller.send();assert.equal(calls,automatic?1:0);assert.equal(f.businessBody.workflow,'contract');
  }
  const f=directFixture();await f.controller.open('c');f.setAutomatic(true);f.controller.edit('准备庭审');
  let release;f.api.assistJudge=()=>new Promise(r=>release=r);const sent=f.controller.send();
  await new Promise(setImmediate);f.controller.edit('另外的内容');release({available:true,result:{status:'ok',answers:{workflow:{choice:'court',confidence:1}}}});
  assert.equal(await sent,false);assert.deepEqual(f.calls,[]);assert.equal(f.controller.state.text,'另外的内容');
});


test('repeated desktop Enter during shared Jev wait sends one judgment and one business request',async()=>{
  const f=directFixture();await f.controller.open('c');f.setAutomatic(true);f.controller.edit('请推演举证与质证');
  let release,judgments=0;f.api.assistJudge=body=>{judgments++;return new Promise(r=>release=()=>r({available:true,result:{status:'ok',scope:body.expected_scope,
    answers:{workflow:{choice:'court',confidence:.95},material_kind:{choice:'judgment',confidence:.9}}}}));};
  const first=f.controller.send();await new Promise(setImmediate);
  assert.equal(await f.controller.send(),false);assert.equal(judgments,1);release();assert.equal(await first,true);
  assert.equal(judgments,1);assert.equal(f.calls.filter(x=>x==='business').length,1);
});
test('changing desktop conversation or retyping identical text discards a pending shared judgment',async()=>{
  for(const change of [async c=>c.newConversation(),async c=>{c.edit('另外文字');c.edit('请推演举证与质证');}]){
    const f=directFixture();await f.controller.open('c');f.setAutomatic(true);f.controller.edit('请推演举证与质证');
    let release;f.api.assistJudge=body=>new Promise(r=>release=()=>r({available:true,result:{status:'ok',scope:body.expected_scope,
      answers:{workflow:{choice:'court',confidence:.99}}}}));
    const first=f.controller.send();await new Promise(setImmediate);await change(f.controller);release();
    assert.equal(await first,false);assert.deepEqual(f.calls,[]);assert.equal(f.controller.state.intakeSuggestion,null);
  }
});
test('low-confidence, unavailable, timeout and foreign-scope shared suggestions fall back to explicit rule route',async()=>{
  for(const mode of ['low','unavailable','timeout','foreign']){
    const f=directFixture();await f.controller.open('c');f.setAutomatic(true);f.controller.edit('审查合同');
    f.api.assistJudge=async body=>{
      if(mode==='timeout')throw {code:'NETWORK_UNKNOWN',status:0};
      return {available:mode!=='unavailable',result:{status:'ok',scope:mode==='foreign'?{...body.expected_scope,conversation_id:'foreign'}:body.expected_scope,
        answers:{workflow:{choice:'court',confidence:mode==='low'?.6:.99}}}};
    };
    assert.equal(await f.controller.send(),true);assert.equal(f.businessBody.workflow,'contract');
  }
});
