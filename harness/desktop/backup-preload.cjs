const {contextBridge,ipcRenderer}=require('electron');
const kinds=new Set(['backupParent','bundle','restoreParent','reviewRoot','activationParent']);
const actions=new Set(['prepareEngine','pause','backup','restore','review','prepare','activate','rollback','resume','openDrafts']);
contextBridge.exposeInMainWorld('qxBackup',Object.freeze({
  state:()=>ipcRenderer.invoke('qx:backup-state'),
  choose:kind=>kinds.has(kind)?ipcRenderer.invoke('qx:backup-choose',kind):Promise.resolve(null),
  act:(action,input)=>actions.has(action)?ipcRenderer.invoke('qx:backup-action',action,input):Promise.resolve(null),
}));
