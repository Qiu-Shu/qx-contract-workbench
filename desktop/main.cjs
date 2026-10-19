const { app, BrowserWindow, Menu, ipcMain, dialog, session, safeStorage } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomUUID } = require('node:crypto');
const { Backend } = require('./backend.cjs');
const { Maintenance } = require('./maintenance.cjs');
const { createModelCredentialStore } = require('./model-credentials.cjs');
const { registerModelSettings } = require('./model-settings.cjs');
const { navigationAllowed, setupSenderAllowed, validLibraryRoot, clipboardWriteAllowed } = require('./policy.cjs');

app.setName('群兴法律工作台验证版');
// An OS-supplied override supports isolated acceptance; never supplied by a page.
const dataParent = process.env.QX_DESKTOP_DATA_PARENT || path.join(app.getPath('appData'), 'QunxingWorkbenchValidation');
if (!path.isAbsolute(dataParent)) app.exit(1);
for (let current = path.resolve(dataParent); ; current = path.dirname(current)) {
  if (fs.existsSync(current) && fs.lstatSync(current).isSymbolicLink()) app.exit(1);
  if (current === path.dirname(current)) break;
}
app.setPath('userData', dataParent);
const setupURL = pathToFileURL(path.join(__dirname, 'setup.html')).href;
const settingsPath = path.join(dataParent, 'desktop-settings.json');
let win, backend, maintenance, modelSettings, origin = '', stopping = false, busy = false;
let settings = {}, state = {mode:'loading', message:'正在打开工作台…'};
function workspacePath(){return path.join(dataParent,'workspaces',settings.workspace||'main');}
function runtime(){return {executable:app.isPackaged?path.join(process.resourcesPath,'backend','qx-backend.exe')
  :path.join(__dirname,'..','.venv','Scripts','python.exe'),args:app.isPackaged?[]:['-m','cn_contract.desktop_entry']};}

function setState(next) { state = {...next, library:settings.library_root || '', dataParent}; if (win && !win.isDestroyed()) win.webContents.send('desktop:state', state); }
function isSetup(event) {
  return win && !win.isDestroyed() && event.sender === win.webContents && setupSenderAllowed(event.senderFrame?.url, setupURL,
    event.senderFrame === win.webContents.mainFrame);
}
function saveSettings(next) {
  const temp = settingsPath+'.tmp';
  for (const file of [settingsPath,temp]) {
    if (fs.existsSync(file) && (fs.lstatSync(file).isSymbolicLink() || fs.statSync(file).nlink !== 1)) throw new Error('SETTINGS_PATH');
  }
  fs.writeFileSync(temp, JSON.stringify(next), {encoding:'utf8',flag:'w'});
  fs.renameSync(temp, settingsPath);
  settings = next;
}
async function changeSettings(next) {
  try { saveSettings(next); setState(state); return {ok:true}; }
  catch {
    await dialog.showMessageBox(win,{type:'error',message:'未能保存工作区设置。请检查资料目录的可写权限和可用空间；原设置已保留。'});
    return {ok:false};
  }
}
async function showError() {
  origin = '';
  setState({mode:'error',message:'工作台未能启动或已意外停止。请重新打开；已有资料会保留。如仍失败，请保留资料目录并联系维护人员。'});
  if (win && !win.isDestroyed()) await win.loadURL(setupURL);
}
async function leavePage(){
  if(win.webContents.getURL()===setupURL)return true;
  try{await win.loadURL(setupURL);}catch{}
  if(win.webContents.getURL()===setupURL)return true;
  await dialog.showMessageBox(win,{type:'info',message:'当前页面仍有未保存内容。请先保存或自行处理这些文字，再打开维护功能；后台仍在运行。'});
  return false;
}
async function startBackend(credentials = {}) {
  if (busy || stopping) return {ok:false};
  busy=true;
  try{if(!await leavePage())return {ok:false};}finally{busy=false;}
  if (!fs.existsSync(workspacePath()) && !('username' in credentials)) {
    setState({mode:'setup',message:'设置此电脑上的账户，开始使用工作台。'});
    if (win.webContents.getURL() !== setupURL) await win.loadURL(setupURL);
    return {ok:false};
  }
  busy = true; setState({mode:'loading',message:'正在检查资料并启动工作台…'});
  try {
    if (backend) await backend.stop();
    if (settings.library_root && !validLibraryRoot(settings.library_root)) throw new Error('LIBRARY_UNAVAILABLE');
    const {executable,args}=runtime();
    backend = new Backend(executable,args);
    backend.on('failed', () => { if (!stopping) void showError(); });
    const ready = await backend.start({data_parent:dataParent,...credentials,...settings});
    origin = `http://127.0.0.1:${ready.port}`;
    await win.loadURL(origin+'/login');
    setState({mode:'ready'}); return {ok:true};
  } catch {
    if (backend) await backend.stop();
    await showError(); return {ok:false};
  } finally { busy = false; }
}
async function chooseLibrary() {
  if (busy) return {ok:false};
  const result = await dialog.showOpenDialog(win,{title:'选择已有法律资料库目录',properties:['openDirectory']});
  if (result.canceled) return {ok:false};
  const selected = result.filePaths[0];
  // Fail early without modifying settings if the expected local catalog is absent.
  if (!validLibraryRoot(selected)) {
    await dialog.showMessageBox(win,{type:'info',message:'请选择已完成索引的法律资料库目录，内含 catalog.sqlite 和 current.json。'});
    return {ok:false};
  }
  return changeSettings({...settings,library_root:selected});
}

async function showMaintenance(operation){
  if(busy||stopping)return;
  if(operation==='backup'&&!fs.existsSync(workspacePath()))return;
  busy=true;
  try{
    if(!await leavePage())return;
    if(backend)await backend.stop();origin='';
    const messages={backup:'备份当前工作区的全部账户和案件资料。',restore:'从加密备份建立独立核对副本，原工作区保留。',
      'model-settings':'主模型设置准备：仅管理这台电脑保存的密钥。'};
    setState({mode:operation,message:messages[operation]});
  }finally{busy=false;}
}
async function runMaintenance(event,values){
  if(!isSetup(event)||busy||stopping||!['backup','restore'].includes(state.mode))return {ok:false};
  if(!values||typeof values.passphrase!=='string'||[...values.passphrase].length<12||[...values.passphrase].length>128)return {ok:false};
  const operation=state.mode;busy=true;
  try{
    let archive;
    if(operation==='backup'){
      const selected=await dialog.showSaveDialog(win,{title:'保存加密案件备份',defaultPath:path.join(app.getPath('documents'),'群兴案件备份-'+Date.now()+'.qxbak'),filters:[{name:'群兴加密备份',extensions:['qxbak']}]});
      if(selected.canceled)return {ok:false,canceled:true};archive=selected.filePath;
    }else{
      const selected=await dialog.showOpenDialog(win,{title:'选择加密案件备份',properties:['openFile'],filters:[{name:'群兴加密备份',extensions:['qxbak']}]});
      if(selected.canceled)return {ok:false,canceled:true};archive=selected.filePaths[0];
    }
    setState({mode:'loading',message:'正在加密或核对全部资料，请保持程序打开…'});
    const {executable,args}=runtime();maintenance=new Maintenance(executable,args);
    let report;
    try{report=await maintenance.run({data_parent:dataParent,workspace:settings.workspace||'main',operation,archive,passphrase:values.passphrase});}
    finally{await maintenance.stop();maintenance=null;}
    if(operation==='restore'){
      const relative=path.relative(path.join(dataParent,'workspaces'),report.restored_root).split(path.sep).join('/');
      if(!/^recovered\/[0-9a-f-]{36}$/.test(relative))throw new Error('MAINTENANCE_FAILED');
      saveSettings({...settings,workspace:relative});
    }
    setState({mode:'maintenance-done',message:operation==='backup'
      ?'加密备份已生成并完成解密核对。请独立妥善保存备份口令。'
      :'独立恢复副本已核对。打开后使用备份时的账户重新登录；副本仅供查阅。',
      resultPath:operation==='backup'?report.archive_path:report.restored_root,
      detail:'已核对 '+report.file_count+' 个文件 · 备份摘要 '+report.archive_sha256});
    return {ok:true};
  }catch(error){
    const messages={ARCHIVE_AUTHENTICATION_FAILED:'口令不正确或备份已损坏。请核对后重试。',
      BACKUP_DESTINATION_INVALID:'目标文件已存在或位于当前工作区内。请选择新的备份位置。',
      WORKSPACE_IN_USE:'资料正被其他程序实例使用，请关闭该实例后重试。',
      ARCHIVE_LIMIT:'资料超过当前 2 GiB 备份上限，请联系维护人员分批处理。'};
    setState({mode:operation,message:messages[error.message]||'操作未完成，原工作区已保留。请检查备份、磁盘空间和文件权限后重试。'});
    return {ok:false};
  }finally{busy=false;}
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
  app.whenReady().then(async () => {
    if (fs.existsSync(settingsPath)) {
      try {
        const info = fs.lstatSync(settingsPath);
        if (info.isSymbolicLink() || info.nlink !== 1 || info.size > 8192) throw new Error();
        const saved = JSON.parse(fs.readFileSync(settingsPath,'utf8'));
        if (Object.keys(saved).some(k=>!['library_root','workspace'].includes(k)) || (saved.library_root && !path.isAbsolute(saved.library_root))
            || (saved.workspace!==undefined && (typeof saved.workspace!=='string'||!/^main$|^recovered\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(saved.workspace)))) throw new Error();
        settings = saved;
      } catch { state = {mode:'error',message:'资料库设置无法读取。请保留资料目录并联系维护人员。'}; }
    }
    const isolated = session.fromPartition('qx-'+randomUUID());
    const canWriteClipboard = (wc,permission,details) => Boolean(win && !win.isDestroyed() && win.isFocused()
      && wc === win.webContents && clipboardWriteAllowed(permission,details.requestingUrl,origin,details.isMainFrame));
    isolated.setPermissionRequestHandler((wc,permission,callback,details)=>callback(canWriteClipboard(wc,permission,details)));
    isolated.setPermissionCheckHandler((wc,permission,_requestingOrigin,details)=>canWriteClipboard(wc,permission,details));
    isolated.on('will-download', (event,item) => {
      const url = item.getURL();
      if (!navigationAllowed(url,origin,'') && !(origin && url.startsWith('blob:'+origin+'/'))) { event.preventDefault(); return; }
      item.setSaveDialogOptions({title:'保存工作台导出文件', defaultPath:path.join(app.getPath('downloads'),path.basename(item.getFilename()))});
    });
    win = new BrowserWindow({width:1240,height:850,minWidth:640,minHeight:540,backgroundColor:'#f2f5f8',show:false,
      webPreferences:{preload:path.join(__dirname,'preload.cjs'),session:isolated,nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event,url)=>{if(!navigationAllowed(url,origin,setupURL)) event.preventDefault();});
    win.webContents.on('will-redirect',(event,url)=>{if(!navigationAllowed(url,origin,setupURL)) event.preventDefault();});
    win.webContents.on('will-attach-webview',event=>event.preventDefault());
    win.webContents.on('render-process-gone',()=>{if(!stopping) void showError();});
    win.once('ready-to-show',()=>win.show());
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      {label:'工作台',submenu:[{label:'连接法律资料库…',click:async()=>{if ((await chooseLibrary()).ok && origin) await startBackend();}},
        {label:'断开资料库连接',click:async()=>{const next={...settings};delete next.library_root;if (!busy && (await changeSettings(next)).ok) await startBackend();}},
        {type:'separator'},
        {label:'主模型设置…',click:()=>showMaintenance('model-settings')},
        {label:'备份案件资料…',click:()=>showMaintenance('backup')},
        {label:'从备份建立核对副本…',click:()=>showMaintenance('restore')},
        {label:'返回原工作区',click:async()=>{if(!busy&&(await changeSettings({...settings,workspace:'main'})).ok)await startBackend();}},
        {label:'重新打开工作台',click:()=>{if(!busy) void startBackend();}}, {type:'separator'},{role:'quit',label:'退出'}]},
      {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
      {label:'视图',submenu:[{role:'resetZoom',label:'恢复字号'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]}
    ]));
    ipcMain.handle('desktop:state',event=>isSetup(event)?state:null);
    ipcMain.handle('desktop:library',event=>isSetup(event)?chooseLibrary():{ok:false});
    ipcMain.handle('desktop:maintenance',runMaintenance);
    modelSettings=registerModelSettings({ipcMain,store:createModelCredentialStore({dataParent,safeStorage,platform:process.platform}),
      isAllowed:event=>!busy&&!stopping&&state.mode==='model-settings'&&isSetup(event),setBusy:value=>{busy=value;}});
    ipcMain.handle('desktop:resume',event=>isSetup(event)&&!busy?startBackend():{ok:false});
    ipcMain.handle('desktop:start',(event,values)=>{
      if (!isSetup(event) || busy) return {ok:false};
      if (state.mode === 'error') return startBackend();
      if (!values || typeof values.username !== 'string' || values.username.length>128 || typeof values.password !== 'string'
          || values.password.length<6 || values.password.length>12) return {ok:false};
      return startBackend({username:values.username,password:values.password});
    });
    await win.loadURL(setupURL);
    if (state.mode === 'error') {setState(state); return;}
    if (fs.existsSync(workspacePath())) await startBackend();
    else setState({mode:'setup',message:'设置此电脑上的账户，开始使用工作台。'});
  }).catch(()=>{app.exit(1);});
}
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
  if (stopping) return;
  event.preventDefault(); stopping = true;
  if (win && !win.isDestroyed()) win.hide();
  Promise.allSettled([backend?.stop(),maintenance?.stop(),modelSettings?.wait()]).finally(()=>app.quit());
});
