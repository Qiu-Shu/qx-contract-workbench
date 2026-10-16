const { app, BrowserWindow, Menu, ipcMain, dialog, session } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomUUID } = require('node:crypto');
const { Backend } = require('./backend.cjs');
const { navigationAllowed, setupSenderAllowed, validLibraryRoot } = require('./policy.cjs');

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
let win, backend, origin = '', stopping = false, busy = false;
let settings = {}, state = {mode:'loading', message:'正在打开工作台…'};

function setState(next) { state = {...next, library:settings.library_root || '', dataParent}; if (win && !win.isDestroyed()) win.webContents.send('desktop:state', state); }
function isSetup(event) {
  return win && event.sender === win.webContents && setupSenderAllowed(event.senderFrame?.url, setupURL,
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
async function changeLibrary(next) {
  try { saveSettings(next); setState(state); return {ok:true}; }
  catch {
    await dialog.showMessageBox(win,{type:'error',message:'未能保存资料库设置。请检查资料目录的可写权限和可用空间；原设置已保留。'});
    return {ok:false};
  }
}
async function showError() {
  origin = '';
  setState({mode:'error',message:'工作台未能启动或已意外停止。请重新打开；已有资料会保留。如仍失败，请保留资料目录并联系维护人员。'});
  if (win && !win.isDestroyed()) await win.loadURL(setupURL);
}
async function startBackend(credentials = {}) {
  if (busy || stopping) return {ok:false};
  if (!fs.existsSync(path.join(dataParent,'workspaces','main')) && !('username' in credentials)) {
    setState({mode:'setup',message:'设置此电脑上的账户，开始使用工作台。'});
    if (win.webContents.getURL() !== setupURL) await win.loadURL(setupURL);
    return {ok:false};
  }
  busy = true; setState({mode:'loading',message:'正在检查资料并启动工作台…'});
  try {
    if (backend) await backend.stop();
    if (settings.library_root && !validLibraryRoot(settings.library_root)) throw new Error('LIBRARY_UNAVAILABLE');
    const executable = app.isPackaged ? path.join(process.resourcesPath,'backend','qx-backend.exe')
      : path.join(__dirname,'..','.venv','Scripts','python.exe');
    backend = new Backend(executable, app.isPackaged ? [] : ['-m','cn_contract.desktop_entry']);
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
  return changeLibrary({library_root:selected});
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
        if (Object.keys(saved).some(k=>k!=='library_root') || (saved.library_root && !path.isAbsolute(saved.library_root))) throw new Error();
        settings = saved;
      } catch { state = {mode:'error',message:'资料库设置无法读取。请保留资料目录并联系维护人员。'}; }
    }
    const isolated = session.fromPartition('qx-'+randomUUID());
    isolated.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    isolated.setPermissionCheckHandler(()=>false);
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
        {label:'断开资料库连接',click:async()=>{if (!busy && (await changeLibrary({})).ok) await startBackend();}},
        {label:'重新打开工作台',click:()=>{if(!busy) void startBackend();}}, {type:'separator'},{role:'quit',label:'退出'}]},
      {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
      {label:'视图',submenu:[{role:'resetZoom',label:'恢复字号'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]}
    ]));
    ipcMain.handle('desktop:state',event=>isSetup(event)?state:null);
    ipcMain.handle('desktop:library',event=>isSetup(event)?chooseLibrary():{ok:false});
    ipcMain.handle('desktop:start',(event,values)=>{
      if (!isSetup(event) || busy) return {ok:false};
      if (state.mode === 'error') return startBackend();
      if (!values || typeof values.username !== 'string' || values.username.length>128 || typeof values.password !== 'string'
          || values.password.length<6 || values.password.length>12) return {ok:false};
      return startBackend({username:values.username,password:values.password});
    });
    await win.loadURL(setupURL);
    if (state.mode === 'error') {setState(state); return;}
    if (fs.existsSync(path.join(dataParent,'workspaces','main'))) await startBackend();
    else setState({mode:'setup',message:'设置此电脑上的账户，开始使用工作台。'});
  }).catch(()=>{app.exit(1);});
}
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{
  if (stopping) return;
  event.preventDefault(); stopping = true;
  if (win && !win.isDestroyed()) win.hide();
  Promise.resolve(backend?.stop()).finally(()=>app.quit());
});
