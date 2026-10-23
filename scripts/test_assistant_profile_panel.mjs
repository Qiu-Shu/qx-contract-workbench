import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';

const module = await import('../src/cn_contract/web/static/assistant-profile.mjs').catch(error => {
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
test('starts hidden, reads only on open, and closes with keyboard focus restored',async()=>{
  const f=fixture(),trigger=f.document.createElement('button');assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.calls.length,0);
  assert.equal(await f.panel.open(trigger),true);assert.deepEqual(f.calls,[[scope.conversation_id,undefined]]);assert.equal(f.opens,1);
  assert.equal(f.document.activeElement,f.at('close-profile-preview'));
  await f.document.fire('keydown',{key:'Escape'});assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.document.activeElement,trigger);
  assert.equal(f.at('profile-content').textContent,'');assert.equal(f.at('profile-notice').textContent,'');
});
test('renders literal candidates, protected explicit null, exact money and unresolved states',async()=>{
  const f=fixture();await f.panel.open();const body=f.at('profile-content');
  for(const expected of ['<img src=x onerror=alert(1)>','9999999999999999.12345678','CNY','候选甲','候选乙','合成本机联系人'])assert.ok(body.textContent.includes(expected));
  assert.match(body.textContent,/律师.*清空/);assert.match(body.textContent,/待核/);assert.match(body.textContent,/冲突/);assert.match(body.textContent,/未知|尚无/);
  assert.equal(walk(body).filter(n=>['img','script','a'].includes(n.tagName)).length,0);
  assert.equal(walk(body).filter(n=>n.tagName==='input').length,1);
});
test('source details preserve complete message and document anchor provenance',async()=>{
  const f=fixture();await f.panel.open();const text=f.at('profile-content').textContent;
  for(const expected of [quote,messageRef().message_id,messageRef().quote_sha256,documentRef().original_sha256,
    documentRef().result_sha256,documentRef().attachment_id,documentRef().anchor.id,documentRef().anchor.element_id,'word/document.xml'])assert.ok(text.includes(expected),expected);
  assert.match(text,/字符.*10/);assert.match(text,/输入版本.*2/);assert.match(text,/读取版本.*1/);
  assert.match(text,/表.*0.*行.*1.*列.*2/);
});
test('empty revision zero explains missing draft without claiming generation or saving',async()=>{
  const f=fixture();f.read=async()=>({scope:{...scope},revision:0,fields:[]});await f.panel.open();
  assert.match(f.at('profile-content').textContent,/尚无.*档案草稿/);assert.equal(walk(f.at('profile-content')).filter(n=>n.tagName==='input').length,0);
  assert.doesNotMatch(f.at('profile-notice').textContent,/保存成功|已生成/);
});
test('current profile null is an honest empty state while absent historical versions remain errors',async()=>{
  const f=fixture();f.read=async()=>null;assert.equal(await f.panel.open(),true);
  assert.match(f.at('profile-content').textContent,/尚无.*档案草稿/);
  assert.doesNotMatch(f.at('profile-notice').textContent,/失败|未能|版本 0|已保存|已生成/);
  f.read=async()=>saved();await f.at('profile-refresh').fire('click');
  const form=walk(f.at('profile-content')).find(n=>n.tagName==='form');walk(form).find(n=>n.tagName==='input').value='1';
  f.read=async()=>{throw {status:409,code:'STATE_CONFLICT'};};await form.fire('submit');
  assert.equal(f.at('profile-content').textContent,'');assert.match(f.at('profile-notice').textContent,/重新读取/);
});
test('history accepts bounded integer versions, gets exact endpoint argument, and can reread latest',async()=>{
  const f=fixture();await f.panel.open();let form=walk(f.at('profile-content')).find(n=>n.tagName==='form');let input=walk(form).find(n=>n.tagName==='input');
  assert.equal(String(input.max),'3');assert.equal(String(input.min),'1');
  for(const invalid of ['0','4','2.5','1e0','']){input.value=invalid;await form.fire('submit');assert.equal(f.calls.length,1);}
  f.read=async(id,revision)=>({...saved(),revision:revision??3});input.value='1';await form.fire('submit');
  assert.deepEqual(f.calls.at(-1),[scope.conversation_id,1]);assert.match(f.at('profile-notice').textContent,/历史.*1|版本 1.*历史/);
  form=walk(f.at('profile-content')).find(n=>n.tagName==='form');input=walk(form).find(n=>n.tagName==='input');assert.equal(String(input.max),'3');
  await f.at('profile-refresh').fire('click');assert.deepEqual(f.calls.at(-1),[scope.conversation_id,undefined]);assert.match(f.at('profile-notice').textContent,/3/);
});
test('huge revision counts use one numeric input rather than enumerating all versions',async()=>{
  const f=fixture();f.read=async()=>({...saved(),revision:1000000000});await f.panel.open();
  assert.ok(walk(f.at('profile-content')).length<200);assert.equal(walk(f.at('profile-content')).filter(n=>n.tagName==='option').length,0);
});
test('wrong historical revision is never presented as the selected version',async()=>{
  const f=fixture();await f.panel.open();const form=walk(f.at('profile-content')).find(n=>n.tagName==='form');walk(form).find(n=>n.tagName==='input').value='1';
  await form.fire('submit');assert.doesNotMatch(f.at('profile-content').textContent,/候选甲/);assert.match(f.at('profile-notice').textContent,/重读|重新读取/);
});
test('workspace conversation binding and scope boundaries reject mismatched snapshots',async()=>{
  for(const mutate of [s=>s.workspace_id='other',s=>s.conversation_id='other',s=>s.binding_revision=2,s=>s.scope_kind='intake',s=>s.scope_ref='other']){
    const f=fixture();f.read=async()=>{const value=saved();mutate(value.scope);return value;};assert.equal(await f.panel.open(),false);
    assert.doesNotMatch(f.at('profile-content').textContent,/候选甲|合成本机联系人/);
  }
});
test('historical input and material revisions are allowed but future or malformed ones are refused',async()=>{
  const f=fixture();assert.equal(await f.panel.open(),true);
  for(const mutate of [s=>s.input_revision=8,s=>s.materials_revision=4,s=>s.input_revision=-1,s=>s.materials_revision='2']){
    f.read=async()=>{const value=saved();mutate(value.scope);return value;};assert.equal(await f.panel.open(),false);
  }
});
test('switching loading or revocation clears old data and discards late responses',async()=>{
  for(const change of [s=>s.id='other',s=>s.view.scope.workspace_id='other',s=>s.view.scope.scope_kind='intake',s=>s.view.scope.scope_ref='other',
    s=>s.view.scope.binding_revision++,s=>s.loading=true,s=>s.status='revoked',s=>s.view=null]){
    const f=fixture(),gate=deferred();f.read=()=>gate.promise;const opened=f.panel.open();change(f.controller.state);f.panel.state(f.controller.state);
    assert.equal(f.at('profile-preview').hidden,true);gate.resolve(saved());assert.equal(await opened,false);assert.equal(f.at('profile-content').textContent,'');
  }
});
test('pagehide clears records and prevents subsequent or late reads',async()=>{
  const f=fixture(),gate=deferred();f.read=()=>gate.promise;const opened=f.panel.open();await f.document.defaultView.fire('pagehide');
  gate.resolve(saved());assert.equal(await opened,false);assert.equal(f.at('profile-content').textContent,'');assert.equal(await f.panel.open(),false);assert.equal(f.calls.length,1);
});
test('newer reads win and close prevents pending data or notices from returning',async()=>{
  const f=fixture(),gate=deferred();f.read=()=>gate.promise;const old=f.panel.open();f.read=async()=>({...saved(),revision:4});await f.panel.open();
  gate.resolve(saved());assert.equal(await old,false);assert.match(f.at('profile-notice').textContent,/4/);
  const next=deferred();f.read=()=>next.promise;const pending=f.panel.open();f.panel.close();next.resolve(saved());assert.equal(await pending,false);assert.equal(f.at('profile-content').textContent,'');
});
test('network failure clears old success and raw diagnostics, then permits explicit reread',async()=>{
  const f=fixture();await f.panel.open();f.read=async()=>{throw {message:'PRIVATE DIAGNOSTIC',code:'NETWORK_UNKNOWN'};};await f.at('profile-refresh').fire('click');
  assert.equal(f.at('profile-content').textContent,'');assert.match(f.at('profile-notice').textContent,/重读|重新读取/);assert.doesNotMatch(f.at('profile-notice').textContent,/PRIVATE|已保存|保存成功/);
  f.read=async()=>saved();await f.at('profile-refresh').fire('click');assert.match(f.at('profile-content').textContent,/候选甲/);
});
test('authorization errors erase all profile values without retaining diagnostics',async()=>{
  for(const status of [401,403]){const f=fixture();await f.panel.open();f.read=async()=>{throw {status,message:'PRIVATE'};};await f.at('profile-refresh').fire('click');
    assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.at('profile-content').textContent,'');assert.equal(f.at('profile-notice').textContent,'');}
});
test('a growing current input snapshot does not erase a still valid historical profile',async()=>{
  const f=fixture();await f.panel.open();f.controller.state.view.scope.input_revision++;f.panel.state(f.controller.state);
  assert.equal(f.at('profile-preview').hidden,false);assert.match(f.at('profile-content').textContent,/候选甲/);assert.equal(f.calls.length,1);
});
test('a rollback below the displayed source snapshot clears now-incompatible content',async()=>{
  for(const key of ['input_revision','materials_revision']){
    const f=fixture();await f.panel.open();f.controller.state.view.scope[key]=0;f.panel.state(f.controller.state);
    assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.at('profile-content').textContent,'');
  }
});
test('no conversation, unresolved scope, loading, and revoked state cannot issue reads',async()=>{
  for(const change of [s=>s.id=null,s=>s.view=null,s=>s.view.scope.conversation_id='other',s=>s.loading=true,s=>s.status='revoked']){
    const f=fixture();change(f.controller.state);f.panel.state(f.controller.state);assert.equal(await f.panel.open(),false);
    assert.equal(f.at('show-profile').disabled,true);assert.equal(f.calls.length,0);
  }
});
test('quote offsets use Unicode code points and reject broken source ranges',async()=>{
  const f=fixture();assert.equal(await f.panel.open(),true);
  for(const change of [v=>v.fields[0].candidates[0].source_refs[0].end++,v=>v.fields[0].candidates[0].source_refs[1].anchor.end++]){
    f.read=async()=>{const result=saved();change(result);return result;};assert.equal(await f.panel.open(),false);
    assert.equal(f.at('profile-content').textContent,'');
  }
});
test('invalid values, claimed verification and model contact proposals never render',async()=>{
  for(const mutate of [v=>v.fields[0].verification='verified',v=>v.fields[0].candidates[0].verification='verified',
    v=>v.fields[1].candidates[0].value.value=9999999999999999,v=>v.fields[3].candidates=[proposal('contact',{kind:'text',value:'无权提取的联系信息'})],
    v=>v.fields[0].candidates[0].source_refs[0].conversation_id='other',v=>v.fields[0].candidates[0].source_refs[0].source_revision=6,
    v=>v.fields[0].candidates[0].source_refs[1].parse_revision=3,v=>v.fields[0].candidates[0].source_refs[1].anchor.document_version_id='other']){
    const f=fixture();f.read=async()=>{const v=saved();mutate(v);return v;};assert.equal(await f.panel.open(),false);assert.equal(f.at('profile-content').textContent,'');
  }
});
test('list material and date values preserve original text and honest material status',async()=>{
  const f=fixture();f.read=async()=>({...saved(),fields:[
    field('questions',[proposal('questions',{kind:'list',value:['合成追问甲','合成追问乙']})]),
    field('materials',[proposal('materials',{kind:'materials',value:[{name:'合成流水',state:'received'},{name:'合成凭证',state:'needed'}]})]),
    field('follow_up_at',[],{kind:'datetime',value:'2026-10-24T08:00:00Z'}),
  ]});await f.panel.open();const text=f.at('profile-content').textContent;
  for(const expected of ['合成追问甲','合成追问乙','合成流水','合成凭证','2026-10-24T08:00:00Z'])assert.ok(text.includes(expected));
  assert.match(text,/已收|已收到/);assert.match(text,/待补|需要/);assert.doesNotMatch(text,/已核验/);
});
