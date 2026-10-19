const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const vm=require('node:vm');
const {EventEmitter}=require('node:events');
const desktop=path.resolve(process.cwd(),'desktop');

async function fixture(t,{recovered=false}={}) {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-model-navigation-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const workspace=recovered?'recovered/00000000-0000-4000-8000-000000000001':'main';
  fs.mkdirSync(path.join(root,'workspaces',workspace),{recursive:true});
  if(recovered)fs.writeFileSync(path.join(root,'desktop-settings.json'),JSON.stringify({workspace}));
  const handlers=new Map(),states=[],backends=[];let ready,win,menu;
  const store={writes:0,async save(){this.writes++;return {status:'saved'};},async remove(){this.writes++;return {status:'empty'};},async status(){return {status:'saved'};},async withSecret(fn){await fn('synthetic-settings-secret');return {status:'saved'};},async drain(){}};
  class Backend extends EventEmitter {
    constructor(){super();this.stops=0;this.configures=0;this.disables=0;backends.push(this);}
    async start(){return {port:18000+backends.length};}
    async stop(){this.stops++;this.closing=true;}
    async configureModel(){this.configures++;return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'};}
    async disableModel(){this.disables++;return {ok:true,status:'disabled'};}
  }
  class Window {
    constructor(){win=this;this.url='';this.preventLeave=false;this.events={};this.webContents={mainFrame:{url:''},
      getURL:()=>this.url,send:(_name,state)=>states.push(state),on:(name,fn)=>this.events[name]=fn,setWindowOpenHandler(){}};}
    async loadURL(url){if(this.preventLeave)return;this.events['did-start-navigation']?.({},url,false,true);this.url=url;this.webContents.mainFrame={url};}
    isDestroyed(){return false;}isFocused(){return true;}once(){}show(){}hide(){}
  }
  const app={setName(){},getPath:()=>root,setPath(){},requestSingleInstanceLock:()=>true,on(){},quit(){},exit(){throw Error('unexpected exit');},
    whenReady:()=>({then:fn=>{ready=fn();return ready;}}),isPackaged:false};
  const electron={app,BrowserWindow:Window,safeStorage:{},Menu:{buildFromTemplate:x=>x,setApplicationMenu:x=>menu=x},
    ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},dialog:{showMessageBox:async()=>({})},
    session:{fromPartition:()=>({setPermissionRequestHandler(){},setPermissionCheckHandler(){},on(){}})}};
  const requireModule=name=>name==='electron'?electron:name==='./backend.cjs'?{Backend}:name==='./model-credentials.cjs'?{createModelCredentialStore:()=>store}
    :name.startsWith('./')?require(path.join(desktop,name)):require(name);
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'main.cjs'),'utf8'),{require:requireModule,__dirname:desktop,URL,
    process:{env:{QX_DESKTOP_DATA_PARENT:root},platform:'win32'}});
  await ready;
  return {win,states,backends,root,handlers,store,
    event:()=>({sender:win.webContents,senderFrame:win.webContents.mainFrame}),
    menu:async label=>{const item=menu[0].submenu.find(x=>x.label===label);assert.ok(item);await item.click();}};
}


const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};

test('renderer failure must retire its configured backend before a later credential replacement',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash')).ok,true);
  const original=f.backends[0],disables=original.disables;
  f.win.events['render-process-gone']();await tick();
  assert.equal(f.states.at(-1).mode,'error');
  await f.menu('主模型设置…');
  const result=await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret');
  assert.ok(original.stops>0 || original.disables>disables,
    'renderer failure orphaned live configuration; subsequent save skipped disable and stop');
  assert.equal(result.status,'saved');assert.equal(f.store.writes,1);
});

test('backend failure during navigation cannot overwrite error with model-settings',async t=>{
  const f=await fixture(t),original=f.backends[0],load=f.win.loadURL.bind(f.win);let once=true;
  f.win.loadURL=async url=>{if(once){once=false;original.emit('failed');}await load(url);};
  await f.menu('主模型设置…');await tick();
  assert.equal(f.states.at(-1).mode,'error');
  const result=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash');
  assert.equal(result.code,'ACCESS_DENIED');assert.equal(original.configures,0);
});

test('navigation epoch invalidates a delayed credential read even if frame URL and identity are unchanged',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  const gate=deferred();f.store.status=()=>gate.promise;
  const event=f.event(),pending=f.handlers.get('desktop:model-status')(event);
  await tick();
  f.win.events['did-start-navigation']({},f.win.url,false,true);
  gate.resolve({status:'saved'});
  assert.equal((await pending).code,'ACCESS_DENIED');
});

test('runtime request and credential request share a lock without a second store operation',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  const gate=deferred();f.store.status=()=>gate.promise;
  const pending=f.handlers.get('desktop:model-status')(f.event());await tick();
  assert.equal((await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash')).code,'ACCESS_DENIED');
  assert.equal((await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret')).code,'ACCESS_DENIED');
  gate.resolve({status:'saved'});assert.equal((await pending).status,'saved');
  assert.equal(f.backends[0].configures,0);assert.equal(f.store.writes,0);
});

test('disable failure stops the owned backend and prevents credential writes',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  const original=f.backends[0];original.disableModel=async()=>({ok:false,code:'BLOCKED_LIVE'});
  const result=await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret');
  assert.equal(result.status,'unavailable');assert.equal(original.stops,1);assert.equal(f.store.writes,0);
  assert.equal(f.states.at(-1).mode,'error');
});

test('late configure ACK is rejected and its old backend stopped after document navigation',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');const original=f.backends[0];
  const gate=deferred();original.configureModel=()=>gate.promise;
  const pending=f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash');await tick();
  f.win.events['did-start-navigation']({},f.win.url,false,true);
  gate.resolve({ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'});
  assert.equal((await pending).code,'ACCESS_DENIED');assert.equal(original.stops,1);
  assert.equal(f.states.at(-1).mode,'model-settings','stale result cannot navigate the new page');
});

test('corrupt replacement credential clears the previously configured backend',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash')).ok,true);
  f.store.withSecret=async()=>({status:'invalid',code:'CREDENTIAL_CORRUPT'});
  const result=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-v4-pro');
  assert.equal(result.ok,false);assert.equal(result.code,'CREDENTIAL_CORRUPT');assert.equal(result.runtime.state,'unconfigured');
  assert.equal(f.backends[0].disables,2);assert.equal(f.backends[0].configures,1);
});

test('ACK followed by backend control failure cannot display configured',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');const original=f.backends[0];
  original.control={ready:true,enabled:true,closed:false,failed:false};
  original.configureModel=async()=>{original.control.failed=true;return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'};};
  const result=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash');
  assert.equal(result.ok,false);assert.equal(result.runtime.state,'unavailable');assert.equal(original.stops,1);
});
const {createModelSession}=require(path.join(desktop,'model-session.cjs'));

test('replacing the backend while secret lookup is pending never configures either instance',async()=>{
  const gate=deferred(),events=[];
  const old={async disableModel(){events.push('old-disable');return {ok:true,status:'disabled'};},
    async configureModel(){events.push('old-configure');},async stop(){events.push('old-stop');}};
  const next={async disableModel(){events.push('new-disable');},async configureModel(){events.push('new-configure');},async stop(){events.push('new-stop');}};
  let current=old;
  const session=createModelSession({getBackend:()=>current,store:{async withSecret(fn){await gate.promise;await fn('synthetic-test-secret');return {status:'saved'};}}});
  const pending=session.configure('deepseek-flash');await tick();current=next;gate.resolve();
  const result=await pending;
  assert.equal(result.ok,false);assert.equal(result.code,'STATE_CONFLICT');assert.deepEqual(events,['old-disable']);
  assert.equal(session.status().runtime.state,'unconfigured');
});

test('replacing backend after configure dispatch stops only the old captured instance',async()=>{
  const gate=deferred(),events=[];
  const old={async disableModel(){events.push('old-disable');return {ok:true,status:'disabled'};},
    async configureModel(){events.push('old-configure');return gate.promise;},async stop(){events.push('old-stop');this.closing=true;}};
  const next={async disableModel(){events.push('new-disable');},async configureModel(){events.push('new-configure');},async stop(){events.push('new-stop');}};
  let current=old;
  const session=createModelSession({getBackend:()=>current,store:{async withSecret(fn){await fn('synthetic-test-secret');return {status:'saved'};}},onFailure:async backend=>{assert.equal(backend,old);}});
  const pending=session.configure('deepseek-flash');await tick();current=next;
  gate.resolve({ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'});
  const result=await pending;
  assert.equal(result.ok,false);assert.equal(result.code,'STATE_CONFLICT');
  assert.deepEqual(events,['old-disable','old-configure','old-stop']);assert.equal(session.status().runtime.state,'unconfigured');
});

test('arbitrary renderer configuration is rejected before secret access and after old authority is cleared',async()=>{
  const events=[],backend={async disableModel(){events.push('disable');return {ok:true,status:'disabled'};},
    async configureModel(){assert.fail('unexpected configure');},async stop(){events.push('stop');}};
  const session=createModelSession({getBackend:()=>backend,store:{async withSecret(){assert.fail('unexpected secret read');}}});
  const result=await session.configure({model:'deepseek-flash',endpoint:'https://untrusted.invalid'});
  assert.equal(result.ok,false);assert.equal(result.runtime.state,'unconfigured');assert.deepEqual(events,['disable']);
});

test('business configure rejection cannot retain the previous runtime metadata',async()=>{
  const events=[],backend={async disableModel(){events.push('disable');return {ok:true,status:'disabled'};},
    async configureModel(){events.push('configure');return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'};},async stop(){events.push('stop');}};
  const session=createModelSession({getBackend:()=>backend,store:{async withSecret(fn){await fn('synthetic-test-secret');return {status:'saved'};}}});
  assert.equal((await session.configure('deepseek-flash')).ok,true);
  backend.configureModel=async()=>{events.push('configure-rejected');return {ok:false,code:'VERSION_CONFLICT'};};
  const result=await session.configure('deepseek-v4-pro');
  assert.equal(result.ok,false);assert.equal(result.code,'VERSION_CONFLICT');assert.equal(result.runtime.state,'unconfigured');
  assert.deepEqual(events,['disable','configure','disable','configure-rejected']);
});
