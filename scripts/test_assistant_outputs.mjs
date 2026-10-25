import assert from 'node:assert/strict';
import test from 'node:test';

const module=await import('../src/cn_contract/web/static/assistant-outputs.mjs').catch(error=>{
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
function fixture({readonly=false,clipboardAllowed=true}={}) {
  assert.equal(typeof module.bindOutputs,'function','saved output panel binder must exist');
  const elements=new Map(),calls=[],copies=[],downloads=[];let copyListener;
  const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},
    createElement(tag){return new Element(tag);},body:{classList:{add(){},remove(){}}},
    addEventListener(_name,handler){copyListener=handler;},removeEventListener(){copyListener=null;},
    execCommand(){if(!clipboardAllowed)return false;copyListener({clipboardData:{setData(_type,value){copies.push(value);}},preventDefault(){}});return true;}};
  const controller={state:{id:cid,status:'saved',loading:false,view:{scope:{conversation_id:cid,binding_revision:1}}},
    revoke(error){if(error.status!==401&&error.status!==403)return false;this.state.status='revoked';panel.state(this.state);return true;}};
  const result=(audience='client')=>({id:audience==='client'?'22222222-2222-4222-8222-222222222222':'33333333-3333-4333-8333-333333333333',
    conversation_id:cid,selection:{source,audience},title:audience==='client'?'客户回复草稿':'律师内部工作稿',source_label:'已保存档案 · 版本 2',
    text:audience==='client'?'客户正文':'内部正文',notes:['未经律师审核'],citations:[],review_status:'unverified',content_sha256:(audience==='client'?'a':'b').repeat(64)});
  const api={listOutputs:async(id,before)=>{calls.push(['list',id,before]);return {conversation_id:cid,items:[{source,label:'档案草稿 · 版本 2',audiences:['client','internal']}],next_before:null};},
    previewOutput:async(id,body)=>{calls.push(['preview',id,body]);return result(body.audience);},
    copyOutput:async(id,body)=>{calls.push(['copy',id,body]);return result(body.audience);},
    downloadOutput:async(id,body)=>{calls.push(['docx',id,body]);return new Blob(['word']);}};
  const panel=module.bindOutputs({controller,api,document,readonly,
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

test('explicit source and audience preview, copy and Word use only the server projection',async()=>{
  const f=fixture();await ready(f);
  assert.equal(f.document.getElementById('output-copy').disabled,false);
  await f.panel.copy();await f.panel.download();
  assert.equal(f.copies.length,1);assert.match(f.copies[0],/客户正文/);assert.doesNotMatch(f.copies[0],/内部正文/);
  assert.equal(f.downloads.length,1);assert.match(f.downloads[0].name,/客户回复草稿.*\.docx$/);
  const body=f.calls.find(call=>call[0]==='docx')[2];
  assert.equal(body.expected_content_sha256,'a'.repeat(64));assert.equal(body.text,undefined);
});

test('audience/source changes invalidate preview and copy cannot use stale text',async()=>{
  const f=fixture();await ready(f);
  const audience=f.document.getElementById('output-audience');audience.value='internal';audience.listeners.change();
  assert.equal(f.document.getElementById('output-copy').disabled,true);
  await f.panel.copy();assert.equal(f.copies.length,0);
  await f.panel.preview();await f.panel.copy();assert.match(f.copies[0],/内部正文/);
});

test('switching conversations drops a late preview and clears saved content',async()=>{
  const f=fixture();await ready(f);
  const pending=deferred();f.api.previewOutput=()=>pending.promise;
  const running=f.panel.preview();
  f.controller.state={...f.controller.state,id:'44444444-4444-4444-8444-444444444444'};f.panel.state(f.controller.state);
  pending.resolve(f.result());await running;
  assert.equal(f.document.getElementById('output-panel').hidden,true);
  assert.equal(f.document.getElementById('output-text').textContent,'');
  await f.panel.copy();assert.equal(f.copies.length,0);
});

test('closing before copy validation returns prevents clipboard and notices',async()=>{
  const f=fixture();await ready(f);const pending=deferred();f.api.copyOutput=()=>pending.promise;
  const running=f.panel.copy();f.panel.close();pending.resolve(f.result());await running;
  assert.equal(f.copies.length,0);assert.equal(f.document.getElementById('output-text').textContent,'');
});

test('copy rechecks permissions and revocation clears the panel',async()=>{
  const f=fixture();await ready(f);f.api.copyOutput=async()=>{throw {status:403,code:'CROSS_MATTER_DENIED'};};
  await f.panel.copy();assert.equal(f.copies.length,0);assert.equal(f.document.getElementById('output-text').textContent,'');
});

test('a different returned audience or digest is not copied',async()=>{
  const f=fixture();await ready(f);f.api.copyOutput=async()=>f.result('internal');
  await f.panel.copy();assert.equal(f.copies.length,0);
  assert.equal(f.document.getElementById('output-copy').disabled,true);
});

test('clipboard refusal leaves the exact visible preview for manual copying',async()=>{
  const f=fixture({clipboardAllowed:false});await ready(f);await f.panel.copy();
  assert.equal(f.document.getElementById('output-text').textContent,'客户正文');
  assert.match(f.document.getElementById('output-notice').textContent,/手动/);
});

test('synchronous browser copy rechecks activity inside the copy event and removes its listener',()=>{
  let listener,content=null,removed=false,active=true;
  const document={addEventListener(_name,fn){listener=fn;},removeEventListener(_name,fn){assert.equal(fn,listener);removed=true;},
    execCommand(){listener({clipboardData:{setData(type,value){assert.equal(type,'text/plain');content=value;}},preventDefault(){}});return true;}};
  module.copyNow('public',()=>active,document);assert.equal(content,'public');assert.equal(removed,true);
  content=null;removed=false;active=false;
  assert.throws(()=>module.copyNow('old case',()=>active,document));assert.equal(content,null);assert.equal(removed,true);
});

test('readonly never lists or exports and a late download cannot save a file',async()=>{
  const f=fixture({readonly:true});await f.panel.open();await f.panel.preview();await f.panel.copy();await f.panel.download();assert.equal(f.calls.length,0);
  const g=fixture();await ready(g);const pending=deferred();g.api.downloadOutput=()=>pending.promise;
  const running=g.panel.download();g.panel.dispose();pending.resolve(new Blob(['word']));await running;assert.equal(g.downloads.length,0);
});
