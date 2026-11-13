const {app,BrowserWindow,ipcMain,shell,safeStorage,dialog}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {createModelCredentialStore}=require('./model-credentials.cjs');
const {assertRestoreReviewed,claimLauncher}=require('./installed-stop.cjs');
const {resolveDataLocation}=require('./data-location.cjs');
const {createBackupController}=require('./backup-controller.cjs');
const {createBackupWindow}=require('./backup-window.cjs');
const {validateKey}=require('./setup-service.cjs');
const {readHostState,inspectHost,stopInstalledHost,restartRuntime}=require('./installed-runtime.cjs');
const {createHostMonitor,createEventLog,hostStartupPending}=require('./host-recovery.cjs');

const payload=process.env.QX_PAYLOAD_ROOT||path.join(process.resourcesPath,'workbench');
const anchor=process.env.QX_INSTALL_DATA||path.join(app.getPath('appData'),'QunxingHarness');
let data=anchor,selectionError=null;
try{const selection=resolveDataLocation(anchor);assertRestoreReviewed(selection.data);data=selection.data;}
catch(error){selectionError=error.code||'LOCATION_RECORD_INVALID';}
fs.mkdirSync(path.join(data,'.local'),{recursive:true});
app.setName('AI师兄法律助手平台');
// Encryption uses Electron's profile key; UI and background must share this path.
app.setPath('userData',path.join(data,'.local','desktop-data'));
process.env.QX_WORKBENCH_ROOT=data;
process.env.QX_INSTALL_DATA=anchor;
process.env.QX_DESKTOP_DATA=path.join(data,'.local','desktop-data');
const store=createModelCredentialStore({dataParent:path.join(data,'.local','desktop-data'),safeStorage});
let setupWindow,starting=false,mainLoaded=false,quitting=false,connection,desktopLease,backupController,backupWindow;
let maintenance=Boolean(selectionError),relaunching=false,replacingSetup=false;
global.qxIsMaintenance=()=>maintenance;
const log=createEventLog(data,'desktop');
const desktopStartedAt=Date.now();
function startupState(phase,errorCode){
  global.qxStartupState={phase,startedAt:global.qxStartupState?.startedAt||Date.now(),
    errorCode:typeof errorCode==='string'&&/^[A-Z0-9_]{1,64}$/.test(errorCode)?errorCode:undefined};
  log('startup_phase',{phase,elapsedMs:Date.now()-desktopStartedAt,errorCode});
  for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:startup-state',global.qxStartupState);
}
global.qxDesktopLog=log;
log('desktop_start');
app.on('before-quit',event=>{
  if(backupController?.isBusy()&&!relaunching){event.preventDefault();backupWindow?.show();return;}
  quitting=true;log('desktop_quit',{intentional:true});
});
app.on('will-quit',()=>{void desktopLease?.close();});
process.on('exit',code=>log('desktop_exit',{code}));
process.on('uncaughtExceptionMonitor',error=>log('desktop_exception',{errorName:error.name,errorCode:error.code}));

async function ensureHost(manual=false){
  if(maintenance||selectionError)throw Object.assign(Error('Maintenance active'),{code:'BACKUP_MAINTENANCE_REQUIRED'});
  let failed=false,spawned=false,retried=false;
  const deadline=Date.now()+120000;
  while(!quitting){
    const host=await inspectHost(data);
    if(maintenance||selectionError)throw Object.assign(Error('Maintenance active'),{code:'BACKUP_MAINTENANCE_REQUIRED'});
    if(host.runtime){process.env.QX_HARNESS_URL=host.runtime.url;return host.runtime;}
    if(Date.now()>=deadline&&!hostStartupPending(host))break;
    if(host.control&&host.state?.phase==='failed'){
      if(!manual)throw Error('后台连续启动失败，请点击重试恢复。');
      if(retried)break;
      await restartRuntime(host.control);retried=true;
    }else if(!host.control&&!host.launcherAlive){
      if(host.hostAlive)throw Error('后台仍在运行但暂时无法连接，请稍后重试，避免打断正在处理的任务。');
      if(failed)break;
      if(!spawned){
        startupState('starting');spawned=true;
        const result=await store.withSecret(secret=>{
          if(maintenance||selectionError)throw Object.assign(Error('Maintenance active'),{code:'BACKUP_MAINTENANCE_REQUIRED'});
          const child=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'desktop-runner/installed-host.cjs')],{
            detached:true,stdio:'ignore',windowsHide:true,
            env:{...process.env,QX_PAYLOAD_ROOT:payload,QX_INSTALL_DATA:data,DEEPSEEK_API_KEY:secret}});
          child.unref();child.once('error',error=>{failed=true;log('launcher_spawn_error',{errorName:error.name,errorCode:error.code})});
          child.once('exit',(code,signal)=>{failed=true;log('launcher_observed_exit',{code,signal})});
        });
        if(result.status!=='saved')throw Error('Windows 暂时无法读取加密配置，请重新填写 API Key。');
      }
    }
    startupState('connecting');
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  const error=Error('本机服务未能启动，请查看资料目录中的 .local/host.log 后重试。');
  error.code=failed?'HOST_EXITED':readHostState(data)?.phase==='running'?'SERVICE_UNAVAILABLE':'STARTUP_TIMEOUT';throw error;
}
async function restoreConnection(){
  if(starting||quitting||maintenance||selectionError)return false;starting=true;
  try{
    for(let attempt=0;attempt<3&&!quitting;attempt++){
      if(attempt)await new Promise(resolve=>setTimeout(resolve,attempt*1000));
      const runtime=await ensureHost();
      if(await global.qxTryReconnectInPlace?.(runtime)){
        connection.connected(runtime);log('connection_restored_in_place');return true;
      }
    }
  }catch(error){log('connection_restore_error',{errorName:error.name,errorCode:error.code});}
  finally{starting=false;}
  for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:connection-state',{phase:'auto-reconnect-failed'});
  log('connection_restore_failed');return false;
}
global.qxRestoreConnection=restoreConnection;
async function showMain(){
  if(!mainLoaded){mainLoaded=true;require('./main.cjs');await global.qxMainReady;}
  else await global.qxReloadMain();
}
async function enter(){
  if(maintenance||selectionError)throw Object.assign(Error('Maintenance active'),{code:'BACKUP_MAINTENANCE_REQUIRED'});
  global.qxStartupState=null;startupState('checking');
  global.qxStartUnavailable=true;
  await showMain();
  if(setupWindow&&!setupWindow.isDestroyed()){
    replacingSetup=true;try{setupWindow.close();}finally{replacingSetup=false;}
  }
  log('startup_window_ready',{elapsedMs:Date.now()-desktopStartedAt});
  try{
    const runtime=await ensureHost(true);
    if(quitting)return;
    startupState('opening');await showMain();
    if(global.qxIsRecoveryPage?.())throw Object.assign(Error('Workbench page failed to load'),{code:'PAGE_LOAD_FAILED'});
    connection?.connected(runtime);global.qxStartupState=null;
    log('startup_complete',{elapsedMs:Date.now()-desktopStartedAt});
  }catch(error){startupState('failed',error.code);connection?.reset();throw error;}
}
function showSetup(){
  if(maintenance||selectionError){backupWindow?.show();return;}
  if(setupWindow&&!setupWindow.isDestroyed()){setupWindow.show();setupWindow.focus();return;}
  setupWindow=new BrowserWindow({width:700,height:720,minWidth:460,minHeight:620,title:'API 设置 · AI师兄法律助手平台',
    show:process.env.QX_DESKTOP_HIDDEN!=='1',
    autoHideMenuBar:true,backgroundColor:'#f7f8f5',webPreferences:{preload:path.join(__dirname,'setup-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
  setupWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  setupWindow.webContents.on('will-navigate',event=>event.preventDefault());
  setupWindow.on('close',event=>{if(backupController?.isBusy()&&!relaunching&&!replacingSetup)event.preventDefault();});
  setupWindow.on('closed',()=>{setupWindow=null;if(!mainLoaded&&!backupWindow?.isOpen())app.quit()});
  void setupWindow.loadFile(path.join(__dirname,'setup.html'));
}
const owns=event=>setupWindow&&!setupWindow.isDestroyed()&&event.sender===setupWindow.webContents&&
  event.senderFrame===setupWindow.webContents.mainFrame&&event.senderFrame.url===pathToFileURL(path.join(__dirname,'setup.html')).href;

if(!app.requestSingleInstanceLock())app.quit();
else{
  connection=createHostMonitor({probe:()=>inspectHost(data),isPaused:()=>starting||quitting||maintenance||!mainLoaded,
    recover:async()=>{
      if(starting||quitting||maintenance)return;starting=true;
      try{await ensureHost()}catch(error){startupState('failed',error.code);throw error}finally{starting=false}
    },log,
    onState:state=>{
      for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:connection-state',state);
      if(state.phase==='ready'&&!starting&&!quitting&&!maintenance&&global.qxStartupState?.errorCode!=='PAGE_LOAD_FAILED'){
        if(global.qxIsRecoveryPage?.())void global.qxReconnectHost();
        else void restoreConnection();
      }
    },
  });
  global.qxConnection=connection;
  global.qxReconnectHost=async()=>{
    if(starting||quitting||maintenance||selectionError)return {ok:false};starting=true;connection.reset();
    try{await enter();return {ok:true}}catch(error){log('manual_reconnect_failed',{errorName:error.name,errorCode:error.code});return {ok:false}}
    finally{starting=false;void connection.tick()}
  };
  const healthTimer=setInterval(()=>void connection.tick(),3000);healthTimer.unref();
  app.once('will-quit',()=>clearInterval(healthTimer));
  global.qxOpenApiSettings=showSetup;
  global.qxOpenBackup=()=>backupWindow?.show();
  app.on('second-instance',()=>{if(maintenance||backupWindow?.isOpen())backupWindow?.show();else if(setupWindow){setupWindow.show();setupWindow.focus()}});
  ipcMain.handle('qx:setup-keys',event=>{if(owns(event))void shell.openExternal('https://platform.deepseek.com/api_keys')});
  ipcMain.handle('qx:setup-backup',event=>{if(owns(event))backupWindow?.show();});
  ipcMain.handle('qx:setup-save',async(event,key)=>{
    if(!owns(event)||starting||maintenance||selectionError||backupController?.isBusy())return {ok:false,message:'正在维护或处理其他操作，请稍候。'};
    starting=true;
    try{
      const checked=await validateKey(key);if(!checked.ok)return checked;
      const result=await store.save(key);
      if(result.status!=='saved')return {ok:false,message:'Windows 未能加密保存密钥，请检查当前账户权限后重试。'};
      await stopInstalledHost(data);
      await enter();return {ok:true};
    }catch{return {ok:false,message:'密钥已保存，但工作台启动未完成。请重新打开；如仍失败，查看资料目录中的 .local/host.log。'};}
    finally{starting=false;}
  });
  app.whenReady().then(async()=>{
    try{desktopLease=await claimLauncher(path.join(anchor,'.local','desktop-instance'));}
    catch{app.quit();return;}
    const setMaintenance=value=>{
      maintenance=value;
      for(const win of BrowserWindow.getAllWindows()){
        if(win.isDestroyed()||win===backupWindow?.getWindow())continue;
        win.setEnabled(!value);if(value)win.hide();
      }
    };
    backupController=createBackupController({anchor,data,payload,selectionError,
      credentialStatus:()=>selectionError?Promise.resolve({status:'unavailable'}):store.status(),
      isStarting:()=>starting||quitting,setMaintenance,stop:()=>stopInstalledHost(data),
      resume:async()=>{
        if(selectionError)throw Object.assign(Error('Location unavailable'),{code:'LOCATION_MISSING'});
        starting=true;
        try{if((await store.status()).status==='saved')await enter();else showSetup();}
        finally{starting=false;void connection.tick();}
      },
      pick:kind=>backupWindow.pick(kind),openDrafts:folder=>shell.openPath(folder),
      relaunch:()=>{relaunching=true;app.relaunch();app.quit();},
    });
    backupWindow=createBackupWindow({app,BrowserWindow,ipcMain,dialog,controller:backupController,
      canClose:()=>!backupController.isBusy()||relaunching,
      onClosed:()=>{
        if(quitting)return;
        if(maintenance||(!mainLoaded&&!setupWindow)){app.quit();return;}
        for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed()){win.setEnabled(true);win.show();}
      },
    });
    global.qxBackupBusy=()=>backupController.isBusy()&&!relaunching;
    if(selectionError){backupWindow.show();return;}
    // Updating is optional: failure to initialize it must never block the existing workbench.
    if(app.isPackaged){
      try{
        const {StrictNsisUpdater,validateFeed}=require('./update-download.cjs');
        const {createUpdateController,createInstallHandoff}=require('./updates.cjs');
        const config=require('./update-config.json');
        const updater=new StrictNsisUpdater(validateFeed(config.feed));
        const handoff=createInstallHandoff({isStarting:()=>starting||maintenance||backupController.isBusy(),setStarting:value=>{starting=value},
          stop:()=>stopInstalledHost(data),restore:enter});
        global.qxUpdates=createUpdateController({updater,version:app.getVersion(),publicKey:config.publicKey,
          onState:state=>{for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:update-state',state)},
          confirmInstall:async()=>{
            if(maintenance||backupController.isBusy())return false;
            const answer=await dialog.showMessageBox({type:'question',title:'安装更新',message:'现在安装并重启工作台？',
              detail:'请先保存正在编辑的内容，并等待文档处理、模型回答和微信任务结束。安装会关闭工作台及微信后台，完成后重新打开。你的材料和设置会保留。',
              buttons:['稍后再说','安装并重启'],defaultId:0,cancelId:0,noLink:true});return answer.response===1;
          },
          prepareInstall:handoff.prepare,recoverInstall:handoff.recover,
        });
        const checkTimer=setTimeout(()=>void global.qxUpdates.check(),15000);checkTimer.unref();
        const periodic=setInterval(()=>void global.qxUpdates.check(),6*60*60*1000);periodic.unref();
        app.once('will-quit',()=>{clearTimeout(checkTimer);clearInterval(periodic)});
      }catch{global.qxUpdates=null;}
    }
    if((await store.status()).status==='saved'){
      starting=true;
      try{await enter()}catch(error){
        log('initial_connection_failed',{errorName:error.name,errorCode:error.code});
      }finally{starting=false;void connection.tick()}
    }else showSetup();
  }).catch(()=>{dialog.showErrorBox('工作台暂未启动','无法初始化本机配置，请检查用户目录权限。');app.quit()});
}
