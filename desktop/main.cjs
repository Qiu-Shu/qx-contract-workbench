const { app, BrowserWindow, Menu, ipcMain, dialog, session, safeStorage } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { randomUUID } = require('node:crypto');
const { Backend } = require('./backend.cjs');
const { Maintenance } = require('./maintenance.cjs');
const { createModelCredentialStore } = require('./model-credentials.cjs');
const { registerModelSettings } = require('./model-settings.cjs');
const { createModelSession, automaticAnalysisPolicy, validAutomaticAnalysis, automaticAnalysisEnabled } = require('./model-session.cjs');
const { registerModelApproval } = require('./model-approval.cjs');
const { registerPersonalWeixin } = require('./personal-weixin.cjs');
const { createModelApprovalWindow } = require('./model-approval-window.cjs');
const { registerAssistantModelBridge, autoConfigureModel } = require('./model-bridge.cjs');
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
let win, backend, maintenance, modelSettings, modelApproval, approvalWindow, origin = '', stopping = false, busy = false;
let mainModelSession = null, personalWeixin = null;
let settings = {}, state = {mode:'loading', message:'正在打开工作台…'};
let documentEpoch=0, settingsReturn=null, activeBackend=null;
function workspacePath(){return path.join(dataParent,'workspaces',settings.workspace||'main');}
function runtime(){return {executable:app.isPackaged?path.join(process.resourcesPath,'backend','qx-backend.exe')
  :path.join(__dirname,'..','.venv','Scripts','python.exe'),args:app.isPackaged?[]:['-m','cn_contract.desktop_entry']};}

function setState(next) { state = {...next, library:settings.library_root || '', dataParent}; if (win && !win.isDestroyed()) win.webContents.send('desktop:state', state); }
function isSetup(event) {
  return win && !win.isDestroyed() && event.sender === win.webContents && setupSenderAllowed(event.senderFrame?.url, setupURL,
    event.senderFrame === win.webContents.mainFrame);
}
function saveSettings(next) {
  if((next.workspace||'main')!==(settings.workspace||'main')){
    next={...next,model_auto_analysis:next.model_auto_analysis===false?false:undefined};
  }
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
async function showError(owned=backend) {
  if(owned!==backend)return;
  const wasBusy=busy;busy=true;
  origin = ''; settingsReturn=null;activeBackend=null;
  try {
    if(owned&&!owned.closing)await owned.stop();
    else if(owned)await owned.stopping;
    if(stopping||owned!==backend)return;
    setState({mode:'error',message:'工作台未能启动或已意外停止。请重新打开；已有资料会保留。如仍失败，请保留资料目录并联系维护人员。'});
    if(win&&!win.isDestroyed())try{await win.loadURL(setupURL);}catch{}
  } finally {if(!wasBusy)busy=false;}
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
    activeBackend=null;settingsReturn=null;origin='';
    if (backend) await backend.stop();
    if (settings.library_root && !validLibraryRoot(settings.library_root)) throw new Error('LIBRARY_UNAVAILABLE');
    const {executable,args}=runtime();
    backend = new Backend(executable,args);
    const owned=backend;
    owned.on('failed', () => { if (!stopping && backend===owned) void showError(owned); });
    const {model:_persistedModel,model_auto_analysis:_automaticAnalysis,...backendSettings}=settings;
    const ready = await backend.start({data_parent:dataParent,...credentials,...backendSettings});
    origin = `http://127.0.0.1:${ready.port}`;
    activeBackend={instance:owned,origin,workspace:settings.workspace||'main'};
    await win.loadURL(origin+'/login');
    if(activeBackend?.instance!==owned)return {ok:false};
    setState({mode:'ready'});
    // Missing legacy preference uses the default; an explicit false survives restarts.
    if (mainModelSession) await autoConfigureModel({settings,runtime:{configure:model=>
      mainModelSession.configure(model,()=>!stopping&&activeBackend?.instance===owned,
        automaticAnalysisEnabled(settings.model_auto_analysis,model,workspacePath()))}});
    return {ok:true};
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
    const previous=win.webContents.getURL(),owned=activeBackend;
    if(!await leavePage())return;
    if(owned&&activeBackend!==owned)return;
    if(operation==='model-settings') {
      if(previous!==setupURL)settingsReturn=navigationAllowed(previous,origin,'')?{owned,url:previous}:null;
    } else {
      activeBackend=null;settingsReturn=null;origin='';
      if(backend)await backend.stop();
    }
    const messages={backup:'备份当前工作区的全部账户和案件资料。',restore:'从加密备份建立独立核对副本，原工作区保留。',
      'model-settings':'管理主模型与可选 Jev 辅助判断。可开启当前任务材料自动分析，范围外仍需单独确认发送。'};
    setState({mode:operation,message:messages[operation]});
  }finally{busy=false;}
}
async function resume(event){
  if(!isSetup(event)||busy||stopping)return {ok:false};
  const owned=activeBackend;
  if(state.mode!=='model-settings'||!owned||!origin||!backend||backend.closing)return startBackend();
  busy=true;
  try {
    const target=settingsReturn?.owned===owned&&navigationAllowed(settingsReturn.url,origin,'')?settingsReturn.url:origin+'/login';
    await win.loadURL(target);
    if(activeBackend!==owned)return {ok:false};
    setState({mode:'ready'});return {ok:true};
  } catch {await showError();return {ok:false};}
  finally {busy=false;}
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
        if (Object.keys(saved).some(k=>!['library_root','workspace','model','model_auto_analysis'].includes(k)) || (saved.library_root && !path.isAbsolute(saved.library_root))
            || (saved.model!==undefined && !['deepseek-flash','deepseek-v4-pro'].includes(saved.model))
            || (saved.workspace!==undefined && (typeof saved.workspace!=='string'||!/^main$|^recovered\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(saved.workspace)))) throw new Error();
        if(saved.model_auto_analysis!==undefined &&
            !validAutomaticAnalysis(saved.model_auto_analysis,saved.model,path.join(dataParent,'workspaces',saved.workspace||'main')))
          saved.model_auto_analysis=false;
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
    win.webContents.on('did-start-navigation',(_event,_url,_inPlace,isMainFrame)=>{if(isMainFrame)documentEpoch++;});
    win.webContents.on('did-navigate-in-page',(_event,_url,isMainFrame)=>{if(isMainFrame)documentEpoch++;});
    win.webContents.on('did-navigate',(_event,url)=>{
      if(origin&&url===origin+'/login')void personalWeixin?.invalidate();
    });
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
        {label:'Jev 辅助设置…',click:()=>showMaintenance('model-settings')},
        {label:'备份案件资料…',click:()=>showMaintenance('backup')},
        {label:'从备份建立核对副本…',click:()=>showMaintenance('restore')},
        {label:'返回原工作区',click:async()=>{if(!busy&&(await changeSettings({...settings,workspace:'main'})).ok)await startBackend();}},
        {label:'重新打开工作台',click:()=>startBackend()}, {type:'separator'},{role:'quit',label:'退出'}]},
      {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{type:'separator'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
      {label:'视图',submenu:[{role:'resetZoom',label:'恢复字号'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]}
    ]));
    ipcMain.handle('desktop:state',event=>isSetup(event)?state:null);
    ipcMain.handle('desktop:library',event=>isSetup(event)?chooseLibrary():{ok:false});
    ipcMain.handle('desktop:maintenance',runMaintenance);
    const store=createModelCredentialStore({dataParent,safeStorage,platform:process.platform});
    const sessionOptions={getBackend:()=>activeBackend?.instance===backend&&origin&&backend&&!backend.closing&&!activeBackend.workspace.startsWith('recovered/')?backend:null,
      onFailure:async owned=>{if(!stopping&&backend===owned)await showError(owned);}};
    const modelSession=createModelSession({store,...sessionOptions,getWorkspace:workspacePath});
    mainModelSession=modelSession;
    const persistModel=(model,automatic=automaticAnalysisEnabled(settings.model_auto_analysis,settings.model,workspacePath()))=>{
      const next={...settings};delete next.model_auto_analysis;
      if(model)next.model=model;else delete next.model;
      next.model_auto_analysis=automatic?automaticAnalysisPolicy(model,workspacePath()):false;
      try{saveSettings(next);return true;}catch{return false;}
    };
    const settingsFailure=async guard=>({...await modelSession.disable(guard),ok:false,code:'CREDENTIAL_STORAGE_FAILED'});
    const settingsRuntime=Object.freeze({...modelSession,
      configure:async(model,guard,automatic=true)=>{
        if(!persistModel(settings.model,false))return settingsFailure(guard);
        const result=await modelSession.configure(model,guard,automatic);
        if(result?.ok===true&&result.runtime?.state==='configured'&&!persistModel(result.runtime.model,automatic))
          return settingsFailure(guard);
        return result;
      },
      beforeCredentialChange:async guard=>{
        if(!persistModel(settings.model))return settingsFailure(guard);
        return modelSession.beforeCredentialChange(guard);
      },
      disable:async guard=>{
        if(!persistModel(null,false))return settingsFailure(guard);
        return modelSession.disable(guard);
      }});
    const judgeStore=createModelCredentialStore({dataParent,safeStorage,platform:process.platform,provider:'typesafe'});
    const judgeSession=createModelSession({store:judgeStore,...sessionOptions,kind:'judge'});
    const settingsOptions={ipcMain,
      isAllowed:event=>!busy&&!stopping&&state.mode==='model-settings'&&isSetup(event),
      captureGuard:event=>{const epoch=documentEpoch;return ()=>epoch===documentEpoch&&!stopping&&state.mode==='model-settings'&&isSetup(event);},
      setBusy:value=>{busy=value;}};
    const handlers=[registerModelSettings({...settingsOptions,store,runtime:settingsRuntime}),
      registerModelSettings({...settingsOptions,store:judgeStore,runtime:judgeSession,kind:'judge'})];
    // Assistant-page bridge: in-place model status and switch, main frame only.
    const isAssistantPage=event=>{
      const url=win&&!win.isDestroyed()?win.webContents.getURL():'';
      return Boolean(!busy&&!stopping&&state.mode==='ready'&&origin&&url&&
        (url===origin+'/assistant'||url.startsWith(origin+'/assistant/'))&&
        event.sender===win.webContents&&event.senderFrame===win.webContents.mainFrame&&
        event.senderFrame.url===url&&activeBackend?.instance===backend&&!backend.closing&&
        !activeBackend.workspace.startsWith('recovered/'));
    };
    registerAssistantModelBridge({ipcMain,runtime:modelSession,isAllowed:isAssistantPage,persist:persistModel});
    modelSettings={wait:()=>Promise.allSettled(handlers.map(handler=>handler.wait()))};
    approvalWindow=createModelApprovalWindow({BrowserWindow,ipcMain,session});
    const captureContext=(event,{allowHome=false}={})=>{
        const owned=activeBackend,epoch=documentEpoch,url=win?.webContents.getURL();
        const valid=()=>Boolean(win&&!win.isDestroyed()&&!stopping&&state.mode==='ready'&&
          owned&&activeBackend===owned&&owned.instance===backend&&!backend.closing&&origin===owned.origin&&
          !owned.workspace.startsWith('recovered/')&&epoch===documentEpoch&&win.webContents.getURL()===url&&
          event.sender===win.webContents&&event.senderFrame===win.webContents.mainFrame&&event.senderFrame.url===url);
        if(!valid())return null;
        if(allowHome&&url===origin+'/assistant')return {origin,session:isolated,parent:win,backend:owned.instance,
          workspace:owned.workspace,conversation_id:null,guard:valid};
        if(!url.startsWith(origin+'/assistant/'))return null;
        const suffix=url.slice((origin+'/assistant/').length);
        if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(suffix))return null;
        return {origin,session:isolated,parent:win,backend:owned.instance,workspace:owned.workspace,conversation_id:suffix,guard:valid};
      };
    modelApproval=registerModelApproval({ipcMain,runtime:modelSession,judgeRuntime:judgeSession,
      isBusy:()=>busy||stopping,setBusy:value=>{busy=value;},confirm:approvalWindow.confirm,captureContext});
    personalWeixin=registerPersonalWeixin({ipcMain,runtime:modelSession,captureContext:event=>captureContext(event,{allowHome:true})});
    ipcMain.handle('desktop:resume',resume);
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
  approvalWindow?.close();
  if (win && !win.isDestroyed()) win.hide();
  Promise.allSettled([personalWeixin?.close(),backend?.stop(),maintenance?.stop(),modelSettings?.wait(),modelApproval?.wait()]).finally(()=>app.quit());
});
