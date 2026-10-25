import test from 'node:test';
import assert from 'node:assert/strict';
import {bindTaskDrafts} from 'file:///D:/Documents/ChatGPT/%E5%BE%8B%E6%89%80%E9%A1%B9%E7%9B%AE/src/cn_contract/web/static/assistant-tasks.mjs';

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


test('independent: newer explicit GET material frame survives stale host notification',async()=>{
  const f=await fixture();
  f.controller.state.materials.scope={conversation_id:'one',materials_revision:1};
  f.tasks.state(f.controller.state);
  const newer={scope:{conversation_id:'one',materials_revision:2},
    attachments:[file(),file('new-file')],items:[{attachment_id:'local',parse_revision:3},{attachment_id:'new-file',parse_revision:4}]};
  f.api.getMaterials=async()=>structuredClone(newer);
  choose(f);await button(f,ASSOCIATE).fire('click');
  assert.deepEqual(selection(f).children.map(item=>item.value),['','local','new-file']);
  choose(f,'new-file');
  f.tasks.state(f.controller.state);
  assert.deepEqual(selection(f).children.map(item=>item.value),['','local','new-file'],
    'an unrelated parent notification must not reinstall materials_revision 1');
  assert.equal(selection(f).value,'new-file','the newly confirmed choice frame must remain current');
  assertNoPatch(f);f.tasks.dispose();
});

test('independent: matched historical resolution reconciles after a later replacement without PATCH',async()=>{
  const f=await fixture(),request=f.api.request;choose(f);
  f.api.request=async(path,options={})=>{
    if(options.method==='PATCH'){f.calls.push([path,structuredClone(options)]);throw {code:'NETWORK_UNKNOWN'};}
    return request(path,options);
  };
  await button(f,ASSOCIATE).fire('click');
  const saved={...expected(),revision:8};
  f.draft={...f.draft,revision:9,media_resolutions:[saved,
    {...expected(file('another')),revision:9}]};
  await f.root.getElementById('task-retry').fire('click');
  assert.equal(patches(f).length,1);
  assert.equal(f.tasks.hasPending(),false);
  assert.match(f.root.getElementById('task-notice').textContent,/已保存/);
  f.tasks.dispose();
});
