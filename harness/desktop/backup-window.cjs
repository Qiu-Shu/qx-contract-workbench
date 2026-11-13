const path=require('node:path'),{pathToFileURL}=require('node:url');
function createBackupWindow({app,BrowserWindow,ipcMain,dialog,controller,onClosed=()=>{},canClose=()=>!controller.isBusy()}){
 let window=null;
 const file=path.join(__dirname,'backup.html'),url=pathToFileURL(file).href;
 const titles={backupParent:'选择备份保存位置',bundle:'选择完整备份文件夹',restoreParent:'选择恢复副本位置',reviewRoot:'选择恢复副本',activationParent:'选择启用副本位置'};
 const actions=new Set(['prepareEngine','pause','backup','restore','review','prepare','activate','rollback','resume','openDrafts']);
 const owns=event=>Boolean(window&&!window.isDestroyed()&&event.sender===window.webContents&&
  event.senderFrame===window.webContents.mainFrame&&event.senderFrame.url===url);
 function show(){
  if(window&&!window.isDestroyed()){window.show();window.focus();return;}
  window=new BrowserWindow({width:980,height:880,minWidth:390,minHeight:600,title:'备份与恢复 · AI师兄法律助手平台',
   show:process.env.QX_DESKTOP_HIDDEN!=='1',autoHideMenuBar:true,backgroundColor:'#f7f8f5',
   webPreferences:{preload:path.join(__dirname,'backup-preload.cjs'),sandbox:true,contextIsolation:true,nodeIntegration:false}});
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  window.on('close',event=>{if(!canClose()){event.preventDefault();window.show();}});
  window.on('closed',()=>{window=null;onClosed();});
  void window.loadFile(file);
 }
 async function pick(kind){
  if(!Object.hasOwn(titles,kind)||!window||window.isDestroyed())return null;
  const state=await controller.state();
  const chosen=await dialog.showOpenDialog(window,{title:titles[kind],defaultPath:state.selected?.[kind]||app.getPath('documents'),
   properties:['openDirectory'],dontAddToRecent:true});
  return chosen.canceled?null:chosen.filePaths[0]||null;
 }
 ipcMain.handle('qx:backup-state',event=>owns(event)?controller.state():null);
 ipcMain.handle('qx:backup-choose',(event,kind)=>owns(event)&&Object.hasOwn(titles,kind)?controller.choose(kind):null);
 ipcMain.handle('qx:backup-action',(event,action,input)=>owns(event)&&actions.has(action)?controller.act(action,input):null);
 return {show,pick,isOpen:()=>Boolean(window&&!window.isDestroyed()),getWindow:()=>window};
}
module.exports={createBackupWindow};
