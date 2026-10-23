import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';

const module = await import('../../../src/cn_contract/web/static/assistant-profile.mjs').catch(error => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return {};
});
const walk = element => [element, ...element.children.flatMap(walk)];
const hash = value => createHash('sha256').update(value).digest('hex');
const deferred = () => {let resolve; const promise = new Promise(done => resolve = done); return {promise, resolve};};
function dom() {
  let root;
  class Element {
    constructor(tag='div') {
      this.tagName=tag; this.children=[]; this.attributes={}; this.listeners={}; this.dataset={};
      this._text=''; this.hidden=false; this.isConnected=true; this.value='';
      const classes=new Set(); this.classList={add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v)};
    }
    set textContent(value) {this._text=String(value); this.replaceChildren();}
    get textContent() {return this._text+this.children.map(x=>x.textContent).join('');}
    set innerHTML(_) {throw new Error('HTML injection is forbidden');}
    setAttribute(key,value) {this.attributes[key]=String(value);}
    removeAttribute(key) {delete this.attributes[key];}
    append(...items) {for(const item of items){item.parentNode=this;this.children.push(item);}}
    replaceChildren(...items) {this.children=[];this.append(...items);}
    addEventListener(key,handler) {(this.listeners[key]??=[]).push(handler);}
    fire(key,event={}) {return Promise.all((this.listeners[key]||[]).map(fn=>fn({preventDefault(){},...event})));}
    focus() {root.activeElement=this;}
  }
  root=new Element(); root.body=new Element('body'); root.defaultView=new Element('window');
  root.createElement=tag=>new Element(tag);
  const nodes=new Map(['show-profile','profile-preview','close-profile-preview','profile-content','profile-refresh','profile-notice','composer']
    .map(key=>[key,new Element()]));
  root.getElementById=key=>nodes.get(key)||walk(root.getElementById('profile-content')).find(n=>n.id===key)||null;
  return root;
}
const scope={workspace_id:'11111111-1111-4111-8111-111111111111',conversation_id:'22222222-2222-4222-8222-222222222222',
  scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:7,materials_revision:3};
const quote='甲公司称收到款项🧾，尚未核对';
const messageRef=()=>({kind:'message',conversation_id:scope.conversation_id,message_id:'33333333-3333-4333-8333-333333333333',
  source_revision:2,start:10,end:10+[...quote].length,quote,quote_sha256:hash(quote)});
const documentRef=()=>({kind:'document',conversation_id:scope.conversation_id,attachment_id:'44444444-4444-4444-8444-444444444444',
  original_sha256:'a'.repeat(64),parse_revision:1,result_sha256:'b'.repeat(64),
  anchor:{id:'55555555-5555-4555-8555-555555555555',document_version_id:'44444444-4444-4444-8444-444444444444',
    part_name:'word/document.xml',element_id:'body/tbl[0]/tr[1]/tc[2]/p[0]',kind:'table_cell',quote,quote_sha256:hash(quote),
    start:0,end:[...quote].length,table:0,row:1,cell:2,page:null,bbox:null}});
const proposal=(field,value,refs=[messageRef()])=>({field,value,origin:'model_inference',verification:'unverified',source_refs:refs});
const field=(name,candidates=[],protected_value=null,verification='unverified')=>({field:name,candidates,protected_value,verification});
const saved=()=>({scope:{...scope,input_revision:5,materials_revision:2},revision:3,fields:[
  field('consultation',[proposal('consultation',{kind:'text',value:'<img src=x onerror=alert(1)> 合成陈述'},[messageRef(),documentRef()])]),
  field('principal_amount',[proposal('principal_amount',{kind:'money',value:'9999999999999999.12345678',unit:'CNY'})]),
  field('title',[proposal('title',{kind:'text',value:'候选甲'}),proposal('title',{kind:'text',value:'候选乙'})],{kind:'null'},'conflicted'),
  field('contact',[],{kind:'text',value:'合成本机联系人'}),
  field('questions',[],null,'unknown'),
]});
function fixture() {
  assert.equal(typeof module.bindProfile,'function','profile panel must export its read-only binder');
  const document=dom(); let panel,read=async()=>saved(),opens=0;const calls=[];
  const controller={state:{id:scope.conversation_id,view:{scope:{...scope}},status:'saved',loading:false},revoke(error){
    if(error.status===401||error.status===403){this.state.status='revoked';panel.state(this.state);return true;}return false;
  }};
  panel=module.bindProfile({controller,document,onOpen:()=>opens++,api:{getProfile:async(...args)=>{calls.push(args);return read(...args);}}});
  return {document,controller,panel,calls,at:key=>document.getElementById(key),set read(fn){read=fn;},get opens(){return opens;}};
}

export {fixture,saved,deferred};
