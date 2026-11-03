// Thin local shell: the official Harness UI owns chat, uploads and model calls.
const {app,BrowserWindow,Menu,ipcMain,dialog,shell}=require('electron');
const {readFileSync,mkdirSync}=require('node:fs');
const {readFile,writeFile,stat}=require('node:fs/promises');
const {join,resolve}=require('node:path');
const {execFile}=require('node:child_process');

const root=resolve(process.env.QX_WORKBENCH_ROOT||resolve(__dirname,'..'));
const userData=resolve(process.env.QX_DESKTOP_DATA||join(root,'.local','desktop-data'));
mkdirSync(userData,{recursive:true});
app.setName('AI师兄法律助手平台');
app.setPath('userData',userData);
const runtimePath=join(root,'.local','runtime.json');
function runtimeUrl(){
  let value=process.env.QX_HARNESS_URL;
  if(!value){try{value=JSON.parse(readFileSync(runtimePath,'utf8').replace(/^\uFEFF/,'')).url;}catch{}}
  const url=new URL(value||'http://127.0.0.1:3080');
  if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw new Error('桌面入口必须是本机 Harness 服务。');
  return url;
}
let window,origin;
const owns=event=>window&&!window.isDestroyed()&&event.sender===window.webContents&&
  event.senderFrame===window.webContents.mainFrame&&new URL(event.senderFrame.url).origin===origin;
function showWechat(){
  if(!window||window.isDestroyed())return;
  window.show();window.focus();
  void window.webContents.executeJavaScript("window.__qxOpenWechatRequested=true;window.dispatchEvent(new Event('qx-open-wechat'));").catch(()=>{});
}
const clipboardScript=[
  '[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)',
  'Add-Type -AssemblyName System.Windows.Forms',
  '$paths = @([System.Windows.Forms.Clipboard]::GetFileDropList())',
  'ConvertTo-Json -InputObject $paths -Compress',
].join('\n');
function clipboardFiles(){
  // This function has no timer or startup caller; only a real paste invokes it.
  return new Promise((resolve,reject)=>execFile('powershell.exe',
    ['-NoProfile','-NonInteractive','-STA','-Command',clipboardScript],
    {windowsHide:true,timeout:8000,maxBuffer:8*1024*1024,encoding:'utf8'},(error,stdout)=>{
      if(error)return reject(new Error('暂时无法读取复制的文件，请重试或直接拖入。'));
      try{const paths=JSON.parse(stdout.replace(/^\uFEFF/,''));resolve(Array.isArray(paths)?paths.filter(p=>typeof p==='string'):[]);}
      catch{reject(new Error('未能识别复制的文件，请直接拖入。'));}
    }));
}
let pasting=false;
async function pasteCopiedFiles(event,request){
  if(!owns(event)||pasting||!request||!/^[a-f0-9-]{36}$/.test(request.marker)||typeof request.sessionId!=='string'||!request.sessionId)return {ok:false};
  pasting=true;
  let attached=false;
  const wc=event.sender;
  try{
    const files=await clipboardFiles();
    if(!files.length)return {ok:true,count:0};
    const info=await Promise.all(files.map(path=>stat(path)));
    if(info.some(item=>!item.isFile()))return {ok:false,message:'请打开文件夹，复制其中需要的文件后粘贴。'};
    if(!owns(event))return {ok:false};
    if(wc.debugger.isAttached())return {ok:false,message:'请关闭开发者工具后重试，或直接拖入文件。'};
    wc.debugger.attach('1.3');attached=true;
    const current=await wc.debugger.sendCommand('Runtime.evaluate',{expression:'document.documentElement.dataset.qxSessionId || ""',returnByValue:true});
    if(current.result.value!==request.sessionId)return {ok:false,message:'会话已切换，文件没有加入新会话；请重新粘贴。'};
    const document=await wc.debugger.sendCommand('DOM.getDocument',{depth:0});
    const node=await wc.debugger.sendCommand('DOM.querySelector',{nodeId:document.root.nodeId,
      selector:`input[type="file"][data-qx-paste-request="${request.marker}"]:not(:disabled)`});
    if(!node.nodeId)return {ok:false,message:'输入框状态已变化，文件未加入；请重新粘贴。'};
    // Chromium creates native File objects and dispatches its ordinary change event.
    await wc.debugger.sendCommand('DOM.setFileInputFiles',{nodeId:node.nodeId,files});
    return {ok:true,count:files.length};
  }catch(error){return {ok:false,message:error.message?.startsWith('暂时')?error.message:'文件没有加入，请重试或直接拖入。'};}
  finally{if(attached&&!wc.isDestroyed())wc.debugger.detach();pasting=false;}
}
async function createWindow(){
  const url=runtimeUrl();origin=url.origin;
  window=new BrowserWindow({width:1320,height:920,minWidth:800,minHeight:600,title:'AI师兄法律助手平台',
    backgroundColor:'#ffffff',show:false,autoHideMenuBar:false,
    webPreferences:{preload:join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,
      additionalArguments:[`--qx-origin=${origin}`]}});
  window.webContents.on('page-title-updated',event=>{event.preventDefault();window.setTitle('AI师兄法律助手平台');});
  window.once('ready-to-show',()=>{if(process.env.QX_DESKTOP_HIDDEN!=='1')window.show();});
  window.webContents.on('will-navigate',(event,target)=>{if(new URL(target).origin!==origin){event.preventDefault();if(/^https?:/.test(target))void shell.openExternal(target);}});
  window.webContents.setWindowOpenHandler(({url})=>{
    const target=new URL(url);
    if(target.origin===origin&&target.pathname==='/qx-wechat')showWechat();
    else if(/^https?:/.test(url))void shell.openExternal(url);
    return {action:'deny'};
  });
  const ownSession=window.webContents.session;
  ownSession.setPermissionCheckHandler((wc,permission,requestingOrigin)=>wc===window.webContents&&requestingOrigin===origin&&permission==='clipboard-sanitized-write');
  ownSession.setPermissionRequestHandler((wc,permission,callback,details)=>callback(wc===window.webContents&&details.isMainFrame&&new URL(details.requestingUrl).origin===origin&&permission==='clipboard-sanitized-write'));
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {label:'工作台',submenu:[{label:'手机微信',click:showWechat},
      ...(global.qxOpenApiSettings?[{label:'API 设置',click:()=>global.qxOpenApiSettings()}]:[]),
      {label:'打开材料文件夹',click:()=>void shell.openPath(join(root,'workspace'))},
      {label:'重新连接',click:()=>void window.loadURL(runtimeUrl().href)},
      ...(global.qxUpdates?[{label:'检查更新',click:()=>{
        void global.qxUpdates.check();
        void window.webContents.executeJavaScript("window.dispatchEvent(new Event('qx-open-update'))").catch(()=>{});
      }}]:[]),
      {type:'separator'},{label:'关闭窗口（微信继续运行）',role:'quit'}]},
    {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},
      {role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
    {label:'显示',submenu:[{role:'resetZoom',label:'实际大小'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},
      {type:'separator'},{role:'togglefullscreen',label:'全屏'}]},
  ]));
  try{await window.loadURL(url.href);if(process.argv.includes('--wechat'))showWechat();}catch{
    await window.loadFile(join(__dirname,'unavailable.html'));
  }
}
global.qxReloadMain=async()=>{
  const previous=window;
  await createWindow();
  if(previous&&!previous.isDestroyed())previous.close();
};
if(!app.requestSingleInstanceLock())app.quit();
else{
  app.on('second-instance',(_event,argv)=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();if(argv.includes('--wechat'))showWechat();}});
  ipcMain.handle('qx:paste-files',pasteCopiedFiles);
  ipcMain.handle('qx:update-state',event=>owns(event)&&global.qxUpdates?global.qxUpdates.state():null);
  ipcMain.handle('qx:update-action',(event,action)=>{
    if(!owns(event)||!global.qxUpdates||!['check','download','cancel','install'].includes(action))return null;
    return global.qxUpdates[action]();
  });
  ipcMain.handle('qx:pick-directory',async event=>{
    if(!owns(event))return null;
    const chosen=await dialog.showOpenDialog(window,{title:'选择工作区',defaultPath:join(root,'workspace'),properties:['openDirectory']});
    return chosen.canceled?null:chosen.filePaths[0]||null;
  });
  ipcMain.handle('qx:locale',async event=>{
    if(!owns(event))return {languages:['zh-CN'],preference:'zh'};
    try{return {languages:['zh-CN','zh'],preference:JSON.parse(await readFile(join(userData,'locale.json'),'utf8')).locale};}
    catch{return {languages:['zh-CN','zh'],preference:'zh'};}
  });
  ipcMain.on('qx:locale-change',(event,locale)=>{if(owns(event)&&typeof locale==='string'&&/^[a-z]{2}(?:-[A-Za-z]+)?$/.test(locale))void writeFile(join(userData,'locale.json'),JSON.stringify({locale}));});
  global.qxMainReady=app.whenReady().then(createWindow).catch(()=>{dialog.showErrorBox('工作台暂未打开','请先启动本机服务，再重新打开AI师兄法律助手平台。');app.quit();});
  app.on('window-all-closed',()=>app.quit());
}
