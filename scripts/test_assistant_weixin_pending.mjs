import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';

const source=new URL('../src/cn_contract/web/static/assistant-weixin-pending.mjs',import.meta.url);
const module=existsSync(source)?await import(source.href):{};
const id=n=>'10000000-0000-4000-8000-'+String(n).padStart(12,'0');
const ids={root:id(1),target:id(2),other:id(3),workspace:id(4)};
const scope=(cid=ids.root)=>({workspace_id:ids.workspace,conversation_id:cid,binding_revision:1,input_revision:0,materials_revision:0});
const view=(cid=ids.target)=>({scope:scope(cid),display_title:'合成目标 '+cid.slice(-1),archived_at:null});
const item=(n=10,cid=ids.target)=>({descriptor_id:id(n),conversation_id:cid,received_at:'2026-10-26T08:00:00Z',has_text:true,media_count:0});
const page=(items=[item()],next_cursor=null,cid=ids.target)=>({mode:'synthetic',read_only:true,conversation_id:cid,items,next_cursor});
const receipt=(n=10,cid=ids.target)=>({mode:'synthetic',state:'recorded',descriptor_id:id(n),conversation_id:cid,
  task_event_id:id(100+n),expected_task_cursor:0,next_task_cursor:1,created_at:'2026-10-26T08:01:00Z',receipt_sha256:'a'.repeat(64)});
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners=new Map();this.value='';this.disabled=false;this.hidden=false;this.open=false;this._text='';}
  get textContent(){return this._text+this.children.map(child=>child.textContent??String(child)).join('');}
  set textContent(value){this._text=String(value);this.children=[];}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this._text='';this.children=[...nodes];}
  setAttribute(name,value){this[name]=value;}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  fire(name){return this.listeners.get(name)?.();}
}
function fixture(options={}){
  assert.equal(typeof module.bindWeixinPending,'function','D2g5h requires a usable pending-list UI binding');
  const elements=new Map(),calls=[],saved=[];
  const root={getElementById(name){if(!elements.has(name))elements.set(name,new Element());return elements.get(name);},createElement:tag=>new Element(tag)};
  const controller={state:{id:ids.root,status:'saved',view:view(ids.root),materials:{scope:scope()},loading:false},revoke:e=>[401,403].includes(e.status)};
  let authorization={state:'target_changed'},blocked=false;
  const api={listConversations:async()=>({items:[view()],next_cursor:null}),request:async(path,opts={})=>{
    calls.push([path,opts]);return opts.method==='POST'?receipt():path.includes('/by-descriptor/')?receipt():page();}};
  const binding=module.bindWeixinPending({controller,api,root,getAuthorization:()=>authorization,isBlocked:()=>blocked,
    onDispatched:async value=>saved.push(value),...options});
  const state=changes=>{controller.state={...controller.state,...changes};binding.state(controller.state);};
  state({});
  return {root,controller,api,binding,calls,saved,state,setAuthorization:v=>{authorization=v;binding.updateControls();},setBlocked:v=>{blocked=v;binding.updateControls();}};
}
const el=(f,name)=>f.root.getElementById('weixin-pending-'+name);
async function ready(f){await f.binding.loadTargets();el(f,'target').value=ids.target;await el(f,'target').fire('change');return f.binding.refresh();}
function buttons(f){return el(f,'list').children.flatMap(row=>row.children).filter(node=>node.tagName==='button');}

test('explicit target loads metadata without writing; one click dispatches the fixed descriptor',async()=>{
  const f=fixture();await ready(f);
  assert.equal(f.calls.length,1);assert.match(f.calls[0][0],new RegExp('target_conversation_id='+ids.target));
  assert.match(el(f,'list').textContent,/文本/);assert.equal(buttons(f).length,1);
  await buttons(f)[0].fire('click');
  const posts=f.calls.filter(([,o])=>o.method==='POST');assert.equal(posts.length,1);
  assert.deepEqual(posts[0][1].body,{descriptor_id:id(10)});
  assert.equal(f.saved.length,1);assert.equal(f.binding.hasPending(),false);
});

test('each page is bounded, uses the returned anchor and never offers later-page delivery',async()=>{
  const f=fixture();const first=page(Array.from({length:20},(_,n)=>item(10+n)),id(29));
  f.api.request=async(path,opts={})=>{f.calls.push([path,opts]);return path.includes('cursor=')?page([item(30)]):first;};
  await ready(f);assert.equal(buttons(f).length,20);assert.equal(buttons(f).filter(b=>!b.disabled).length,1);
  await buttons(f)[1].fire('click');assert.equal(f.calls.length,1);
  await el(f,'more').fire('click');assert.match(f.calls[1][0],new RegExp('cursor='+id(29)));
  assert.equal(buttons(f).length,1);assert.equal(buttons(f)[0].disabled,true);
  await buttons(f)[0].fire('click');assert.equal(f.calls.length,2);
  await el(f,'read').fire('click');assert.equal(buttons(f).length,20);
});

for(const [name,damage] of [
  ['wrong target',p=>p.conversation_id=ids.other],['mode',p=>p.mode='live'],['not readonly',p=>p.read_only=false],
  ['extra page field',p=>p.bot='secret'],['over limit',p=>p.items=Array.from({length:21},(_,n)=>item(10+n))],
  ['duplicate items',p=>p.items.push(p.items[0])],['extra item field',p=>p.items[0].text='private'],
  ['bad id',p=>p.items[0].descriptor_id='bad'],['wrong item target',p=>p.items[0].conversation_id=ids.other],
  ['boolean',p=>p.items[0].has_text='true'],['fractional count',p=>p.items[0].media_count=.5],
  ['negative count',p=>p.items[0].media_count=-1],['too many media',p=>p.items[0].media_count=21],
  ['no timezone',p=>p.items[0].received_at='2026-10-26T08:00:00'],['invalid time',p=>p.items[0].received_at='badZ'],
  ['calendar rollover',p=>p.items[0].received_at='2026-02-30T08:00:00Z'],
  ['foreign cursor',p=>p.next_cursor=id(99)],
])test('reject malformed metadata: '+name,async()=>{
  const f=fixture();const value=page();damage(value);f.api.request=async()=>value;
  await ready(f);assert.equal(buttons(f).length,0);assert.equal(el(f,'more').hidden,true);
  assert.equal(f.binding.hasPending(),false);
});

test('empty page has useful copy and no writes; failed refresh clears old entries',async()=>{
  const f=fixture();await ready(f);f.api.request=async()=>page([]);await f.binding.refresh();
  assert.match(el(f,'notice').textContent,/没有尚未分发/);assert.equal(buttons(f).length,0);
  f.api.request=async()=>page();await f.binding.refresh();f.api.request=async()=>{throw {code:'NETWORK_UNKNOWN'};};
  await f.binding.refresh();assert.equal(buttons(f).length,0);
});

for(const change of [{dirty:true},{loading:true},{conflict:{}},{materialAction:{}},{status:'saving'},{status:'error'}])
test('unstable root does not dispatch: '+JSON.stringify(change),async()=>{
  const f=fixture();await ready(f);f.state(change);await buttons(f)[0].fire('click');
  assert.equal(buttons(f)[0].disabled,true);assert.equal(f.calls.length,1);
});
for(const state of ['revoked','archived','unbound','restored_blocked'])test('authorization state blocks delivery: '+state,async()=>{
  const f=fixture();await ready(f);f.setAuthorization({state});await buttons(f)[0].fire('click');
  assert.equal(buttons(f)[0].disabled,true);assert.equal(f.calls.length,1);
});
test('readonly does not even request pending metadata',async()=>{
  const f=fixture({readonly:true});await ready(f);assert.equal(f.calls.length,0);assert.equal(el(f,'read').disabled,true);
});
test('other local pending operation blocks delivery',async()=>{
  const f=fixture();await ready(f);f.setBlocked(true);assert.equal(buttons(f)[0].disabled,true);
  await buttons(f)[0].fire('click');assert.equal(f.calls.length,1);
});

test('unknown delivery remains fixed and only exact GET reconciles it',async()=>{
  const f=fixture();await ready(f);let found=null;
  f.api.request=async(path,opts={})=>{f.calls.push([path,opts]);
    if(opts.method==='POST')throw {code:'NETWORK_UNKNOWN',status:0};
    return path.includes('/by-descriptor/')?found:page([]);};
  const button=buttons(f)[0];await button.fire('click');assert.equal(f.binding.hasPending(),true);
  assert.equal(el(f,'target').disabled,true);await button.fire('click');
  el(f,'target').value=ids.root;await el(f,'target').fire('change');assert.equal(el(f,'target').value,ids.target);
  await f.binding.refresh();await f.binding.find();assert.equal(f.binding.hasPending(),true);
  found=receipt(10,ids.other);await f.binding.find();assert.equal(f.binding.hasPending(),true);
  found=receipt();await f.binding.find();assert.equal(f.binding.hasPending(),false);
  assert.equal(f.calls.filter(([,o])=>o.method==='POST').length,1);
  assert.equal(f.calls.filter(([p])=>p.includes('/by-descriptor/')).length,3);
  assert.ok(f.calls.filter(([p])=>p.includes('/by-descriptor/')).every(([p])=>p.endsWith('/'+id(10))));
});

for(const [name,change] of [
  ['descriptor',r=>r.descriptor_id=id(99)],['target',r=>r.conversation_id=ids.other],['event',r=>r.task_event_id='bad'],
  ['cursor',r=>r.next_task_cursor=3],['digest',r=>r.receipt_sha256='bad'],['time',r=>r.created_at='bad'],
  ['extra',r=>r.text='private'],['state',r=>r.state='pending'],
  ['digest array',r=>r.receipt_sha256=['a'.repeat(64)]],
])test('unmatched POST receipt keeps unknown operation: '+name,async()=>{
  const f=fixture();await ready(f);const r=receipt();change(r);f.api.request=async()=>r;
  await buttons(f)[0].fire('click');assert.equal(f.binding.hasPending(),true);assert.equal(el(f,'find').hidden,false);
});

test('double click during POST cannot duplicate; confirmed delivery survives list refresh failure',async()=>{
  const f=fixture();await ready(f);let finish;
  f.api.request=(path,opts={})=>{f.calls.push([path,opts]);return opts.method==='POST'?new Promise(r=>finish=r):Promise.reject({code:'NETWORK_UNKNOWN'});};
  const button=buttons(f)[0],posting=button.fire('click');await button.fire('click');assert.equal(f.binding.hasPending(),true);
  finish(receipt());await posting;assert.equal(f.binding.hasPending(),false);assert.equal(f.saved.length,1);
  assert.match(el(f,'result').textContent,/回执已确认/);assert.equal(f.calls.filter(([,o])=>o.method==='POST').length,1);
});

test('confirmed callback cannot unlock target selection until projection refresh ends',async()=>{
  let finish;const f=fixture({onDispatched:()=>new Promise(resolve=>finish=resolve)});await ready(f);
  const posting=buttons(f)[0].fire('click');await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.binding.hasPending(),true);assert.equal(el(f,'target').disabled,true);
  finish();await posting;assert.equal(f.binding.hasPending(),false);
});

for(const situation of ['target','cid','scope','revoke','dispose'])test('late metadata cannot restore an obsolete view: '+situation,async()=>{
  const f=fixture();await ready(f);let finish;f.api.request=()=>new Promise(r=>finish=r);
  const loading=f.binding.refresh();
  if(situation==='target'){el(f,'target').value=ids.root;await el(f,'target').fire('change');}
  if(situation==='cid')f.state({id:ids.other,view:view(ids.other)});
  if(situation==='scope')f.state({view:{...view(ids.root),scope:{...scope(),input_revision:1}}});
  if(situation==='revoke')f.state({status:'revoked'});
  if(situation==='dispose')f.binding.dispose();
  finish(page());await loading;assert.equal(buttons(f).length,0);
});

for(const status of [401,403,409])test('known server refusal clears list and does not retry: '+status,async()=>{
  const f=fixture();await ready(f);f.api.request=async(path,opts={})=>{f.calls.push([path,opts]);throw {status,code:'STATE_CONFLICT'};};
  await buttons(f)[0].fire('click');assert.equal(f.binding.hasPending(),false);assert.equal(buttons(f).length,0);
  assert.equal(f.calls.filter(([,o])=>o.method==='POST').length,1);
});

test('conversation choices paginate and retain the selected historical target',async()=>{
  const f=fixture();f.api.listConversations=async cursor=>cursor?{items:[view(ids.other)],next_cursor:null}:{items:[view()],next_cursor:'saved-cursor'};
  await ready(f);await el(f,'targets-more').fire('click');assert.equal(el(f,'target').value,ids.target);
  assert.equal(el(f,'target').children.length,4);assert.equal(buttons(f).length,0);
});

test('repeated next page cannot resurrect already seen descriptor IDs',async()=>{
  const f=fixture(),value=page(Array.from({length:20},(_,n)=>item(10+n)),id(29));f.api.request=async()=>value;
  await ready(f);await el(f,'more').fire('click');assert.equal(buttons(f).length,0);
});
