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
  const handlers=new Map(),states=[],backends=[];let ready,win,menu,approvalOptions;
  const store={writes:0,async save(){this.writes++;return {status:'saved'};},
    async status(){return {status:'saved'};},async withSecret(fn){await fn('synthetic-settings-secret');return {status:'saved'};},async drain(){}};
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
  const requireModule=name=>name==='electron'?electron:name==='./backend.cjs'?{Backend}:name==='./model-approval.cjs'?{registerModelApproval:options=>{approvalOptions=options;return {wait:async()=>{}};}}:name==='./model-credentials.cjs'?{createModelCredentialStore:()=>store}
    :name==='./model-approval.cjs'?{registerModelApproval:options=>{approvalOptions=options;return require('../model-approval.cjs').registerModelApproval(options);}}
    :name.startsWith('./')?require(path.join(desktop,name)):require(name);
  vm.runInNewContext(fs.readFileSync(path.join(desktop,'main.cjs'),'utf8'),{require:requireModule,__dirname:desktop,URL,
    process:{env:{QX_DESKTOP_DATA_PARENT:root},platform:'win32'}});
  await ready;
  return {win,states,backends,root,handlers,store,approvalOptions,approvalOptions,
    event:()=>({sender:win.webContents,senderFrame:win.webContents.mainFrame}),
    menu:async label=>{const item=menu[0].submenu.find(x=>x.label===label);assert.ok(item);await item.click();}};
}


const CID='11111111-2222-4333-8444-555555555555';
const route='http://127.0.0.1:18001/assistant/'+CID;

test('actual main permits only the original ready main frame on an exact conversation route',async t=>{
  const f=await fixture(t);await f.win.loadURL(route);
  const capture=f.approvalOptions.captureContext,good=capture(f.event());
  assert.ok(good);assert.equal(good.conversation_id,CID);assert.equal(good.parent,f.win);
  assert.equal(good.backend,f.backends[0]);assert.equal(good.guard(),true);
  assert.equal(capture({sender:{},senderFrame:f.win.webContents.mainFrame}),null);
  assert.equal(capture({sender:f.win.webContents,senderFrame:{url:route}}),null);
  for(const url of ['http://127.0.0.1:18001/assistant','http://127.0.0.1:18001/assistant/'+CID+'?x=1',
    'http://127.0.0.1:18001/assistant/'+CID+'#fragment','http://127.0.0.1:18002/assistant/'+CID]) {
    await f.win.loadURL(url);assert.equal(capture(f.event()),null,url);
  }
});

test('actual main captured document expires on navigation even with the same URL and frame',async t=>{
  const f=await fixture(t);await f.win.loadURL(route);const event=f.event(),context=f.approvalOptions.captureContext(event);
  f.win.events['did-start-navigation']({},route,false,true);
  assert.equal(context.guard(),false);
});

test('actual main refuses recovered workspaces and settings pages before native reads',async t=>{
  const recovered=await fixture(t,{recovered:true});await recovered.win.loadURL(route);
  assert.equal(recovered.approvalOptions.captureContext(recovered.event()),null);
  const normal=await fixture(t);await normal.menu('主模型设置…');
  assert.equal(normal.approvalOptions.captureContext(normal.event()),null);
});

test('actual main menus cannot switch workspace or stop backend while approval owns shared busy',async t=>{
  const f=await fixture(t);await f.win.loadURL(route);const context=f.approvalOptions.captureContext(f.event());
  f.approvalOptions.setBusy(true);
  for(const label of ['主模型设置…','备份案件资料…','从备份建立核对副本…','返回原工作区','重新打开工作台'])await f.menu(label);
  assert.equal(f.win.url,route);assert.equal(context.guard(),true);assert.equal(f.backends.length,1);assert.equal(f.backends[0].stops,0);
  f.approvalOptions.setBusy(false);
});
