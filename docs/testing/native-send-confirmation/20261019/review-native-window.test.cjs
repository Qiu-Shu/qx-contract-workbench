const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const desktop=path.resolve(process.cwd(),'desktop');
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

function page(read=async()=>details) {
  const html=fs.readFileSync(path.join(desktop,'model-approval.html'),'utf8'),elements=new Map(),events=new Map(),calls=[];
  const document={activeElement:null,scrollY:0,getElementById:id=>elements.get(id)};
  class Element {
    constructor(){this.textContent='';this.disabled=true;this.listeners={};}
    addEventListener(name,listener){this.listeners[name]=listener;}
    focus(options){document.activeElement=this;if(options?.preventScroll!==true)document.scrollY=400;}
    set innerHTML(_value){throw Error('untrusted markup must never render');}
  }
  for(const match of html.matchAll(/\bid="([^"]+)"/g))elements.set(match[1],new Element());
  const api={state:read,decide:async value=>{calls.push(value);return true;}};
  const window={desktopApproval:api,addEventListener:(name,listener)=>events.set(name,listener)};
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'model-approval.js'),'utf8'),{document,window});
  return {api,calls,events,html,document,at:id=>elements.get(id)};
}



test('only the displayed original approval frame can approve, and late former windows cannot decide',async()=>{
  const f=fixture(),first=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const old=f.windows[0];
  const read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
  assert.equal(await decide(f.event(old),true),false);
  const extraWindow={sender:{},senderFrame:old.webContents.mainFrame};
  const subframe={sender:old.webContents,senderFrame:{url:old.url}};
  for(const event of [extraWindow,subframe]){assert.equal(await read(event),null);assert.equal(await decide(event,true),false);}
  assert.equal((await read(f.event(old))).content,details.content);
  f.api.close();assert.equal(await first,false);
  const second=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const current=f.windows[1];
  assert.equal(await decide(f.event(old),true),false);assert.equal(await read(f.event(old)),null);
  await read(f.event(current));assert.equal(await decide(f.event(current),false),true);assert.equal(await second,false);
});

test('approval has no cookie-sharing partition or outbound resource route and does not parse content as HTML',async()=>{
  const f=fixture(),pending=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const win=f.windows[0],isolated=f.sessions[0];
  assert.match(isolated.name,/^qx-approval-/);assert.doesNotMatch(isolated.name,/^persist:/);assert.equal(isolated.options.cache,false);
  for(const url of ['https://api.deepseek.com/chat/completions','http://127.0.0.1:1234/api/session',
    'data:text/html,<script>x</script>','blob:http://127.0.0.1:1234/test','file:///C:/unrelated.txt']){
    let result;isolated.network({url},value=>result=value);assert.equal(result.cancel,true,url);
  }
  let result;isolated.network({url:win.url},value=>result=value);assert.equal(result.cancel,false);
  f.api.close();assert.equal(await pending,false);
  const content='<script>throw Error("not run")</script>\n  合成空白与长文'+ '界'.repeat(5000);
  const ui=page(async()=>({...details,content}));await tick();assert.equal(ui.at('approval-content').textContent,content);
  assert.equal(ui.document.activeElement,ui.at('approval-cancel'));assert.deepEqual(ui.calls,[]);
  assert.equal(ui.document.scrollY,0,'default Cancel focus must not scroll away from the approval heading');
  ui.api.decide=async()=>false;await ui.at('approval-confirm').listeners.click();assert.equal(ui.document.scrollY,0);
  const failed=page(async()=>{throw Error('synthetic-read-failure');});await tick();
  assert.equal(failed.document.activeElement,failed.at('approval-cancel'));assert.equal(failed.document.scrollY,0);
  assert.match(ui.html,/connect-src 'none'/);assert.match(ui.html,/id="approval-cancel"[^>]*disabled/);
});

test('guard loss parent destruction and timeout each settle false and remove the previous timers',async()=>{
  for(const cause of ['guard','destroy','timeout']){
    const f=fixture();let valid=true;const pending=f.api.confirm({parent:f.parent,details,guard:()=>valid});await tick();
    const win=f.windows[0];await f.handlers.get('desktop:approval-state')(f.event(win));
    if(cause==='guard'){valid=false;assert.equal(await f.handlers.get('desktop:approval-decision')(f.event(win),true),false);}
    if(cause==='destroy')f.parent.webContents.emit('destroyed');
    if(cause==='timeout')f.fire(120000);
    assert.equal(await pending,false,cause);assert.equal(f.timers.size,0);assert.equal(win.dead,true);
  }
});

test('failed session cleanup cannot leave a granted or canceled approval unresolved',async()=>{
  for(const approved of [false,true]){
    const f=fixture(),pending=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const win=f.windows[0];
    f.sessions[0].webRequest.onBeforeRequest=()=>{throw Error('private-cleanup');};
    f.sessions[0].clearStorageData=()=>{throw Error('private-cleanup');};
    f.sessions[0].clearCache=()=>Promise.reject(Error('private-cleanup'));
    await f.handlers.get('desktop:approval-state')(f.event(win));
    assert.equal(await f.handlers.get('desktop:approval-decision')(f.event(win),approved),true);
    assert.equal(await pending,approved);assert.equal(f.timers.size,0);assert.equal(win.dead,true);
  }
});
