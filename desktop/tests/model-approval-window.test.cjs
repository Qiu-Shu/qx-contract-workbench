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

const judgeDetails=(available=true,max_total_usd='0.005')=>({...details,judge:{available,max_total_usd}});
const plain=value=>JSON.parse(JSON.stringify(value));

test('approval presents optional Judge separately and accepts only the displayed exact selection',async()=>{
  for(const selected of [false,true]){
    const f=fixture(),pending=f.api.confirm({parent:f.parent,details:judgeDetails(),guard:()=>true});await tick();
    assert.equal(f.windows.length,1);const win=f.windows[0],read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
    const value={main:true,judge:selected};
    assert.equal(await decide(f.event(win),value),false,'unpresented selection');
    assert.deepEqual(plain(await read(f.event(win))),judgeDetails());
    for(const invalid of [true,{main:true},{judge:true},{main:false,judge:true},{main:1,judge:false},
      {main:true,judge:'true'},{main:true,judge:false,extra:true},[true,false]])
      assert.equal(await decide(f.event(win),invalid),false);
    assert.equal(await decide({sender:{},senderFrame:win.webContents.mainFrame},value),false);
    assert.equal(await decide(f.event(win),value,'extra'),false);
    assert.equal(await decide(f.event(win),value),true);assert.deepEqual(plain(await pending),value);
    assert.equal(f.timers.size,0);
  }
});

test('unavailable Judge cannot be forged as selected and cancellation remains independent',async()=>{
  for(const selection of [false,{main:true,judge:false}]){
    const f=fixture(),pending=f.api.confirm({parent:f.parent,details:judgeDetails(false,null),guard:()=>true});await tick();
    assert.equal(f.windows.length,1);const event=f.event(f.windows[0]);
    await f.handlers.get('desktop:approval-state')(event);
    assert.equal(await f.handlers.get('desktop:approval-decision')(event,{main:true,judge:true}),false);
    assert.equal(await f.handlers.get('desktop:approval-decision')(event,selection),true);
    assert.deepEqual(plain(await pending),selection);
  }
});

test('Judge display schema rejects missing fields, misleading budgets and surplus configuration',async()=>{
  const f=fixture();
  for(const judge of [undefined,null,[],{}, {available:true}, {max_total_usd:'0.005'},
    {available:1,max_total_usd:'0.005'}, {available:false,max_total_usd:'0.005'},
    {available:true,max_total_usd:null}, {available:true,max_total_usd:'0'},
    {available:true,max_total_usd:'0.000000000000'}, {available:true,max_total_usd:'1000000.000000000001'},
    {available:true,max_total_usd:'0.0000000000001'}, {available:true,max_total_usd:0.005},
    {available:true,max_total_usd:'1e-3'}, {available:true,max_total_usd:'00.005'},
    {available:true,max_total_usd:'0.005',recipient:'Other'}]){
    assert.equal(await f.api.confirm({parent:f.parent,details:{...details,judge},guard:()=>true}),false);
  }
  assert.equal(f.windows.length,0);
  for(const budget of ['0.000000000001','1000000','1000000.000000000000']){
    const pending=f.api.confirm({parent:f.parent,details:judgeDetails(true,budget),guard:()=>true});await tick();
    const win=f.windows.at(-1);assert(win);
    const shown=await f.handlers.get('desktop:approval-state')(f.event(win));assert.equal(shown.judge.max_total_usd,budget);
    f.api.close();assert.equal(await pending,false);
  }
});

test('legacy display cannot accept a new Judge selection and successive windows keep independent choices',async()=>{
  const f=fixture(),first=f.api.confirm({parent:f.parent,details:judgeDetails(),guard:()=>true});await tick();
  assert.equal(f.windows.length,1);const old=f.windows[0],read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
  await read(f.event(old));assert.equal(await decide(f.event(old),{main:true,judge:true}),true);await first;
  const second=f.api.confirm({parent:f.parent,details,guard:()=>true});await tick();const current=f.windows[1];
  assert.equal(await read(f.event(old)),null);assert.equal(await decide(f.event(old),{main:true,judge:true}),false);
  await read(f.event(current));assert.equal(await decide(f.event(current),{main:true,judge:false}),false);
  assert.equal(await decide(f.event(current),true),true);assert.equal(await second,true);
});

test('Judge page starts unselected, discloses the separate recipient and exact budget, and returns explicit choices',async()=>{
  for(const selected of [false,true]){
    const f=page(async()=>judgeDetails());await tick();const checkbox=f.at('approval-judge-select');assert(checkbox);
    assert.equal(checkbox.checked,false);assert.equal(checkbox.disabled,false);
    assert.equal(f.at('approval-judge').hidden,false);
    assert.match(f.html,/TypeSafe（api\.typesafe\.ai）/);assert.match(f.html,/Jev 1\.13\.0/);
    assert.match(f.html,/判断首个处理流程/);assert.match(f.html,/同一完整文字/);
    assert.match(f.at('approval-judge-budget').textContent,/0\.005/);
    assert.match(f.at('approval-judge-budget').textContent,/不是供应商收费上限/);
    assert.match(f.at('approval-judge-budget').textContent,/实际费用尚未核对/);
    assert.equal(f.document.activeElement,f.at('approval-cancel'));
    checkbox.checked=selected;await f.at('approval-confirm').listeners.click();
    assert.deepEqual(plain(f.calls),[{main:true,judge:selected}]);assert.equal(checkbox.disabled,true);
  }
  const fresh=page(async()=>judgeDetails());await tick();assert.equal(fresh.at('approval-judge-select').checked,false);
});

test('unavailable Judge remains unselected and disabled without blocking main confirmation',async()=>{
  const f=page(async()=>judgeDetails(false,null));await tick();const checkbox=f.at('approval-judge-select');assert(checkbox);
  assert.equal(checkbox.disabled,true);assert.equal(checkbox.checked,false);
  assert.match(f.at('approval-judge-budget').textContent,/尚未启用/);assert.match(f.at('approval-judge-budget').textContent,/不会发送/);
  assert.doesNotMatch(f.at('approval-judge-budget').textContent,/USD/);
  assert.equal(f.at('approval-confirm').disabled,false);
  checkbox.checked=true;checkbox.disabled=false;await f.at('approval-confirm').listeners.click();
  assert.deepEqual(plain(f.calls),[{main:true,judge:false}]);
});

test('malformed or late Judge display never enables confirmation or restores a selection',async()=>{
  for(const judge of [null,{}, {available:true,max_total_usd:'NaN'}, {available:false,max_total_usd:'0.005'},
    {available:true,max_total_usd:'1000000.000000000001'}, {available:true,max_total_usd:'0.005',extra:true}]){
    const f=page(async()=>({...details,judge}));await tick();
    assert.equal(f.at('approval-confirm').disabled,true);await f.at('approval-confirm').listeners.click();assert.deepEqual(f.calls,[]);
  }
  let release;const f=page(()=>new Promise(resolve=>release=resolve));await tick();
  f.events.get('pagehide')();release(judgeDetails());await tick();
  assert.equal(f.at('approval-content').textContent,'');assert.equal(f.at('approval-confirm').disabled,true);
  await f.at('approval-confirm').listeners.click();assert.deepEqual(f.calls,[]);
});

test('preload forwards only booleans or exact Main and Judge selections',async()=>{
  let exposed;const calls=[];
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'model-approval-preload.cjs'),'utf8'),{require:()=>({
    contextBridge:{exposeInMainWorld:(_name,value)=>exposed=value},
    ipcRenderer:{invoke:(...args)=>{calls.push(args);return Promise.resolve(true);}}})});
  for(const judge of [false,true])assert.equal(await exposed.decide({main:true,judge}),true);
  for(const value of [{main:true},{main:false,judge:false},{main:1,judge:false},{main:true,judge:1},
    {main:true,judge:false,extra:0},[true,false],new Boolean(true)])assert.equal(await exposed.decide(value),false);
  assert.deepEqual(plain(calls),[['desktop:approval-decision',{main:true,judge:false}],['desktop:approval-decision',{main:true,judge:true}]]);
});

test('a displayed Judge choice cannot survive a stale guard, Escape or a later window',async()=>{
  for(const cause of ['guard','escape','parent']){
    const f=fixture();let current=true;
    const pending=f.api.confirm({parent:f.parent,details:judgeDetails(),guard:()=>current});await tick();
    const win=f.windows[0],read=f.handlers.get('desktop:approval-state'),decide=f.handlers.get('desktop:approval-decision');
    await read(f.event(win));
    if(cause==='guard')current=false;
    if(cause==='escape')win.webContents.emit('before-input-event',{preventDefault(){}},{type:'keyDown',key:'Escape'});
    if(cause==='parent')f.parent.emit('closed');
    assert.equal(await decide(f.event(win),{main:true,judge:true}),false,cause);
    assert.equal(await pending,false);assert.equal(f.timers.size,0);
  }
});

test('missing Judge display keeps legacy choice and a rejected approval cannot resend either service',async()=>{
  const legacy=page();await tick();assert.equal(legacy.at('approval-judge').hidden,true);
  assert.equal(legacy.at('approval-judge-select').checked,false);assert.equal(legacy.at('approval-judge-select').disabled,true);
  const f=page(async()=>judgeDetails());await tick();f.at('approval-judge-select').checked=true;
  f.api.decide=async value=>{f.calls.push(value);return false;};
  await f.at('approval-confirm').listeners.click();
  assert.equal(f.at('approval-confirm').disabled,true);assert.equal(f.at('approval-judge-select').disabled,true);
  assert.equal(f.at('approval-cancel').disabled,false);assert.equal(f.document.activeElement,f.at('approval-cancel'));
  await f.at('approval-confirm').listeners.click();assert.deepEqual(plain(f.calls),[{main:true,judge:true}]);
  f.events.get('pagehide')();assert.equal(f.at('approval-judge-select').checked,false);
});
