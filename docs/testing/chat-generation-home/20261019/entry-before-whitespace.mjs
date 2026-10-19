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
function fixture({initial='合成文字'}={}) {
  let remote={scope:scope('one'),draft_input:initial,composer_revision:1,messages:[],latest_run:null};
  const calls=[],timers=new Map(),pendingReads=new Set();let sequence=0,coordinator;
  const api={
    async getConversation(id){calls.push('view');return clone({...remote,scope:scope(id)});},
    async saveDraft(id,body){calls.push('save');remote={...remote,draft_input:body.content,composer_revision:remote.composer_revision+1};return clone(remote);},
    async getGenerationCapability(){calls.push('cap');return {scope:clone(remote.scope),composer_revision:remote.composer_revision,basis:'saved_draft',content_sha256:remote.draft_input.trim()?sha(remote.draft_input):null,state:'ready'};},
    async submitGeneration(){calls.push('POST');throw Object.assign(Error('lost'),{code:'NETWORK_UNKNOWN',status:0});},
    async findGenerationRequest(){calls.push('find');return null;},
    async getGenerationHistory(id,ids){calls.push('history');return {scope:clone(remote.scope),items:[]};},
  };
  const c=createDraftController(api,{uuid:()=>`synthetic-${++sequence}`,onChange:s=>coordinator?.(s)});
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

