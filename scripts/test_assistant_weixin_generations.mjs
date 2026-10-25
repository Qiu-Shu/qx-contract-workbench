import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {bindWeixinGenerations} from '../src/cn_contract/web/static/assistant-weixin-generations.mjs';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
const ids={root:'10000000-0000-4000-8000-000000000001',a:'10000000-0000-4000-8000-000000000002',
  b:'10000000-0000-4000-8000-000000000003',latest:'10000000-0000-4000-8000-000000000004',
  archived:'10000000-0000-4000-8000-000000000005',workspace:'20000000-0000-4000-8000-000000000001',
  binding:'30000000-0000-4000-8000-000000000001',request:'40000000-0000-4000-8000-000000000001'};
const scope=(cid=ids.root)=>({workspace_id:ids.workspace,conversation_id:cid,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:1});
const digest=value=>createHash('sha256').update(JSON.stringify(value,Object.keys(value).sort())).digest('hex');
const view=(cid=ids.a)=>({scope:scope(cid),display_title:'独立合成目标 '+cid.slice(-1),archived_at:null});
const binding=(cid=ids.a)=>({id:ids.binding,conversation_id:cid,channel:'synthetic',cursor:0,created_at:'2026-10-25T08:00:00Z'});
const head=(generation=0)=>{const s=scope(generation?ids.latest:ids.root);return {mode:'synthetic',state:'history_only',
  generation,generation_sha256:generation?'a'.repeat(64):null,scope:s,scope_sha256:digest(s),checkpoint_revision:7};};
const endpoint=cid=>'/api/assistant/conversations/'+cid;
const base=endpoint(ids.root)+'/weixin-authorization/generations';
const receipt=body=>({mode:'synthetic',state:'history_only',generation:body.expected_generation+1,
  request_id:body.request_id,scope:structuredClone(body.expected_scope),scope_sha256:digest(body.expected_scope),
  previous_generation_sha256:body.expected_previous_generation_sha256,
  previous_scope_sha256:body.expected_previous_scope_sha256,checkpoint_revision:body.expected_checkpoint_revision,
  created_at:'2026-10-25T08:01:00Z',generation_sha256:'b'.repeat(64)});
class Element{
  constructor(tag='div'){
    this.tagName=tag.toUpperCase();this.children=[];this.listeners=new Map();this.attributes={};this.dataset={};
    this.value='';this.open=false;this.hidden=false;this.disabled=false;this._text='';
  }
  get textContent(){return this._text+this.children.map(el=>el.textContent??String(el)).join('');}
  set textContent(value){this._text=String(value??'');this.children=[];}
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.children.push(node);return node;}
  replaceChildren(...nodes){this._text='';this.children=[...nodes];}
  addEventListener(name,fn){if(!this.listeners.has(name))this.listeners.set(name,[]);this.listeners.get(name).push(fn);}
  removeEventListener(name,fn){this.listeners.set(name,(this.listeners.get(name)||[]).filter(value=>value!==fn));}
  setAttribute(name,value){this.attributes[name]=String(value);}
  removeAttribute(name){delete this.attributes[name];}
  focus(){this.focused=true;}
  fire(name){const event={type:name,target:this,currentTarget:this,preventDefault(){}};
    return Promise.all((this.listeners.get(name)||[]).map(fn=>fn(event)));}
}
function fixture({readonly=false,onSaved}={}){
  const elements=new Map(),calls=[],activities=[];
  const root={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
    createElement:tag=>new Element(tag)};
  const controller={state:{id:ids.root,status:'saved',dirty:false,loading:false,view:view(ids.root),materials:{scope:scope()}},
    revoked:[],revoke(error){this.revoked.push(error);return [401,403].includes(error.status);}};
  const f={root,controller,calls,activities,authorization:{state:'current'},blocked:false,currentHead:head(),
    pages:new Map([[null,{items:[view(ids.root),view(ids.a),view(ids.b)],next_cursor:null}]]),
    targetViews:new Map([[ids.a,view(ids.a)],[ids.b,view(ids.b)]]),targetBinding:binding(),saved:0};
  f.handle=async(path,options={})=>{
    if(path.endsWith('/generations/head'))return f.currentHead;
    if(path.endsWith('/task-drafts'))return {items:[],unassigned_events:[],binding:f.targetBinding};
    if(path.endsWith('/task-bindings')&&options.method==='POST')return binding();
    if(path.endsWith('/generations')&&options.method==='POST')return receipt(options.body);
    throw new Error('unexpected synthetic request '+path);
  };
  const api={request:async(path,options={})=>{calls.push({kind:'request',path,options:structuredClone(options)});return f.handle(path,options);},
    listConversations:async(cursor)=>{calls.push({kind:'list',cursor:cursor??null});return f.pages.get(cursor??null);},
    getConversation:async(cid)=>{calls.push({kind:'conversation',cid});return f.targetViews.get(cid);}};
  const module=bindWeixinGenerations({controller,api,root,readonly,uuid:()=>ids.request,
    getAuthorization:()=>f.authorization,isBlocked:()=>f.blocked,onActivityChange:value=>activities.push(value),
    onSaved:async()=>{++f.saved;if(onSaved)await onSaved();}});
  f.api=api;f.module=module;
  f.state=changes=>{controller.state={...controller.state,...changes};module.state(controller.state);};
  f.state({});return f;
}
const el=(f,name)=>f.root.getElementById('weixin-generation-'+name);
const click=(f,name)=>el(f,name).fire('click');
const writes=f=>f.calls.filter(value=>value.kind==='request'&&value.options.method==='POST');
async function open(f){el(f,'panel').open=true;await click(f,'read');}
async function choose(f,cid=ids.a,reason='独立合成明确切换目标，仅保存历史记录'){
  el(f,'target').value=cid;await el(f,'target').fire('change');
  el(f,'reason').value=reason;await el(f,'reason').fire('input');
}
async function prepare(f){await open(f);await choose(f);await click(f,'prepare');}
function values(element){return element.children.flatMap(child=>[child.value,...values(child)]).filter(Boolean);}

test('closed panel never reads or writes merely because a conversation became current',async()=>{
  const f=fixture();await tick();assert.equal(f.calls.length,0);assert.equal(f.module.hasPending(),false);f.module.dispose();
});

test('explicit reading filters root latest archived targets and paginates without a write',async()=>{
  const f=fixture();f.currentHead=head(2);
  f.pages.set(null,{items:[view(ids.root),view(ids.latest),{...view(ids.archived),archived_at:'2026-10-25T08:00:00Z'},view(ids.a)],next_cursor:'opaque-page-two'});
  f.pages.set('opaque-page-two',{items:[view(ids.b)],next_cursor:null});
  await open(f);assert.ok(f.calls.some(call=>call.path===base+'/head'));
  assert.deepEqual(values(el(f,'target')),[ids.a]);await click(f,'more');
  assert.deepEqual(values(el(f,'target')),[ids.a,ids.b]);
  assert.ok(f.calls.some(call=>call.kind==='list'&&call.cursor==='opaque-page-two'));
  assert.equal(writes(f).length,0);f.module.dispose();
});

test('prepare reads current target and task binding and never creates a missing binding',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);
  assert.ok(f.calls.some(call=>call.kind==='conversation'&&call.cid===ids.a));
  assert.ok(f.calls.some(call=>call.path===endpoint(ids.a)+'/task-drafts'));
  assert.equal(writes(f).length,0);assert.notEqual(el(f,'preview').textContent,'');
  assert.equal(el(f,'save').disabled,false);f.module.dispose();
});

test('explicit save with a known binding submits the frozen complete eight field CAS',async()=>{
  const f=fixture();await prepare(f);await click(f,'save');
  const posts=writes(f);assert.equal(posts.length,1);assert.equal(posts[0].path,base);
  assert.deepEqual(posts[0].options.body,{request_id:ids.request,expected_generation:0,
    expected_previous_generation_sha256:null,expected_previous_scope_sha256:head().scope_sha256,
    expected_checkpoint_revision:7,task_binding_id:ids.binding,expected_scope:scope(ids.a),
    reason:'独立合成明确切换目标，仅保存历史记录'});
  assert.equal(f.saved,1);assert.equal(f.module.hasPending(),false);
  assert.equal(el(f,'reason').value,'');assert.equal(el(f,'target').value,'');
  assert.match(el(f,'notice').textContent,/历史/);assert.match(el(f,'notice').textContent,/暂停|不会|未启|不启/);
  assert.ok(f.calls.filter(call=>call.path===base+'/head').length>=2);f.module.dispose();
});

test('explicit save creates an absent synthetic target binding before generation and sends no binding body',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);await click(f,'save');
  const posts=writes(f);assert.deepEqual(posts.map(post=>post.path),[endpoint(ids.a)+'/task-bindings',base]);
  assert.equal(posts[0].options.body,undefined);assert.equal(posts[1].options.body.task_binding_id,ids.binding);f.module.dispose();
});

test('readonly users may read historical head and targets but cannot prepare or save writes',async()=>{
  const f=fixture({readonly:true});await prepare(f);await click(f,'save');
  assert.ok(f.calls.some(call=>call.path===base+'/head'));assert.equal(writes(f).length,0);
  assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('unbound null head cannot invent generation zero checkpoint or a writable preview',async()=>{
  const f=fixture();f.currentHead=null;await prepare(f);await click(f,'save');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('unbound revoked archived restored and absent authorization projections forbid writes',async()=>{
  for(const state of ['unbound','revoked','archived','restored_blocked',null]){
    const f=fixture();await prepare(f);f.authorization=state?{state}:null;f.module.updateControls();
    await click(f,'save');assert.equal(writes(f).length,0,String(state));f.module.dispose();
  }
});

for(const [name,change] of [['dirty',{dirty:true}],['loading',{loading:true}],['materials',{materialAction:{}}],
  ['conflict',{conflict:{}}],['saving',{status:'saving'}]])
test('a locally unstable '+name+' snapshot cannot save a prepared generation',async()=>{
  const f=fixture();await prepare(f);f.state(change);await click(f,'save');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('another module pending action blocks preparation and save',async()=>{
  const f=fixture();await prepare(f);f.blocked=true;f.module.updateControls();await click(f,'save');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

for(const field of ['target','reason'])
test('changing '+field+' discards the frozen preview until another explicit prepare',async()=>{
  const f=fixture();await prepare(f);
  el(f,field).value=field==='target'?ids.b:'独立合成改后的明确理由';await el(f,field).fire(field==='target'?'change':'input');
  await click(f,'save');assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('unsaved selection reason and preparing activity protect against navigation and known form may clear',async()=>{
  const f=fixture();await open(f);await choose(f);assert.equal(f.module.hasPending(),true);
  await click(f,'clear');assert.equal(f.module.hasPending(),false);assert.equal(el(f,'reason').value,'');
  assert.equal(el(f,'target').value,'');assert.equal(writes(f).length,0);f.module.dispose();
});

test('unknown binding creation only queries task drafts and requires another explicit save after finding binding',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);const original=f.handle;
  f.handle=async(path,options)=>{if(path.endsWith('/task-bindings'))throw {code:'NETWORK_UNKNOWN',status:0};return original(path,options);};
  await click(f,'save');assert.equal(f.module.hasPending(),true);assert.equal(writes(f).length,1);
  f.targetBinding=binding();const before=f.calls.length;await click(f,'find');
  assert.deepEqual(f.calls.slice(before).filter(call=>call.kind==='request').map(call=>call.path),[endpoint(ids.a)+'/task-drafts']);
  assert.equal(writes(f).length,1);assert.equal(f.saved,0);await click(f,'save');
  assert.deepEqual(writes(f).map(post=>post.path),[endpoint(ids.a)+'/task-bindings',base]);
  assert.equal(f.saved,1);f.module.dispose();
});

test('missing or mismatched binding lookup keeps unknown operation and cannot clear or repeat create',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);const original=f.handle;
  f.handle=async(path,options)=>{if(path.endsWith('/task-bindings'))throw {code:'NETWORK_UNKNOWN',status:0};return original(path,options);};
  await click(f,'save');await click(f,'find');assert.equal(f.module.hasPending(),true);
  f.targetBinding=binding(ids.b);await click(f,'find');await click(f,'clear');await click(f,'save');
  assert.equal(f.module.hasPending(),true);assert.equal(writes(f).length,1);assert.equal(f.saved,0);f.module.dispose();
});

test('unknown generation POST keeps exact request and lookup alone resolves null then fixed receipt',async()=>{
  const f=fixture();await prepare(f);let operation,found=null;const original=f.handle;
  f.handle=async(path,options)=>{if(path===base&&options.method==='POST'){operation=structuredClone(options.body);throw {code:'NETWORK_UNKNOWN',status:0};}
    if(path===base+'/by-request/'+ids.request)return found;return original(path,options);};
  await click(f,'save');await click(f,'clear');await click(f,'save');assert.equal(writes(f).length,1);
  const before=f.calls.length;await click(f,'find');assert.equal(f.module.hasPending(),true);
  assert.deepEqual(f.calls.slice(before).filter(call=>call.kind==='request').map(call=>call.path),[base+'/by-request/'+ids.request]);
  found=receipt(operation);await click(f,'find');assert.equal(f.saved,1);assert.equal(f.module.hasPending(),false);
  assert.equal(writes(f).length,1);f.module.dispose();
});

for(const [name,variants] of [['request',[value=>({...value,request_id:ids.b})]],
  ['generation',[value=>({...value,generation:value.generation+1})]],
  ['mode or state',[value=>({...value,mode:'live'}),value=>({...value,state:'active'})]],
  ['checkpoint or predecessor',[value=>({...value,checkpoint_revision:99}),
    value=>({...value,previous_generation_sha256:'f'.repeat(64)}),value=>({...value,previous_scope_sha256:'f'.repeat(64)})]],
  ['scope or digest',[value=>({...value,scope:{...value.scope,materials_revision:99}}),
    value=>({...value,generation_sha256:'invalid'}),value=>({...value,scope_sha256:'invalid'})]],
  ['missing or invalid UTC creation time',[value=>{const {created_at,...rest}=value;return rest;},
    value=>({...value,created_at:'not-a-time'}),value=>({...value,created_at:'2026-10-25T08:01:00+08:00'})]]])
test('unrelated '+name+' receipt remains unknown and never claims a saved generation',async()=>{
  for(const alter of variants){
    const f=fixture();await prepare(f);let wrong;const original=f.handle;
    f.handle=async(path,options)=>{if(path===base&&options.method==='POST'){wrong=alter(receipt(options.body));return wrong;}
      if(path===base+'/by-request/'+ids.request)return wrong;return original(path,options);};
    await click(f,'save');await click(f,'find');assert.equal(f.saved,0);assert.equal(f.module.hasPending(),true);
    assert.equal(writes(f).length,1);assert.doesNotMatch(el(f,'notice').textContent,/已保存/);f.module.dispose();
  }
});

test('409 never retries a write and requires a fresh head and explicit preview',async()=>{
  const f=fixture();await prepare(f);const original=f.handle;
  f.handle=async(path,options)=>{if(path===base&&options.method==='POST')throw {code:'VERSION_CONFLICT',status:409};return original(path,options);};
  await click(f,'save');await click(f,'save');assert.equal(writes(f).length,1);assert.equal(el(f,'save').disabled,true);
  assert.match(el(f,'notice').textContent,/重|读取|变化|冲突/);f.module.dispose();
});

for(const status of [401,403])
test('current permission denial '+status+' revokes pending display and never retries',async()=>{
  const f=fixture();await prepare(f);f.handle=async()=>{throw {status,code:status===401?'AUTHORIZATION_REQUIRED':'CROSS_MATTER_DENIED'};};
  await click(f,'save');assert.equal(f.controller.revoked.length,1);assert.equal(f.module.hasPending(),false);
  assert.equal(el(f,'save').disabled,true);assert.equal(el(f,'preview').textContent,'');await click(f,'save');
  assert.equal(writes(f).length,1);f.module.dispose();
});

test('double click cannot submit two generation writes while the first receipt is outstanding',async()=>{
  const f=fixture();await prepare(f);let finish;const original=f.handle;
  f.handle=(path,options)=>path===base&&options.method==='POST'?
    new Promise(resolve=>{finish=()=>resolve(receipt(options.body));}):original(path,options);
  const first=click(f,'save');await click(f,'save');assert.equal(writes(f).length,1);assert.equal(f.module.hasPending(),true);
  finish();await first;assert.equal(f.saved,1);assert.equal(writes(f).length,1);f.module.dispose();
});

test('a late root head cannot paint or prepare after current conversation changes',async()=>{
  const f=fixture();let finish;const original=f.handle;
  f.handle=(path,options)=>path===base+'/head'?new Promise(resolve=>{finish=resolve;}):original(path,options);
  el(f,'panel').open=true;const reading=click(f,'read');await tick();
  f.state({id:ids.b,view:view(ids.b),materials:{scope:scope(ids.b)}});finish(head());await reading;await choose(f);await click(f,'prepare');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('disposed module ignores pending head and disables all write controls',async()=>{
  const f=fixture();let finish;f.handle=()=>new Promise(resolve=>{finish=resolve;});
  el(f,'panel').open=true;const reading=click(f,'read');await tick();f.module.dispose();finish(head());await reading;
  assert.equal(el(f,'save').disabled,true);assert.equal(el(f,'preview').textContent,'');assert.equal(writes(f).length,0);
});

test('target change while current target is loading cannot produce a stale writable preview',async()=>{
  const f=fixture();await open(f);await choose(f);let finish;
  f.api.getConversation=cid=>{f.calls.push({kind:'conversation',cid});return new Promise(resolve=>{finish=resolve;});};
  const preparing=click(f,'prepare');await tick();el(f,'target').value=ids.b;await el(f,'target').fire('change');
  finish(view(ids.a));await preparing;await click(f,'save');assert.equal(writes(f).length,0);
  assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('root scope revision change invalidates a prepared head without silently preserving write authority',async()=>{
  const f=fixture();await prepare(f);
  f.state({view:{...view(ids.root),scope:{...scope(),input_revision:1}}});await click(f,'save');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('a newer explicit read wins when the older head returns last',async()=>{
  const f=fixture();const resolvers=[];const original=f.handle;
  f.handle=(path,options)=>path===base+'/head'?new Promise(resolve=>resolvers.push(resolve)):original(path,options);
  el(f,'panel').open=true;const old=f.module.refresh(),fresh=f.module.refresh();await tick();
  assert.equal(resolvers.length,2,'new explicit reads must supersede a pending read');
  resolvers[1](null);await fresh;resolvers[0](head());await old;await choose(f);await click(f,'prepare');await click(f,'save');
  assert.equal(writes(f).length,0);assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('controller revocation ignores late target or binding responses and prevents the next write',async()=>{
  for(const phase of ['target','binding']){
    const f=fixture();let finish,waiting;
    if(phase==='target'){
      await open(f);await choose(f);
      f.api.getConversation=()=>new Promise(resolve=>{finish=()=>resolve(view(ids.a));});waiting=click(f,'prepare');
    }else{
      f.targetBinding=null;await prepare(f);const original=f.handle;
      f.handle=(path,options)=>path.endsWith('/task-bindings')?
        new Promise(resolve=>{finish=()=>resolve(binding());}):original(path,options);waiting=click(f,'save');
    }
    await tick();f.state({status:'revoked'});finish();await waiting;await click(f,'save');
    assert.equal(f.module.hasPending(),false);assert.equal(el(f,'save').disabled,true);
    assert.equal(el(f,'preview').textContent,'');assert.equal(writes(f).length,phase==='target'?0:1);f.module.dispose();
  }
});

test('refresh invalidates an already loading prepare so its late target cannot resurrect the preview',async()=>{
  const f=fixture();await open(f);await choose(f);let finish;
  f.api.getConversation=()=>new Promise(resolve=>{finish=resolve;});const preparing=click(f,'prepare');await tick();
  f.currentHead=head(1);await f.module.refresh();finish(view(ids.a));await preparing;
  assert.equal(el(f,'save').disabled,true);assert.equal(el(f,'preview').textContent,'');
  await click(f,'save');assert.equal(writes(f).length,0);f.module.dispose();
});

test('an old prepare finishing cannot unlock controls while a newer head refresh is still pending',async()=>{
  const f=fixture();await open(f);await choose(f);let finishTarget,finishHead;const original=f.handle;
  f.api.getConversation=()=>new Promise(resolve=>{finishTarget=resolve;});const preparing=click(f,'prepare');await tick();
  f.handle=(path,options)=>path===base+'/head'?new Promise(resolve=>{finishHead=resolve;}):original(path,options);
  const refreshing=f.module.refresh();await tick();finishTarget(view(ids.a));await preparing;
  assert.equal(el(f,'target').disabled,true);assert.equal(el(f,'prepare').disabled,true);
  finishHead(head(1));await refreshing;assert.equal(el(f,'save').disabled,true);f.module.dispose();
});

test('a valid stored receipt is not relabelled unknown merely because the authorization refresh fails',async()=>{
  const f=fixture({onSaved:async()=>{throw {code:'NETWORK_UNKNOWN',status:0};}});
  await prepare(f);await click(f,'save');
  assert.equal(writes(f).length,1);assert.equal(f.module.hasPending(),false);
  assert.match(el(f,'notice').textContent,/已保存/);assert.doesNotMatch(el(f,'notice').textContent,/结果尚未确认/);
  assert.match(el(f,'notice').textContent,/重新读取|未.*更新|刷新.*失败|状态.*未/);f.module.dispose();
});

test('scope growth during an unknown binding operation preserves lookup but invalidates later write authority',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);const original=f.handle;
  f.handle=async(path,options)=>{if(path.endsWith('/task-bindings'))throw {code:'NETWORK_UNKNOWN',status:0};return original(path,options);};
  await click(f,'save');f.state({view:{...view(ids.root),scope:{...scope(),input_revision:1}}});
  assert.equal(f.module.hasPending(),true);f.targetBinding=binding();await click(f,'find');
  assert.equal(el(f,'save').disabled,true);await click(f,'save');assert.equal(writes(f).length,1);f.module.dispose();
});

test('a stable UI that becomes dirty during binding creation cannot proceed with the generation POST',async()=>{
  const f=fixture();f.targetBinding=null;await prepare(f);let finish;const original=f.handle;
  f.handle=(path,options)=>path.endsWith('/task-bindings')?
    new Promise(resolve=>{finish=()=>resolve(binding());}):original(path,options);
  const saving=click(f,'save');await tick();f.state({dirty:true});finish();await saving;
  assert.equal(writes(f).length,1);assert.equal(writes(f)[0].path,endpoint(ids.a)+'/task-bindings');
  assert.equal(el(f,'save').disabled,true);f.module.dispose();
});
