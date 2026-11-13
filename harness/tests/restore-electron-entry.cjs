// Native Electron acceptance entry. Run only in a copied Electron runtime with an isolated plan.
// Real source windows/preloads/IPC/controller/storage; only the directory dialog is scripted.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {app,BrowserWindow,dialog,session}=require('electron');
const planFile=process.env.QX_RESTORE_ELECTRON_PLAN;
assert.ok(planFile&&path.isAbsolute(planFile)&&/^[d-z]:[\\/]/i.test(planFile));
let plan=JSON.parse(fs.readFileSync(planFile,'utf8'));
assert.equal(plan.syntheticOnly,true);assert.ok(plan.anchor.startsWith(plan.fixture+path.sep));
assert.equal(path.resolve(process.env.QX_INSTALL_DATA),path.resolve(plan.anchor));
const record=()=>fs.writeFileSync(planFile,JSON.stringify(plan,null,2)+'\n');
plan.pids=[...(plan.pids||[]),process.pid];record();
const check=(name,details={})=>{plan.checks.push({name,...details});record();};
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
app.disableHardwareAcceleration();
// This is source acceptance, not an installer/update test. Do not schedule updater network work.
Object.defineProperty(app,'isPackaged',{get:()=>false});
global.fetch=async()=>{throw Error('Network is disabled in restore acceptance');};
const choices={'选择恢复副本':plan.reviewRoot,'选择启用副本位置':plan.activationParent};
dialog.showOpenDialog=async(_window,options)=>{assert.ok(choices[options.title],'Unexpected directory dialog');return {canceled:false,filePaths:[choices[options.title]]};};
dialog.showErrorBox=(title,content)=>{plan.status='failed';plan.failure=title+': '+content;record();app.exit(1);};
app.whenReady().then(()=>session.defaultSession.webRequest.onBeforeRequest({urls:['http://*/*','https://*/*','ws://*/*','wss://*/*']},(_request,callback)=>callback({cancel:true})));
const timeout=setTimeout(()=>{plan.status='failed';plan.failure='Native acceptance timed out';record();app.exit(1);},600000);
require('../desktop/installed.cjs');
async function windowFor(name){
 const end=Date.now()+30000;
 while(Date.now()<end){const win=BrowserWindow.getAllWindows().find(w=>!w.isDestroyed()&&w.webContents.getURL().endsWith('/'+name));
  if(win&&await win.webContents.executeJavaScript('document.readyState==="complete"').catch(()=>false))return win;
  await delay(100);
 }throw Error('Expected native window: '+name);
}
async function state(win){return win.webContents.executeJavaScript('window.qxBackup.state()');}
async function act(win,name,input={}){
 plan.operation=name;record();
 const result=await win.webContents.executeJavaScript('window.qxBackup.act('+JSON.stringify(name)+','+JSON.stringify(input)+')');
 assert.equal(result?.ok,true,name+': '+(await state(win)).error);return state(win);
}
async function run(){
 await app.whenReady();const setup=await windowFor('setup.html');
 assert.equal(await setup.webContents.executeJavaScript('document.querySelector("#api-key").value'),'');
 assert.equal(fs.existsSync(path.join(process.env.QX_WORKBENCH_ROOT,'.local/runtime.json'))&&JSON.parse(fs.readFileSync(path.join(process.env.QX_WORKBENCH_ROOT,'.local/runtime.json'))).hostPid!==null,false);
 await setup.webContents.executeJavaScript('window.setup.openBackup()');const win=await windowFor('backup.html');
 let current=await state(win);
 if(plan.phase===0){
  assert.equal(path.resolve(current.data),path.resolve(plan.anchor));assert.equal(current.engineReady,true);check('original-native-setup-and-backup-entry');
  await act(win,'pause',{confirm:true});assert.equal((await state(win)).stopped,true);
  for(const kind of ['reviewRoot','activationParent'])assert.equal((await win.webContents.executeJavaScript('window.qxBackup.choose('+JSON.stringify(kind)+')')).ok,true);
  current=await act(win,'review');assert.ok(current.review.counts.files>0);assert.ok(current.review.pending.length>0);
  const decisions=Object.fromEntries(current.review.pending.map(item=>[item.id,item.kind==='wechat'?'draft':'hold']));
  current=await act(win,'prepare',{reviewToken:current.review.reviewToken,applySettings:true,decisions});
  plan.prepared=current.prepared.destination;check('native-ipc-review-and-preparation',{pending:current.review.pending.length});
  assert.equal(JSON.parse(fs.readFileSync(path.join(plan.prepared,'.local/restore-activation.json'))).phase,'prepared');
  plan.phase=1;record();
  // Real app.relaunch must close this process and launch the next phase against the selected root.
  await win.webContents.executeJavaScript('window.qxBackup.act("activate",{confirm:true})').catch(()=>{});
 }else if(plan.phase===1){
  assert.equal(path.resolve(current.data),path.resolve(plan.prepared));assert.equal(path.resolve(current.previousData),path.resolve(plan.anchor));
  assert.equal(path.resolve(app.getPath('userData')),path.join(plan.prepared,'.local/desktop-data'));
  assert.notEqual(current.credentialStatus.status,'saved');check('actual-relaunch-uses-ready-copy-and-reauthorization');
  await act(win,'pause',{confirm:true});plan.phase=2;record();
  await win.webContents.executeJavaScript('window.qxBackup.act("rollback",{confirm:true})').catch(()=>{});
 }else if(plan.phase===2){
  assert.equal(path.resolve(current.data),path.resolve(plan.anchor));assert.ok(fs.existsSync(plan.prepared));assert.ok(fs.existsSync(plan.reviewRoot));
  check('actual-rollback-relaunch-preserves-both-copies');plan.phase=3;plan.status='passed';record();clearTimeout(timeout);app.quit();
 }else throw Error('Unexpected acceptance phase');
}
run().catch(error=>{plan.status='failed';plan.failure=error.stack;record();clearTimeout(timeout);app.exit(1);});
