import test from 'node:test';
import assert from 'node:assert/strict';
import {bindTaskDrafts} from '../src/cn_contract/web/static/assistant-tasks.mjs';

const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PDF='application/pdf';
const ASSOCIATE='关联所选原件并更新读取状态';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners=new Map();this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.checked=false;this.dataset={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  setAttribute(name,value){this[name]=value;}
  focus(){}
  scrollIntoView(){}
  fire(name){return this.listeners.get(name)?.({preventDefault(){}});}
}
const walk=element=>[element,...element.children.flatMap(walk)];
const file=(id='local',mime=DOCX,name='同名合成合同.docx')=>({id,mime,original_name:name,sha256:(id==='local'?'a':'b').repeat(64)});
const original={media_id:'wire-file',name:'同名合成合同.docx',mime:DOCX,status:'pending'};
const parse=(mime=DOCX)=>({reading_status:'readable',parser_version:mime===PDF?'qx-pdf-attachments-v1':'qx-docx-attachments-v1',baseline_view:'original'});
async function fixture({readonly=false,state='collecting',files=[file()],items,media=original,resolutions=[]}={}){
  const elements=new Map(),calls=[],parses=[],materialReads=[];
  const root={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement:tag=>new Element(tag)};
  const controller={state:{id:'one',status:'saved',loading:false,materials:{attachments:files,items:items||files.map(item=>({attachment_id:item.id,parse_revision:3}))}},revoke:error=>[401,403].includes(error.status)};
  let draft={id:'draft',state,revision:7,instruction:'合成审查',blockers:['media_pending'],events:[{id:'event',text:'',media:[structuredClone(media)]}],media_resolutions:structuredClone(resolutions)};
  const api={
    getMaterials:async cid=>{materialReads.push(cid);return structuredClone(controller.state.materials);},
    getParse:async(...args)=>{parses.push(args);return parse(files.find(item=>item.id===args[1])?.mime);},
    request:async(path,options={})=>{
      calls.push([path,structuredClone(options)]);
      if(path.endsWith('/task-drafts'))return {items:[structuredClone(draft)],unassigned_events:[],binding:{id:'binding',cursor:0}};
      if(options.method==='PATCH'){
        draft={...draft,revision:draft.revision+1,media_resolutions:[...draft.media_resolutions,...options.body.media_resolutions.map(item=>({...item,revision:options.body.expected_revision+1}))]};
      }
      return structuredClone(draft);
    },
  };
  const tasks=bindTaskDrafts({root,controller,api,readonly});tasks.state(controller.state);await tick();
  root.getElementById('task-select').value='draft';root.getElementById('task-select').fire('change');
  return {root,controller,api,tasks,calls,parses,materialReads,get draft(){return draft;},set draft(value){draft=value;}};
}
const nodes=f=>walk(f.root.getElementById('task-current'));
const button=(f,text)=>{const el=nodes(f).find(item=>item.tagName==='button'&&item.textContent===text);assert.ok(el,text);return el;};
const selection=f=>{const label=nodes(f).find(item=>item.tagName==='label'&&item.textContent==='已上传原件');assert.ok(label,'explicit original-file selector');return label.children.find(item=>item.tagName==='select');};
const choose=(f,id='local')=>{const select=selection(f);select.value=id;select.fire('change');return select;};
const patches=f=>f.calls.filter(([,options])=>options.method==='PATCH');
const expected=(attachment=file())=>({event_id:'event',media_id:'wire-file',action:'resolve',replacement:{media_id:'wire-file',name:attachment.original_name,mime:attachment.mime,status:'ready',attachment_id:attachment.id,sha256:attachment.sha256,parse_revision:3}});
const assertNoPatch=f=>assert.equal(patches(f).length,0);

test('pending wire material has labelled same-conversation DOCX/PDF choices with no automatic name match',async()=>{
  const f=await fixture({files:[file(),file('other',PDF,'同名合成合同.docx'),file('text','text/plain','说明.txt')]});
  const select=selection(f);assert.equal(select.value,'');assert.deepEqual(select.children.map(item=>item.value),['','local','other']);
  assert.equal(button(f,ASSOCIATE).disabled,true);assert.equal(f.tasks.hasPending(),false);assertNoPatch(f);f.tasks.dispose();
});
test('empty materials keep the explicit selector empty and explain upload and reading',async()=>{
  const f=await fixture({files:[]});assert.equal(selection(f).value,'');assert.equal(selection(f).children.length,1);
  assert.match(nodes(f).map(item=>item.textContent).join(' '),/上传.*读取/);assert.equal(button(f,ASSOCIATE).disabled,true);f.tasks.dispose();
});
test('an unconfirmed choice is pending, clears notices, and survives an unrelated render',async()=>{
  const f=await fixture();f.root.getElementById('task-notice').textContent='旧提示';choose(f);assert.equal(f.tasks.hasPending(),true);
  assert.equal(f.root.getElementById('task-notice').textContent,'');await f.tasks.refresh();assert.equal(selection(f).value,'local');assert.equal(f.tasks.hasPending(),true);f.tasks.dispose();
});
for(const mime of [DOCX,PDF])test('explicit association preserves wire IDs and uses exact current original and parse: '+mime,async()=>{
  const attachment=file('local',mime,mime===PDF?'合成合同.pdf':'合成合同.docx'),f=await fixture({files:[attachment]});
  choose(f);await button(f,ASSOCIATE).fire('click');assert.equal(patches(f).length,1);assert.deepEqual(patches(f)[0][1].body,{expected_revision:7,media_resolutions:[expected(attachment)]});
  assert.deepEqual(f.parses,[['one','local',3]]);assert.equal(f.draft.events[0].media[0].attachment_id,undefined);assert.equal(f.tasks.hasPending(),false);
  assert.equal(selection(f).value,'');assert.match(f.root.getElementById('task-notice').textContent,/已保存/);assert.equal(f.calls.some(([path])=>/review|runs|model/.test(path)),false);f.tasks.dispose();
});
for(const [name,mime,result] of [
  ['pending no parse',DOCX,null],['partial DOCX',DOCX,{...parse(),reading_status:'partial'}],
  ['needs baseline',DOCX,{...parse(),reading_status:'needs_baseline'}],['failed DOCX',DOCX,{...parse(),reading_status:'failed'}],
  ['foreign DOCX parser',DOCX,{...parse(),parser_version:'foreign'}],['wrong DOCX baseline',DOCX,{...parse(),baseline_view:'invented'}],
  ['partial PDF',PDF,{...parse(PDF),reading_status:'partial'}],['failed PDF',PDF,{...parse(PDF),reading_status:'failed'}],
  ['accepted PDF',PDF,{...parse(PDF),baseline_view:'accepted_view'}],['rejected PDF',PDF,{...parse(PDF),baseline_view:'rejected_view'}],
  ['foreign PDF parser',PDF,{...parse(PDF),parser_version:'qx-docx-attachments-v1'}],
])test('association refuses incomplete or mismatched reading: '+name,async()=>{
  const f=await fixture({files:[file('local',mime)],...(result?{}:{items:[{attachment_id:'local',parse_revision:null}]})});
  f.api.getParse=async()=>result;choose(f);await button(f,ASSOCIATE).fire('click');assertNoPatch(f);assert.match(f.root.getElementById('task-notice').textContent,/读取|核对/);assert.equal(f.tasks.hasPending(),true);f.tasks.dispose();
});
for(const baseline_view of ['accepted_view','rejected_view'])test('DOCX complete supported view can associate: '+baseline_view,async()=>{
  const f=await fixture();f.api.getParse=async()=>({...parse(),baseline_view});choose(f);await button(f,ASSOCIATE).fire('click');assert.equal(patches(f).length,1);f.tasks.dispose();
});
test('existing replacement attachment drives update reading and explicit reselection remains available',async()=>{
  const attachment=file('other'),resolution={...expected(attachment),revision:6};resolution.replacement.parse_revision=2;
  const f=await fixture({files:[file(),attachment],resolutions:[resolution]});assert.equal(selection(f).value,'');await button(f,'更新读取状态').fire('click');
  assert.equal(patches(f)[0][1].body.media_resolutions[0].replacement.attachment_id,'other');choose(f,'local');await button(f,ASSOCIATE).fire('click');
  assert.equal(patches(f)[1][1].body.media_resolutions[0].replacement.attachment_id,'local');f.tasks.dispose();
});
for(const [name,options] of [['readonly',{readonly:true}],['frozen',{state:'frozen'}]])test('association cannot write while '+name,async()=>{
  const f=await fixture(options);const select=selection(f);assert.equal(select.disabled,true);select.value='local';select.fire('change');
  const action=nodes(f).find(item=>item.tagName==='button'&&item.textContent===ASSOCIATE);if(action){assert.equal(action.disabled,true);await action.fire('click');}assertNoPatch(f);f.tasks.dispose();
});
test('loading disables an already chosen selector and association',async()=>{
  const f=await fixture();choose(f);f.controller.state.loading=true;f.tasks.state(f.controller.state);assert.equal(selection(f).disabled,true);assert.equal(button(f,ASSOCIATE).disabled,true);
  await button(f,ASSOCIATE).fire('click');assertNoPatch(f);f.tasks.dispose();
});
test('same-conversation material update invalidates a choice and explains why',async()=>{
  const f=await fixture();choose(f);f.controller.state.materials={...f.controller.state.materials,items:[{attachment_id:'local',parse_revision:4}]};f.tasks.state(f.controller.state);
  assert.equal(selection(f).value,'');assert.equal(f.tasks.hasPending(),false);assert.match(f.root.getElementById('task-notice').textContent,/材料.*变化|材料.*更新/);f.tasks.dispose();
});
for(const phase of ['materials','parse'])for(const change of ['cid','draft-revision','selection','materials','dispose','loading','revoke'])test('late '+phase+' is discarded after '+change,async()=>{
  const f=await fixture(),waiting=deferred();choose(f);const before=structuredClone(f.controller.state.materials);
  if(phase==='materials')f.api.getMaterials=()=>waiting.promise;else f.api.getParse=()=>waiting.promise;
  const operation=button(f,ASSOCIATE).fire('click');await tick();
  if(change==='cid'){f.controller.state={id:'two',status:'saved',materials:null};f.tasks.state(f.controller.state);}
  if(change==='draft-revision'){f.draft={...f.draft,revision:8};await f.tasks.refresh();}
  if(change==='selection'){const select=selection(f);select.value='';select.fire('change');}
  if(change==='materials'){f.controller.state.materials={...before,items:[{attachment_id:'local',parse_revision:4}]};f.tasks.state(f.controller.state);}
  if(change==='dispose')f.tasks.dispose();
  if(change==='loading'){f.controller.state.loading=true;f.tasks.state(f.controller.state);}
  if(change==='revoke'){f.controller.state.status='revoked';f.tasks.state(f.controller.state);}
  waiting.resolve(phase==='materials'?before:parse());await operation;assertNoPatch(f);
  if(phase==='materials')assert.equal(f.parses.length,0);f.tasks.dispose();
});
test('a newer GET material version cannot silently validate the previously chosen file',async()=>{
  const f=await fixture();choose(f);f.api.getMaterials=async()=>({...f.controller.state.materials,attachments:[{...file(),sha256:'f'.repeat(64)}]});
  await button(f,ASSOCIATE).fire('click');assertNoPatch(f);assert.equal(selection(f).value,'');assert.equal(f.tasks.hasPending(),false);
  assert.match(f.root.getElementById('task-notice').textContent,/材料.*更新/);f.tasks.dispose();
});
const scope=(overrides={})=>({workspace_id:'workspace',conversation_id:'one',scope_kind:'conversation',scope_ref:null,
  binding_revision:1,input_revision:1,materials_revision:1,...overrides});
for(const revision of ['binding_revision','input_revision','materials_revision'])test('new GET material frame and choice survive a stale host '+revision,async()=>{
  const f=await fixture();f.controller.state.materials.scope=scope();f.tasks.state(f.controller.state);
  const newer={scope:scope({binding_revision:2,input_revision:2,materials_revision:2}),
    attachments:[file(),file('new-file')],items:[{attachment_id:'local',parse_revision:3},{attachment_id:'new-file',parse_revision:4}]};
  f.api.getMaterials=async()=>structuredClone(newer);choose(f);await button(f,ASSOCIATE).fire('click');choose(f,'new-file');
  const notice=f.root.getElementById('task-notice');notice.textContent='当前选择请核对';
  f.controller.state.materials={...f.controller.state.materials,scope:scope({...newer.scope,[revision]:1})};f.tasks.state(f.controller.state);
  assert.deepEqual(selection(f).children.map(item=>item.value),['','local','new-file']);assert.equal(selection(f).value,'new-file');
  assert.equal(notice.textContent,'当前选择请核对');assert.equal(f.tasks.hasPending(),true);assertNoPatch(f);f.tasks.dispose();
});
test('equal and newer material scope notifications still accept real changes and invalidate choices',async()=>{
  const f=await fixture();f.controller.state.materials.scope=scope();f.tasks.state(f.controller.state);choose(f);
  f.controller.state.materials={scope:scope(),attachments:[file(),file('equal-file')],items:[]};f.tasks.state(f.controller.state);
  assert.equal(selection(f).value,'');assert.deepEqual(selection(f).children.map(item=>item.value),['','local','equal-file']);choose(f,'equal-file');
  f.controller.state.materials={scope:scope({binding_revision:2,scope_kind:'matter',scope_ref:'matter'}),attachments:[file('rebound')],items:[]};f.tasks.state(f.controller.state);
  assert.equal(selection(f).value,'');assert.deepEqual(selection(f).children.map(item=>item.value),['','rebound']);assert.equal(f.tasks.hasPending(),false);f.tasks.dispose();
});
for(const phase of ['materials','parse'])test('late '+phase+' cannot act on a different selected draft',async()=>{
  const f=await fixture(),waiting=deferred();choose(f);const materials=structuredClone(f.controller.state.materials);
  if(phase==='materials')f.api.getMaterials=()=>waiting.promise;else f.api.getParse=()=>waiting.promise;
  const operation=button(f,ASSOCIATE).fire('click');await tick();f.root.getElementById('task-select').value='';f.root.getElementById('task-select').fire('change');
  waiting.resolve(phase==='materials'?materials:parse());await operation;assertNoPatch(f);f.tasks.dispose();
});
test('double activation makes a single PATCH and disables select during the read',async()=>{
  const f=await fixture(),waiting=deferred();choose(f);f.api.getParse=()=>waiting.promise;const action=button(f,ASSOCIATE);
  const first=action.fire('click');await tick();assert.equal(selection(f).disabled,true);await action.fire('click');waiting.resolve(parse());await first;assert.equal(patches(f).length,1);f.tasks.dispose();
});
for(const found of [true,false])test('unknown association queries the precise result without repeating PATCH: '+found,async()=>{
  const f=await fixture(),request=f.api.request;choose(f);
  f.api.request=async(path,options={})=>{if(options.method==='PATCH'){if(found)await request(path,options);else f.calls.push([path,structuredClone(options)]);throw {code:'NETWORK_UNKNOWN'};}return request(path,options);};
  await button(f,ASSOCIATE).fire('click');assert.equal(f.tasks.hasPending(),true);const retry=f.root.getElementById('task-retry');assert.equal(retry.textContent,'查询本次关联结果');
  await retry.fire('click');assert.equal(patches(f).length,1);assert.ok(f.calls.some(([path,options])=>path==='/api/task-drafts/draft'&&(!options.method||options.method==='GET')));
  assert.equal(f.tasks.hasPending(),!found);if(!found){await retry.fire('click');assert.equal(patches(f).length,1);assert.equal(f.tasks.hasPending(),true);}f.tasks.dispose();
});
for(const mismatch of ['revision','event_id','media_id','action','attachment_id','sha256','parse_revision','name','mime','status'])test('unknown query does not infer success from a different saved resolution: '+mismatch,async()=>{
  const f=await fixture(),request=f.api.request;choose(f);f.api.request=async(path,options={})=>{if(options.method==='PATCH'){f.calls.push([path,structuredClone(options)]);throw {code:'NETWORK_UNKNOWN'};}return request(path,options);};
  await button(f,ASSOCIATE).fire('click');const resolution={...expected(),revision:8};
  if(['revision','event_id','media_id','action'].includes(mismatch))resolution[mismatch]=mismatch==='revision'?9:'different';else resolution.replacement={...resolution.replacement,[mismatch]:'different'};
  f.draft={...f.draft,revision:9,media_resolutions:[resolution]};await f.root.getElementById('task-retry').fire('click');assert.equal(f.tasks.hasPending(),true);assert.equal(patches(f).length,1);f.tasks.dispose();
});
test('confirmed association remains saved when subsequent list refresh loses its connection',async()=>{
  const f=await fixture(),request=f.api.request;choose(f);let saved=false;
  f.api.request=async(path,options={})=>{if(saved&&path.endsWith('/task-drafts'))throw {code:'NETWORK_UNKNOWN'};const result=await request(path,options);if(options.method==='PATCH')saved=true;return result;};
  await button(f,ASSOCIATE).fire('click');assert.equal(patches(f).length,1);assert.equal(f.tasks.hasPending(),false);assert.match(f.root.getElementById('task-notice').textContent,/已保存.*刷新/);assert.equal(f.root.getElementById('task-retry').hidden,true);f.tasks.dispose();
});
test('revoke clears choices and private original names',async()=>{
  const f=await fixture();choose(f);f.controller.state.status='revoked';f.tasks.state(f.controller.state);assert.equal(f.tasks.hasPending(),false);
  assert.equal(f.root.getElementById('task-current').children.length,0);assert.equal(f.root.getElementById('task-attachments').children.length,0);f.tasks.dispose();
});
test('material and wire names remain text nodes, never HTML',async()=>{
  const name='<img src=x onerror=alert(1)>.docx',f=await fixture({files:[file('local',DOCX,name)],media:{...original,name}});const select=selection(f);
  assert.equal(select.children[1].textContent,name);assert.equal(nodes(f).some(item=>item.tagName==='img'),false);choose(f);await button(f,ASSOCIATE).fire('click');assert.equal(patches(f)[0][1].body.media_resolutions[0].replacement.name,name);f.tasks.dispose();
});
