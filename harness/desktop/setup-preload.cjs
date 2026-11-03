const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('setup',{
  save:key=>ipcRenderer.invoke('qx:setup-save',key),
  openKeys:()=>ipcRenderer.invoke('qx:setup-keys'),
});
