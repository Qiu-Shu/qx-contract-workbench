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
  field('title',[proposal('title',{kind:'text',value:'候选甲'}),proposal('title',{kind:'text',value:'候选乙'})],{kind:'null',value:null},'conflicted'),
  field('contact',[],{kind:'text',value:'合成本机联系人'}),
  field('questions',[],null,'unknown'),
]});
function fixture({writable=false,readonly=false}={}) {
  assert.equal(typeof module.bindProfile,'function','profile panel must export its binder');
  const document=dom(); let panel,read=async()=>saved(),opens=0;const calls=[],writes=[],lookups=[];let submit=async(_id,body)=>({...receipt(),profile_revision:body.patch.base_profile_revision+1,intake_id:body.expected_intake_id,intake_revision:body.expected_intake_revision,intake_sha256:body.expected_intake_id?'a'.repeat(64):null}),lookup=async()=>null;
  const controller={state:{id:scope.conversation_id,view:{scope:{...scope},projection_intake_id:null,archived_at:null},status:'saved',loading:false},revoke(error){
    if(error.status===401||error.status===403){this.state.status='revoked';panel.state(this.state);return true;}return false;
  }};
  const api={getProfile:async(...args)=>{calls.push(args);return read(...args);}};
  if(writable)Object.assign(api,{getConversation:async()=>structuredClone(controller.state.view),getIntake:async id=>({id,revision:4,matter_id:null}),
    submitProfileCommit:async(id,body)=>{writes.push([id,body]);return submit(id,body);},findProfileReceipt:async(id,key)=>{lookups.push([id,key]);return lookup(id,key);}});
  panel=module.bindProfile({controller,readonly,uuid:()=> '66666666-6666-4666-8666-666666666666',document,onOpen:()=>opens++,api});
  return {document,controller,panel,api,calls,writes,lookups,set submit(fn){submit=fn;},set lookup(fn){lookup=fn;},at:key=>document.getElementById(key),set read(fn){read=fn;},get opens(){return opens;}};
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

const receipt=()=>({conversation_id:scope.conversation_id,request_id:'66666666-6666-4666-8666-666666666666',
  sequence:1,profile_revision:4,profile_changed:true,projection_changed:false,intake_id:null,intake_revision:null,
  intake_sha256:null,event_type:'profile.saved',audience:'internal',consultation_origin:'user',created_at:'2026-10-24T00:00:00Z'});
async function edit(f,name,value){await f.at('profile-edit').fire('click');f.at('profile-edit-field').value=name;
  await f.at('profile-edit-field').fire('change');if(value!==undefined)f.at('profile-edit-value').value=value;}
const submitEdit=f=>f.at('profile-edit-form').fire('submit');
test('manual text/contact commit uses current scope, profile and intake baselines without model proposals',async()=>{
  const f=fixture({writable:true});f.controller.state.view.projection_intake_id='77777777-7777-4777-8777-777777777777';
  await f.panel.open();await edit(f,'contact','合成联系人');await submitEdit(f);
  assert.equal(f.writes.length,1);const body=f.writes[0][1];assert.deepEqual(body.patch.scope,scope);
  assert.equal(body.patch.base_profile_revision,3);assert.deepEqual(body.patch.changes,[]);
  assert.deepEqual(body.manual_edits,[{field:'contact',value:{kind:'text',value:'合成联系人'}}]);
  assert.equal(body.expected_intake_id,f.controller.state.view.projection_intake_id);assert.equal(body.expected_intake_revision,4);
  assert.equal(body.project_intake,false);assert.match(f.at('profile-notice').textContent,/保存|回执/);
});
test('manual form supports explicit protected clear, lists, money and timezone-aware dates',async()=>{
  for(const [name,text,expected] of [['questions','追问甲\n追问乙',{kind:'list',value:['追问甲','追问乙']}],
    ['principal_amount','9999999999999999.12345678',{kind:'money',value:'9999999999999999.12345678',unit:'CNY'}],
    ['follow_up_at','2026-10-24T08:30',{kind:'datetime',value:new Date('2026-10-24T08:30').toISOString()}]]){
    const f=fixture({writable:true});await f.panel.open();await edit(f,name,text);await submitEdit(f);
    assert.deepEqual(f.writes[0][1].manual_edits[0].value,expected);
  }
  const f=fixture({writable:true});await f.panel.open();await edit(f,'title');f.at('profile-edit-clear').checked=true;
  await f.at('profile-edit-clear').fire('change');await submitEdit(f);assert.deepEqual(f.writes[0][1].manual_edits,[{field:'title',value:{kind:'null',value:null}}]);
});
test('materials keep individual states including lawyer checked status',async()=>{
  const f=fixture({writable:true});await f.panel.open();await edit(f,'materials');await f.at('profile-material-add').fire('click');
  f.at('profile-material-name-0').value='合成证据';f.at('profile-material-state-0').value='checked';await submitEdit(f);
  assert.deepEqual(f.writes[0][1].manual_edits[0].value,{kind:'materials',value:[{name:'合成证据',state:'checked'}]});
});
test('history readonly and archived views never expose editors',async()=>{
  const readonly=fixture({writable:true,readonly:true});await readonly.panel.open();assert.equal(readonly.at('profile-edit'),null);
  const archived=fixture({writable:true});archived.controller.state.view.archived_at='2026-10-24T00:00:00Z';await archived.panel.open();assert.equal(archived.at('profile-edit'),null);
  const f=fixture({writable:true});await f.panel.open();f.read=async(_id,revision)=>({...saved(),revision:revision??3});
  const history=walk(f.at('profile-content')).find(n=>n.tagName==='form');walk(history).find(n=>n.tagName==='input').value='1';await history.fire('submit');
  assert.equal(f.at('profile-edit'),null);
});
test('unknown POST performs receipt lookup only and cannot submit a duplicate',async()=>{
  const f=fixture({writable:true});f.submit=async()=>{throw {code:'NETWORK_UNKNOWN',status:0};};await f.panel.open();await edit(f,'contact','待核');
  await submitEdit(f);assert.equal(f.writes.length,1);assert.equal(f.lookups.length,1);assert.match(f.at('profile-notice').textContent,/尚未确认|未知/);
  await f.at('profile-check-receipt').fire('click');assert.equal(f.writes.length,1);assert.equal(f.lookups.length,2);
  f.lookup=async()=>receipt();await f.at('profile-check-receipt').fire('click');assert.equal(f.writes.length,1);assert.match(f.at('profile-notice').textContent,/保存|回执/);
});
test('VERSION_CONFLICT refreshes latest profile and invalidates edits',async()=>{
  const f=fixture({writable:true});await f.panel.open();await edit(f,'contact','过期内容');f.submit=async()=>{throw {code:'VERSION_CONFLICT',status:409};};
  f.read=async()=>({...saved(),revision:5});await submitEdit(f);assert.equal(f.writes.length,1);assert.ok(f.calls.length>=2);
  assert.equal(f.at('profile-edit-form'),null);assert.match(f.at('profile-notice').textContent,/版本.*变化|版本.*更新/);
});
test('input change, scope switch and closing during baseline read cannot apply stale edits',async()=>{
  const f=fixture({writable:true});await f.panel.open();await edit(f,'contact','过期');f.controller.state.view.scope.input_revision++;f.panel.state(f.controller.state);
  assert.equal(f.at('profile-edit-form'),null);assert.equal(f.writes.length,0);
  const g=fixture({writable:true});await g.panel.open();await edit(g,'contact','待核');const gate=deferred();g.submit=()=>gate.promise;
  const saving=submitEdit(g);g.controller.state.id='other';g.panel.state(g.controller.state);gate.resolve(receipt());await saving;
  assert.equal(g.at('profile-content').textContent,'');assert.equal(g.at('profile-notice').textContent,'');
});
test('empty profile can be manually started and blank title is rejected without POST',async()=>{
  const f=fixture({writable:true});f.read=async()=>null;await f.panel.open();await edit(f,'title','');await submitEdit(f);
  assert.equal(f.writes.length,0);f.at('profile-edit-value').value='合成事项';await submitEdit(f);assert.equal(f.writes[0][1].patch.base_profile_revision,0);
});

test('explicit revision routes including latest remain read-only until current is reread',async()=>{
  const f=fixture({writable:true});await f.panel.open();const history=walk(f.at('profile-content')).find(n=>n.tagName==='form');
  walk(history).find(n=>n.tagName==='input').value='3';await history.fire('submit');assert.equal(f.at('profile-edit'),null);
  await f.at('profile-refresh').fire('click');assert.ok(f.at('profile-edit'));
});
test('unchanged receipt is accurately reported and malformed receipt stays unknown',async()=>{
  const f=fixture({writable:true});f.submit=async()=>({...receipt(),profile_revision:3,profile_changed:false,event_type:'profile.unchanged'});
  await f.panel.open();await edit(f,'contact','合成本机联系人');await submitEdit(f);assert.match(f.at('profile-notice').textContent,/未变化/);
  const g=fixture({writable:true});g.submit=async()=>({...receipt(),conversation_id:'other'});await g.panel.open();await edit(g,'contact','不确认');await submitEdit(g);
  assert.equal(g.lookups.length,1);assert.match(g.at('profile-notice').textContent,/尚未确认/);assert.equal(g.at('profile-edit'),null);
});
test('reopening an unknown save retains receipt-only recovery',async()=>{
  const f=fixture({writable:true});f.submit=async()=>{throw {code:'NETWORK_UNKNOWN'};};await f.panel.open();await edit(f,'contact','待核');await submitEdit(f);
  f.panel.close();await f.panel.open();assert.equal(f.at('profile-edit'),null);assert.ok(f.at('profile-check-receipt'));assert.match(f.at('profile-notice').textContent,/尚未确认/);
});

test('late intake baseline read after panel close does not restore editor or submit',async()=>{
  const f=fixture({writable:true}),gate=deferred();f.controller.state.view.projection_intake_id='77777777-7777-4777-8777-777777777777';
  f.api.getIntake=()=>gate.promise;await f.panel.open();const editing=f.at('profile-edit').fire('click');
  await Promise.resolve();f.panel.close();gate.resolve({id:'77777777-7777-4777-8777-777777777777',revision:4,matter_id:null});await editing;
  assert.equal(f.at('profile-content').textContent,'');assert.equal(f.writes.length,0);
});
test('duplicate submit during save creates one request and no premature receipt lookup',async()=>{
  const f=fixture({writable:true}),gate=deferred();await f.panel.open();await edit(f,'contact','合成联系');f.submit=()=>gate.promise;
  const form=f.at('profile-edit-form'),saving=form.fire('submit');await form.fire('submit');assert.equal(f.writes.length,1);assert.equal(f.lookups.length,0);
  gate.resolve(receipt());await saving;assert.equal(f.writes.length,1);
});

test('definite rejected save after close clears pending without reopening the old panel',async()=>{
  const f=fixture({writable:true}),gate=deferred();
  await f.panel.open();await edit(f,'contact','合成待拒绝更正');
  f.submit=async()=>{await gate.promise;throw {code:'VERSION_CONFLICT',status:409};};
  const saving=submitEdit(f);assert.equal(f.writes.length,1);f.panel.close();
  gate.resolve();await saving;
  assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.at('profile-content').textContent,'');
  await f.panel.open();
  assert.ok(f.at('profile-edit'),'a confirmed rejection must not leave a receipt-only dead end');
  assert.equal(f.at('profile-check-receipt'),null);assert.equal(f.writes.length,1);assert.equal(f.lookups.length,0);
});

test('definite rejected save after same-scope refresh clears pending without stale notices',async()=>{
  const f=fixture({writable:true}),gate=deferred();
  await f.panel.open();await edit(f,'contact','合成无效更正');
  f.submit=async()=>{await gate.promise;throw {code:'VALIDATION_ERROR',status:422};};
  const saving=submitEdit(f);assert.equal(f.writes.length,1);
  await f.at('profile-refresh').fire('click');const latestNotice=f.at('profile-notice').textContent;
  gate.resolve();await saving;
  assert.equal(f.at('profile-notice').textContent,latestNotice,'an old callback must not replace the refreshed view notice');
  await f.at('profile-refresh').fire('click');
  assert.ok(f.at('profile-edit'),'confirmed rejection after epoch change must permit a new explicit edit');
  assert.equal(f.at('profile-check-receipt'),null);assert.equal(f.writes.length,1);assert.equal(f.lookups.length,0);
});

test('late profile reread after successful save cannot put its receipt notice on another conversation',async()=>{
  const f=fixture({writable:true}),gate=deferred();
  await f.panel.open();await edit(f,'contact','合成原对话更正');
  f.read=()=>gate.promise;
  const saving=submitEdit(f);
  for(let tick=0;tick<10&&f.calls.length<2;tick++)await Promise.resolve();
  assert.equal(f.calls.length,2,'successful save must have started its follow-up profile read');
  const next='88888888-8888-4888-8888-888888888888';
  f.controller.state.id=next;f.controller.state.view.scope={...scope,conversation_id:next};f.panel.state(f.controller.state);
  f.read=async()=>({scope:{...scope,conversation_id:next},revision:9,fields:[]});
  await f.panel.open();const latestNotice=f.at('profile-notice').textContent;
  assert.match(latestNotice,/9/);
  gate.resolve(saved());await saving;
  assert.equal(f.at('profile-notice').textContent,latestNotice,'old save confirmation must not label the new conversation');
  assert.equal(f.writes.length,1);
});

for(const delayedStage of ['controller','profile'])test(`late conflict refresh at ${delayedStage} cannot read or label another conversation`,async()=>{
  const f=fixture({writable:true}),gate=deferred();let refreshing=false;
  await f.panel.open();await edit(f,'contact','合成过期更正');
  f.submit=async()=>{throw {code:'VERSION_CONFLICT',status:409};};
  f.controller.refresh=async()=>{refreshing=true;if(delayedStage==='controller')await gate.promise;return true;};
  if(delayedStage==='profile')f.read=()=>gate.promise;
  const saving=submitEdit(f);
  for(let tick=0;tick<10&&(!refreshing||(delayedStage==='profile'&&f.calls.length<2));tick++)await Promise.resolve();
  assert.equal(refreshing,true);
  if(delayedStage==='profile')assert.equal(f.calls.length,2);
  const next='99999999-9999-4999-8999-999999999999';
  f.controller.state.id=next;f.controller.state.view.scope={...scope,conversation_id:next};f.panel.state(f.controller.state);
  f.read=async()=>({scope:{...scope,conversation_id:next},revision:10,fields:[]});
  await f.panel.open();const latestNotice=f.at('profile-notice').textContent,reads=f.calls.length;
  gate.resolve(delayedStage==='profile'?saved():true);await saving;
  assert.equal(f.calls.length,reads,'old conflict refresh must not fetch the new conversation');
  assert.equal(f.at('profile-notice').textContent,latestNotice,'old conflict must not label the new conversation');
  assert.equal(f.writes.length,1);
});
