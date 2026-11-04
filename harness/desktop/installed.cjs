const {app,BrowserWindow,ipcMain,shell,safeStorage,dialog}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {createModelCredentialStore}=require('./model-credentials.cjs');
const {validateKey}=require('./setup-service.cjs');
const {initialize,readRuntime,readControl,readHostState,inspectHost,stopInstalledHost,restartRuntime}=require('./installed-runtime.cjs');
const {createHostMonitor,createEventLog}=require('./host-recovery.cjs');

const payload=process.env.QX_PAYLOAD_ROOT||path.join(process.resourcesPath,'workbench');
const data=process.env.QX_INSTALL_DATA||path.join(app.getPath('appData'),'QunxingHarness');
fs.mkdirSync(path.join(data,'.local'),{recursive:true});
app.setName('AI师兄法律助手平台');
// Encryption uses Electron's profile key; UI and background must share this path.
app.setPath('userData',path.join(data,'.local','desktop-data'));
process.env.QX_WORKBENCH_ROOT=data;
process.env.QX_DESKTOP_DATA=path.join(data,'.local','desktop-data');
const store=createModelCredentialStore({dataParent:path.join(data,'.local','desktop-data'),safeStorage});
let setupWindow,starting=false,mainLoaded=false,quitting=false,connection;
const log=createEventLog(data,'desktop');
global.qxDesktopLog=log;
log('desktop_start');
app.on('before-quit',()=>{quitting=true;log('desktop_quit',{intentional:true})});
process.on('exit',code=>log('desktop_exit',{code}));
process.on('uncaughtExceptionMonitor',error=>log('desktop_exception',{errorName:error.name,errorCode:error.code}));

async function ensureHost(manual=false){
  const existing=await readRuntime(data);
  if(existing){process.env.QX_HARNESS_URL=existing.url;return existing;}
  const control=readControl(data);
  let failed=false;
  if(control){
    if(readHostState(data)?.phase==='failed'){
      if(!manual)throw Error('后台连续启动失败，请点击重试恢复。');
      await restartRuntime(control);
    }
  }else{
    const host=await inspectHost(data);
    if(host.hostAlive)throw Error('后台仍在运行但暂时无法连接，请稍后重试，避免打断正在处理的任务。');
    initialize(payload,data);
    const result=await store.withSecret(secret=>{
    const child=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'desktop-runner/installed-host.cjs')],{
      detached:true,stdio:'ignore',windowsHide:true,
      env:{...process.env,QX_PAYLOAD_ROOT:payload,QX_INSTALL_DATA:data,DEEPSEEK_API_KEY:secret}});
      child.unref();child.once('error',error=>{failed=true;log('launcher_spawn_error',{errorName:error.name,errorCode:error.code})});
      child.once('exit',(code,signal)=>{failed=true;log('launcher_observed_exit',{code,signal})});
    });
    if(result.status!=='saved')throw Error('Windows 暂时无法读取加密配置，请重新填写 API Key。');
  }
  const deadline=Date.now()+120000;
  while(Date.now()<deadline&&!failed){
    const runtime=await readRuntime(data);
    if(runtime){process.env.QX_HARNESS_URL=runtime.url;return runtime;}
    if(readControl(data)&&readHostState(data)?.phase==='failed')break;
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  throw Error('本机服务未能启动，请查看资料目录中的 .local/host.log 后重试。');
}
async function enter(){
  const runtime=await ensureHost(true);
  if(!mainLoaded){mainLoaded=true;require('./main.cjs');await global.qxMainReady;}
  else await global.qxReloadMain();
  if(setupWindow&&!setupWindow.isDestroyed())setupWindow.close();
  connection?.connected(runtime);
}
function showSetup(){
  if(setupWindow&&!setupWindow.isDestroyed()){setupWindow.show();setupWindow.focus();return;}
  setupWindow=new BrowserWindow({width:700,height:720,minWidth:460,minHeight:620,title:'API 设置 · AI师兄法律助手平台',
    show:process.env.QX_DESKTOP_HIDDEN!=='1',
    autoHideMenuBar:true,backgroundColor:'#f7f8f5',webPreferences:{preload:path.join(__dirname,'setup-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
  setupWindow.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  setupWindow.webContents.on('will-navigate',event=>event.preventDefault());
  setupWindow.on('closed',()=>{setupWindow=null;if(!mainLoaded)app.quit()});
  void setupWindow.loadFile(path.join(__dirname,'setup.html'));
}
const owns=event=>setupWindow&&!setupWindow.isDestroyed()&&event.sender===setupWindow.webContents&&
  event.senderFrame===setupWindow.webContents.mainFrame&&event.senderFrame.url===pathToFileURL(path.join(__dirname,'setup.html')).href;

if(!app.requestSingleInstanceLock())app.quit();
else{
  connection=createHostMonitor({probe:()=>inspectHost(data),isPaused:()=>starting||quitting||!mainLoaded,
    recover:async()=>{if(starting||quitting)return;starting=true;try{await ensureHost()}finally{starting=false}},log,
    onState:state=>{for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:connection-state',state)},
  });
  global.qxConnection=connection;
  global.qxReconnectHost=async()=>{
    if(starting||quitting)return {ok:false};starting=true;connection.reset();
    try{await enter();return {ok:true}}catch(error){log('manual_reconnect_failed',{errorName:error.name,errorCode:error.code});return {ok:false}}
    finally{starting=false;void connection.tick()}
  };
  const healthTimer=setInterval(()=>void connection.tick(),3000);healthTimer.unref();
  app.once('before-quit',()=>clearInterval(healthTimer));
  global.qxOpenApiSettings=showSetup;
  app.on('second-instance',()=>{if(setupWindow){setupWindow.show();setupWindow.focus()}});
  ipcMain.handle('qx:setup-keys',event=>{if(owns(event))void shell.openExternal('https://platform.deepseek.com/api_keys')});
  ipcMain.handle('qx:setup-save',async(event,key)=>{
    if(!owns(event)||starting)return {ok:false,message:'正在处理，请稍候。'};
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
    // Updating is optional: failure to initialize it must never block the existing workbench.
    if(app.isPackaged){
      try{
        const {StrictNsisUpdater,validateFeed}=require('./update-download.cjs');
        const {createUpdateController,createInstallHandoff}=require('./updates.cjs');
        const config=require('./update-config.json');
        const updater=new StrictNsisUpdater(validateFeed(config.feed));
        const handoff=createInstallHandoff({isStarting:()=>starting,setStarting:value=>{starting=value},
          stop:()=>stopInstalledHost(data),restore:enter});
        global.qxUpdates=createUpdateController({updater,version:app.getVersion(),publicKey:config.publicKey,
          onState:state=>{for(const win of BrowserWindow.getAllWindows())if(!win.isDestroyed())win.webContents.send('qx:update-state',state)},
          confirmInstall:async()=>{
            const answer=await dialog.showMessageBox({type:'question',title:'安装更新',message:'现在安装并重启工作台？',
              detail:'请先保存正在编辑的内容，并等待文档处理、模型回答和微信任务结束。安装会关闭工作台及微信后台，完成后重新打开。你的材料和设置会保留。',
              buttons:['稍后再说','安装并重启'],defaultId:0,cancelId:0,noLink:true});return answer.response===1;
          },
          prepareInstall:handoff.prepare,recoverInstall:handoff.recover,
        });
        const checkTimer=setTimeout(()=>void global.qxUpdates.check(),15000);checkTimer.unref();
        const periodic=setInterval(()=>void global.qxUpdates.check(),6*60*60*1000);periodic.unref();
        app.once('before-quit',()=>{clearTimeout(checkTimer);clearInterval(periodic)});
      }catch{global.qxUpdates=null;}
    }
    if((await store.status()).status==='saved'){
      try{await enter()}catch(error){dialog.showErrorBox('工作台暂未启动',error.message);showSetup()}
    }else showSetup();
  }).catch(()=>{dialog.showErrorBox('工作台暂未启动','无法初始化本机配置，请检查用户目录权限。');app.quit()});
}
