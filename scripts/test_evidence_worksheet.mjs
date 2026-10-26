import assert from 'node:assert/strict';
import test from 'node:test';
const mod=await import('../src/cn_contract/web/static/evidence-worksheet.mjs').catch(e=>{if(e.code==='ERR_MODULE_NOT_FOUND')return {};throw e;});
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

test('a fact uses saved statement and requires explicit save',async()=>{const f=fixture();await draft(f);assert.equal(f.calls.length,0);assert.equal(f.panel.hasPending(),true);await f.panel.save();assert.equal(f.calls[0][2].rows[0].source.quote,f.getView().statement);assert.equal(f.calls[0][2].rows[0].category,'disbursement');assert.equal(f.panel.hasPending(),false);});
test('typed but unadded fact protects navigation',async()=>{const f=fixture();await f.panel.open();f.input('evidence-content','尚未加入的一条事实');assert.equal(f.panel.hasPending(),true);assert.equal(await f.panel.save(),false);assert.equal(f.calls.length,0);});
test('unknown result only looks up the fixed request key',async()=>{const f=fixture();await draft(f);f.api.saveEvidence=async(id,b)=>{f.calls.push(['post',id,b]);throw {status:0,code:'NETWORK_UNKNOWN'};};await f.panel.save();await f.panel.save();await f.panel.lookup();assert.equal(f.calls.filter(x=>x[0]==='post').length,1);assert.equal(f.calls.filter(x=>x[0]==='get-receipt').length,1);assert.equal(f.calls[1][2],f.calls[0][2].request_id);assert.equal(f.panel.hasPending(),true);});
test('a rejected save preserves edits and allows a new explicit attempt',async()=>{const f=fixture();await draft(f);f.api.saveEvidence=async()=>{throw {status:409,code:'VERSION_CONFLICT'};};await f.panel.save();assert.equal(f.panel.hasPending(),true);assert.equal(f.document.getElementById('evidence-lookup').hidden,true);});
test('late view cannot fill another conversation',async()=>{const f=fixture();const d=deferred();f.api.getEvidence=()=>d.promise;const run=f.panel.open();f.controller.state.id='other';f.panel.state(f.controller.state);d.resolve(f.getView());await run;assert.equal(f.document.getElementById('evidence-rows').children.length,0);});
test('read only view cannot add or save',async()=>{const f=fixture({readonly:true});await f.panel.open();f.input('evidence-content','不可保存');assert.equal(await f.panel.addFact(),false);assert.equal(await f.panel.save(),false);assert.equal(f.calls.length,0);});
test('historical version is read only and current version can be reopened',async()=>{const f=fixture();await f.panel.open();f.input('evidence-history-version','1');await f.panel.loadVersion();assert.equal(f.document.getElementById('evidence-save').disabled,true);assert.equal(f.document.getElementById('evidence-content').disabled,true);await f.panel.refresh();assert.equal(f.document.getElementById('evidence-content').disabled,false);});
test('refreshing current sources keeps local rows if evidence revision did not change',async()=>{const f=fixture();await draft(f);f.setView({profile_revision:2});await f.panel.refresh();await f.panel.save();assert.equal(f.calls[0][2].expected_profile_revision,2);assert.equal(f.calls[0][2].rows.length,1);});
test('refresh cannot overwrite concurrent fact changes with a stale local snapshot',async()=>{const f=fixture();await draft(f);f.setView({revision:1,rows:[row()]});assert.equal(await f.panel.refresh(),false);assert.equal(f.panel.hasPending(),true);assert.match(f.document.getElementById('evidence-notice').textContent,/另一|版本|冲突/);});
test('revocation clears private draft and hides source',async()=>{const f=fixture();await draft(f);f.controller.state.status='revoked';f.panel.state(f.controller.state);assert.equal(f.document.getElementById('evidence-content').value,'');assert.equal(f.document.getElementById('evidence-rows').children.length,0);});

test('concurrent version conflicts also protect a fact still being typed in the form',async()=>{const f=fixture();await f.panel.open();f.input('evidence-content','尚未加入的本地事实');f.setView({revision:1,rows:[row()]});assert.equal(await f.panel.refresh(),false);assert.equal(f.panel.hasPending(),true);});

test('late source A cannot replace the more recently opened source B',async()=>{const f=fixture();const a=row(),b=row();b.id='55555555-5555-4555-8555-555555555555';
 for(const [r,id]of [[a,'A'],[b,'B']])r.source={kind:'document',attachment_id:id,parse_revision:1,result_sha256:'a'.repeat(64),anchor:{quote:id,element_id:'source-'+id}};
 f.setView({rows:[a,b]});const waits={A:deferred(),B:deferred()};f.api.getParse=(cid,id)=>waits[id].promise;await f.panel.open();
 const articles=f.document.getElementById('evidence-rows').children;articles[0].children.find(e=>e.textContent==='回查这条依据').listeners.click();articles[1].children.find(e=>e.textContent==='回查这条依据').listeners.click();
 const parsed=r=>({result_sha256:r.source.result_sha256,result:{anchors:[r.source.anchor]}});waits.B.resolve(parsed(b));await new Promise(setImmediate);waits.A.resolve(parsed(a));await new Promise(setImmediate);
 assert.equal(f.document.getElementById('evidence-source-detail').children[1].textContent,'B');});
