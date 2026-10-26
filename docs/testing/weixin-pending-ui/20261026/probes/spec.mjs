import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync} from 'node:fs';

const source=new URL('../../../../../src/cn_contract/web/static/assistant-weixin-pending.mjs',import.meta.url);
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

test('strict receipt rejects array digest and preserves unresolved operation',async()=>{
  const f=fixture();await ready(f);const value=receipt();value.receipt_sha256=['a'.repeat(64)];
  f.api.request=async(path,opts={})=>opts.method==='POST'?value:page([]);
  await buttons(f)[0].fire('click');
  assert.equal(f.binding.hasPending(),true,'non-string hash must not confirm dispatch');
  assert.equal(f.saved.length,0);
});
test('strict UTC metadata rejects impossible calendar date',async()=>{
  const f=fixture(),value=page();value.items[0].received_at='2026-02-30T08:00:00Z';
  f.api.request=async()=>value;await ready(f);
  assert.equal(buttons(f).length,0,'invalid Feb 30 must not display as March 2');
});
test('late POST after CID switch never displays receipt or invokes projection callback',async()=>{
  const f=fixture();await ready(f);let finish;f.api.request=()=>new Promise(resolve=>finish=resolve);
  const posting=buttons(f)[0].fire('click');f.state({id:ids.other,view:view(ids.other)});
  finish(receipt());await posting;
  assert.equal(f.saved.length,0);assert.equal(f.binding.hasPending(),false);assert.equal(el(f,'result').textContent,'');
});