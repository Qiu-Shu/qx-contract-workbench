const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const vm=require('node:vm');
const desktop=path.join(__dirname,'..');
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));

async function native(t) {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'qx-model-ui-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const handlers=new Map(),events=new Map(),states=[],calls=[];let ready,window,menu,quit=0;
  const store={async status(){calls.push('status');return {status:'empty'};},
    async save(value){calls.push(['save',value]);return {status:'saved'};},
    async remove(){calls.push('remove');return {status:'empty'};}};
  class Window {
    constructor(){window=this;this.url='';this.webContents={mainFrame:{url:''},send:(_name,state)=>states.push(state),
      getURL:()=>this.url,setWindowOpenHandler(){},on(){}};}
    async loadURL(url){this.url=url;this.webContents.mainFrame={url};}
    isDestroyed(){return false;}once(){}show(){}hide(){}isFocused(){return true;}
  }
  const app={setName(){},getPath:()=>directory,setPath(){},requestSingleInstanceLock:()=>true,
    on:(name,listener)=>events.set(name,listener),whenReady:()=>({then:fn=>{ready=fn();return ready;}}),
    quit:()=>quit++,exit:()=>{throw Error('unexpected exit');},isPackaged:false};
  const electron={app,BrowserWindow:Window,safeStorage:{},Menu:{buildFromTemplate:value=>value,setApplicationMenu:value=>menu=value},
    ipcMain:{handle:(name,handler)=>handlers.set(name,handler)},dialog:{showMessageBox:async()=>({})},
    session:{fromPartition:()=>({setPermissionRequestHandler(){},setPermissionCheckHandler(){},on(){}})}};
  const requireModule=name=>name==='electron'?electron:name==='./model-credentials.cjs'?{createModelCredentialStore:()=>store}
    :name.startsWith('./')?require(path.join(desktop,name)):require(name);
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'main.cjs'),'utf8'),{require:requireModule,__dirname:desktop,
    process:{env:{QX_DESKTOP_DATA_PARENT:directory},platform:'win32'},console});
  await ready;
  const event=()=>({sender:window.webContents,senderFrame:window.webContents.mainFrame});
  return {store,calls,handlers,events,states,event,window,get quit(){return quit;},
    open:async()=>{const entry=menu[0].submenu.find(item=>item.label==='主模型设置…');assert.ok(entry,'native model settings menu missing');await entry.click();}};
}

test('native menu enters a distinct settings mode and only returns protected credential status',async t=>{
  const f=await native(t);await f.open();
  assert.equal(f.states.at(-1).mode,'model-settings');assert.match(f.states.at(-1).message,/准备|设置/);
  const read=f.handlers.get('desktop:model-status');assert.equal(typeof read,'function');
  assert.equal((await read(f.event())).status,'empty');
  const save=f.handlers.get('desktop:model-save');assert.equal((await save(f.event(),'synthetic-secret')).status,'saved');
  assert.deepEqual(f.calls,['status',['save','synthetic-secret']]);
  assert.ok(!JSON.stringify(f.states).includes('synthetic-secret'));
});

test('each credential IPC rejects other windows, subframes, backend pages and the wrong mode',async t=>{
  const f=await native(t);await f.open();
  for(const name of ['desktop:model-status','desktop:model-save','desktop:model-remove']) {
    const run=f.handlers.get(name);assert.equal(typeof run,'function');
    for(const event of [{sender:{},senderFrame:f.window.webContents.mainFrame},
      {sender:f.window.webContents,senderFrame:{url:f.window.url}},
      {sender:f.window.webContents,senderFrame:{url:'http://127.0.0.1:8767/assistant'}}]) {
      assert.equal((await run(event,'synthetic-secret')).code,'ACCESS_DENIED');
    }
    const setup=f.window.webContents.mainFrame.url;
    for(const url of ['http://127.0.0.1:8767/assistant',setup+'?redirect=1']) {
      f.window.webContents.mainFrame.url=url;
      assert.equal((await run(f.event(),'synthetic-secret')).code,'ACCESS_DENIED');
    }
    f.window.webContents.mainFrame.url=setup;
  }
  assert.deepEqual(f.calls,[]);
  await f.handlers.get('desktop:resume')(f.event());
  assert.equal((await f.handlers.get('desktop:model-remove')(f.event())).code,'ACCESS_DENIED');
  assert.deepEqual(f.calls,[]);
});

test('a pending status read also locks mutation and rechecks permission on the next call',async t=>{
  const f=await native(t);await f.open();const gate=deferred();
  f.store.status=async()=>{f.calls.push('status');await gate.promise;return {status:'saved'};};
  const read=f.handlers.get('desktop:model-status'),pending=read(f.event());await tick();
  assert.equal((await f.handlers.get('desktop:model-remove')(f.event())).code,'ACCESS_DENIED');
  gate.resolve();assert.equal((await pending).status,'saved');
  f.window.webContents.mainFrame.url='http://127.0.0.1:8767/assistant';
  assert.equal((await read(f.event())).code,'ACCESS_DENIED');assert.deepEqual(f.calls,['status']);
});

test('pending status/save operations reject duplicate IPC and quit waits for the operation',async t=>{
  const f=await native(t);await f.open();const gate=deferred();
  f.store.save=async value=>{f.calls.push(['save',value]);await gate.promise;return {status:'saved'};};
  const save=f.handlers.get('desktop:model-save'),pending=save(f.event(),'synthetic-secret');await tick();
  assert.equal((await save(f.event(),'duplicate')).code,'ACCESS_DENIED');
  assert.equal((await f.handlers.get('desktop:model-status')(f.event())).code,'ACCESS_DENIED');
  const stateCount=f.states.length;await f.open();
  assert.equal(f.states.length,stateCount,'menu must not replace a busy settings page');
  assert.equal((await f.handlers.get('desktop:resume')(f.event())).ok,false);
  assert.equal(f.states.length,stateCount,'return must wait for the protected operation');
  f.events.get('before-quit')({preventDefault(){}});await tick();assert.equal(f.quit,0);
  gate.resolve();await pending;await tick();assert.equal(f.quit,1);
  assert.equal((await f.handlers.get('desktop:model-remove')(f.event())).code,'ACCESS_DENIED');
  assert.deepEqual(f.calls,[['save','synthetic-secret']]);
});

test('store failures and unexpected fields never escape through IPC',async t=>{
  const f=await native(t);await f.open();
  f.store.save=async()=>{throw Error('synthetic-private-diagnostic');};
  const result=await f.handlers.get('desktop:model-save')(f.event(),'synthetic-secret');
  assert.equal(result.status,'unavailable');assert.ok(!JSON.stringify(result).includes('synthetic'));
  f.store.status=async()=>({status:'saved',secret:'synthetic-secret',code:'synthetic-private-code'});
  const status=await f.handlers.get('desktop:model-status')(f.event());
  assert.ok(!JSON.stringify(status).includes('synthetic'));assert.equal(status.status,'saved');
});

test('preload exposes only explicit credential operations and package includes their modules',()=>{
  let exposed;const seen=[];
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'preload.cjs'),'utf8'),{require:()=>({
    contextBridge:{exposeInMainWorld:(_name,value)=>exposed=value},ipcRenderer:{invoke:(...args)=>seen.push(args),on(){}}})});
  assert.equal(typeof exposed.modelStatus,'function');exposed.modelStatus();exposed.modelSave('synthetic-secret');exposed.modelRemove();
  assert.deepEqual(seen,[['desktop:model-status'],['desktop:model-save','synthetic-secret'],['desktop:model-remove']]);
  const files=JSON.parse(fs.readFileSync(path.join(desktop,'package.json'),'utf8')).build.files;
  assert.ok(files.includes('model-settings.cjs'));assert.ok(files.includes('model-credentials.cjs'));
});

function page() {
  const html=fs.readFileSync(path.join(desktop,'setup.html'),'utf8'),elements=new Map(),listeners=new Map(),calls=[];
  class Element {
    constructor(tag){this.tag=tag;this.value='';this.hidden=false;this.disabled=false;this.listeners={};this.textContent='';}
    addEventListener(name,listener){this.listeners[name]=listener;}focus(){}setAttribute(name,value){this[name]=value;}
  }
  for(const match of html.matchAll(/<(\w+)\b[^>]*\bid="([^"]+)"/g))elements.set('#'+match[2],new Element(match[1]));
  const document={querySelector:selector=>elements.get(selector),querySelectorAll:selector=>selector==='button'
    ?[...elements.values()].filter(value=>value.tag==='button'):[]};
  let onState;const api={onState:fn=>onState=fn,state:async()=>({mode:'setup'}),chooseLibrary(){},start(){},resume:async()=>{calls.push('resume');},maintenance(){},
    modelStatus:async()=>({status:'empty'}),modelSave:async value=>{calls.push(['save',value]);return {status:'saved'};},
    modelRemove:async()=>{calls.push('remove');return {status:'empty'};}};
  const window={desktopSetup:api,addEventListener:(name,fn)=>listeners.set(name,fn)};
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'setup.js'),'utf8'),{document,window,console});
  return {api,calls,listeners,at:id=>elements.get('#'+id),state:value=>onState(value),html};
}

test('credential form saves once, clears input immediately and labels stored credentials without enabling model use',async()=>{
  const f=page();await tick();assert.ok(f.at('model-secret'),'password field missing');
  f.state({mode:'model-settings'});await tick();
  const gate=deferred();f.api.modelSave=async value=>{f.calls.push(['save',value]);await gate.promise;return {status:'saved'};};
  f.at('model-secret').value='synthetic-secret';const submit=f.at('model-settings').listeners.submit;
  const saving=submit({preventDefault(){}});assert.equal(f.at('model-secret').value,'');
  await submit({preventDefault(){}});assert.equal(f.calls.filter(value=>Array.isArray(value)).length,1);
  assert.equal(f.at('model-save').disabled,true);gate.resolve();await saving;
  assert.match(f.at('model-status').textContent,/已保存/);assert.match(f.at('model-save').textContent,/替换/);
  assert.match(f.html,/不会启用模型|不启用模型/);assert.match(f.html,/不授权|不会授权/);assert.match(f.html,/不产生费用|不会产生费用/);
});

test('credential errors clear inputs, hide raw errors and leaving discards delayed responses',async()=>{
  const f=page();await tick();assert.ok(f.at('model-secret'),'password field missing');f.state({mode:'model-settings'});await tick();
  f.api.modelSave=async()=>{throw Error('synthetic-private-diagnostic');};f.at('model-secret').value='synthetic-secret';
  await f.at('model-settings').listeners.submit({preventDefault(){}});
  assert.equal(f.at('model-secret').value,'');assert.ok(!f.at('model-status').textContent.includes('synthetic'));
  f.state({mode:'setup'});f.state({mode:'model-settings'});await tick();
  const gate=deferred();f.api.modelSave=()=>gate.promise;f.at('model-secret').value='synthetic-secret';
  const pending=f.at('model-settings').listeners.submit({preventDefault(){}});
  f.state({mode:'setup',message:'其他页面'});gate.resolve({status:'saved'});await pending;
  assert.equal(f.at('model-settings').hidden,true);assert.equal(f.at('status').textContent,'其他页面');
  f.at('model-secret').value='synthetic-secret';f.listeners.get('pagehide')();assert.equal(f.at('model-secret').value,'');
});

test('credential remove and return clear an unsubmitted replacement',async()=>{
  const f=page();await tick();assert.ok(f.at('model-secret'),'password field missing');
  f.api.modelStatus=async()=>({status:'saved'});f.state({mode:'model-settings'});await tick();
  f.at('model-secret').value='synthetic-unsubmitted';await f.at('model-remove').listeners.click();
  assert.equal(f.at('model-secret').value,'');assert.match(f.at('model-status').textContent,/未配置|已移除/);
  f.at('model-secret').value='synthetic-unsubmitted';await f.at('resume').listeners.click();
  assert.equal(f.at('model-secret').value,'');assert.deepEqual(f.calls,['remove','resume']);
});

test('unavailable settings can be checked again and reopening the same mode refreshes status',async()=>{
  const f=page();await tick();let reads=0;
  f.api.modelStatus=async()=>{reads++;return {status:'unavailable',code:'CREDENTIAL_STORAGE_UNAVAILABLE'};};
  f.state({mode:'model-settings'});await tick();assert.equal(f.at('model-save').disabled,true);
  assert.equal(f.at('model-recheck').disabled,false);
  f.api.modelStatus=async()=>{reads++;return {status:'empty'};};
  await f.at('model-recheck').listeners.click();assert.equal(f.at('model-save').disabled,false);
  f.state({mode:'model-settings'});await tick();assert.equal(reads,3);
});

test('a late old settings reply cannot erase text entered after reopening settings',async()=>{
  const f=page();await tick();f.state({mode:'model-settings'});await tick();
  const gate=deferred();f.api.modelSave=()=>gate.promise;
  f.at('model-secret').value='synthetic-old-secret';const saving=f.at('model-settings').listeners.submit({preventDefault(){}});
  f.state({mode:'setup'});f.state({mode:'model-settings'});await tick();
  f.at('model-secret').value='synthetic-new-secret';gate.resolve({status:'saved'});await saving;
  assert.equal(f.at('model-secret').value,'synthetic-new-secret');
  assert.match(f.at('model-status').textContent,/未配置/);
});
