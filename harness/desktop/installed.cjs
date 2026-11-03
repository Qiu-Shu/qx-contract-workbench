const {app,BrowserWindow,ipcMain,shell,safeStorage,dialog}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const {createModelCredentialStore}=require('./model-credentials.cjs');
const {validateKey}=require('./setup-service.cjs');
const {initialize,readRuntime,stopRuntime}=require('./installed-runtime.cjs');

const payload=process.env.QX_PAYLOAD_ROOT||path.join(process.resourcesPath,'workbench');
const data=process.env.QX_INSTALL_DATA||path.join(app.getPath('appData'),'QunxingHarness');
fs.mkdirSync(path.join(data,'.local'),{recursive:true});
app.setName('群兴法律工作台');
// Encryption uses Electron's profile key; UI and background must share this path.
app.setPath('userData',path.join(data,'.local','desktop-data'));
process.env.QX_WORKBENCH_ROOT=data;
process.env.QX_DESKTOP_DATA=path.join(data,'.local','desktop-data');
const store=createModelCredentialStore({dataParent:path.join(data,'.local','desktop-data'),safeStorage});
let setupWindow,starting=false,mainLoaded=false;

async function ensureHost(){
  const existing=await readRuntime(data);
  if(existing){process.env.QX_HARNESS_URL=existing.url;return;}
  initialize(payload,data);
  let failed=false;
  const result=await store.withSecret(secret=>{
    const child=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'desktop-runner/installed-host.cjs')],{
      detached:true,stdio:'ignore',windowsHide:true,
      env:{...process.env,QX_PAYLOAD_ROOT:payload,QX_INSTALL_DATA:data,DEEPSEEK_API_KEY:secret}});
    child.unref();child.once('error',()=>{failed=true});child.once('exit',code=>{if(code!==0)failed=true});
  });
  if(result.status!=='saved')throw Error('Windows 暂时无法读取加密配置，请重新填写 API Key。');
  const deadline=Date.now()+120000;
  while(Date.now()<deadline&&!failed){
    const runtime=await readRuntime(data);
    if(runtime){process.env.QX_HARNESS_URL=runtime.url;return;}
    await new Promise(resolve=>setTimeout(resolve,500));
  }
  throw Error('本机服务未能启动，请查看资料目录中的 .local/host.log 后重试。');
}
async function enter(){
  await ensureHost();
  if(!mainLoaded){mainLoaded=true;require('./main.cjs');await global.qxMainReady;}
  else await global.qxReloadMain();
  if(setupWindow&&!setupWindow.isDestroyed())setupWindow.close();
}
function showSetup(){
  if(setupWindow&&!setupWindow.isDestroyed()){setupWindow.show();setupWindow.focus();return;}
  setupWindow=new BrowserWindow({width:700,height:720,minWidth:460,minHeight:620,title:'API 设置 · 群兴法律工作台',
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
      const prior=await readRuntime(data);
      if(prior)await stopRuntime(prior);
      await enter();return {ok:true};
    }catch{return {ok:false,message:'密钥已保存，但工作台启动未完成。请重新打开；如仍失败，查看资料目录中的 .local/host.log。'};}
    finally{starting=false;}
  });
  app.whenReady().then(async()=>{
    if((await store.status()).status==='saved'){
      try{await enter()}catch(error){dialog.showErrorBox('工作台暂未启动',error.message);showSetup()}
    }else showSetup();
  }).catch(()=>{dialog.showErrorBox('工作台暂未启动','无法初始化本机配置，请检查用户目录权限。');app.quit()});
}
