import assert from 'node:assert/strict';
import test from 'node:test';

const module=await import('file:///Users/molin/Project/qx-contract-workbench/src/cn_contract/web/static/assistant-outputs.mjs').catch(error=>{
  if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;
  return {};
});
const cid='11111111-1111-4111-8111-111111111111';
const source={kind:'profile',output_id:null,profile_revision:2};
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.hidden=true;this.disabled=false;this.dataset={};this.textContent='';}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];this.textContent='';}
  addEventListener(name,handler){this.listeners[name]=handler;}
  setAttribute(name,value){this[name]=value;}
  focus(){this.focused=true;}
}
function fixture({readonly=false,writeClipboard}={}) {
  assert.equal(typeof module.bindOutputs,'function','saved output panel binder must exist');
  const elements=new Map();
  const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
    createElement(tag){return new Element(tag);},body:{classList:{add(){},remove(){}}}};
  const calls=[],copies=[],downloads=[];
  const controller={state:{id:cid,status:'saved',loading:false,view:{scope:{conversation_id:cid,binding_revision:1}}},
    revoke(error){if(error.status!==401&&error.status!==403)return false;this.state.status='revoked';panel.state(this.state);return true;}};
  const result=(audience='client')=>({id:audience==='client'?'22222222-2222-4222-8222-222222222222':'33333333-3333-4333-8333-333333333333',
    conversation_id:cid,selection:{source,audience},title:audience==='client'?'客户回复草稿':'律师内部工作稿',source_label:'已保存档案 · 版本 2',
    text:audience==='client'?'客户正文':'内部正文',notes:['未经律师审核'],citations:[],review_status:'unverified',content_sha256:(audience==='client'?'a':'b').repeat(64)});
  const api={listOutputs:async(id,before)=>{calls.push(['list',id,before]);return {conversation_id:cid,items:[{source,label:'档案草稿 · 版本 2',audiences:['client','internal']}],next_before:null};},
    previewOutput:async(id,body)=>{calls.push(['preview',id,body]);return result(body.audience);},
    copyOutput:async(id,body)=>{calls.push(['copy',id,body]);return result(body.audience);},
    downloadOutput:async(id,body)=>{calls.push(['docx',id,body]);return new Blob(['word']);}};
  const panel=module.bindOutputs({controller,api,document,readonly,writeClipboard:writeClipboard || (async value=>copies.push(value)),
    saveBlob:(blob,name)=>downloads.push({blob,name})});
  panel.state(controller.state);
  return {panel,controller,api,document,calls,copies,downloads,result,elements};
}
async function ready(f,audience='client') {
  await f.panel.open();
  const source=f.document.getElementById('output-source');source.value='0';source.listeners.change();
  const selected=f.document.getElementById('output-audience');selected.value=audience;selected.listeners.change();
  await f.panel.preview();
}

test('pending clipboard permission can complete an old conversation copy after switching',async()=>{
  const started=deferred(),finish=deferred(),copies=[];
  const f=fixture({writeClipboard:async text=>{started.resolve();await finish.promise;copies.push(text);}});
  await ready(f);const running=f.panel.copy();await started.promise;
  f.controller.state={...f.controller.state,id:'44444444-4444-4444-8444-444444444444'};f.panel.state(f.controller.state);
  assert.equal(f.document.getElementById('output-panel').hidden,true);
  finish.resolve();await running;
  assert.equal(copies.length,1);assert.match(copies[0],/客户正文/);
  console.log('PROBE: old conversation clipboard write completed after switching conversations');
});
