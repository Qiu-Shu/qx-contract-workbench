const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
async function boot({saved=true,healthy=false}={}){
  const seen={setup:0,main:0,dialogs:0,secretWrites:0};
  const runtime={readRuntime:async()=>healthy?{url:'http://127.0.0.1:54321/'}:null,readControl:()=>null,
    inspectHost:async()=>{if(healthy)return {runtime:{url:'http://127.0.0.1:54321/'}};throw Error('Synthetic startup failure')},readHostState:()=>null};
  const app={getPath:()=>path.resolve('.local/startup-unit'),setName(){},setPath(){},on(){},once(){},quit(){},
    whenReady:()=>Promise.resolve(),requestSingleInstanceLock:()=>true,isPackaged:false};
  class Window{constructor(){seen.setup++}webContents={setWindowOpenHandler(){},on(){}};on(){}loadFile(){}static getAllWindows(){return []}}
  const context={process:{env:{QX_PAYLOAD_ROOT:path.resolve('.local/payload')},on(){}},__dirname:__dirname,
    setInterval:()=>({unref(){}}),clearInterval(){},console};context.global=context;
  context.require=name=>{
    if(name==='electron')return {app,BrowserWindow:Window,ipcMain:{handle(){}},shell:{},safeStorage:{},dialog:{showErrorBox(){seen.dialogs++}}};
    if(name==='node:fs')return {mkdirSync(){}};
    if(name==='./data-location.cjs')return {resolveDataLocation:anchor=>({anchor,data:anchor})};
    if(name==='./installed-stop.cjs')return {assertRestoreReviewed(){},claimLauncher:async()=>({close:async()=>{}})};
    if(name==='./backup-controller.cjs')return {createBackupController:()=>({isBusy:()=>false})};
    if(name==='./backup-window.cjs')return {createBackupWindow:()=>({show(){},isOpen:()=>false,getWindow:()=>null})};
    if(name==='./model-credentials.cjs')return {createModelCredentialStore:()=>({status:async()=>({status:saved?'saved':'missing'}),save(){seen.secretWrites++}})};
    if(name==='./setup-service.cjs')return {};
    if(name==='./installed-runtime.cjs')return runtime;
    if(name==='./host-recovery.cjs')return {createEventLog:()=>()=>{},createHostMonitor:()=>({connected(){},reset(){},tick(){}})};
    if(name==='./main.cjs'){seen.main++;seen.unavailable=context.qxStartUnavailable===true;context.qxMainReady=Promise.resolve();context.qxReloadMain=async()=>{seen.unavailable=false};return {}};
    return require(name);
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'installed.cjs'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));return seen;
}
test('saved credentials and failed backend open the recovery window, never API setup or a blocking error dialog',async()=>{
  assert.deepEqual(await boot(),{setup:0,main:1,dialogs:0,secretWrites:0,unavailable:true});
});
test('saved credentials and a healthy backend enter directly',async()=>{
  assert.deepEqual(await boot({healthy:true}),{setup:0,main:1,dialogs:0,secretWrites:0,unavailable:false});
});
test('a genuinely fresh installation still opens API setup',async()=>{
  assert.deepEqual(await boot({saved:false}),{setup:1,main:0,dialogs:0,secretWrites:0});
});
