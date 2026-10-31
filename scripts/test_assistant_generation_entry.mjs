import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {createDraftController} from '../src/cn_contract/web/static/assistant-state.mjs';

const clone=structuredClone, sha=value=>createHash('sha256').update(value).digest('hex');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const source=readFileSync(new URL('../src/cn_contract/web/static/assistant.mjs',import.meta.url),'utf8');
const start=source.indexOf('function coordinateGeneration(state)');
const end=source.indexOf('async function loadList(',start);
assert.ok(start>=0&&end>start);
const coordinateSource=source.slice(start,end);
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const scope=id=>({workspace_id:'w',conversation_id:id,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0});
function fixture({initial='合成文字',nativeAuthorization,nativeMaterialAuthorization}={}) {
  let remote={scope:scope('one'),draft_input:initial,composer_revision:1,messages:[],latest_run:null};
  const calls=[],timers=new Map(),pendingReads=new Set();let sequence=0,coordinator;
  const api={
    async getConversation(id){calls.push('view');return clone({...remote,scope:{...remote.scope,conversation_id:id}});},
    async saveDraft(id,body){calls.push('save');remote={...remote,draft_input:body.content,composer_revision:remote.composer_revision+1};return clone(remote);},
    async getGenerationCapability(){calls.push('cap');return {scope:clone(remote.scope),composer_revision:remote.composer_revision,basis:'saved_draft',content_sha256:remote.draft_input.trim()?sha(remote.draft_input):null,state:'ready'};},
    async submitGeneration(){calls.push('POST');throw Object.assign(Error('lost'),{code:'NETWORK_UNKNOWN',status:0});},
    async submitMaterialGeneration(){calls.push('material-POST');throw Object.assign(Error('lost'),{code:'NETWORK_UNKNOWN',status:0});},
    async findGenerationRequest(){calls.push('find');return null;},
    async getGenerationHistory(id,ids){calls.push('history');return {scope:clone(remote.scope),items:[]};},
  };
  const c=createDraftController(api,{uuid:()=>`synthetic-${++sequence}`,onChange:s=>coordinator?.(s),nativeAuthorization,nativeMaterialAuthorization});
  const document={hidden:false};
  const factory=new Function('controller','document','safely','setTimeout','clearTimeout',
    'let closed=false,generationTimer,pollTimer,generationKey=null;'+coordinateSource+';return coordinateGeneration;');
  coordinator=factory(c,document,action=>{const task=Promise.resolve().then(action).finally(()=>pendingReads.delete(task));pendingReads.add(task);return task;},
    (fn,delay)=>{const id=++sequence;timers.set(id,{fn,delay});return id;},id=>timers.delete(id));
  async function drainZero() {
    for(let loops=0;loops<20;loops++) {
      const zero=[...timers].filter(([,timer])=>timer.delay===0);
      for(const [id,timer] of zero){timers.delete(id);await timer.fn();}
      await Promise.all([...pendingReads]);await tick();
      if(![...timers.values()].some(timer=>timer.delay===0))break;
    }
  }
  return {api,c,calls,document,timers,drainZero,coordinator,get remote(){return remote;},set remote(value){remote=value;}};
}

async function acceptedEntryFixture(material) {
  const f=fixture({initial:material?'审查这份虚构合同':'合成文字',
    ...(material?{nativeMaterialAuthorization:async()=>({ok:true})}:{})});
  let businessResult=null,attempt=null,failRead=false;
  const getConversation=f.api.getConversation;
  f.api.getConversation=async id=>{
    if(failRead){failRead=false;f.calls.push('view-lost');throw {code:'NETWORK_UNKNOWN',status:0};}
    return getConversation(id);
  };
  if(material){
    f.remote={...f.remote,scope:{...f.remote.scope,materials_revision:1}};
    f.api.getMaterials=async()=>({scope:clone(f.remote.scope),items:[{attachment_id:'fictional',parse_revision:1}]});
    f.api.submitBusiness=async(id,body)=>{
      f.calls.push('business-POST');
      const next={...body.expected_scope,input_revision:body.expected_scope.input_revision+1};
      businessResult={request_id:body.request_id,run_id:'parent',message_id:'business-message',task_id:'task',workflow:'contract',scope:next};
      f.remote={...f.remote,scope:next,draft_input:'',composer_revision:body.expected_composer_revision+1,
        messages:[{id:'business-message',role:'user',content:body.content}]};
      return clone(businessResult);
    };
    f.api.getBusinessHistory=async()=>businessResult?[clone(businessResult)]:[];
  }
  const submit=async(id,body)=>{
    f.calls.push(material?'material-POST':'POST');
    const next={...body.expected_scope,input_revision:body.expected_scope.input_revision+1};
    attempt={id:'accepted-attempt',run_id:'accepted-run',scope:next,state:'reserved',output:null,
      ...(material?{input_format:'material-business-v1'}:{})};
    f.remote={...f.remote,scope:next,draft_input:'',composer_revision:body.expected_composer_revision+1,
      messages:[...f.remote.messages,{id:'model-message',role:'user',content:body.content||'审查这份虚构合同'}]};
    failRead=true;
    return clone(attempt);
  };
  f.api[material?'submitMaterialGeneration':'submitGeneration']=submit;
  f.api.getGenerationHistory=async()=>{
    f.calls.push('history');
    if(!attempt)return {scope:clone(f.remote.scope),items:[]};
    return {scope:clone(f.remote.scope),items:[{message_id:'model-message',attempt:{...clone(attempt),state:'received',
      output:{id:'saved-output',run_id:attempt.run_id,scope:clone(attempt.scope),candidate:{text:'已保存的虚构分析',citations:[]}}}}]};
  };
  await f.c.open('one');await f.drainZero();
  return f;
}

for(const material of [false,true])test(`${material?'material':'plain'} accepted entry recovers a lost draft read through existing polling without resubmission`,async()=>{
  const f=await acceptedEntryFixture(material),sent=await f.c.send();
  assert.equal(f.c.state.status,'error');
  assert.equal(f.c.state.error.code,'NETWORK_UNKNOWN');
  assert.equal(f.c.state.generation.phase,'tracking','acknowledged generation must keep a read-only recovery poll');
  assert.equal(sent,false,'failed draft read is not reported as a completed refresh');
  assert.ok([...f.timers.values()].some(timer=>timer.delay===2000));
  f.c.edit('新问题仍待发送');
  const [id,poll]=[...f.timers].find(([,timer])=>timer.delay===2000);
  f.timers.delete(id);await poll.fn();await f.drainZero();
  assert.equal(f.c.state.text,'新问题仍待发送');
  assert.equal(f.c.state.error,null);assert.equal(f.c.state.generation.phase,'idle');
  assert.equal(f.c.state.generation.items[0].attempt.output.candidate.text,'已保存的虚构分析');
  assert.equal(f.calls.filter(call=>call===(material?'material-POST':'POST')).length,1);
  assert.equal(f.calls.filter(call=>call==='find').length,0,'registration is already proven');
  assert.equal(f.calls.filter(call=>call==='business-POST').length,material?1:0);
  assert.equal([...f.timers.values()].some(timer=>timer.delay===2000),false);
});

test('material recovery polling stops on revoked access without restoring the saved output',async()=>{
  const f=await acceptedEntryFixture(true);await f.c.send();
  f.api.getConversation=async()=>{throw {code:'AUTHORIZATION_REQUIRED',status:401};};
  const [id,poll]=[...f.timers].find(([,timer])=>timer.delay===2000);
  f.timers.delete(id);await poll.fn();await f.drainZero();
  assert.equal(f.c.state.status,'revoked');assert.equal(f.c.state.id,null);
  assert.deepEqual(f.c.state.generation.items,[]);
  assert.equal([...f.timers.values()].some(timer=>timer.delay===2000),false);
  assert.equal(f.calls.filter(call=>call==='material-POST').length,1);
});

test('a late material recovery read cannot restore state after access is revoked',async()=>{
  const f=await acceptedEntryFixture(true);await f.c.send();
  const gate=deferred(),entered=deferred();
  f.api.getConversation=()=>{entered.resolve();return gate.promise;};
  const [id,poll]=[...f.timers].find(([,timer])=>timer.delay===2000);
  f.timers.delete(id);const reading=poll.fn();await entered.promise;
  f.c.revoke({code:'AUTHORIZATION_REQUIRED',status:401});gate.resolve(clone(f.remote));
  await reading;await f.drainZero();
  assert.equal(f.c.state.status,'revoked');assert.equal(f.c.state.id,null);
  assert.deepEqual(f.c.state.generation.items,[]);
  assert.equal(f.calls.filter(call=>call==='material-POST').length,1);
});

test('entry rechecks readiness after input changes and returns to the saved text',async()=>{
  const f=fixture();await f.c.open('one');await f.drainZero();assert.equal(f.c.state.generation.canSend,true);
  f.c.edit('临时增加的一句');f.c.edit('合成文字');await f.c.save();await f.drainZero();
  assert.equal(f.c.state.generation.canSend,true,'unchanged saved text must become sendable again after capability invalidation');
});

test('entry rechecks readiness after a skill selection is immediately cancelled',async()=>{
  const f=fixture();await f.c.open('one');await f.drainZero();assert.equal(f.c.state.generation.canSend,true);
  f.c.selectSkill('client_reply');f.c.selectSkill(null);await f.drainZero();
  assert.equal(f.c.state.generation.canSend,true,'restoring the previous selection must not strand the send button');
});

test('unknown network outcome repeated send and refresh use original lookup without resubmission',async()=>{
  const f=fixture();await f.c.open('one');await f.drainZero();await f.c.send();
  await f.c.send();await f.c.refreshGeneration();await f.drainZero();
  assert.equal(f.calls.filter(x=>x==='POST').length,1);assert.equal(f.calls.filter(x=>x==='find').length,2);
  assert.equal(f.c.state.generation.phase,'unknown');assert.equal(f.c.state.text,'合成文字');
});

test('late capability success cannot authorize another conversation',async()=>{
  const f=fixture(),gate=deferred(),normal=f.api.getGenerationCapability;
  await f.c.open('one');f.api.getGenerationCapability=async()=>{const value=await normal();await gate.promise;return value;};
  const reading=f.c.refreshGeneration();await tick();
  f.remote={...f.remote,scope:scope('two')};await f.c.open('two');gate.resolve();await reading;
  assert.equal(f.c.state.id,'two');assert.equal(f.c.state.generation.canSend,false);assert.deepEqual(f.c.state.generation.items,[]);
});

test('history response for a former binding is rejected and cannot be displayed',async()=>{
  const f=fixture();f.remote.messages=[{id:'synthetic-message',role:'user',content:'来源'}];
  await f.c.open('one');f.api.getGenerationHistory=async()=>({scope:clone(f.remote.scope),items:[{message_id:'synthetic-message',
    attempt:{id:'attempt',run_id:'run',scope:{...scope('one'),binding_revision:0},state:'received',output:null}}]});
  assert.equal(await f.c.refreshGeneration(),false);assert.deepEqual(f.c.state.generation.items,[]);
  assert.equal(f.calls.filter(x=>x==='POST').length,0);
});

test('a delayed history authorization error after revocation cannot restore old state',async()=>{
  const f=fixture(),gate=deferred(),started=deferred();f.remote.messages=[{id:'synthetic-message',role:'user',content:'来源'}];
  await f.c.open('one');f.api.getGenerationHistory=()=>{started.resolve();return gate.promise;};
  const reading=f.c.refreshGeneration();await started.promise;f.c.revoke({code:'AUTHORIZATION_REQUIRED',status:401});
  gate.reject({code:'CROSS_MATTER_DENIED',status:403});await reading;
  assert.equal(f.c.state.id,null);assert.equal(f.c.state.text,'');assert.equal(f.c.state.status,'revoked');
  assert.deepEqual(f.c.state.generation.items,[]);
});

test('a failed capability read is attempted once and does not create an automatic retry loop',async()=>{
  const f=fixture();f.api.getGenerationCapability=async()=>{f.calls.push('cap');throw {code:'NETWORK_UNKNOWN',status:0};};
  await f.c.open('one');await f.drainZero();
  assert.equal(f.c.state.generation.phase,'error');
  for(let count=0;count<3;count++){f.coordinator(f.c.state);await f.drainZero();}
  assert.equal(f.calls.filter(value=>value==='cap').length,1);
  assert.equal(f.calls.filter(value=>value==='POST').length,0);
  assert.equal([...f.timers.values()].filter(timer=>timer.delay===0).length,0);
});

test('shipped entry injects only the dedicated native authorization bridge when present',async()=>{
  const block=source.slice(source.indexOf('const controller=createDraftController('),source.indexOf('function drawState('));
  const entry=new Function('api','createDraftController','window','readonly',block+';return controller;');
  const approvals=[],value={request_id:'fixed-request'},answer={ok:false,canceled:true};
  const options=entry({},(_api,settings)=>settings,{desktopAssistant:{authorizeGeneration:async input=>{approvals.push(input);return answer;}}},false);
  assert.equal(typeof options.nativeAuthorization,'function');assert.equal(await options.nativeAuthorization(value),answer);
  assert.deepEqual(approvals,[value]);
  for(const bridge of [undefined,{}, {authorizeGeneration:'not a function'}]) {
    assert.equal(entry({},(_api,settings)=>settings,{desktopAssistant:bridge},false).nativeAuthorization,null);
  }
});

test('entry does not enqueue capability reads while a native confirmation is outstanding',async()=>{
  const entered=deferred(),gate=deferred();
  const f=fixture({nativeAuthorization:()=>{entered.resolve();return gate.promise;}});
  await f.c.open('one');await f.drainZero();const sending=f.c.send();await entered.promise;
  assert.equal(f.c.state.generation.phase,'confirming');
  assert.equal([...f.timers.values()].filter(timer=>timer.delay===0).length,0);
  f.coordinator(f.c.state);assert.equal([...f.timers.values()].filter(timer=>timer.delay===0).length,0);
  gate.resolve({ok:false,canceled:true});assert.equal(await sending,false);assert.equal(f.calls.filter(x=>x==='POST').length,0);
});
