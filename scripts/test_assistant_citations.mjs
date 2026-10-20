import assert from 'node:assert/strict';
import test from 'node:test';
import {bindCitations,renderResearch} from '../src/cn_contract/web/static/assistant-citations.mjs';
import {createRenderer} from '../src/cn_contract/web/static/assistant-render.mjs';
const id='11111111-1111-4111-8111-111111111111';
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const walk=element=>[element,...element.children.flatMap(walk)];
function dom(){
  let root;
  class Element{
    constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.listeners={};this._text='';this.hidden=false;this.isConnected=true;
      const classes=new Set();this.classList={add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v),toggle:(v,on)=>on?classes.add(v):classes.delete(v)};}
    set textContent(v){this._text=String(v);this.replaceChildren();}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
    setAttribute(k,v){this.attributes[k]=String(v);}removeAttribute(k){delete this.attributes[k];}
    addEventListener(k,v){this.listeners[k]=v;}removeEventListener(k,v){if(this.listeners[k]===v)delete this.listeners[k];}
    append(...items){for(const item of items){item.remove();item.parentNode=this;this.children.push(item);}}
    replaceChildren(...items){for(const item of this.children)item.parentNode=null;this.children=[];this.append(...items);}
    focus(){root.activeElement=this;}fire(name,event={}){return this.listeners[name]?.(event);}
    remove(){if(this.parentNode){this.parentNode.children.splice(this.parentNode.children.indexOf(this),1);this.parentNode=null;}}
    insertBefore(child,before){child.remove();child.parentNode=this;this.children.splice(before?this.children.indexOf(before):this.children.length,0,child);}
    get firstChild(){return this.children[0]||null;}get nextSibling(){return this.parentNode?.children[this.parentNode.children.indexOf(this)+1]||null;}
    querySelectorAll(selector){return walk(this).slice(1).filter(x=>x.className?.split(' ').includes(selector.slice(1)));}
  }
  const elements=new Map();root=new Element();root.body=new Element('body');root.createElement=tag=>new Element(tag);
  root.getElementById=key=>{if(!elements.has(key))elements.set(key,new Element());return elements.get(key);};root.querySelectorAll=()=>[];return root;
}
const scope={workspace_id:'w',conversation_id:'conversation',scope_kind:'conversation',scope_ref:null,binding_revision:1,input_revision:3,materials_revision:0};
const citation={title:'合成法条 <img onerror=alert(1)>',quote:'<script>alert(1)</script>\n第二行合成原文',kind:'law_markdown',line_start:4,line_end:5,start:10,end:30,
  source_id:'s'.repeat(64),version_id:'v'.repeat(64),generation_id:'synthetic-generation',match_in_quote:true,article:null};
const saved=()=>({id,scope:{...scope,input_revision:1},citation:structuredClone(citation),created_at:'2026-10-20T12:00:00Z'});
function fixture(){
  const root=dom(),controller={state:{id:scope.conversation_id,view:{scope},status:'saved',loading:false},revoke(error){
    if(error.status===401){controller.state.status='revoked';panel.state(controller.state);return true;}return false;
  }};let reads=0,opening=0,load=async()=>saved();
  const panel=bindCitations({root,controller,onOpen:()=>opening++,read:async key=>{assert.equal(key,id);reads++;return load();}});
  return {root,controller,panel,at:key=>root.getElementById(key),set read(value){load=value;},get reads(){return reads;},get opening(){return opening;}};
}
test('source snapshots display only literal text with provenance and pending review',async()=>{
  const f=fixture(),trigger=f.root.createElement('button');assert.equal(await f.panel.open(id,trigger),true);
  assert.equal(f.opening,1);assert.equal(f.root.activeElement,f.at('close-citation-preview'));
  assert.equal(f.at('citation-preview-title').textContent,citation.title);
  assert.match(f.at('citation-preview-content').textContent,/历史片段.*不是全文/);
  assert.match(f.at('citation-preview-content').textContent,/适用性.*待.*核对/);
  assert.ok(f.at('citation-preview-content').textContent.includes(citation.quote));
  assert.equal(walk(f.at('citation-preview-content')).filter(x=>['img','script'].includes(x.tagName)).length,0);
  f.root.fire('keydown',{key:'Escape',preventDefault(){}});assert.equal(f.root.activeElement,trigger);
  assert.equal(f.at('citation-preview').hidden,true);assert.equal(f.at('citation-preview-content').textContent,'');
});
test('closing invalidates a pending response and restores a connected trigger or composer',async()=>{
  const f=fixture(),gate=deferred(),trigger=f.root.createElement('button');f.read=()=>gate.promise;
  const opened=f.panel.open(id,trigger);trigger.isConnected=false;f.at('close-citation-preview').fire('click');
  gate.resolve(saved());assert.equal(await opened,false);assert.equal(f.root.activeElement,f.at('composer'));
  assert.equal(f.at('citation-preview-content').textContent,'');assert.equal(f.at('citation-preview-title').textContent,'已保存的引用片段');
});
test('scope rebinding, switching, loading and revocation clear panel and reject late data',async()=>{
  for(const change of [s=>s.id='other',s=>s.view={scope:{...scope,binding_revision:2}},s=>s.loading=true,s=>s.status='revoked']){
    const f=fixture(),gate=deferred();f.read=()=>gate.promise;const opened=f.panel.open(id);change(f.controller.state);f.panel.state(f.controller.state);
    assert.equal(f.at('citation-preview').hidden,true);gate.resolve(saved());assert.equal(await opened,false);assert.equal(f.at('citation-preview-content').textContent,'');
  }
});
test('saved UUID and conversation identity must match; ordinary draft revision does not erase snapshot',async()=>{
  const f=fixture();assert.equal(await f.panel.open('not-a-uuid'),false);assert.equal(f.reads,0);
  f.read=async()=>({...saved(),id:'other'});assert.equal(await f.panel.open(id),false);assert.doesNotMatch(f.at('citation-preview-content').textContent,/script/);
  f.read=async()=>saved();await f.panel.open(id);f.controller.state.view={scope:{...scope,input_revision:5}};f.panel.state(f.controller.state);
  assert.equal(f.at('citation-preview').hidden,false);assert.ok(f.at('citation-preview-content').textContent.includes(citation.quote));
});
test('lookup authorization error clears and cannot render raw diagnostics',async()=>{
  const f=fixture();f.read=async()=>{throw {status:401,message:'PRIVATE DIAGNOSTIC'};};await f.panel.open(id);
  assert.equal(f.at('citation-preview').hidden,true);assert.equal(f.at('citation-preview-content').textContent,'');
});
test('result statuses distinguish unavailable, incomplete and zero hits',()=>{
  const root=dom(),patterns={ready:/未命中/,timeout:/超时.*不完整/,not_ready:/暂不可用/,not_configured:/尚未连接/};
  for(const [state,pattern] of Object.entries(patterns)){
    const result=renderResearch(root,{run:{state:'completed'},receipts:[{result:{citation_ids:[],result:{page:{state,citations:[]}}}}]});
    assert.match(result.textContent,pattern);assert.match(result.textContent,/未调用模型/);
  }
});
test('card click passes only saved UUID and malformed IDs are never links',()=>{
  const root=dom(),clicks=[],research={run:{state:'completed'},receipts:[{result:{citation_ids:[id,'bad-id'],result:{page:{state:'ready',citations:[citation,citation]}}}}]};
  const view=renderResearch(root,research,(...args)=>clicks.push(args));const buttons=walk(view).filter(x=>x.tagName==='button');
  assert.equal(buttons.length,1);buttons[0].fire('click');assert.equal(clicks[0][0],id);assert.equal(clicks[0][1],buttons[0]);
});
test('shared renderer uses local send rules while ordinary native approval remains distinct',()=>{
  const root=dom(),previous=globalThis.document;globalThis.document=root;
  try{
    const render=createRenderer(root),state={id:'conversation',view:{scope,messages:[]},text:'合成关键词',status:'saved',skill:'legal_research',
      research:{phase:'idle',canSend:true,items:[]},generation:{phase:'idle',canSend:false,nativeConfirmation:true,items:[],capability:{state:'unconfigured'}}};
    render.state(state);assert.equal(root.getElementById('send').disabled,false);assert.equal(root.getElementById('send').textContent,'本机检索');
    assert.match(root.getElementById('generation-note').textContent,/不会发送给模型/);assert.doesNotMatch(root.getElementById('input-help').textContent,/确认/);
    state.text='长'.repeat(201);state.research.canSend=false;render.state(state);assert.match(root.getElementById('generation-note').textContent,/超过 200/);
    state.research.phase='unknown';state.skill=null;render.state(state);assert.equal(root.getElementById('recover-generation').hidden,false);
    assert.match(root.getElementById('generation-status').textContent,/本机检索.*不确定/);
  }finally{globalThis.document=previous;}
});
