const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {EventEmitter}=require('node:events');
async function boot({saved=true,selectionError=false,reviewError=false,leaseBusy=false,packaged=false}={}){
 const seen={main:0,setup:0,backup:0,quit:0,storeReads:0,storeWrites:0,stops:0,leases:[],hidden:0,enabled:[],routes:{},paths:{},busy:false};
 const anchor=path.resolve('synthetic-anchor'),active=path.resolve('synthetic-active'),windows=[];
 const app=new EventEmitter();Object.assign(app,{getPath:()=>anchor,setName(){},setPath:(name,value)=>{seen.paths[name]=value;},
  quit(){seen.quit++;},relaunch(){seen.relaunch=true;},whenReady:()=>Promise.resolve(),requestSingleInstanceLock:()=>true,isPackaged:packaged,getVersion:()=> '0.0.0'});
 class Window extends EventEmitter{
  constructor(){super();seen.setup++;windows.push(this);this.webContents=new EventEmitter();this.webContents.mainFrame={url:''};this.webContents.setWindowOpenHandler=()=>{};this.webContents.send=()=>{};}
  static getAllWindows(){return windows;}isDestroyed(){return false;}show(){}focus(){}hide(){seen.hidden++;}setEnabled(value){seen.enabled.push(value);}
  close(){this.emit('closed');}loadFile(file){this.webContents.mainFrame.url=require('node:url').pathToFileURL(file).href;return Promise.resolve();}
 }
 const context={process:{env:{QX_INSTALL_DATA:anchor,QX_PAYLOAD_ROOT:path.resolve('synthetic-payload')},on(){}},__dirname,
  setInterval:()=>({unref(){}}),clearInterval(){},setTimeout,clearTimeout,console};context.global=context;
 context.require=name=>{
  if(name==='electron')return {app,BrowserWindow:Window,ipcMain:{handle:(name,handler)=>{seen.routes[name]=handler;}},shell:{},safeStorage:{},dialog:{showErrorBox(){seen.errorBox=true;}}};
  if(name==='node:fs')return {mkdirSync(){}};
  if(name==='./data-location.cjs')return {resolveDataLocation:()=>{if(selectionError)throw Object.assign(Error('synthetic'),{code:'LOCATION_RECORD_INVALID'});return {anchor,data:active};}};
  if(name==='./installed-stop.cjs')return {assertRestoreReviewed(){if(reviewError)throw Object.assign(Error('synthetic'),{code:'BACKUP_RESTORE_REVIEW_REQUIRED'});},claimLauncher:async target=>{seen.leases.push(target);if(leaseBusy)throw Object.assign(Error('synthetic'),{code:'EADDRINUSE'});return {close:async()=>{seen.leaseClosed=true;}};}};
  if(name==='./model-credentials.cjs')return {createModelCredentialStore:()=>({status:async()=>{seen.storeReads++;return {status:saved?'saved':'empty'};},save:async()=>{seen.storeWrites++;return {status:'saved'};}})};
  if(name==='./setup-service.cjs')return {validateKey:async()=>({ok:true})};
  if(name==='./installed-runtime.cjs')return {inspectHost:async()=>({runtime:{url:'http://127.0.0.1:54321/'}}),stopInstalledHost:async()=>{seen.stops++;}};
  if(name==='./host-recovery.cjs')return {createEventLog:()=>()=>{},createHostMonitor:options=>{seen.monitor=options;return {connected(){},reset(){},tick(){}};}};
  if(name==='./backup-controller.cjs')return {createBackupController:options=>{seen.controller=options;return {isBusy:()=>seen.busy,isMaintenance:()=>context.qxIsMaintenance?.(),state:async()=>({})};}};
  if(name==='./backup-window.cjs')return {createBackupWindow:options=>{seen.backupOptions=options;return {show(){seen.backup++;seen.backupOpen=true;},isOpen:()=>Boolean(seen.backupOpen),pick(){},getWindow:()=>null};}};
  if(name==='./update-download.cjs')return {StrictNsisUpdater:class{},validateFeed:()=> 'synthetic'};
  if(name==='./updates.cjs')return {createInstallHandoff:options=>{seen.handoff=options;return {prepare(){},recover(){}};},createUpdateController:options=>{seen.updates=options;return {check(){}};}};
  if(name==='./update-config.json')return {};
  if(name==='./main.cjs'){
   seen.main++;const win=new Window();seen.setup--;context.qxMainReady=Promise.resolve();context.qxReloadMain=async()=>{};seen.mainWindow=win;return {};
  }
  return require(name);
 };
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'installed.cjs'),'utf8'),context);
 for(let index=0;index<5;index++)await new Promise(resolve=>setImmediate(resolve));
 return {seen,context,app,anchor,active,windows};
}
test('desktop selects the active profile while preserving the fixed anchor and separate desktop lease',async()=>{
 const f=await boot();assert.equal(f.seen.paths.userData,path.join(f.active,'.local/desktop-data'));
 assert.equal(f.context.process.env.QX_WORKBENCH_ROOT,f.active);assert.equal(f.context.process.env.QX_INSTALL_DATA,f.anchor);
 assert.deepEqual(f.seen.leases,[path.join(f.anchor,'.local','desktop-instance')]);assert.equal(f.seen.main,1);
});
test('invalid selection or unreviewed selected root opens only maintenance, never an empty host or credential setup',async()=>{
 for(const flag of ['selectionError','reviewError']){
  const f=await boot({[flag]:true});assert.equal(f.seen.backup,1);assert.equal(f.seen.main,0);assert.equal(f.seen.setup,0);assert.equal(f.seen.storeReads,0);
  assert.equal(f.context.qxIsMaintenance(),true);assert.ok(f.seen.controller.selectionError);
 }
});
test('maintenance blocks reconnect and credential writes, and hides and disables business windows',async()=>{
 const f=await boot({saved:false});const win=f.windows[0],event={sender:win.webContents,senderFrame:win.webContents.mainFrame};
 f.seen.controller.setMaintenance(true);
 assert.equal(f.seen.monitor.isPaused(),true);assert.ok(f.seen.hidden>0);assert.ok(f.seen.enabled.includes(false));
 assert.equal((await f.context.qxReconnectHost()).ok,false);assert.equal(await f.context.qxRestoreConnection(),false);
 const result=await f.seen.routes['qx:setup-save'](event,'synthetic-key-long-enough');assert.equal(result.ok,false);assert.equal(f.seen.storeWrites,0);
});
test('opening backup from setup never pauses and closing setup keeps an open maintenance window alive',async()=>{
 const f=await boot({saved:false});const win=f.windows[0],event={sender:win.webContents,senderFrame:win.webContents.mainFrame};
 await f.seen.routes['qx:setup-backup'](event);assert.equal(f.seen.backup,1);assert.equal(f.seen.stops,0);assert.equal(f.context.qxIsMaintenance(),false);
 win.close();assert.equal(f.seen.quit,0);
});
test('busy maintenance prevents app quit without poisoning later recovery, while completed relaunch is allowed',async()=>{
 const f=await boot();f.seen.busy=true;let prevented=false;
 f.app.emit('before-quit',{preventDefault(){prevented=true;}});assert.equal(prevented,true);
 f.seen.busy=false;assert.equal(f.seen.monitor.isPaused(),false);
 f.seen.busy=true;f.seen.controller.relaunch();assert.equal(f.seen.relaunch,true);assert.equal(f.seen.quit,1);
});
test('another desktop lease prevents profile startup even when the selected Electron profile differs',async()=>{
 const f=await boot({leaseBusy:true});assert.equal(f.seen.quit,1);assert.equal(f.seen.main,0);assert.equal(f.seen.setup,0);assert.equal(f.seen.storeReads,0);
});
test('installer handoff and confirmation share the maintenance and busy guard',async()=>{
 const f=await boot({packaged:true});assert.equal(f.seen.handoff.isStarting(),false);
 f.seen.controller.setMaintenance(true);assert.equal(f.seen.handoff.isStarting(),true);assert.equal(await f.seen.updates.confirmInstall(),false);
 f.seen.controller.setMaintenance(false);f.seen.busy=true;assert.equal(f.seen.handoff.isStarting(),true);assert.equal(await f.seen.updates.confirmInstall(),false);
});
