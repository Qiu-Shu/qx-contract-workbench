import test from 'node:test';
import assert from 'node:assert/strict';
import {bindProfile} from '../../../src/cn_contract/web/static/assistant-profile.mjs';
const uuid=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
const scope={workspace_id:uuid(1),conversation_id:uuid(2),scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:2,materials_revision:1};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function setup(){
 let document;class E{
  constructor(){this.children=[];this.listeners={};this.attrs={};this.hidden=false;this.isConnected=true;this._text='';this.classList={add(){},remove(){}};}
  set textContent(v){this._text=String(v);this.children=[];}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  set innerHTML(_){throw Error('unsafe HTML');}append(...x){this.children.push(...x);}replaceChildren(...x){this._text='';this.children=x;}
  setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}focus(){document.activeElement=this;}
  addEventListener(k,v){(this.listeners[k]??=[]).push(v);}fire(k){for(const f of this.listeners[k]||[])f({preventDefault(){},currentTarget:this});}
 }
 const nodes=new Map(['show-profile','profile-preview','close-profile-preview','profile-content','profile-refresh','profile-notice','composer'].map(x=>[x,new E()]));
 document=new E();document.body=new E();document.defaultView=new E();document.getElementById=id=>nodes.get(id);document.createElement=()=>new E();
 const controller={state:{id:scope.conversation_id,view:{scope:{...scope}},status:'saved',loading:false},revoke(){return false;}};
 let response=async()=>({scope:{...scope},revision:1,fields:[]});const calls=[];
 const panel=bindProfile({controller,document,api:{getProfile:async(...x)=>{calls.push(x);return response(...x);}}});
 return {panel,controller,document,nodes,calls,setResponse(fn){response=fn;}};
}
test('a closed panel cannot be resurrected by a late saved profile response',async()=>{
 const f=setup(),gate=deferred();f.setResponse(()=>gate.promise);
 const pending=f.panel.open();f.panel.close();gate.resolve({scope:{...scope},revision:1,fields:[]});
 assert.equal(await pending,false);assert.equal(f.nodes.get('profile-preview').hidden,true);assert.equal(f.nodes.get('profile-content').textContent,'');
 assert.equal(f.nodes.get('profile-notice').textContent,'');assert.equal(f.calls.length,1);
});
test('same conversation with changed binding cannot publish a late profile result',async()=>{
 const f=setup(),gate=deferred();f.setResponse(()=>gate.promise);const pending=f.panel.open();
 f.controller.state.view.scope.binding_revision++;f.panel.state(f.controller.state);
 gate.resolve({scope:{...scope},revision:1,fields:[]});assert.equal(await pending,false);
 assert.equal(f.nodes.get('profile-content').textContent,'');assert.equal(f.nodes.get('profile-preview').hidden,true);
});
test('protected large decimal and HTML-shaped text remain exact text and read-only',async()=>{
 const f=setup(),money='9007199254740993.1234567890123456789',markup='<svg onload=private()> synthetic only';
 f.setResponse(async()=>({scope:{...scope},revision:3,fields:[
  {field:'principal_amount',verification:'unverified',protected_value:{kind:'money',value:money,unit:'CNY'},candidates:[]},
  {field:'title',verification:'unverified',protected_value:{kind:'text',value:markup},candidates:[]}
 ]}));assert.equal(await f.panel.open(),true);
 const text=f.nodes.get('profile-content').textContent;assert.ok(text.includes(money+' CNY'));assert.ok(text.includes(markup));
 assert.ok(text.includes('受保护'));assert.equal(f.calls.length,1);assert.deepEqual(f.calls[0],[scope.conversation_id,undefined]);
});
test('pagehide invalidates pending content and future opens without issuing another read',async()=>{
 const f=setup(),gate=deferred();f.setResponse(()=>gate.promise);const pending=f.panel.open();f.document.defaultView.fire('pagehide');
 gate.resolve({scope:{...scope},revision:1,fields:[]});assert.equal(await pending,false);assert.equal(await f.panel.open(),false);
 assert.equal(f.calls.length,1);assert.equal(f.nodes.get('profile-content').textContent,'');
});
