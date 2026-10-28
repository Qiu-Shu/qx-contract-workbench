const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const vm=require('node:vm');
const {EventEmitter}=require('node:events');
const desktop=path.resolve(__dirname,'..');

async function fixture(t,{recovered=false,model,automatic=false,policyChange}={}) {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'qx-model-navigation-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const workspace=recovered?'recovered/00000000-0000-4000-8000-000000000001':'main';
  fs.mkdirSync(path.join(root,'workspaces',workspace),{recursive:true});
  const initial={...(recovered?{workspace}:{}),...(model?{model}:{})};
  if(automatic)initial.model_auto_analysis={model,workspace:path.join(root,'workspaces',workspace),
    scope:'selected-task-materials',max_calls:1,max_total_usd:'0.024576'};
  if(policyChange)Object.assign(initial.model_auto_analysis,policyChange);
  if(Object.keys(initial).length)fs.writeFileSync(path.join(root,'desktop-settings.json'),JSON.stringify(initial));
  const handlers=new Map(),states=[],backends=[];let ready,win,menu,approvalOptions;
  const store={writes:0,async save(){this.writes++;return {status:'saved'};},
    async status(){return {status:'saved'};},async withSecret(fn){await fn('synthetic-settings-secret');return {status:'saved'};},async drain(){}};
  class Backend extends EventEmitter {
    constructor(){super();this.stops=0;this.configures=0;this.disables=0;this.judgeConfigures=0;this.judgeDisables=0;this.control={ready:true,enabled:true,judgeEnabled:true};backends.push(this);}
    async start(params){this.startParams=params;return {port:18000+backends.length};}
    async stop(){this.stops++;this.closing=true;}
    async configureModel(){this.configures++;return {ok:true,status:'configured',config_sha256:'a'.repeat(64),config_version:'00000000-0000-4000-8000-000000000002'};}
    async disableModel(){this.disables++;return {ok:true,status:'disabled'};}
    async configureJudge(){this.judgeConfigures++;return {ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:'00000000-0000-4000-8000-000000000003'};}
    async disableJudge(){this.judgeDisables++;return {ok:true,status:'disabled'};}
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
    :name==='./model-approval.cjs'?{registerModelApproval:options=>{approvalOptions=options;return require('../model-approval.cjs').registerModelApproval(options);}}
    :name.startsWith('./')?require(path.join(desktop,name)):require(name);
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'main.cjs'),'utf8'),{require:requireModule,__dirname:desktop,URL,
    process:{env:{QX_DESKTOP_DATA_PARENT:root},platform:'win32'}});
  await ready;
  return {win,states,backends,root,handlers,store,approvalOptions,
    event:()=>({sender:win.webContents,senderFrame:win.webContents.mainFrame}),
    menu:async label=>{const item=menu[0].submenu.find(x=>x.label===label);assert.ok(item);await item.click();}};
}

test('native model settings preserve the running backend and return to the prior trusted conversation',async t=>{
  const f=await fixture(t),original=f.backends[0];
  const url='http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003';
  await f.win.loadURL(url);await f.menu('主模型设置…');
  assert.equal(original.stops,0,'opening model settings must preserve the live configuration channel');
  assert.equal(f.states.at(-1).mode,'model-settings');
  const configured=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash');
  assert.equal(configured.ok,true);assert.equal(configured.runtime.state,'configured');
  assert.equal((await f.handlers.get('desktop:resume')(f.event())).ok,true);
  assert.equal(f.win.url,url);assert.equal(f.backends.length,1);assert.equal(original.stops,0);
  await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.state,'configured');
});

test('explicit automatic scope persists and restores only for the selected native workspace',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  const result=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash',true);
  assert.equal(result.runtime.automatic_analysis,true);
  const saved=JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8'));
  assert.deepEqual(saved.model_auto_analysis,{model:'deepseek-flash',workspace:path.join(f.root,'workspaces','main'),
    scope:'selected-task-materials',max_calls:1,max_total_usd:'0.024576'});
  await f.menu('重新打开工作台');await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.automatic_analysis,true);
  assert.equal(Object.hasOwn(f.backends.at(-1).startParams,'model_auto_analysis'),false);
});

test('credential changes and disable remove persisted automatic consent before restarting',async t=>{
  for(const action of ['save','disable']){
    const f=await fixture(t,{model:'deepseek-flash',automatic:true});await f.menu('主模型设置…');
    assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.automatic_analysis,true);
    await f.handlers.get('desktop:model-'+action)(f.event(),'synthetic-replacement-secret');
    const saved=JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8'));
    assert.equal(Object.hasOwn(saved,'model_auto_analysis'),false);
    await f.menu('重新打开工作台');await f.menu('主模型设置…');
    assert.notEqual((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.automatic_analysis,true);
  }
});

test('startup rejects altered automatic scope without losing the saved model choice',async t=>{
  for(const policyChange of [{scope:'all-history'},{max_calls:2},{max_total_usd:'100'},
    {workspace:'another-workspace'},{model:'deepseek-v4-pro'}]){
    const f=await fixture(t,{model:'deepseek-flash',automatic:true,policyChange});
    await f.menu('主模型设置…');
    const result=await f.handlers.get('desktop:model-runtime-status')(f.event());
    assert.equal(result.runtime.state,'configured');assert.notEqual(result.runtime.automatic_analysis,true);
  }
});

test('assistant model switch discards automatic scope and credential write stops on settings failure',async t=>{
  const f=await fixture(t,{model:'deepseek-flash',automatic:true});
  await f.win.loadURL('http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003');
  const switched=await f.handlers.get('desktop:assistant-model-switch')(f.event());
  assert.equal(switched.runtime.model,'deepseek-v4-pro');assert.notEqual(switched.runtime.automatic_analysis,true);
  assert.equal(Object.hasOwn(JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8')),'model_auto_analysis'),false);
  await f.menu('主模型设置…');
  fs.mkdirSync(path.join(f.root,'desktop-settings.json.tmp'));
  const failed=await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret');
  assert.equal(failed.status,'unavailable');assert.equal(f.store.writes,0);
  assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.state,'unconfigured');
});

test('unsaved page rejection keeps its backend and does not enter settings',async t=>{
  const f=await fixture(t),before=f.win.url;f.win.preventLeave=true;
  await f.menu('主模型设置…');
  assert.equal(f.win.url,before);assert.equal(f.states.at(-1).mode,'ready');assert.equal(f.backends[0].stops,0);
});

test('backup still stops the owned backend and returning restores the persisted model choice',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash')).ok,true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8')).model,'deepseek-flash');
  await f.menu('备份案件资料…');assert.equal(f.backends[0].stops,1);assert.equal(f.states.at(-1).mode,'backup');
  assert.equal((await f.handlers.get('desktop:resume')(f.event())).ok,true);assert.equal(f.backends.length,2);
  assert.equal(f.backends[1].configures,1,'the persisted choice is restored without reopening settings');
  await f.menu('主模型设置…');
  const status=await f.handlers.get('desktop:model-runtime-status')(f.event());
  assert.equal(status.runtime.state,'configured');assert.equal(status.runtime.model,'deepseek-flash');
});

test('restored read-only workspace can inspect credentials but cannot configure a model',async t=>{
  const f=await fixture(t,{recovered:true});await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-status')(f.event())).status,'saved');
  const result=await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash');
  assert.equal(result.ok,false);assert.equal(result.runtime.state,'unavailable');assert.equal(f.backends[0].configures,0);
});

test('new runtime IPC rejects ordinary HTTP pages and subframes',async t=>{
  const f=await fixture(t);
  for(const name of ['desktop:model-runtime-status','desktop:model-configure','desktop:model-disable']) {
    assert.equal((await f.handlers.get(name)(f.event(),'deepseek-flash')).code,'ACCESS_DENIED');
  }
  await f.menu('主模型设置…');
  const subframe={sender:f.win.webContents,senderFrame:{url:f.win.url}};
  assert.equal((await f.handlers.get('desktop:model-configure')(subframe,'deepseek-flash')).code,'ACCESS_DENIED');
  assert.equal(f.backends[0].configures,0);
});

test('resuming never loads an untrusted previous URL',async t=>{
  const f=await fixture(t);await f.win.loadURL('https://untrusted.invalid/');await f.menu('主模型设置…');
  await f.handlers.get('desktop:resume')(f.event());
  assert.equal(f.win.url,'http://127.0.0.1:18001/login');assert.equal(f.backends.length,1);
});

test('a failure from an old backend cannot replace the current page',async t=>{
  const f=await fixture(t),old=f.backends[0];await f.menu('重新打开工作台');
  const current=f.win.url;old.emit('failed');await new Promise(resolve=>setImmediate(resolve));
  assert.equal(f.win.url,current);assert.equal(f.states.at(-1).mode,'ready');
});

test('renderer failure blocks credential replacement until the configured backend has stopped',async t=>{
  const f=await fixture(t);await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-configure')(f.event(),'deepseek-flash')).ok,true);
  const original=f.backends[0];let release,stopped=false;
  const stopGate=new Promise(resolve=>{release=resolve;});
  original.stop=function(){this.stops++;this.closing=true;
    return this.stopping=stopGate.then(()=>{stopped=true;});};
  f.win.events['render-process-gone']();
  assert.equal(original.stops,1);
  assert.equal((await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret')).code,'ACCESS_DENIED');
  assert.equal(f.store.writes,0);
  release();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(stopped,true);assert.equal(f.states.at(-1).mode,'error');
  await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-save')(f.event(),'synthetic-replacement-secret')).status,'saved');
  assert.equal(f.store.writes,1);
  assert.equal((await f.handlers.get('desktop:resume')(f.event())).ok,true);
  assert.equal(f.backends.length,2);
  assert.equal(f.backends[1].configures,1,'the persisted choice is restored after a renderer failure');
  await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.state,'configured');
});

test('send confirmation context uses only the displayed conversation and owned main frame',async t=>{
  const f=await fixture(t),capture=f.approvalOptions.captureContext;
  assert.equal(capture(f.event()),null,'login is not a confirmation origin');
  const id='00000000-0000-4000-8000-000000000003';
  const url='http://127.0.0.1:18001/assistant/'+id;
  await f.win.loadURL(url);
  const context=capture(f.event());assert.equal(context.conversation_id,id);
  assert.equal(context.backend,f.backends[0]);assert.equal(context.guard(),true);
  assert.equal(capture({sender:{},senderFrame:f.win.webContents.mainFrame}),null);
  assert.equal(capture({sender:f.win.webContents,senderFrame:{url}}),null);
  await f.win.loadURL(url+'?other=1');assert.equal(capture(f.event()),null);assert.equal(context.guard(),false);
  await f.win.loadURL(url);assert.equal(context.guard(),false,'returning to an old URL cannot revive the document guard');
  const beforeReload=capture(f.event());await f.win.loadURL(url);assert.equal(beforeReload.guard(),false);
  const beforeSettings=capture(f.event());await f.menu('主模型设置…');assert.equal(beforeSettings.guard(),false);
  assert.equal(capture(f.event()),null);
});

test('restored workspaces and replaced backends cannot approve a send',async t=>{
  const f=await fixture(t,{recovered:true});
  await f.win.loadURL('http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003');
  assert.equal(f.approvalOptions.captureContext(f.event()),null);
  const g=await fixture(t);await g.win.loadURL('http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003');
  const context=g.approvalOptions.captureContext(g.event());
  await g.menu('重新打开工作台');assert.equal(context.guard(),false);
  assert.notEqual(g.backends.at(-1),context.backend);
});


test('startup restores a persisted model choice and disable clears it for the next start',async t=>{
  const f=await fixture(t,{model:'deepseek-v4-pro'});
  assert.equal(f.backends[0].configures,1,'startup configures without opening settings');
  assert.equal('model' in f.backends[0].startParams,false,'backend.start must not receive the desktop-only model key');
  await f.menu('主模型设置…');
  const status=await f.handlers.get('desktop:model-runtime-status')(f.event());
  assert.equal(status.runtime.state,'configured');assert.equal(status.runtime.model,'deepseek-v4-pro');
  assert.equal((await f.handlers.get('desktop:model-disable')(f.event())).ok,true);
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8')).model,undefined);
  await f.menu('重新打开工作台');
  assert.equal(f.backends.length,2);assert.equal(f.backends[1].configures,0,'a cleared choice never auto-configures');
  await f.menu('主模型设置…');
  assert.equal((await f.handlers.get('desktop:model-runtime-status')(f.event())).runtime.state,'unconfigured');
});

test('assistant page reads and switches the configured model while other pages are refused',async t=>{
  const f=await fixture(t,{model:'deepseek-flash'});
  const url='http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003';
  await f.win.loadURL(url);
  assert.deepEqual(await f.handlers.get('desktop:assistant-model-status')(f.event()),
    {ok:true,runtime:{state:'configured',model:'deepseek-flash'}});
  const switched=await f.handlers.get('desktop:assistant-model-switch')(f.event());
  assert.equal(switched.ok,true);assert.equal(switched.runtime.model,'deepseek-v4-pro');
  assert.equal(JSON.parse(fs.readFileSync(path.join(f.root,'desktop-settings.json'),'utf8')).model,'deepseek-v4-pro');
  const back=await f.handlers.get('desktop:assistant-model-switch')(f.event());
  assert.equal(back.runtime.model,'deepseek-flash');
  await f.win.loadURL('http://127.0.0.1:18001/login');
  assert.equal((await f.handlers.get('desktop:assistant-model-status')(f.event())).ok,false,'login page');
  await f.win.loadURL(url);
  const subframe={sender:f.win.webContents,senderFrame:{url}};
  assert.equal((await f.handlers.get('desktop:assistant-model-switch')(subframe)).ok,false,'subframe');
  const g=await fixture(t,{recovered:true});
  await g.win.loadURL('http://127.0.0.1:18001/assistant/00000000-0000-4000-8000-000000000003');
  assert.equal((await g.handlers.get('desktop:assistant-model-status')(g.event())).ok,false,'recovered workspace');
});

test('judge menu shares trusted lifecycle while main and judge operations remain separate',async t=>{
  const f=await fixture(t);await f.menu('Jev 辅助设置…');
  const call=(name,...args)=>f.handlers.get('desktop:'+name)(f.event(),...args);
  assert.equal((await call('model-configure','deepseek-flash')).ok,true);
  assert.equal((await call('judge-configure','jev-1.13.0')).ok,true);
  assert.equal((await call('judge-disable')).ok,true);
  assert.equal((await call('model-runtime-status')).runtime.state,'configured');
  assert.equal((await call('judge-runtime-status')).runtime.state,'unconfigured');
  assert.equal((await call('judge-configure','jev-1.13.0')).ok,true);
  assert.equal((await call('model-disable')).ok,true);
  assert.equal((await call('judge-runtime-status')).runtime.state,'configured');
  assert.equal(f.backends[0].stops,0);
  await call('resume');
  assert.equal((await call('judge-disable')).code,'ACCESS_DENIED');
});
test('judge config is unavailable in a restored read-only workspace',async t=>{
  const f=await fixture(t,{recovered:true});await f.menu('Jev 辅助设置…');
  const result=await f.handlers.get('desktop:judge-configure')(f.event(),'jev-1.13.0');
  assert.equal(result.ok,false);assert.equal(f.backends[0].judgeConfigures,0);
});
test('shared native settings busy lock prevents main credential writes during judge configuration',async t=>{
  const f=await fixture(t);await f.menu('Jev 辅助设置…');
  let finish;f.backends[0].configureJudge=()=>new Promise(resolve=>{finish=resolve;});
  const pending=f.handlers.get('desktop:judge-configure')(f.event(),'jev-1.13.0');
  for(let n=0;!finish&&n<10;n++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof finish,'function');
  assert.equal((await f.handlers.get('desktop:model-save')(f.event(),'synthetic-unused-secret')).code,'ACCESS_DENIED');
  assert.equal(f.store.writes,0);
  finish({ok:true,status:'configured',config_sha256:'b'.repeat(64),config_version:'00000000-0000-4000-8000-000000000003'});
  assert.equal((await pending).ok,true);
});
