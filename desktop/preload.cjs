const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktopSetup',Object.freeze({
  state:()=>ipcRenderer.invoke('desktop:state'),
  start:values=>ipcRenderer.invoke('desktop:start',values),
  chooseLibrary:()=>ipcRenderer.invoke('desktop:library'),
  maintenance:values=>ipcRenderer.invoke('desktop:maintenance',values),
  modelStatus:()=>ipcRenderer.invoke('desktop:model-status'),
  modelSave:secret=>ipcRenderer.invoke('desktop:model-save',secret),
  modelRemove:()=>ipcRenderer.invoke('desktop:model-remove'),
  modelRuntimeStatus:()=>ipcRenderer.invoke('desktop:model-runtime-status'),
  modelConfigure:model=>ipcRenderer.invoke('desktop:model-configure',model),
  modelDisable:()=>ipcRenderer.invoke('desktop:model-disable'),
  resume:()=>ipcRenderer.invoke('desktop:resume'),
  onState:callback=>ipcRenderer.on('desktop:state',(_event,value)=>callback(value))
}));
