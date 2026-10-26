import assert from 'node:assert/strict';
import test from 'node:test';
const mod=await import('file:///Users/molin/Project/qx-contract-workbench/src/cn_contract/web/static/evidence-worksheet.mjs').catch(e=>{if(e.code==='ERR_MODULE_NOT_FOUND')return {};throw e;});
class Element{constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.hidden=false;this.disabled=false;this.open=false;}append(...items){this.children.push(...items);}replaceChildren(...items){this.children=[...items];this.textContent='';}addEventListener(n,f){this.listeners[n]=f;}setAttribute(n,v){this[n]=v;}focus(){}}
const cid='11111111-1111-4111-8111-111111111111';
const scope={workspace_id:'22222222-2222-4222-8222-222222222222',conversation_id:cid,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
function fixture({readonly=false}={}){
 assert.equal(typeof mod.bindEvidenceWorksheet,'function','evidence binder must exist');
 const els=new Map(),calls=[];let key=0;
 const document={getElementById(id){if(!els.has(id))els.set(id,new Element());return els.get(id);},createElement:t=>new Element(t)};
 const controller={state:{id:cid,status:'saved',loading:false,materialAction:null,view:{scope:{...scope}}},revoke(e){if([401,403].includes(e.status)){this.state.status='revoked';panel.state(this.state);return true;}return false;}};
 let view={scope:{...scope},profile_revision:1,revision:0,rows:[],saved_scope:null,statement:'甲称借出10万元，乙称部分已还。',writable:true,materials:[],historical_ids:[]};
 const api={getEvidence:async()=>structuredClone(view),saveEvidence:async(id,body)=>{calls.push(['post',id,body]);view={...view,revision:view.revision+1,rows:body.rows,saved_scope:view.scope};return {conversation_id:cid,request_id:body.request_id,revision:view.revision,snapshot_sha256:'a'.repeat(64),created_at:'2026-10-26T00:00:00Z'};},findEvidenceReceipt:async(id,key)=>{calls.push(['get-receipt',id,key]);return null;},getEvidenceVersion:async()=>({scope,profile_revision:1,revision:1,rows:[row()],created_at:'2026-10-26T00:00:00Z'}),originalUrl:(id,file)=>'/original/'+file};
 const panel=mod.bindEvidenceWorksheet({controller,api,document,readonly,uuid:()=>`33333333-3333-4333-8333-${String(++key).padStart(12,'0')}`});panel.state(controller.state);
 const input=(id,v)=>{const el=document.getElementById(id);el.value=v;el.listeners.input?.();};
 return {panel,api,controller,calls,document,input,setView(v){view={...view,...v};},getView:()=>view};
}
function row(){return {id:'44444444-4444-4444-8444-444444444444',category:'agreement',content:'甲称借款，待核',event_date:null,review_state:'pending',note:'',source:{kind:'statement',profile_revision:1,start:0,end:1,quote:'甲'}};}
async function draft(f){await f.panel.open();f.input('evidence-source','statement');await f.panel.chooseSource();f.input('evidence-content','甲自述借出十万元，实际交付待核');f.input('evidence-category','disbursement');await f.panel.addFact();}


const f=fixture();
f.setView({revision:1,rows:[row()]});
await f.panel.open();
// Open saved row in the editor; do not add it back to the snapshot yet.
f.document.getElementById('evidence-rows').children[0].children.find(e=>e.textContent==='编辑这条').listeners.click();
f.input('evidence-content','本地正在改第一条');
const concurrent=row();concurrent.id='55555555-5555-4555-8555-555555555555';concurrent.content='另一个窗口已保存的新事实';
f.setView({revision:2,rows:[row(),concurrent]});
console.log('refresh_result',await f.panel.refresh());
await f.panel.addFact();await f.panel.save();
console.log('submitted_base_revision',f.calls[0][2].base_revision,'submitted_contents',f.calls[0][2].rows.map(r=>r.content));
console.log('concurrent_row_preserved',f.calls[0][2].rows.some(r=>r.id===concurrent.id));
