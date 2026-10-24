import test from 'node:test';
import assert from 'node:assert/strict';
import {bindWeixinAuthorization} from '../src/cn_contract/web/static/assistant-weixin.mjs';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
const scope={workspace_id:'workspace',conversation_id:'one',scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:1};
const view=(state='refresh_required')=>({mode:'synthetic',state,current_scope:{...scope},
  authorized_scope:{...scope,materials_revision:0},grant_revision:0,scope_sha256:'a'.repeat(64)});
const receipt=()=>({id:'grant',request_id:'request-one',revision:1,previous_scope_sha256:'a'.repeat(64),
  scope:{...scope},scope_sha256:'c'.repeat(64),grant_sha256:'b'.repeat(64)});
class Element{
  constructor(){this.textContent='';this.hidden=false;this.disabled=false;this.listeners=new Map();}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  fire(name){return this.listeners.get(name)?.();}
  setAttribute(name,value){this[name]=value;}
}
function fixture({readonly=false}={}){
  const elements=new Map(),calls=[];
  const root={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}};
  const controller={state:{id:'one',status:'saved',view:{scope},materials:{scope},loading:false},
    revoke:error=>[401,403].includes(error.status)};
  let current=view();
  const api={request:async(path,options={})=>{calls.push([path,options]);return current;}};
  const binding=bindWeixinAuthorization({controller,api,root,readonly,uuid:()=> 'request-one'});
  const state=changes=>{controller.state={...controller.state,...changes};binding.state(controller.state);};
  state({});
  return {root,controller,api,binding,calls,state,setView:value=>{current=value;}};
}
const el=(f,id)=>f.root.getElementById(id);
const write=(f)=>el(f,'weixin-authorize').fire('click');
const lookup=(f)=>el(f,'weixin-find').fire('click');

test('projection reads only and explicit update submits the displayed exact scope',async()=>{
  const f=fixture();await tick();
  assert.equal(f.calls.length,1);assert.equal(f.calls[0][1].method,undefined);
  assert.equal(el(f,'weixin-authorize').disabled,false);
  f.api.request=async(path,options={})=>{
    f.calls.push([path,options]);return options.method==='POST'?receipt():view('current');
  };
  await write(f);
  const posts=f.calls.filter(([,value])=>value.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(posts[0][1].body,{request_id:'request-one',expected_grant_revision:0,
    expected_scope_sha256:'a'.repeat(64),expected_scope:scope,reason:'对话页显式更新同目标输入和材料授权'});
  assert.equal(f.binding.hasPending(),false);assert.equal(el(f,'weixin-authorize').hidden,true);
  assert.match(el(f,'weixin-notice').textContent,/已保存/);f.binding.dispose();
});

for(const state of ['unbound','current','target_changed','revoked','archived','restored_blocked'])
test('state never offers automatic or inappropriate authorization: '+state,async()=>{
  const f=fixture();f.setView(view(state));await f.binding.refresh();await tick();
  assert.equal(el(f,'weixin-authorize').hidden,true);
  await write(f);assert.equal(f.calls.some(([,value])=>value.method==='POST'),false);f.binding.dispose();
});

for(const blocked of [{dirty:true},{loading:true},{materialAction:{}},{conflict:{}},{status:'saving'}])
test('local action prevents changing authorization while the working snapshot is unstable '+JSON.stringify(blocked),async()=>{
  const f=fixture();await tick();f.state(blocked);
  assert.equal(el(f,'weixin-authorize').disabled,true);await write(f);
  assert.equal(f.calls.some(([,value])=>value.method==='POST'),false);f.binding.dispose();
});

test('readonly current projection cannot authorize',async()=>{
  const f=fixture({readonly:true});await tick();await write(f);
  assert.equal(f.calls.some(([,value])=>value.method==='POST'),false);f.binding.dispose();
});

test('unknown write keeps one request and only queries its result',async()=>{
  const f=fixture();await tick();let found=null;
  f.api.request=async(path,options={})=>{
    f.calls.push([path,options]);
    if(options.method==='POST')throw {code:'NETWORK_UNKNOWN',status:0};
    if(path.includes('/by-request/'))return found;
    return view('current');
  };
  await write(f);assert.equal(f.binding.hasPending(),true);
  assert.equal(el(f,'weixin-find').hidden,false);await write(f);await lookup(f);
  assert.equal(f.binding.hasPending(),true);assert.match(el(f,'weixin-notice').textContent,/尚未查到/);
  found=receipt();await lookup(f);
  assert.equal(f.binding.hasPending(),false);
  assert.equal(f.calls.filter(([,value])=>value.method==='POST').length,1);
  assert.ok(f.calls.some(([path])=>path.endsWith('/refreshes/by-request/request-one')));
  f.binding.dispose();
});

test('late projection never paints a different conversation',async()=>{
  const f=fixture();await tick();let old;
  f.api.request=path=>path.includes('/one/')?new Promise(resolve=>{old=resolve;}):
    Promise.resolve({...view('unbound'),current_scope:{...scope,conversation_id:'two'}});
  const reading=f.binding.refresh();f.state({id:'two',view:{scope:{...scope,conversation_id:'two'}}});await tick();
  old(view('refresh_required'));await reading;
  assert.match(el(f,'weixin-state').textContent,/尚未绑定/);
  assert.equal(el(f,'weixin-authorize').hidden,true);f.binding.dispose();
});

test('disposed module ignores pending projection',async()=>{
  const f=fixture();await tick();let old;
  f.api.request=()=>new Promise(resolve=>{old=resolve;});
  const reading=f.binding.refresh();f.binding.dispose();old(view());await reading;
  assert.equal(el(f,'weixin-authorize').disabled,true);
});

test('a newer read wins within the same conversation',async()=>{
  const f=fixture();await tick();const callbacks=[];
  f.api.request=()=>new Promise(resolve=>callbacks.push(resolve));
  const old=f.binding.refresh(),fresh=f.binding.refresh();
  callbacks[1](view('revoked'));await fresh;callbacks[0](view('refresh_required'));await old;
  assert.match(el(f,'weixin-state').textContent,/已撤销/);
  assert.equal(el(f,'weixin-authorize').hidden,true);f.binding.dispose();
});

test('double click cannot submit a second authorization',async()=>{
  const f=fixture();await tick();let finish;
  f.api.request=(path,options={})=>{f.calls.push([path,options]);
    return options.method==='POST'?new Promise(resolve=>{finish=resolve;}):Promise.resolve(view('current'));};
  const writing=write(f);await write(f);assert.equal(f.binding.hasPending(),true);
  finish(receipt());await writing;
  assert.equal(f.calls.filter(([,value])=>value.method==='POST').length,1);f.binding.dispose();
});

test('projection for a different CID is discarded before any action',async()=>{
  const f=fixture();await tick();
  f.setView({...view(),current_scope:{...scope,conversation_id:'foreign'}});await f.binding.refresh();
  await write(f);assert.equal(f.calls.some(([,value])=>value.method==='POST'),false);
  assert.equal(el(f,'weixin-authorize').hidden,true);f.binding.dispose();
});

test('a current-permission denial clears the projection and pending action',async()=>{
  const f=fixture();await tick();f.api.request=async()=>{throw {status:403,code:'CROSS_MATTER_DENIED'};};
  await f.binding.refresh();assert.equal(el(f,'weixin-authorize').disabled,true);
  assert.equal(f.binding.hasPending(),false);assert.doesNotMatch(el(f,'weixin-state').textContent,/材料版本/);
  f.binding.dispose();
});

test('conflict never retries a POST and refreshes the actual projection',async()=>{
  const f=fixture();await tick();
  f.api.request=async(path,options={})=>{f.calls.push([path,options]);
    if(options.method==='POST')throw {status:409,code:'VERSION_CONFLICT'};return view('target_changed');};
  await write(f);assert.equal(f.binding.hasPending(),false);
  assert.equal(f.calls.filter(([,value])=>value.method==='POST').length,1);
  assert.equal(el(f,'weixin-authorize').hidden,true);f.binding.dispose();
});

test('an unrelated or incomplete JSON response never claims authorization was saved',async()=>{
  const f=fixture();await tick();
  f.api.request=async(path,options={})=>{f.calls.push([path,options]);return {id:'unrelated'};};
  await write(f);assert.equal(f.binding.hasPending(),true);
  assert.doesNotMatch(el(f,'weixin-notice').textContent,/已保存/);
  await lookup(f);assert.equal(f.binding.hasPending(),true);
  assert.equal(f.calls.filter(([,value])=>value.method==='POST').length,1);f.binding.dispose();
});
