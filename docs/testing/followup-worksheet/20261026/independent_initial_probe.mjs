import assert from 'node:assert/strict';
import test from 'node:test';
const mod=await import('file:///Users/molin/Project/qx-contract-workbench/src/cn_contract/web/static/followup-worksheet.mjs').catch(e=>{if(e.code==='ERR_MODULE_NOT_FOUND')return {};throw e;});
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.open=false;this.selected=false;}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this.children=[...children];this.textContent='';}
 addEventListener(name,fn){this.listeners[name]=fn;}
 removeEventListener(name,fn){if(this.listeners[name]===fn)delete this.listeners[name];}
 get selectedOptions(){return this.children.filter(x=>x.selected);}
}
const cid='11111111-1111-4111-8111-111111111111';
const scope={workspace_id:'22222222-2222-4222-8222-222222222222',conversation_id:cid,scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:0,materials_revision:0};
const fact={id:'44444444-4444-4444-8444-444444444444',content:'甲称尚缺转账凭证，待核',source:{kind:'statement',profile_revision:1,quote:'甲称'}};
const material={attachment:{id:'55555555-5555-4555-8555-555555555555',original_name:'虚构凭证.pdf',sha256:'a'.repeat(64)},selected:true,parse_revision:1,reading_status:'readable'};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const item=(extra={})=>({id:'66666666-6666-4666-8666-666666666666',title:'补交转账凭证',reason:'实际交付尚待核对',impact:'影响交付金额核对',next_action:'请客户查找原件',due_date:null,status:'open',result:'',facts:[{evidence_revision:1,fact_id:fact.id}],materials:[],...extra});
function fixture({readonly=false}={}){
 assert.equal(typeof mod.bindFollowupWorksheet,'function','follow-up binder must exist');
 const els=new Map(),calls=[];let key=0;
 const document={getElementById(id){if(!els.has(id))els.set(id,new Element());return els.get(id);},createElement:tag=>new Element(tag)};
 const controller={state:{id:cid,status:'saved',loading:false,materialAction:null,view:{scope:{...scope}}},revoke(error){if([401,403].includes(error.status)){this.state.status='revoked';panel.state(this.state);return true;}return false;}};
 let view={scope:{...scope},profile_revision:1,evidence_revision:1,revision:0,items:[],writable:true,facts:[structuredClone(fact)],materials:[structuredClone(material)],attention:[]};
 const receipt=body=>({conversation_id:cid,request_id:body.request_id,revision:body.base_revision+1,snapshot_sha256:'b'.repeat(64),created_at:'2026-10-26T01:00:00Z'});
 const api={getFollowups:async()=>structuredClone(view),saveFollowups:async(id,body)=>{calls.push(['post',id,body]);view={...view,revision:body.base_revision+1,items:structuredClone(body.items)};return receipt(body);},findFollowupReceipt:async(id,key)=>{calls.push(['receipt',id,key]);return null;},getFollowupVersion:async(id,rev)=>({scope:{...scope},profile_revision:1,evidence_revision:1,revision:rev,items:[item()]}),getEvidenceVersion:async(id,rev)=>({scope:{...scope},profile_revision:1,revision:rev,rows:[structuredClone(fact)]}),originalUrl:(id,file)=>'/original/'+id+'/'+file};
 const panel=mod.bindFollowupWorksheet({controller,api,document,readonly,uuid:()=>`33333333-3333-4333-8333-${String(++key).padStart(12,'0')}`});panel.state(controller.state);
 const input=(id,value)=>{const el=document.getElementById('followup-'+id);el.value=value;el.listeners.input?.();el.listeners.change?.();};
 const select=(id,values)=>{const el=document.getElementById('followup-'+id);for(const option of el.children)option.selected=values.includes(option.value);el.listeners.change?.();};
 return {panel,api,controller,document,calls,input,select,receipt,setView(change){view={...view,...change};},getView:()=>view};
}
const requiredText=f=>{f.input('reason','实际交付尚待核对');f.input('impact','影响交付金额核对');};
async function draft(f,{facts=[fact.id],materials=[],title='补交尚未收到的转账凭证'}={}){await f.panel.open();f.select('facts',facts);f.select('materials',materials);f.panel.linkSelected();f.input('title',title);requiredText(f);assert.equal(f.panel.addItem(),true);}
const textTree=e=>e.textContent+' '+e.children.map(textTree).join(' ');


test('probe current front end accepts title and link while reason and impact empty', async()=>{
 const f=fixture(); await draft(f);
 assert.equal(await f.panel.save(),true);
 assert.equal(f.calls[0][2].items[0].reason,'');
 assert.equal(f.calls[0][2].items[0].impact,'');
 console.log('CONFIRMED: invalid blank reason/impact enter outbound POST');
});
test('probe automatic same conversation rebinding discards unjoined form', async()=>{
 const f=fixture(); await f.panel.open(); f.input('title','这段尚未加入的私有编辑');
 assert.equal(f.panel.hasPending(),true);
 f.controller.state.view.scope={...scope,binding_revision:2,scope_kind:'intake',scope_ref:'99999999-9999-4999-8999-999999999999'};
 f.panel.state(f.controller.state);
 assert.equal(f.document.getElementById('followup-title').value,'');
 assert.equal(f.panel.hasPending(),false);
 console.log('CONFIRMED: same-conversation binding change clears local form silently');
});
test('probe automatic same conversation rebinding discards unknown request identity', async()=>{
 const f=fixture(); await draft(f);
 f.api.saveFollowups=async(id,body)=>{f.calls.push(['post',id,body]);throw {code:'NETWORK_UNKNOWN',status:0};};
 assert.equal(await f.panel.save(),false);
 assert.equal(f.panel.hasPending(),true);
 assert.equal(f.document.getElementById('followup-lookup').hidden,false);
 f.controller.state.view.scope={...scope,binding_revision:2,scope_kind:'intake',scope_ref:'99999999-9999-4999-8999-999999999999'};
 f.panel.state(f.controller.state);
 assert.equal(f.panel.hasPending(),false);
 assert.equal(f.document.getElementById('followup-lookup').hidden,true);
 assert.equal(await f.panel.lookup(),false);
 assert.equal(f.calls.filter(x=>x[0]==='receipt').length,0);
 console.log('CONFIRMED: same-conversation binding change loses unknown request and receipt lookup');
});
