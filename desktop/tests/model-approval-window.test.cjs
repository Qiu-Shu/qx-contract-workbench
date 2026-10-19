const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const desktop=path.join(__dirname,'..');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const details={content:'合成文字：<img src=x onerror=alert(1)>\n请核对完整文字。',
  model:'deepseek-flash',max_total_usd:'0.024576',recipient:'DeepSeek（api.deepseek.com）'};

function fixture() {
  const handlers=new Map(),windows=[],sessions=[],timers=new Set();
  const ipcMain={handle(name,fn){assert(!handlers.has(name));handlers.set(name,fn);}};
  class Window extends EventEmitter {
    constructor(options){super();this.options=options;this.dead=false;windows.push(this);
      this.webContents=new EventEmitter();Object.assign(this.webContents,{mainFrame:{url:''},
        getURL:()=>this.url||'',setWindowOpenHandler:fn=>this.openHandler=fn});}
    loadURL(url){this.url=url;this.webContents.mainFrame.url=url;queueMicrotask(()=>this.emit('ready-to-show'));return Promise.resolve();}
    show(){this.shown=true;}isDestroyed(){return this.dead;}
    destroy(){if(this.dead)return;this.dead=true;this.emit('closed');}
  }
  const session={fromPartition(name,options){const item=new EventEmitter();Object.assign(item,{name,options,
    setPermissionRequestHandler:fn=>item.requestPermission=fn,setPermissionCheckHandler:fn=>item.checkPermission=fn,
    webRequest:{onBeforeRequest:(...args)=>item.network=args.at(-1)},
    clearStorageData:async()=>{item.cleared=true;},clearCache:async()=>{item.cacheCleared=true;}});sessions.push(item);return item;}};
  const schedule=(fn,ms)=>{const value={fn,ms,unref(){}};timers.add(value);return value;};
  const module={exports:{}};
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'model-approval-window.cjs'),'utf8'),{
    module,exports:module.exports,require,__dirname:desktop,Buffer,
    setTimeout:schedule,setInterval:schedule,clearTimeout:value=>timers.delete(value),clearInterval:value=>timers.delete(value)});
  const api=module.exports.createModelApprovalWindow({BrowserWindow:Window,ipcMain,session});
  const parent=new EventEmitter();parent.isDestroyed=()=>false;parent.webContents=new EventEmitter();
  const event=window=>({sender:window.webContents,senderFrame:window.webContents.mainFrame});
  return {api,parent,windows,sessions,timers,handlers,event,fire:ms=>[...timers].filter(value=>value.ms===ms).forEach(value=>value.fn())};
}

test('approval creates one isolated modal and only its exact main frame can read or explicitly decide',async()=>{
  const f=fixture();const pending=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();
  const win=f.windows[0],read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
  assert.equal(win.options.parent,f.parent);assert.equal(win.options.modal,true);
  assert.equal(win.options.webPreferences.sandbox,true);assert.equal(win.options.webPreferences.contextIsolation,true);
  assert.equal(win.options.webPreferences.nodeIntegration,false);assert.equal(win.options.webPreferences.webSecurity,true);
  assert.equal(win.options.webPreferences.webviewTag,false);assert.equal(win.options.webPreferences.session,f.sessions[0]);
  assert(!f.sessions[0].name.startsWith('persist:'));assert.equal(win.options.show,false);
  assert.equal(f.sessions[0].checkPermission(),false);
  let permission;f.sessions[0].requestPermission({},'camera',value=>permission=value);assert.equal(permission,false);
  assert.equal(win.openHandler({url:'https://example.invalid'}).action,'deny');
  assert.equal(await decide(f.event(win),true),false,'reading the displayed state must precede approval');
  for(const event of [{sender:{},senderFrame:win.webContents.mainFrame},
    {sender:win.webContents,senderFrame:{url:win.url}}]) {
    assert.equal(await read(event),null);assert.equal(await decide(event,true),false);
  }
  const url=win.url;win.webContents.mainFrame.url=url+'?other=1';assert.equal(await read(f.event(win)),null);
  win.webContents.mainFrame.url=url;
  assert.deepEqual(JSON.parse(JSON.stringify(await read(f.event(win)))),details);
  for(const value of ['true',1,{},undefined])assert.equal(await decide(f.event(win),value),false);
  assert.equal(await decide(f.event(win),true,'extra'),false);
  assert.equal(await decide(f.event(win),true),true);assert.equal(await pending,true);
  assert.equal(win.dead,true);assert.equal(f.timers.size,0);assert.equal(await read(f.event(win)),null);
});

test('approval cancellation releases lifecycle handlers and a following window cannot borrow the previous decision',async()=>{
  const f=fixture();const first=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const old=f.windows[0];
  assert.equal(await f.api.confirm({parent:f.parent,details,guard:()=>true}),false);assert.equal(f.windows.length,1);
  f.api.close();assert.equal(await first,false);assert.equal(f.parent.listenerCount('closed'),0);assert.equal(f.timers.size,0);
  const next=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const win=f.windows[1];
  assert.notEqual(f.sessions[0].name,f.sessions[1].name);
  const read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
  assert.equal(await read(f.event(old)),null);assert.equal(await decide(f.event(old),true),false);
  await read(f.event(win));assert.equal(await decide(f.event(win),false),true);assert.equal(await next,false);
  assert.equal(f.handlers.size,2);assert.equal(f.timers.size,0);
});

test('approval stale guard, parent close, Escape and bounded timeout cancel without a decision',async()=>{
  for(const cause of ['guard','parent','escape','timeout','window']) {
    const f=fixture();let current=true;
    const pending=f.api.confirm({parent:f.parent,details,guard:()=>current});await tick();const win=f.windows[0];
    if(cause==='guard'){current=false;f.fire(250);}
    if(cause==='parent')f.parent.emit('closed');
    if(cause==='escape'){let prevented=false;win.webContents.emit('before-input-event',
      {preventDefault(){prevented=true;}},{type:'keyDown',key:'Escape'});assert.equal(prevented,true);}
    if(cause==='timeout')f.fire(120000);
    if(cause==='window')win.destroy();
    assert.equal(await pending,false,cause);assert.equal(f.timers.size,0,cause);
  }
});

function page(read=async()=>details) {
  const html=fs.readFileSync(path.join(desktop,'model-approval.html'),'utf8'),elements=new Map(),events=new Map(),calls=[];
  const document={activeElement:null,getElementById:id=>elements.get(id)},viewport={scrollY:0};
  class Element {
    constructor(){this.textContent='';this.disabled=true;this.listeners={};}
    addEventListener(name,listener){this.listeners[name]=listener;}
    focus(options){document.activeElement=this;if(options?.preventScroll!==true)viewport.scrollY=400;}
    set innerHTML(_value){throw Error('untrusted markup must never render');}
  }
  for(const match of html.matchAll(/\bid="([^"]+)"/g))elements.set(match[1],new Element());
  const api={state:read,decide:async value=>{calls.push(value);return true;}};
  const window={desktopApproval:api,addEventListener:(name,listener)=>events.set(name,listener)};
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'model-approval.js'),'utf8'),{document,window});
  return {api,calls,events,html,document,viewport,at:id=>elements.get(id)};
}

test('approval default cancel focus preserves the initial top viewport',async()=>{
  const f=page();await tick();
  assert.equal(f.document.activeElement,f.at('approval-cancel'));
  assert.equal(f.viewport.scrollY,0,'focusing the lower cancel button must not scroll away from recipient, model and budget');
  assert.doesNotMatch(f.html,/\bautofocus\b/,'native autofocus must not race the controlled default focus');
});

test('approval page renders full untrusted text as text and defaults focus to cancel',async()=>{
  const content='<img src=x onerror=alert(1)>\n'+'合成原文。'.repeat(4000);
  const f=page(async()=>({...details,content}));await tick();
  assert.equal(f.at('approval-content').textContent,content);
  assert.equal(f.at('approval-recipient').textContent,details.recipient);
  assert.match(f.at('approval-budget').textContent,/0\.024576/);
  assert.equal(f.document.activeElement,f.at('approval-cancel'));
  assert.equal(f.at('approval-confirm').disabled,false);assert.deepEqual(f.calls,[]);
  assert.match(f.html,/只发送下列文字；本机原附件不会发送。结果保存为内部待核草稿。/);
  await f.at('approval-cancel').listeners.click();assert.deepEqual(f.calls,[false]);
});

test('approval page never confirms while loading and explicit confirm is sent only once',async()=>{
  let release;const gate=new Promise(resolve=>release=resolve),f=page(()=>gate);
  assert.equal(f.at('approval-confirm').disabled,true);
  await f.at('approval-confirm').listeners.click();assert.deepEqual(f.calls,[]);
  release(details);await tick();
  let accept;f.api.decide=value=>{f.calls.push(value);return new Promise(resolve=>accept=resolve);};
  const pending=f.at('approval-confirm').listeners.click();await f.at('approval-confirm').listeners.click();
  assert.equal(f.at('approval-confirm').disabled,true);assert.deepEqual(f.calls,[true]);accept(true);await pending;
});

test('approval preload exposes only two dedicated calls and refuses truthy decision values',async()=>{
  let exposed;const calls=[];
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'model-approval-preload.cjs'),'utf8'),{require:()=>({
    contextBridge:{exposeInMainWorld:(name,value)=>{assert.equal(name,'desktopApproval');exposed=value;}},
    ipcRenderer:{invoke:(...args)=>{calls.push(args);return Promise.resolve(true);}}})});
  assert.deepEqual(Object.keys(exposed).sort(),['decide','state']);
  await exposed.state();await exposed.decide(false);await exposed.decide(true);
  for(const value of [1,'true',null,{}])assert.equal(await exposed.decide(value),false);
  assert.deepEqual(calls,[['desktop:approval-state'],['desktop:approval-decision',false],['desktop:approval-decision',true]]);
});

test('approval still settles cancellation if optional session cleanup fails',async()=>{
  const f=fixture();const pending=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();
  f.sessions[0].clearStorageData=()=>{throw Error('synthetic-private-diagnostic');};
  assert.doesNotThrow(()=>f.api.close());assert.equal(await pending,false);assert.equal(f.timers.size,0);
});

test('approval validates the display boundary and admits the full 65536-byte text without truncation',async()=>{
  const f=fixture();
  for(const changed of [{...details,secret:'not-allowed'},{...details,model:'other'},
    {...details,recipient:'Other'},{...details,max_total_usd:'NaN'},{...details,max_total_usd:'0'},
    {...details,max_total_usd:'1000000.1'},{...details,content:'界'.repeat(21846)}])
    assert.equal(await f.api.confirm({parent:f.parent,details:changed,guard:()=>true}),false);
  assert.equal(f.windows.length,0);
  const content='a'.repeat(65536),pending=f.api.confirm({parent:f.parent,details:{...details,content},guard:()=>true});
  await tick();assert.equal((await f.handlers.get('desktop:approval-state')(f.event(f.windows[0]))).content,content);
  f.api.close();assert.equal(await pending,false);
});

test('approval blocks navigation, all external requests and cancels a crashed renderer',async()=>{
  const f=fixture(),pending=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const win=f.windows[0];
  for(const name of ['will-navigate','will-frame-navigate','will-redirect','will-attach-webview']){
    let prevented=false;win.webContents.emit(name,{preventDefault(){prevented=true;}},'https://example.invalid');
    assert.equal(prevented,true,name);
  }
  for(const url of ['https://api.deepseek.com','file:///unrelated.html',win.url+'?other=1']){
    let response;f.sessions[0].network({url},value=>response=value);assert.equal(response.cancel,true);
  }
  let response;f.sessions[0].network({url:win.url},value=>response=value);assert.equal(response.cancel,false);
  win.webContents.emit('render-process-gone');assert.equal(await pending,false);
});

test('approval page loading failure and page departure never enable or dispatch confirmation',async()=>{
  const failed=page(async()=>{throw Error('synthetic-private-diagnostic');});await tick();
  assert.equal(failed.at('approval-confirm').disabled,true);assert.equal(failed.at('approval-cancel').disabled,false);
  assert.doesNotMatch(failed.at('approval-status').textContent,/synthetic/);
  await failed.at('approval-confirm').listeners.click();assert.deepEqual(failed.calls,[]);
  let release;const later=page(()=>new Promise(resolve=>release=resolve));await tick();later.events.get('pagehide')();
  release(details);await tick();assert.equal(later.at('approval-content').textContent,'');
  await later.at('approval-confirm').listeners.click();assert.deepEqual(later.calls,[]);
});
