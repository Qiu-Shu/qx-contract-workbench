import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bindTaskDrafts} from '../src/cn_contract/web/static/assistant-tasks.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners=new Map();this.value='';this.textContent='';this.disabled=false;this.hidden=false;this.checked=false;this.dataset={};}
  append(...nodes){for(const node of nodes)node.parentNode=this;this.children.push(...nodes);}
  replaceChildren(...nodes){for(const node of this.children)node.parentNode=null;this.children=[];this.append(...nodes);}
  addEventListener(name,fn){this.listeners.set(name,fn);}
  setAttribute(name,value){this[name]=value;}
  focus(){this.focused=true;}
  scrollIntoView(){}
  fire(name){return this.listeners.get(name)?.({preventDefault(){}});}
}
function fixture(options={}){
  const elements=new Map(),calls=[];
  const root={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement:tag=>new Element(tag)};
  const controller={state:{id:'one',status:'saved',materials:{items:[],attachments:[]}},save:async()=>true,revoke(error){return error.status===403;}};
  let sequence=0;
  const api={request:async(path,options={})=>{calls.push([path,options]);return path.endsWith('task-drafts')?{items:[],unassigned_events:[],binding:null}:path==='/api/matters'?[]:{id:'binding',cursor:0};},
    getParse:async()=>({reading_status:'readable',parser_version:'qx-docx-attachments-v1',baseline_view:'original'}),getMaterials:async()=>controller.state.materials};
  const tasks=bindTaskDrafts({root,controller,api,uuid:()=>`key-${++sequence}`,...options});tasks.state(controller.state);
  return {root,controller,api,tasks,calls};
}
const walk=element=>[element,...element.children.flatMap(walk)];
test('personal task is labeled honestly and cannot enter synthetic collection or mock execution',async()=>{
  const f=fixture();await tick();
  const draft={id:'personal',synthetic:false,state:'frozen',revision:1,instruction:'虚构微信审查',blockers:[],events:[{channel:'weixin_personal',text:'审查',media:[]}],
    execution:{id:'execution',state:'prepared',manifest:{synthetic:false}}};
  f.api.request=async()=>({items:[draft],unassigned_events:[],binding:{channel:'weixin_personal'}});
  await f.tasks.refresh();f.root.getElementById('task-select').value='personal';f.root.getElementById('task-select').fire('change');
  const content=walk(f.root.getElementById('task-current')).map(el=>el.textContent).join(' ');
  assert.match(content,/本人微信/);assert.doesNotMatch(content,/模拟/);
  assert.equal(f.root.getElementById('task-collect').disabled,true);
  assert.equal(walk(f.root.getElementById('task-current')).some(el=>el.tagName==='button'),false);
  f.tasks.dispose();
});
test('pending Weixin operation locks task writes while preserving read controls',async()=>{
  let blocked=true;const f=fixture({isBlocked:()=>blocked});await tick();
  const input=f.root.getElementById('task-instruction'),save=f.root.getElementById('task-collect');
  input.value='独立合成待补指令';f.tasks.updateControls();
  assert.equal(save.disabled,true);const before=f.calls.length;await save.fire('click');assert.equal(f.calls.length,before);
  blocked=false;f.tasks.updateControls();assert.equal(save.disabled,false);f.tasks.dispose();
});
const taskButton=(f,label)=>{const found=walk(f.root.getElementById('task-current')).find(el=>el.tagName==='button'&&el.textContent===label);assert.ok(found,label);return found;};
test('unreadable and pending media are both included, never silently dropped',async()=>{
  const f=fixture();await tick();
  f.controller.state.materials={items:[{attachment_id:'doc',parse_revision:null},{attachment_id:'pdf',parse_revision:null}],attachments:[
    {id:'doc',original_name:'等待读取.docx',mime:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',sha256:'a'.repeat(64)},
    {id:'pdf',original_name:'附件.pdf',mime:'application/pdf',sha256:'b'.repeat(64)}]};
  f.tasks.state(f.controller.state);
  for(const label of f.root.getElementById('task-attachments').children)label.children[0].checked=true;
  await f.root.getElementById('task-collect').fire('click');
  const batch=f.calls.find(([path])=>path.endsWith('/batches'))[1].body;
  assert.deepEqual(batch.events[0].media.map(m=>m.status),['pending','pending']);
  assert.equal(batch.events[0].start_new,true);f.tasks.dispose();
});

for(const [name,reading_status,parser_version,baseline_view,want] of [
  ['native original','readable','qx-pdf-attachments-v1','original','ready'],
  ['partial scan','partial','qx-pdf-attachments-v1','original','pending'],
  ['failed encrypted','failed','qx-pdf-attachments-v1',null,'pending'],
  ['foreign parser','readable','qx-docx-attachments-v1','original','pending'],
  ['revision baseline','readable','qx-pdf-attachments-v1','accepted_view','pending'],
])test('PDF collection requires an exact complete original parse: '+name,async()=>{
  const f=fixture();await tick();
  const file={id:'pdf',original_name:'合成合同.pdf',mime:'application/pdf',sha256:'b'.repeat(64)};
  f.controller.state.materials={attachments:[file],items:[{attachment_id:'pdf',parse_revision:3}]};
  f.api.getParse=async()=>({reading_status,parser_version,baseline_view});f.tasks.state(f.controller.state);
  f.root.getElementById('task-attachments').children[0].children[0].checked=true;
  await f.root.getElementById('task-collect').fire('click');
  const batch=f.calls.find(([path])=>path.endsWith('/batches'))[1].body;
  assert.equal(batch.events[0].media[0].status,want);
  assert.equal(batch.events[0].media[0].parse_revision,want==='ready'?3:undefined);
  assert.equal(f.calls.some(([path])=>path.includes('/review')||path.includes('/runs')),false);
  f.tasks.dispose();
});

test('ready PDF appears as a main contract and its later complete parse can resolve the inbound record',async()=>{
  const f=fixture();await tick();
  const file={id:'pdf',original_name:'合成合同.pdf',mime:'application/pdf',sha256:'b'.repeat(64)};
  f.controller.state.materials={attachments:[file],items:[{attachment_id:'pdf',parse_revision:2}]};
  f.api.getParse=async()=>({reading_status:'readable',parser_version:'qx-pdf-attachments-v1',baseline_view:'original'});
  const draft={id:'draft',state:'collecting',revision:2,instruction:'合成审查',blockers:[],events:[{
    id:'event',media:[{media_id:'incoming',name:file.original_name,mime:file.mime,status:'ready',attachment_id:'pdf',parse_revision:1}]}]};
  f.api.request=async(path,options={})=>{f.calls.push([path,options]);return path.endsWith('task-drafts')?{items:[draft],unassigned_events:[]}:draft;};
  await f.tasks.refresh();f.root.getElementById('task-select').value='draft';f.root.getElementById('task-select').fire('change');
  const main=walk(f.root.getElementById('task-current')).find(el=>el.tagName==='select');
  assert.ok(main,'PDF must be available for main contract selection');assert.equal(main.value,'pdf');
  await taskButton(f,'更新读取状态').fire('click');
  const patch=f.calls.find(([,options])=>options.method==='PATCH');assert.ok(patch);
  assert.deepEqual(patch[1].body.media_resolutions[0].replacement,{
    media_id:'incoming',name:'合成合同.pdf',mime:'application/pdf',status:'ready',attachment_id:'pdf',sha256:'b'.repeat(64),parse_revision:2});
  f.tasks.dispose();
});

test('partial PDF stays blocked and offers an explicit exclusion without resolving it as ready',async()=>{
  const f=fixture();await tick();
  const file={id:'pdf',original_name:'扫描合同.pdf',mime:'application/pdf',sha256:'b'.repeat(64)};
  f.controller.state.materials={attachments:[file],items:[{attachment_id:'pdf',parse_revision:1}]};
  f.api.getParse=async()=>({reading_status:'partial',parser_version:'qx-pdf-attachments-v1',baseline_view:'original'});
  const draft={id:'draft',state:'collecting',revision:2,instruction:'合成审查',blockers:['media_pending'],events:[{
    id:'event',media:[{media_id:'incoming',name:file.original_name,mime:file.mime,status:'pending',attachment_id:'pdf'}]}]};
  f.api.request=async(path,options={})=>{f.calls.push([path,options]);return path.endsWith('task-drafts')?{items:[draft],unassigned_events:[]}:draft;};
  await f.tasks.refresh();f.root.getElementById('task-select').value='draft';f.root.getElementById('task-select').fire('change');
  assert.equal(taskButton(f,'冻结材料').disabled,true);
  await taskButton(f,'更新读取状态').fire('click');
  assert.match(f.root.getElementById('task-notice').textContent,/人工核对/);
  assert.equal(f.calls.some(([,o])=>o.method==='PATCH'),false);
  const reason=walk(f.root.getElementById('task-current')).find(el=>el.tagName==='input');reason.value='另行人工核对扫描件';
  await taskButton(f,'记录原因并排除此项').fire('click');
  const patch=f.calls.find(([,o])=>o.method==='PATCH');assert.equal(patch[1].body.media_resolutions[0].action,'exclude');
  f.tasks.dispose();
});
test('an uncertain collection retries the identical batch and preserves text',async()=>{
  const f=fixture();await tick();const original=f.api.request;let fail=true;
  f.api.request=async(path,options)=>{if(path.endsWith('/batches')){f.calls.push([path,structuredClone(options)]);if(fail)throw {code:'NETWORK_UNKNOWN'};return {drafts:[]};}return original(path,options);};
  f.root.getElementById('task-instruction').value='合成审查指令';
  await f.root.getElementById('task-collect').fire('click');
  assert.equal(f.root.getElementById('task-instruction').value,'合成审查指令');
  assert.equal(f.tasks.hasPending(),true);fail=false;
  await f.root.getElementById('task-retry').fire('click');
  const batches=f.calls.filter(([path])=>path.endsWith('/batches'));
  assert.deepEqual(batches[0][1].body,batches[1][1].body);
  assert.equal(f.root.getElementById('task-instruction').value,'');f.tasks.dispose();
});
test('late task reads cannot cross a changed conversation',async()=>{
  const f=fixture();await tick();let complete;
  f.api.request=async()=>new Promise(resolve=>complete=resolve);
  const reading=f.tasks.refresh();
  f.controller.state={id:null,status:'saved',materials:null};f.tasks.state(f.controller.state);
  complete({items:[{id:'private',state:'collecting',instruction:'旧会话秘密',events:[],blockers:[]}],unassigned_events:[]});
  await reading;
  assert.equal(f.root.getElementById('task-current').children.length,0);f.tasks.dispose();
});
test('readonly task card never submits a write',async()=>{
  const f=fixture({readonly:true});await tick();f.root.getElementById('task-instruction').value='不能写';
  await f.root.getElementById('task-collect').fire('click');
  assert.equal(f.calls.filter(([,o])=>o.method&&o.method!=='GET').length,0);f.tasks.dispose();
});

test('switching conversations disables collection until the destination finishes loading',async()=>{
  const f=fixture();await tick();f.controller.state.loading=true;f.tasks.state(f.controller.state);
  f.root.getElementById('task-instruction').value='不可误收进旧会话';
  await f.root.getElementById('task-collect').fire('click');
  assert.equal(f.calls.filter(([,o])=>o.method&&o.method!=='GET').length,0);
  assert.equal(f.root.getElementById('task-collect').disabled,true);f.tasks.dispose();
});

test('readonly users can still refresh saved task records',async()=>{
  const f=fixture({readonly:true});await tick();const before=f.calls.length;
  await f.root.getElementById('task-refresh').fire('click');
  assert.equal(f.calls.length,before+1);assert.equal(f.calls.at(-1)[0],'/api/assistant/conversations/one/task-drafts');f.tasks.dispose();
});

test('contract capability stays on the shared chat composer',()=>{
  const source=readFileSync(new URL('../src/cn_contract/web/static/assistant.mjs',import.meta.url),'utf8');
  const start=source.indexOf("document.querySelectorAll('[data-skill]').forEach",source.indexOf('const examples='));
  const end=source.indexOf("byId('clear-skill')",start);
  const buttons=[new Element('button'),new Element('button')];
  buttons[0].dataset.skill='contract_review';buttons[1].dataset.skill='client_reply';
  const selected=[],opened=[];
  const register=new Function('document','controller','tasks','closeMenu','byId','examples','composer','clearTimeout','setTimeout','safely',
    'let timer;'+source.slice(start,end));
  register({querySelectorAll:()=>buttons},{selectSkill:value=>selected.push(value),state:{text:'普通聊天保留'}},
    {open:()=>opened.push('simulation')},()=>{},()=>new Element(),{}, {isComposing:()=>false},()=>{},()=>{},()=>{});
  buttons[0].fire('click');
  assert.deepEqual(opened,[]);assert.deepEqual(selected,['contract_review']);
  buttons[1].fire('click');assert.deepEqual(selected,['contract_review','client_reply']);
});

test('simulation reads the current facts and submits only the frozen document hashes',async()=>{
  const f=fixture();await tick();
  const draft={id:'draft',state:'frozen',revision:3,instruction:'合成审查',events:[],blockers:[],
    execution:{id:'execution',state:'awaiting_facts',matter_id:'matter',document_versions:{version:'frozen-hash'}}};
  f.api.request=async(path,options={})=>{
    f.calls.push([path,options]);
    if(path.endsWith('/task-drafts'))return {items:[draft],unassigned_events:[]};
    if(path.endsWith('/context'))return {parses:[],facts:{version:7,facts:[{id:'f',field:'price',typed_value:{kind:'text',value:'虚构'},confirmation_status:'confirmed',anchor_ids:[]}]}};
    return {};
  };
  await f.tasks.refresh();f.root.getElementById('task-select').value='draft';f.root.getElementById('task-select').fire('change');
  await tick();
  await taskButton(f,'运行模拟审查').fire('click');
  const writes=f.calls.filter(([,o])=>o.method==='POST');
  assert.equal(writes.length,1);assert.equal(writes[0][0],'/api/task-executions/execution/review');
  assert.deepEqual(writes[0][1].body.review,{fact_version:7,document_hashes:{version:'frozen-hash'}});
  f.tasks.dispose();
});

test('a current task authorization failure clears already displayed private data',async()=>{
  const f=fixture();await tick();
  f.api.request=async()=>({items:[{id:'private',state:'collecting',revision:1,instruction:'保密指令',events:[],blockers:[]}],unassigned_events:[]});
  await f.tasks.refresh();f.root.getElementById('task-select').value='private';f.root.getElementById('task-select').fire('change');
  assert.ok(f.root.getElementById('task-current').children.length);
  f.api.request=async()=>{throw {status:403,code:'CROSS_MATTER_DENIED'};};
  await assert.rejects(f.tasks.refresh());
  assert.equal(f.root.getElementById('task-current').children.length,0);
  assert.equal(f.root.getElementById('task-collect').disabled,true);f.tasks.dispose();
});

test('saved review source is labelled from the run rather than the workspace mode',()=>{
  const source=readFileSync(new URL('../src/cn_contract/web/static/workbench.js',import.meta.url),'utf8');
  const start=source.indexOf('function renderRunSource()'),end=source.indexOf('function coverage()',start);
  assert.ok(start>=0&&end>start,'saved-run source label must be implemented');
  const status=new Element(),render=new Function('document','run',source.slice(start,end)+';renderRunSource();');
  const document={getElementById:id=>id==='review-run-status'?status:null};
  render(document,{manifest:{model_provider:'mock'}});assert.match(status.textContent,/模拟审查/);assert.doesNotMatch(status.textContent,/离线人工候选/);
  render(document,{manifest:{model_provider:'assisted_manual'}});assert.match(status.textContent,/离线人工候选/);assert.doesNotMatch(status.textContent,/模拟审查/);
});

for(const excluded of [false,true])test(excluded?'an excluded attachment can be explicitly restored':'a ready attachment can be updated to resolve a parser revision conflict',async()=>{
  const f=fixture();await tick();
  const file={id:'file',original_name:'合成.docx',mime:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',sha256:'a'.repeat(64)};
  f.controller.state.materials={attachments:[file],items:[{attachment_id:'file',parse_revision:2}]};
  const draft={id:'draft',state:'collecting',revision:4,instruction:'合成',blockers:['media_revision_conflict'],events:[{
    id:'event',text:'',media:[{media_id:'inbound',name:file.original_name,mime:file.mime,status:'ready',attachment_id:'file',parse_revision:1}]}],
    media_resolutions:excluded?[{event_id:'event',media_id:'inbound',action:'exclude',reason:'误操作'}]:[]};
  f.api.request=async(path,options={})=>{f.calls.push([path,options]);return path.endsWith('task-drafts')?{items:[draft],unassigned_events:[]}:draft;};
  await f.tasks.refresh();f.root.getElementById('task-select').value='draft';f.root.getElementById('task-select').fire('change');
  await taskButton(f,excluded?'恢复此项并更新读取状态':'更新读取状态').fire('click');
  const patch=f.calls.find(([,options])=>options.method==='PATCH');assert.ok(patch);
  const resolution=patch[1].body.media_resolutions[0];
  assert.equal(resolution.action,'resolve');assert.equal(resolution.event_id,'event');assert.equal(resolution.replacement.parse_revision,2);
  assert.equal(resolution.replacement.media_id,'inbound');f.tasks.dispose();
});

for(const readonly of [false,true])test('completed result stays inline in active and recovery mode: '+readonly,async()=>{
  const f=fixture({readonly});await tick();
  f.api.request=async path=>path.endsWith('/context')?{parses:[],review:{status:'completed',findings:[{issue_type:'合成风险',analysis:'待核对分析',anchor_ids:[]}],limitations:[]}}:
    {items:[{id:'draft',state:'frozen',revision:3,instruction:'合成',events:[],blockers:[],
    execution:{id:'execution',state:'completed',matter_id:'matter',review_run_id:'run'}}],unassigned_events:[]};
  await f.tasks.refresh();f.root.getElementById('task-select').value='draft';f.root.getElementById('task-select').fire('change');
  await tick();
  const nodes=walk(f.root.getElementById('task-current'));
  assert.ok(nodes.some(el=>el.textContent==='合成风险'));
  assert.equal(nodes.some(el=>el.tagName==='a'),false);
  f.tasks.dispose();
});
