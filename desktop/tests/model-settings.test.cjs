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
  assert.equal(f.states.at(-1).mode,'model-settings');assert.match(f.states.at(-1).message,/单独确认发送/);
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
    modelRemove:async()=>{calls.push('remove');return {status:'empty'};},
    modelRuntimeStatus:async()=>({ok:true,runtime:{state:'unconfigured',model:null}}),
    modelConfigure:async model=>{calls.push(['configure',model]);return {ok:true,runtime:{state:'configured',model}};},
    modelDisable:async()=>{calls.push('disable');return {ok:true,runtime:{state:'unconfigured',model:null}};}};
  const window={desktopSetup:api,addEventListener:(name,fn)=>listeners.set(name,fn)};
  const context=vm.createContext({document,window,console});
  if(fs.existsSync(path.join(desktop,'setup-model.js')))
    vm.runInContext(fs.readFileSync(path.join(desktop,'setup-model.js'),'utf8'),context);
  vm.runInContext(fs.readFileSync(path.join(desktop,'setup.js'),'utf8'),context);
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
  assert.match(f.html,/保存密钥不会配置/);assert.match(f.html,/不授权|不会授权/);assert.match(f.html,/不会产生调用费用/);
});

test('automatic analysis defaults on, discloses unlimited cost and preserves explicit off on model changes',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();
  const automatic=f.at('model-automatic-analysis');assert.ok(automatic);
  assert.equal(Boolean(automatic.checked),true);
  assert.match(f.html,/api\.deepseek\.com/);assert.match(f.html,/当前聊天.*选定材料/);
  assert.match(f.at('model-automatic-limit').textContent,/不设费用上限/);
  assert.match(f.at('model-automatic-limit').textContent,/每次分析最多调用 1 次/);
  f.api.modelConfigure=async(model,automatic)=>{f.calls.push([model,automatic]);
    return {ok:true,runtime:{state:'configured',model,automatic_analysis:automatic}};};
  automatic.checked=true;automatic.listeners.change();await f.at('model-configure').listeners.click();
  assert.deepEqual(f.calls,[['deepseek-flash',true]]);
  assert.match(f.at('model-runtime-status').textContent,/自动分析/);
  automatic.checked=false;automatic.listeners.change();
  assert.equal(f.at('model-configure').disabled,false);
  await f.at('model-configure').listeners.click();
  assert.deepEqual(f.calls.at(-1),['deepseek-flash',false]);
  assert.match(f.at('model-runtime-status').textContent,/可手动发送.*自动分析关闭/);
  f.at('model-id').value='deepseek-v4-pro';f.at('model-id').listeners.change();
  assert.equal(automatic.checked,false);
  assert.match(f.at('model-automatic-limit').textContent,/不设费用上限/);
});

test('explicit off survives credential replacement and reopening an unconfigured settings page',async()=>{
  const f=page();let runtime={state:'configured',model:'deepseek-flash',automatic_analysis:false};
  await tick();
  f.api.modelStatus=async()=>({status:'saved'});
  f.api.modelRuntimeStatus=async()=>({ok:true,runtime});
  f.api.modelSave=async()=>{runtime={state:'unconfigured',model:null,automatic_analysis:false};return {status:'saved'};};
  f.api.modelConfigure=async(model,automatic)=>{f.calls.push(['configure',model,automatic]);
    return {ok:true,runtime:{state:'configured',model,automatic_analysis:automatic}};};
  f.state({mode:'model-settings'});await tick();
  assert.equal(f.at('model-automatic-analysis').checked,false);
  f.at('model-secret').value='synthetic-replacement-secret';
  await f.at('model-settings').listeners.submit({preventDefault(){}});
  f.state({mode:'ready'});f.state({mode:'model-settings'});await tick();
  assert.equal(f.at('model-automatic-analysis').checked,false);
  await f.at('model-configure').listeners.click();
  assert.deepEqual(f.calls.at(-1),['configure','deepseek-flash',false]);
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
  assert.equal(f.at('model-secret').value,'');assert.match(f.at('model-status').textContent,/未保存|已移除/);
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
  assert.match(f.at('model-status').textContent,/未保存/);
});

test('model page checks storage before runtime and distinguishes stored credentials from configuration',async()=>{
  const f=page();await tick();const gate=deferred(),reads=[];
  f.api.modelStatus=async()=>{reads.push('credential');await gate.promise;return {status:'saved'};};
  f.api.modelRuntimeStatus=async()=>{reads.push('runtime');return {ok:true,runtime:{state:'unconfigured',model:null}};};
  f.state({mode:'model-settings'});await tick();assert.deepEqual(reads,['credential']);
  gate.resolve();await tick();assert.deepEqual(reads,['credential','runtime']);
  assert.match(f.at('model-status').textContent,/已保存/);
  assert.match(f.at('model-runtime-status').textContent,/本次运行.*未配置/);
  assert.equal(f.at('model-configure').disabled,false);
  assert.equal(f.at('model-disable').disabled,true);
  assert.deepEqual(f.calls,[],'reading or saving credentials cannot configure automatically');
});

test('model page configures only a fixed selected ID, serializes actions and can switch or disable',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();
  const gate=deferred();f.api.modelConfigure=async model=>{f.calls.push(['configure',model]);await gate.promise;
    return {ok:true,runtime:{state:'configured',model}};};
  f.at('model-secret').value='synthetic-unsubmitted';
  const configuring=f.at('model-configure').listeners.click();
  assert.equal(f.at('model-secret').value,'');assert.equal(f.at('model-configure').disabled,true);
  await f.at('model-configure').listeners.click();await f.at('model-disable').listeners.click();
  await f.at('model-recheck').listeners.click();await f.at('resume').listeners.click();
  assert.deepEqual(f.calls,[['configure','deepseek-flash']]);
  gate.resolve();await configuring;
  assert.match(f.at('model-runtime-status').textContent,/本次运行已配置.*可手动发送.*自动分析关闭/);
  assert.equal(f.at('model-configure').disabled,true,'same model needs no repeated configuration');
  f.at('model-id').value='deepseek-v4-pro';f.at('model-id').listeners.change();
  assert.equal(f.at('model-configure').disabled,false);
  await f.at('model-configure').listeners.click();assert.match(f.at('model-runtime-status').textContent,/V4 Pro/);
  await f.at('model-disable').listeners.click();assert.match(f.at('model-runtime-status').textContent,/本次运行未配置/);
  assert.match(f.at('model-status').textContent,/已保存/);
  f.at('model-id').value='unexpected-model';f.at('model-id').listeners.change();
  assert.equal(f.at('model-configure').disabled,true);await f.at('model-configure').listeners.click();
  assert.deepEqual(f.calls,[['configure','deepseek-flash'],['configure','deepseek-v4-pro'],'disable']);
});

test('model page hides stale runtime configuration while replacing credentials and reads back serially',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.api.modelRuntimeStatus=async()=>({ok:true,runtime:{state:'configured',model:'deepseek-flash'}});
  f.state({mode:'model-settings'});await tick();
  const saving=deferred(),reading=deferred(),order=[];
  f.api.modelSave=async()=>{order.push('save');await saving.promise;return {status:'saved'};};
  f.api.modelRuntimeStatus=async()=>{order.push('runtime');await reading.promise;return {ok:true,runtime:{state:'unconfigured',model:null}};};
  f.at('model-secret').value='synthetic-replacement';
  const pending=f.at('model-settings').listeners.submit({preventDefault(){}});
  assert.deepEqual(order,['save']);assert.doesNotMatch(f.at('model-runtime-status').textContent,/已配置/);
  saving.resolve();await tick();assert.deepEqual(order,['save','runtime']);
  assert.equal(f.at('resume').disabled,true);assert.doesNotMatch(f.at('model-runtime-status').textContent,/已配置/);
  reading.resolve();await pending;
  assert.match(f.at('model-status').textContent,/已保存/);assert.match(f.at('model-runtime-status').textContent,/未配置/);
  assert.equal(f.at('model-configure').disabled,false);
});

test('model page runtime failure is separate from stored credentials and a recheck can recover',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();
  f.api.modelConfigure=async()=>{throw Error('synthetic-private-key');};
  await f.at('model-configure').listeners.click();
  assert.match(f.at('model-status').textContent,/已保存/);
  assert.equal(f.at('model-runtime-validation').hidden,false);
  assert.doesNotMatch(f.at('model-runtime-validation').textContent,/synthetic/);
  assert.equal(f.at('model-configure').disabled,true);
  await f.at('model-recheck').listeners.click();
  assert.equal(f.at('model-runtime-validation').hidden,true);assert.equal(f.at('model-configure').disabled,false);
});

test('model page discards delayed configuration after leaving without clearing the new page input',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.state({mode:'model-settings'});await tick();const gate=deferred();f.api.modelConfigure=()=>gate.promise;
  const configuring=f.at('model-configure').listeners.click();
  f.state({mode:'setup'});f.state({mode:'model-settings'});await tick();
  f.at('model-secret').value='synthetic-new-secret';
  gate.resolve({ok:true,runtime:{state:'configured',model:'deepseek-v4-pro'}});await configuring;
  assert.equal(f.at('model-secret').value,'synthetic-new-secret');
  assert.match(f.at('model-runtime-status').textContent,/未配置/);
  f.listeners.get('pagehide')();assert.equal(f.at('model-secret').value,'');
  await f.at('model-configure').listeners.click();assert.deepEqual(f.calls,[]);
});

test('model page allows credential maintenance when runtime is unavailable and restart stays unconfigured',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.api.modelRuntimeStatus=async()=>({ok:true,runtime:{state:'unavailable',model:null}});
  f.state({mode:'model-settings'});await tick();
  assert.equal(f.at('model-save').disabled,false);assert.equal(f.at('model-remove').disabled,false);
  assert.equal(f.at('model-configure').disabled,true);assert.equal(f.at('model-disable').disabled,true);
  await f.at('model-configure').listeners.click();assert.deepEqual(f.calls,[]);
  f.state({mode:'error'});f.api.modelRuntimeStatus=async()=>({ok:true,runtime:{state:'unconfigured',model:null}});
  f.state({mode:'model-settings'});await tick();
  assert.match(f.at('model-status').textContent,/已保存/);assert.match(f.at('model-runtime-status').textContent,/本次运行未配置/);
  assert.equal(f.at('model-configure').disabled,false);assert.deepEqual(f.calls,[]);
});

test('model page rejects unknown model projection and never renders raw runtime errors',async()=>{
  const f=page();await tick();f.api.modelStatus=async()=>({status:'saved'});
  f.api.modelRuntimeStatus=async()=>({ok:true,runtime:{state:'configured',model:'synthetic-private-value'}});
  f.state({mode:'model-settings'});await tick();
  assert.doesNotMatch(f.at('model-runtime-status').textContent,/synthetic|已配置/);
  assert.equal(f.at('model-configure').disabled,true);
  f.api.modelRuntimeStatus=async()=>({ok:false,runtime:{state:'unavailable',model:null},code:'synthetic-private-key'});
  await f.at('model-recheck').listeners.click();assert.equal(f.at('model-runtime-validation').hidden,false);
  assert.doesNotMatch(f.at('model-runtime-validation').textContent,/synthetic/);
});
