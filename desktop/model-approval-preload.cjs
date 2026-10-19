const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('desktopApproval',Object.freeze({
  state:()=>ipcRenderer.invoke('desktop:approval-state'),
  decide:value=>typeof value==='boolean'?ipcRenderer.invoke('desktop:approval-decision',value):Promise.resolve(false)
}));
