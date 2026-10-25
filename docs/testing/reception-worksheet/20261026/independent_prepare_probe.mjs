import assert from 'node:assert/strict';
import test from 'node:test';

const module=await import('/Users/molin/Project/qx-contract-workbench/src/cn_contract/web/static/reception-worksheet.mjs').catch(error=>{
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


const f=fixture();await f.panel.open();const waiting=deferred();f.api.prepareWorksheet=()=>waiting.promise;
f.controller.selectSkill=function(skill){this.state.skill=skill;};
const running=f.panel.prepare();await new Promise(done=>setImmediate(done));
f.controller.selectSkill('legal_research');
waiting.resolve({scope,composer_revision:0,profile_revision:1,model_called:false,content:'【接待追问任务：借贷咨询】\n旧资料'});await running;
console.log(JSON.stringify({skill:f.controller.state.skill,text:f.controller.state.text,edits:f.calls.filter(x=>x[0]==='edit-composer').length}));
