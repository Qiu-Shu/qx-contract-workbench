import assert from 'node:assert/strict';
import test from 'node:test';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const copy=structuredClone, tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const scope=id=>({workspace_id:'workspace',conversation_id:id,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0});
function fixture({readonly=false,attachments=false}={}) {
  let remote={scope:scope('one'),draft_input:'',composer_revision:0,messages:[],latest_run:null},sequence=0;
  const calls=[],records=new Map(),byRequest=new Map();
  const api={
    async createConversation(){return copy(remote);},
    async getConversation(id){return copy({...remote,scope:{...remote.scope,conversation_id:id}});},
    async getMaterials(){return {scope:copy(remote.scope),items:attachments?[{attachment_id:'file'}]:[],attachments:[]};},
    async saveDraft(id,body){calls.push('save');assert.deepEqual(body.expected_scope,remote.scope);
      remote={...remote,draft_input:body.content,composer_revision:remote.composer_revision+1};return copy(remote);},
    async submitResearch(id,body){
      calls.push(['submit',copy(body)]);assert.equal(body.requested_skill,'legal_research');assert.deepEqual(body.attachment_ids,[]);
      assert.deepEqual(body.expected_scope,remote.scope);assert.equal(body.expected_composer_revision,remote.composer_revision);
      const messageId='message-'+records.size;
      remote={...remote,scope:{...remote.scope,input_revision:remote.scope.input_revision+1},draft_input:'',composer_revision:remote.composer_revision+1};
      const run={id:'run-'+records.size,message_id:messageId,request_id:body.request_id,requested_skill:'legal_research',scope:copy(remote.scope),state:'retrieving'};
      const result={run,receipts:[]};records.set(messageId,result);byRequest.set(body.request_id,result);
      remote.latest_run=run;remote.messages.push({id:messageId,role:'user',content:body.content});return copy(result);
    },
    async findResearchRequest(id,key){calls.push('find');return copy(byRequest.get(key)||null);},
    async getResearchHistory(id,ids){calls.push('history');assert.ok(ids.length<=50);
      return {scope:copy(remote.scope),items:ids.filter(key=>records.has(key)).map(key=>({message_id:key,research:copy(records.get(key))}))};},
  };
  const controller=createDraftController(api,{uuid:()=>`request-${++sequence}`,readonly,
    nativeAuthorization(){assert.fail('local research must never ask for external model approval');}});
  return {api,controller,calls,records,byRequest,get remote(){return remote;},set remote(value){remote=value;}};
}
const sends=f=>f.calls.filter(call=>Array.isArray(call)&&call[0]==='submit');

test('explicit local research saves keywords and dispatches once without model configuration',async()=>{
  const f=fixture(),c=f.controller;c.edit('合成纠纷');c.selectSkill('legal_research');
  const first=c.send(),second=c.send();assert.equal(await first,true);assert.equal(await second,true);
  assert.equal(sends(f).length,1);assert.equal(sends(f)[0][1].content,'合成纠纷');
  assert.equal(c.state.text,'');assert.equal(c.state.research.items.length,1);assert.equal(c.state.research.phase,'tracking');
});
test('skill click alone preserves text and never dispatches',async()=>{
  const f=fixture(),c=f.controller;c.edit('保留原文');c.selectSkill('legal_research');await tick();
  assert.equal(c.state.text,'保留原文');assert.equal(sends(f).length,0);assert.equal(c.state.research.canSend,true);
});
test('readonly, attachments, empty or overlong keyword never dispatch',async()=>{
  for(const options of [{readonly:true},{attachments:true},{text:''},{text:'词'.repeat(201)}]){
    const f=fixture(options),c=f.controller;await c.open('one');c.edit(options.text??'合成关键词');c.selectSkill('legal_research');
    assert.equal(await c.send(),false);assert.equal(sends(f).length,0);
  }
});
test('edit or skill change during save aborts the clicked search',async()=>{
  for(const change of [c=>c.edit('新关键词'),c=>c.selectSkill(null)]){
    const f=fixture(),c=f.controller,gate=deferred(),save=f.api.saveDraft;await c.open('one');
    f.api.saveDraft=async(...args)=>{await gate.promise;return save(...args);};c.edit('原关键词');c.selectSkill('legal_research');
    const sending=c.send();await tick();change(c);gate.resolve();assert.equal(await sending,false);assert.equal(sends(f).length,0);
  }
});
test('unknown registration uses original lookup even after skill changes and never resends',async()=>{
  const f=fixture(),c=f.controller,submit=f.api.submitResearch;await c.open('one');c.edit('原关键词');c.selectSkill('legal_research');
  f.api.submitResearch=async(...args)=>{await submit(...args);throw {code:'NETWORK_UNKNOWN',status:0};};
  assert.equal(await c.send(),false);assert.equal(c.state.research.phase,'unknown');
  c.selectSkill(null);c.edit('新草稿');assert.equal(await c.send(),true);
  assert.equal(sends(f).length,1);assert.equal(f.calls.filter(x=>x==='find').length,1);assert.equal(c.state.text,'新草稿');
});
test('unknown not-found stays unresolved and prevents competing model or material work',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');c.edit('合成关键词');c.selectSkill('legal_research');
  f.api.submitResearch=async()=>{f.calls.push(['submit']);throw {code:'NETWORK_UNKNOWN',status:0};};
  await c.send();c.selectSkill(null);await c.send();assert.equal(await c.save(),false);
  assert.equal(sends(f).length,1);assert.equal(c.state.research.phase,'unknown');assert.equal(c.canLeave(),false);
});
test('registration proof followed by read failure unlocks newer draft without resubmitting',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');c.edit('合成关键词');c.selectSkill('legal_research');
  const read=f.api.getConversation;f.api.getConversation=async()=>{throw {code:'NETWORK_UNKNOWN',status:0};};
  assert.equal(await c.send(),false);f.api.getConversation=read;c.edit('下一份草稿');
  assert.equal(await c.retry(),true);assert.equal(sends(f).length,1);assert.equal(c.state.savedText,'下一份草稿');
});
test('switch and revocation discard late research history immediately',async()=>{
  for(const revoke of [false,true]){
    const f=fixture(),c=f.controller;await c.open('one');c.edit('合成关键词');c.selectSkill('legal_research');await c.send();
    const gate=deferred(),read=f.api.getResearchHistory;f.api.getResearchHistory=async(...args)=>{const result=await read(...args);await gate.promise;return result;};
    const waiting=c.refreshGeneration();await tick();
    if(revoke)c.revoke({code:'AUTHORIZATION_REQUIRED',status:401});else {f.remote={...f.remote,scope:scope('two'),messages:[]};await c.open('two');}
    assert.deepEqual(c.state.research.items,[]);gate.resolve();await waiting;assert.deepEqual(c.state.research.items,[]);
  }
});
test('history rejects unrelated messages and receipt scopes but allows authorized older revisions',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');c.edit('合成关键词');c.selectSkill('legal_research');await c.send();
  const messageId=f.remote.messages[0].id;f.records.get(messageId).run.state='completed';
  f.remote.scope.input_revision++;await c.refresh();assert.equal(await c.refreshGeneration(),true);
  assert.equal(c.state.research.items[0].research.run.scope.input_revision,1);
  f.records.get(messageId).run.scope.conversation_id='someone-else';
  assert.equal(await c.refreshGeneration(),false);assert.equal(c.state.research.phase,'error');
});
test('authorization error clears entire active view and history',async()=>{
  const f=fixture(),c=f.controller;await c.open('one');c.edit('合成关键词');c.selectSkill('legal_research');await c.send();
  f.api.getResearchHistory=async()=>{throw {code:'CROSS_MATTER_DENIED',status:403};};
  await c.refreshGeneration();assert.equal(c.state.status,'revoked');assert.equal(c.state.text,'');assert.deepEqual(c.state.research.items,[]);
});
