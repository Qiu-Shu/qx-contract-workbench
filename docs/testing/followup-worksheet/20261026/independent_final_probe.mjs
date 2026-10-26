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



const nextBinding={...scope,binding_revision:2,scope_kind:'intake',scope_ref:'99999999-9999-4999-8999-999999999999'};
const rebind=f=>{f.controller.state.view.scope={...nextBinding};f.panel.state(f.controller.state);};

test('final: empty reason and impact are blocked before joining',async()=>{
 const f=fixture();await f.panel.open();f.select('facts',[fact.id]);f.panel.linkSelected();f.input('title','待补材料');
 assert.equal(f.panel.addItem(),false);assert.equal(f.calls.length,0);
});

test('final: unjoined form survives rebinding and only explicit discard accepts the new binding',async()=>{
 const f=fixture();await f.panel.open();f.input('title','未加入的独立探针内容');
 const late=deferred();f.api.getFollowups=()=>late.promise;const inflight=f.panel.refresh();
 rebind(f);f.panel.state(f.controller.state);
 assert.equal(f.document.getElementById('followup-title').value,'未加入的独立探针内容');
 assert.equal(f.document.getElementById('followup-title').disabled,true);
 assert.equal(f.panel.hasPending(),true);assert.equal(await f.panel.save(),false);assert.equal(f.panel.addItem(),false);
 late.resolve(f.getView());assert.equal(await inflight,false);
 f.setView({scope:nextBinding});f.api.getFollowups=async()=>structuredClone(f.getView());
 assert.equal(await f.panel.refresh(),false);
 assert.equal(f.document.getElementById('followup-title').value,'未加入的独立探针内容');
 assert.equal(await f.panel.refresh({discard:true}),true);
 assert.equal(f.panel.hasPending(),false);assert.equal(f.document.getElementById('followup-title').value,'');
 assert.equal(f.document.getElementById('followup-title').disabled,false);
});

test('final: joined dirty items survive rebinding and are not silently rebound',async()=>{
 const f=fixture();await draft(f);rebind(f);
 assert.equal(f.panel.hasPending(),true);assert.equal(await f.panel.save(),false);
 assert.match(textTree(f.document.getElementById('followup-rows')),/补交尚未收到的转账凭证/);
 f.setView({scope:nextBinding,evidence_revision:2,profile_revision:2});
 assert.equal(await f.panel.refresh(),false);assert.equal(f.calls.length,0);
 assert.equal(await f.panel.refresh({discard:true}),true);await draft(f);
 assert.equal(await f.panel.save(),true);
 assert.equal(f.calls.length,1);assert.deepEqual(f.calls[0][2].expected_scope,nextBinding);
 assert.equal(f.calls[0][2].items[0].facts[0].evidence_revision,2);
});

test('final: unknown request keeps its exact key across rebinding and repeated state, with GET-only recovery',async()=>{
 const f=fixture();await draft(f);
 const post=deferred();let sent;
 f.api.saveFollowups=async(id,b)=>{f.calls.push(['post',id,b]);sent=b;return post.promise;};
 const saving=f.panel.save();rebind(f);f.panel.state(f.controller.state);
 post.resolve(f.receipt(sent));assert.equal(await saving,false);
 assert.equal(f.panel.hasPending(),true);assert.equal(f.document.getElementById('followup-lookup').hidden,false);
 assert.equal(await f.panel.save(),false);assert.equal(await f.panel.refresh({discard:true}),false);
 assert.equal(await f.panel.lookup(),false);
 assert.equal(f.calls.filter(x=>x[0]==='post').length,1);
 assert.equal(f.calls.find(x=>x[0]==='receipt')[2],sent.request_id);
 f.setView({scope:nextBinding,revision:sent.base_revision+1,items:sent.items});
 const get=deferred();f.api.findFollowupReceipt=async(id,key)=>{f.calls.push(['receipt',id,key]);return get.promise;};
 const recovering=f.panel.lookup();f.panel.state(f.controller.state);get.resolve(f.receipt(sent));
 assert.equal(await recovering,true);assert.equal(f.panel.hasPending(),false);
 assert.equal(f.document.getElementById('followup-lookup').hidden,true);
 assert.equal(f.document.getElementById('followup-title').disabled,false);
 assert.equal(f.calls.filter(x=>x[0]==='post').length,1);
 assert.ok(f.calls.filter(x=>x[0]==='receipt').every(x=>x[2]===sent.request_id));
});

test('final: a receipt GET started before a binding change cannot clear the retained unknown request',async()=>{
 const f=fixture();await draft(f);let sent;
 f.api.saveFollowups=async(id,b)=>{sent=b;f.calls.push(['post',id,b]);throw {code:'NETWORK_UNKNOWN',status:0};};
 await f.panel.save();const older=deferred();f.api.findFollowupReceipt=()=>older.promise;
 const lookup=f.panel.lookup();rebind(f);older.resolve(f.receipt(sent));assert.equal(await lookup,false);
 assert.equal(f.panel.hasPending(),true);assert.equal(f.document.getElementById('followup-lookup').hidden,false);
 f.setView({scope:nextBinding,revision:sent.base_revision+1,items:sent.items});
 f.api.findFollowupReceipt=async(id,key)=>{assert.equal(key,sent.request_id);return f.receipt(sent);};
 assert.equal(await f.panel.lookup(),true);assert.equal(f.panel.hasPending(),false);
});

test('final: conversation, workspace and permission changes still clear private drafts',async()=>{
 for(const kind of ['conversation','workspace','revoked']){
  const f=fixture();await f.panel.open();f.input('title','不得带入其他权限范围');
  if(kind==='conversation')f.controller.state.id='88888888-8888-4888-8888-888888888888';
  if(kind==='workspace')f.controller.state.view.scope.workspace_id='77777777-7777-4777-8777-777777777777';
  if(kind==='revoked')f.controller.state.status='revoked';
  f.panel.state(f.controller.state);assert.equal(f.panel.hasPending(),false,kind);
  assert.equal(f.document.getElementById('followup-title').value,'',kind);
 }
});
