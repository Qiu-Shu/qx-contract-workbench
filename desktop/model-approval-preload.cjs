const {contextBridge,ipcRenderer}=require('electron');
const selection=value=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===2&&
  Object.hasOwn(value,'main')&&Object.hasOwn(value,'judge')&&value.main===true&&typeof value.judge==='boolean';
contextBridge.exposeInMainWorld('desktopApproval',Object.freeze({
  state:()=>ipcRenderer.invoke('desktop:approval-state'),
  decide:value=>typeof value==='boolean'?ipcRenderer.invoke('desktop:approval-decision',value):
    selection(value)?ipcRenderer.invoke('desktop:approval-decision',{main:true,judge:value.judge}):Promise.resolve(false)
}));
