import assert from 'node:assert/strict';
import test from 'node:test';

const module=await import('../src/cn_contract/web/static/reception-worksheet.mjs').catch(error=>{
  if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;return {};
});
const cid='11111111-1111-4111-8111-111111111111';
const scope={workspace_id:'22222222-2222-4222-8222-222222222222',conversation_id:cid,scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:0,materials_revision:0};
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const walk=e=>[e,...e.children.flatMap(walk)];
class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.open=false;}
  append(...items){this.children.push(...items);}replaceChildren(...items){this.children=[...items];this.textContent='';}
  addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(name,value){this[name]=value;}focus(){this.focused=true;}
}
function fixture({readonly=false}={}){
  assert.equal(typeof module.bindReceptionWorksheet,'function','worksheet binder must exist');
  const elements=new Map(),calls=[];let revision=1,key=0;
  let fields=[{field:'consultation',protected_value:{kind:'text',value:'甲称借出10万元，部分已还。'},candidates:[],verification:'unverified'},
    {field:'internal_notes',protected_value:{kind:'text',value:'原内部备注保留'},candidates:[],verification:'unverified'}];
  const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement:tag=>new Element(tag)};
  const view=()=>({scope:{...scope},composer_revision:controller.state.view.composer_revision,profile_revision:revision,
    expected_intake_id:null,expected_intake_revision:null,writable:true,fields:structuredClone(fields)});
  const controller={state:{id:cid,status:'saved',loading:false,dirty:false,text:'补充：还款方式待核',savedText:'补充：还款方式待核',skill:null,
    view:{scope:{...scope},composer_revision:0,archived_at:null},generation:{items:[]}},
    revoke(error){if(error.status!==401&&error.status!==403)return false;this.state.status='revoked';panel.state(this.state);return true;},
    async save(){calls.push(['save-composer']);this.state.savedText=this.state.text;this.state.dirty=false;return true;},
    async refresh(){return true;},edit(text){this.state.text=text;this.state.dirty=true;calls.push(['edit-composer',text]);}};
  const receipt=body=>({conversation_id:cid,request_id:body.request_id,profile_revision:revision,profile_changed:true,
    projection_changed:false,intake_id:null,intake_revision:null,intake_sha256:null,audience:'internal',sequence:revision,event_type:'profile.saved'});
  const api={getWorksheet:async()=>{calls.push(['read']);return view();},
    commitWorksheet:async(id,body)=>{calls.push(['commit',id,body]);revision++;
      for(const edit of body.manual_edits){const old=fields.find(f=>f.field===edit.field);if(old)old.protected_value=edit.value;
        else fields.push({field:edit.field,protected_value:edit.value,candidates:[],verification:'unverified'});}return receipt(body);},
    findWorksheetReceipt:async(id,key)=>{calls.push(['lookup',id,key]);return null;},
    suggestWorksheet:async()=>({scope:{...scope},profile_revision:revision,origin:'template',model_called:false,
      items:[{question:'还款的时间、金额与凭证是什么？',reason:'余额仍待核。',quote:'部分已还',source_field:'consultation',materials:['还款凭证']}]}),
    prepareWorksheet:async()=>({scope:{...scope},composer_revision:controller.state.view.composer_revision,profile_revision:revision,
      model_called:false,content:'【接待追问任务：借贷咨询】\n补充：还款方式待核'})};
  const panel=module.bindReceptionWorksheet({controller,api,document,readonly,uuid:()=>`request-${++key}`});panel.state(controller.state);
  const input=(id,value)=>{const e=document.getElementById(id);e.value=value;e.listeners.input();};
  return {panel,controller,api,document,calls,input,view,setFields:value=>{fields=value;},receipt};
}

test('manual notes retain old text, are protected in one save and reopen without sending',async()=>{
  const f=fixture();await f.panel.open();f.input('worksheet-notes','原内部备注保留\n客户诉求：核对还款');
  assert.equal(f.panel.hasPending(),true);await f.panel.save();
  const body=f.calls.find(x=>x[0]==='commit')[2];assert.equal(body.project_intake,false);
  assert.deepEqual(body.manual_edits.map(x=>x.field),['internal_notes']);
  assert.equal(f.panel.hasPending(),false);await f.panel.refresh();
  assert.match(f.document.getElementById('worksheet-notes').value,/原内部备注保留/);
});

test('template suggestions are explicitly adopted into editable fields, never auto saved',async()=>{
  const f=fixture();await f.panel.open();await f.panel.suggest();
  const nodes=walk(f.document.getElementById('worksheet-suggestions'));
  assert.ok(nodes.some(e=>e.textContent.includes('模板')));
  nodes.find(e=>e.textContent==='采用此追问').listeners.click();
  assert.match(f.document.getElementById('worksheet-questions').value,/还款/);
  assert.match(f.document.getElementById('worksheet-materials').value,/还款凭证/);
  assert.equal(f.calls.filter(x=>x[0]==='commit').length,0);assert.equal(f.panel.hasPending(),true);
});

test('unknown save queries its original receipt without repeating the POST',async()=>{
  const f=fixture();await f.panel.open();f.input('worksheet-client-reply','请补还款记录。');
  f.api.commitWorksheet=async(id,body)=>{f.calls.push(['commit',id,body]);throw {code:'NETWORK_UNKNOWN',status:0};};
  await f.panel.save();await f.panel.save();await f.panel.lookup();
  assert.equal(f.calls.filter(x=>x[0]==='commit').length,1);
  const lookups=f.calls.filter(x=>x[0]==='lookup');assert.ok(lookups.length>=1);assert.ok(lookups.every(x=>x[2]===lookups[0][2]));
  assert.equal(f.panel.hasPending(),true);
});

test('a version conflict retains local edits until explicit resolution',async()=>{
  const f=fixture();await f.panel.open();f.input('worksheet-notes','我的未保存更正');
  f.api.commitWorksheet=async()=>{throw {code:'VERSION_CONFLICT',status:409};};
  await f.panel.save();assert.equal(f.document.getElementById('worksheet-notes').value,'我的未保存更正');
  assert.equal(f.document.getElementById('worksheet-conflict').hidden,false);
  await f.panel.useServer();assert.equal(f.document.getElementById('worksheet-notes').value,'原内部备注保留');
});

test('preparation keeps additional input visible and never invokes a send',async()=>{
  const f=fixture();await f.panel.open();await f.panel.prepare();
  assert.match(f.controller.state.text,/补充：还款方式待核/);
  assert.match(f.controller.state.text,/接待追问任务/);
  assert.equal(f.calls.filter(x=>x[0]==='edit-composer').length,1);
});

test('new typing while preparation waits is never overwritten',async()=>{
  const f=fixture();await f.panel.open();const pending=deferred();f.api.prepareWorksheet=()=>pending.promise;
  const running=f.panel.prepare();await new Promise(done=>setImmediate(done));
  f.controller.state.text='刚输入的新补充';f.controller.state.dirty=true;
  pending.resolve({scope,composer_revision:0,profile_revision:1,model_called:false,content:'【接待追问任务：借贷咨询】\n旧资料'});await running;
  assert.equal(f.controller.state.text,'刚输入的新补充');
  assert.equal(f.calls.filter(x=>x[0]==='edit-composer').length,0);
});

test('late read and suggestions cannot populate another conversation',async()=>{
  const f=fixture();const pending=deferred();f.api.getWorksheet=()=>pending.promise;
  const running=f.panel.open();f.controller.state={...f.controller.state,id:'different'};f.panel.state(f.controller.state);
  pending.resolve(f.view());await running;
  assert.equal(f.document.getElementById('worksheet-source').value,'');
});

test('conflicting candidates are shown, not silently selected or cleared on unrelated saves',async()=>{
  const f=fixture();f.setFields([{field:'consultation',protected_value:null,verification:'conflicted',candidates:[
    {value:{kind:'text',value:'候选甲'},origin:'model_inference',source_refs:[]},
    {value:{kind:'text',value:'候选乙'},origin:'model_inference',source_refs:[]}]}]);
  await f.panel.open();assert.equal(f.document.getElementById('worksheet-source').value,'');
  f.input('worksheet-notes','内部记录');await f.panel.save();
  assert.deepEqual(f.calls.find(x=>x[0]==='commit')[2].manual_edits.map(e=>e.field),['internal_notes']);
});

test('readonly, archived and revoked contexts disable saves and preparation',async()=>{
  const f=fixture({readonly:true});await f.panel.open();await f.panel.save();await f.panel.prepare();
  assert.deepEqual(f.calls.map(x=>x[0]),['read']);assert.equal(f.document.getElementById('worksheet-notes').value,'原内部备注保留');
  assert.equal(f.document.getElementById('worksheet-notes').disabled,true);
  const g=fixture();await g.panel.open();g.controller.state.status='revoked';g.panel.state(g.controller.state);
  assert.equal(g.document.getElementById('worksheet-source').value,'');assert.equal(g.panel.hasPending(),false);
});

for(const mutation of ['skill','context','materials','scope'])test(`preparation preserves a new ${mutation} choice made while waiting`,async()=>{
  const f=fixture();await f.panel.open();const pending=deferred();f.api.prepareWorksheet=()=>pending.promise;
  const running=f.panel.prepare();await new Promise(done=>setImmediate(done));
  if(mutation==='skill')f.controller.state.skill='legal_research';
  if(mutation==='context')f.controller.state.context={selected:['new-citation']};
  if(mutation==='materials')f.controller.state.materialAction='upload';
  if(mutation==='scope')f.controller.state.view.scope={...scope,materials_revision:1};
  pending.resolve({scope,composer_revision:0,profile_revision:1,model_called:false,content:'【接待追问任务：借贷咨询】\n旧资料'});await running;
  assert.equal(f.calls.filter(x=>x[0]==='edit-composer').length,0);
  if(mutation==='skill')assert.equal(f.controller.state.skill,'legal_research');
});

test('explicitly adopting an unchanged displayed candidate still saves a protected manual value',async()=>{
  const f=fixture();f.setFields([{field:'questions',protected_value:null,verification:'unverified',candidates:[
    {value:{kind:'list',value:['请补还款凭证。']},origin:'model_inference',source_refs:[]}]}]);
  await f.panel.open();
  const use=walk(f.document.getElementById('worksheet-candidates')).find(e=>e.textContent==='采用这项候选');
  assert.equal(use.disabled,false);use.listeners.click();
  assert.equal(f.panel.hasPending(),true);await f.panel.save();
  assert.deepEqual(f.calls.find(x=>x[0]==='commit')[2].manual_edits,[{field:'questions',value:{kind:'list',value:['请补还款凭证。']}}]);
});

test('keeping local edits after conflict does not overwrite another field changed on the server',async()=>{
  const f=fixture();await f.panel.open();f.input('worksheet-notes','我的底稿修改');
  f.setFields([{field:'internal_notes',protected_value:{kind:'text',value:'原内部备注保留'},verification:'unverified',candidates:[]},
    {field:'client_reply',protected_value:{kind:'text',value:'另一窗口的新客户回复'},verification:'unverified',candidates:[]}]);
  await f.panel.refresh();await f.panel.keepLocal();
  assert.equal(f.document.getElementById('worksheet-client-reply').value,'另一窗口的新客户回复');
  await f.panel.save();assert.deepEqual(f.calls.find(x=>x[0]==='commit')[2].manual_edits.map(e=>e.field),['internal_notes']);
});
