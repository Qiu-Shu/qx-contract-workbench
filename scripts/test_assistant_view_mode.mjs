import assert from 'node:assert/strict';
import test from 'node:test';

const mod=await import('../src/cn_contract/web/static/assistant-view-mode.mjs').catch(error=>{
  if(error.code==='ERR_MODULE_NOT_FOUND')return {};
  throw error;
});

// DOM boundary only: actual geometry, native details and tab order need a browser.
class Events {
  constructor(){this.listeners=new Map();}
  addEventListener(type,fn,options=false){
    const list=this.listeners.get(type)||[];list.push({fn,capture:options===true||options.capture===true});this.listeners.set(type,list);
  }
  removeEventListener(type,fn){this.listeners.set(type,(this.listeners.get(type)||[]).filter(value=>value.fn!==fn));}
  fire(type,event={},capture){
    event={target:this,currentTarget:this,defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},stopPropagation(){this.stopped=true;},...event};
    for(const item of this.listeners.get(type)||[])if(capture===undefined||item.capture===capture)item.fn(event);
    return event;
  }
}
class Element extends Events {
  constructor(doc,id,tag='div'){
    super();this.doc=doc;this.id=id;this.tagName=tag.toUpperCase();this.children=[];this.parentNode=null;
    this.dataset={};this.attributes={};this.hidden=false;this.open=false;this.inert=false;this.disabled=false;this.value='';this.textContent='';
    this.selectionStart=0;this.selectionEnd=0;this.clientHeight=300;this.scrollHeight=1000;this._scrollTop=0;
    const classes=new Set();this.classList={add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value),toggle:(value,on)=>on?classes.add(value):classes.delete(value)};
    const styles=new Map();this.style={setProperty:(name,value)=>styles.set(name,value),getPropertyValue:name=>styles.get(name)||'',removeProperty:name=>styles.delete(name)};
  }
  get scrollTop(){return this._scrollTop;}
  set scrollTop(value){this._scrollTop=Math.max(0,Math.min(value,this.scrollHeight-this.clientHeight));}
  append(...items){for(const item of items){if(item.parentNode)item.parentNode.children.splice(item.parentNode.children.indexOf(item),1);item.parentNode=this;this.children.push(item);}}
  contains(item){return item===this||this.children.some(child=>child.contains(item));}
  setAttribute(name,value){this.attributes[name]=String(value);}
  getAttribute(name){return this.attributes[name]??null;}
  removeAttribute(name){delete this.attributes[name];}
  querySelector(selector){return this.children.find(child=>child.tagName.toLowerCase()===selector)||null;}
  scrollIntoView(){this.scrolledIntoView=true;}
  getBoundingClientRect(){return {height:64};}
  focus(){
    for(let node=this;node;node=node.parentNode){
      if(node.hidden||node.inert)return;
      if(node.tagName==='DETAILS'&&!node.open&&this!==node.children[0])return;
    }
    this.doc.activeElement=this;this.doc.fire('focusin',{target:this});
  }
  click(){if(this.disabled)return;this.focus();const event=this.fire('click',{},true);this.fire('click',event,false);}
}
function fixture({inertComposer=false}={}){
  assert.equal(typeof mod.bindViewMode,'function','view-mode binder must exist');
  const doc=new Events(),els=new Map(),create=(id,tag)=>{const element=new Element(doc,id,tag);els.set(id,element);return element;};
  doc.body=create('body','body');doc.body.dataset.viewMode='workbench';doc.activeElement=doc.body;
  doc.getElementById=id=>els.get(id)||null;
  doc.querySelector=selector=>selector==='.compose-section'?els.get('compose-section'):selector==='.page-toolbar'?els.get('page-toolbar'):null;
  const top=create('page-toolbar'),switcher=create('view-mode-switch'),bench=create('view-mode-workbench','button'),chat=create('view-mode-chat','button');
  const workHost=create('workspace-tools-host'),chatHost=create('chat-tools-host'),tools=create('conversation-tools','details'),summary=create('conversation-tools-summary','summary'),nav=create('tools-nav','nav');
  doc.body.append(top,workHost);top.append(switcher,chatHost);switcher.append(bench,chat);workHost.append(tools);tools.append(summary,nav);tools.open=true;
  const thread=create('conversation-thread'),history=create('history'),compose=create('compose-section'),input=create('composer','textarea'),form=create('composer-form','form');
  doc.body.append(thread,compose);thread.append(history);compose.append(form);form.append(input);compose.inert=inertComposer;
  const materialAdd=create('add-material','button');compose.append(materialAdd);
  const dock=create('chat-workarea'),title=create('chat-workarea-title'),close=create('close-chat-workarea','button');dock.append(title,close);doc.body.append(dock);
  const tasks=create('show-workbench-tasks','button'),taskPanel=create('task-draft-panel','details'),taskSummary=create('task-draft-summary','summary');
  nav.append(tasks);doc.body.append(taskPanel);taskPanel.append(taskSummary);
  const panels={};const businessEvents=[];
  for(const [buttonId,panelId]of [['show-worksheet','worksheet-panel'],['show-evidence','evidence-panel'],['show-followups','followup-panel']]){
    const button=create(buttonId,'button'),panel=create(panelId,'details'),field=create(panelId+'-input','textarea');panels[panelId]=panel;nav.append(button);dock.append(panel);panel.append(field);
    button.addEventListener('click',()=>{businessEvents.push(buttonId);panel.open=true;panel.fire('toggle');});
  }
  const closeCounts=new Map();
  for(const [buttonId,panelId,closeId]of [['show-profile','profile-preview','close-profile-preview'],['show-outputs','output-panel','close-outputs'],['material-source','material-preview','close-material-preview'],['citation-source','citation-preview','close-citation-preview']]){
    const trigger=create(buttonId,'button'),panel=create(panelId,'aside'),closer=create(closeId,'button');nav.append(trigger);doc.body.append(panel);panel.append(closer);panel.hidden=true;
    trigger.addEventListener('click',()=>{panel.hidden=false;closer.focus();});
    closer.addEventListener('click',()=>{closeCounts.set(panelId,(closeCounts.get(panelId)||0)+1);panel.hidden=true;(panelId==='material-preview'?materialAdd:trigger).focus();});
  }
  doc.addEventListener('keydown',event=>{if(event.key==='Escape'&&!els.get('profile-preview').hidden){els.get('profile-preview').hidden=true;els.get('show-profile').focus();}});
  for(const type of ['input','change','submit'])input.addEventListener(type,()=>businessEvents.push(type));
  form.addEventListener('submit',()=>businessEvents.push('form-submit'));
  let nextFrame=0;const frames=new Map(),observers=[];
  class Observer{constructor(fn){this.fn=fn;this.connected=false;observers.push(this);}observe(target){this.target=target;this.connected=true;}disconnect(){this.connected=false;}fire(){if(this.connected)this.fn([]);}}
  const win=Object.assign(new Events(),{scrollY:0,requestAnimationFrame:fn=>{const id=++nextFrame;frames.set(id,fn);return id;},cancelAnimationFrame:id=>frames.delete(id),scrollTo:value=>{win.scrollY=value.top;},MutationObserver:Observer,ResizeObserver:Observer});
  const view=mod.bindViewMode({document:doc,window:win});
  const flush=()=>{while(frames.size){const current=[...frames];frames.clear();for(const [,fn]of current)fn();}};
  const escape=()=>{const event=doc.fire('keydown',{key:'Escape',target:doc.activeElement},true);if(!event.stopped)doc.fire('keydown',event,false);return event;};
  // Native browser input can perform a microtask checkpoint between listeners.
  const nativeClick=async element=>{element.focus();const event=element.fire('click',{},true);await Promise.resolve();element.fire('click',event,false);await Promise.resolve();};
  const nativeEscape=async()=>{const event=doc.fire('keydown',{key:'Escape',target:doc.activeElement},true);await Promise.resolve();if(!event.stopped)doc.fire('keydown',event,false);await Promise.resolve();return event;};
  return {doc,win,els,at:id=>els.get(id),view,panels,businessEvents,flush,escape,nativeClick,nativeEscape,closeCounts,observers,frames};
}

test('default workbench keeps original tools and exposes an explicit pressed state',()=>{
  const f=fixture();assert.equal(f.view.mode(),'workbench');assert.equal(f.doc.body.dataset.viewMode,'workbench');
  assert.equal(f.at('conversation-tools').parentNode,f.at('workspace-tools-host'));assert.equal(f.at('conversation-tools').open,true);
  assert.equal(f.at('view-mode-workbench').getAttribute('aria-pressed'),'true');assert.equal(f.at('view-mode-chat').getAttribute('aria-pressed'),'false');
});
test('round-trip mode switches preserve draft, selection, history and every business node',()=>{
  const f=fixture(),input=f.at('composer'),history=f.at('history'),trigger=f.at('show-evidence'),business={phase:'tracking',materials:['A']};
  input.value='未保存的咨询';input.selectionStart=2;input.selectionEnd=5;history.business=business;
  f.at('view-mode-chat').click();f.flush();
  assert.equal(f.view.mode(),'chat');assert.equal(f.at('conversation-tools').parentNode,f.at('chat-tools-host'));assert.equal(f.at('conversation-tools').open,false);
  assert.equal(f.at('view-mode-chat').getAttribute('aria-pressed'),'true');assert.equal(f.at('show-evidence'),trigger);
  f.at('view-mode-workbench').click();f.flush();assert.equal(f.at('composer'),input);assert.equal(input.value,'未保存的咨询');assert.equal(input.selectionStart,2);assert.equal(input.selectionEnd,5);
  assert.equal(f.at('history'),history);assert.equal(history.business,business);assert.deepEqual(f.businessEvents,[]);
});
test('invalid and repeated mode choices do not reset an open tools menu or touch the draft',()=>{
  const f=fixture();assert.equal(f.view.setMode('invalid'),false);f.view.setMode('chat');f.at('conversation-tools').open=true;
  f.view.setMode('chat');assert.equal(f.at('conversation-tools').open,true);assert.deepEqual(f.businessEvents,[]);
});
test('entering chat preserves open native sheets and selects the last focused one',()=>{
  const f=fixture();f.panels['worksheet-panel'].open=true;f.panels['evidence-panel'].open=true;
  f.at('evidence-panel-input').value='未保存事实';f.at('evidence-panel-input').focus();f.at('view-mode-chat').click();
  assert.equal(f.panels['evidence-panel'].dataset.chatActive,'true');assert.equal(f.at('chat-workarea').classList.contains('is-open'),true);
  assert.equal(f.at('conversation-thread').inert,true);assert.equal(f.at('compose-section').inert,true);
  f.view.setMode('workbench');assert.equal(f.panels['worksheet-panel'].open,true);assert.equal(f.panels['evidence-panel'].open,true);assert.equal(f.at('evidence-panel-input').value,'未保存事实');
  assert.equal(f.at('conversation-thread').inert,false);assert.equal(f.at('compose-section').inert,false);
});
test('sheet selection and return preserve fields, open state and a pre-existing inert value',()=>{
  const f=fixture({inertComposer:true});f.view.setMode('chat');f.at('conversation-tools').open=true;
  f.at('show-followups').click();assert.equal(f.panels['followup-panel'].dataset.chatActive,'true');assert.equal(f.at('conversation-tools').open,false);
  f.at('followup-panel-input').value='仍待保存的跟进';f.at('close-chat-workarea').click();
  assert.equal(f.at('chat-workarea').classList.contains('is-open'),false);assert.equal(f.panels['followup-panel'].open,true);assert.equal(f.at('followup-panel-input').value,'仍待保存的跟进');
  assert.equal(f.at('conversation-thread').inert,false);assert.equal(f.at('compose-section').inert,true);assert.equal(f.doc.activeElement,f.at('conversation-tools-summary'));
  assert.equal(f.at('show-followups').getAttribute('aria-expanded'),'false');
  f.view.setMode('workbench');assert.equal(f.at('show-followups').getAttribute('aria-expanded'),'true');
});
test('a delayed native toggle cannot reopen a layer the user already dismissed',()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-worksheet').click();f.at('close-chat-workarea').click();
  f.panels['worksheet-panel'].fire('toggle');assert.equal(f.at('chat-workarea').classList.contains('is-open'),false);
  assert.equal(f.panels['worksheet-panel'].open,true);assert.equal(f.at('show-worksheet').getAttribute('aria-expanded'),'false');
});
test('entering chat is not overridden by delayed toggles from other already-open sheets',()=>{
  const f=fixture();f.panels['worksheet-panel'].open=true;f.panels['evidence-panel'].open=true;
  f.at('evidence-panel-input').focus();f.at('view-mode-chat').click();f.panels['worksheet-panel'].fire('toggle');
  assert.equal(f.panels['evidence-panel'].dataset.chatActive,'true');
});
test('native sheet closure clears the chat overlay and restores tools focus',()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-evidence').click();f.panels['evidence-panel'].open=false;f.panels['evidence-panel'].fire('toggle');
  assert.equal(f.at('chat-workarea').classList.contains('is-open'),false);assert.equal(f.doc.activeElement,f.at('conversation-tools-summary'));
});
test('Escape closes the menu first, then the sheet, without business actions',()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-worksheet').click();f.businessEvents.length=0;f.at('conversation-tools').open=true;
  f.escape();assert.equal(f.at('conversation-tools').open,false);assert.equal(f.at('chat-workarea').classList.contains('is-open'),true);
  f.escape();assert.equal(f.at('chat-workarea').classList.contains('is-open'),false);assert.equal(f.panels['worksheet-panel'].open,true);assert.deepEqual(f.businessEvents,[]);
});
test('outside pointer closes the menu and keeps the original summary available',()=>{
  const f=fixture();f.view.setMode('chat');f.at('conversation-tools').open=true;f.at('show-evidence').focus();
  f.doc.fire('pointerdown',{target:f.at('composer')},true);assert.equal(f.at('conversation-tools').open,false);assert.equal(f.doc.activeElement,f.at('conversation-tools-summary'));assert.deepEqual(f.businessEvents,[]);
});
test('source closure restores chat tools focus after the legacy close handler',async()=>{
  const f=fixture();f.view.setMode('chat');f.at('conversation-tools').open=true;f.at('show-outputs').click();
  assert.equal(f.at('output-panel').hidden,false);f.at('close-outputs').click();await Promise.resolve();f.flush();assert.equal(f.at('output-panel').hidden,true);assert.equal(f.doc.activeElement,f.at('conversation-tools-summary'));
});
test('native event checkpoints cannot lose focus after closing profile or outputs',async()=>{
  const f=fixture();f.view.setMode('chat');
  for(const [trigger,panel,close]of [['show-profile','profile-preview','close-profile-preview'],['show-outputs','output-panel','close-outputs']]){
    f.at('conversation-tools').open=true;f.at(trigger).click();await f.nativeClick(f.at(close));f.flush();
    assert.equal(f.at(panel).hidden,true);assert.equal(f.doc.activeElement.id,'conversation-tools-summary');
  }
});
test('native Escape waits for existing handlers and closes an unhandled source exactly once',async()=>{
  const f=fixture();f.view.setMode('chat');f.at('conversation-tools').open=true;f.at('show-profile').click();
  await f.nativeEscape();f.flush();assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.closeCounts.get('profile-preview')||0,0);
  assert.equal(f.doc.activeElement.id,'conversation-tools-summary');
  f.at('conversation-tools').open=true;f.at('show-outputs').click();await f.nativeEscape();f.flush();
  assert.equal(f.at('output-panel').hidden,true);assert.equal(f.closeCounts.get('output-panel'),1);assert.equal(f.doc.activeElement.id,'conversation-tools-summary');
});
test('material close and Escape retain the visible add-material return target',async()=>{
  const f=fixture();f.view.setMode('chat');
  f.at('material-source').click();await f.nativeClick(f.at('close-material-preview'));f.flush();assert.equal(f.doc.activeElement.id,'add-material');
  f.at('material-source').click();await f.nativeEscape();f.flush();assert.equal(f.at('material-preview').hidden,true);assert.equal(f.doc.activeElement.id,'add-material');
});
test('Escape gives a visible source drawer priority and does not close the sheet behind it',async()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-evidence').click();f.at('profile-preview').hidden=false;
  f.escape();await Promise.resolve();f.flush();assert.equal(f.at('profile-preview').hidden,true);assert.equal(f.at('chat-workarea').classList.contains('is-open'),true);assert.equal(f.doc.activeElement,f.at('conversation-tools-summary'));
});
test('Escape lets source handlers run first and uses the original close button as fallback',()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-evidence').click();f.at('output-panel').hidden=false;
  const event=f.escape();assert.equal(f.at('output-panel').hidden,false);assert.equal(event.defaultPrevented,false);
  f.flush();assert.equal(f.at('output-panel').hidden,true);assert.equal(f.closeCounts.get('output-panel'),1);
  assert.equal(f.at('chat-workarea').classList.contains('is-open'),true);
});
test('more workflows returns to the original workbench panel with its draft preserved',()=>{
  const f=fixture(),task=f.at('task-draft-panel');task.draft={content:'原流程草稿'};f.view.setMode('chat');
  f.at('show-workbench-tasks').click();f.flush();assert.equal(f.view.mode(),'workbench');assert.equal(task.open,true);
  assert.equal(task.draft.content,'原流程草稿');assert.equal(f.doc.activeElement,f.at('task-draft-summary'));assert.deepEqual(f.businessEvents,[]);
});
test('reading positions are independent and first chat entry starts at the history tail',()=>{
  const f=fixture();f.win.scrollY=240;f.view.setMode('chat');f.flush();assert.equal(f.at('conversation-thread').scrollTop,700);
  f.at('conversation-thread').scrollTop=320;f.at('conversation-thread').fire('scroll');f.view.setMode('workbench');f.flush();assert.equal(f.win.scrollY,240);
  f.win.scrollY=410;f.view.setMode('chat');f.flush();assert.equal(f.at('conversation-thread').scrollTop,320);
  f.view.setMode('workbench');f.flush();assert.equal(f.win.scrollY,410);
});
test('new content follows the tail only while the reader was already near the bottom',()=>{
  const f=fixture();f.view.setMode('chat');f.flush();const observer=f.observers.find(item=>item.target===f.at('history'));
  assert.ok(observer,'history observer exists');f.at('conversation-thread').scrollHeight=1300;observer.fire();f.flush();assert.equal(f.at('conversation-thread').scrollTop,1000);
  f.at('conversation-thread').scrollTop=200;f.at('conversation-thread').fire('scroll');f.at('conversation-thread').scrollHeight=1600;observer.fire();f.flush();assert.equal(f.at('conversation-thread').scrollTop,200);
});
test('manual scroll-up cancels a queued tail follow before its animation frame runs',()=>{
  const f=fixture();f.view.setMode('chat');f.flush();const observer=f.observers.find(item=>item.target===f.at('history'));
  f.at('conversation-thread').scrollHeight=1300;observer.fire();f.at('conversation-thread').scrollTop=100;f.at('conversation-thread').fire('scroll');
  f.flush();assert.equal(f.at('conversation-thread').scrollTop,100);
});
test('dispose removes UI listeners, cancels pending scrolling and restores prior inert state',()=>{
  const f=fixture();f.view.setMode('chat');f.at('show-worksheet').click();assert.equal(f.at('conversation-thread').inert,true);
  f.view.dispose();assert.equal(f.at('conversation-thread').inert,false);assert.equal(f.frames.size,0);assert.equal(f.observers.every(observer=>!observer.connected),true);
  f.at('view-mode-workbench').click();assert.equal(f.view.mode(),'chat');assert.equal(f.view.setMode('workbench'),false);assert.equal(f.at('composer').value,'');
});
