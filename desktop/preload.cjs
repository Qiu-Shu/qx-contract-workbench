const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktopSetup',Object.freeze({
  state:()=>ipcRenderer.invoke('desktop:state'),
  start:values=>ipcRenderer.invoke('desktop:start',values),
  chooseLibrary:()=>ipcRenderer.invoke('desktop:library'),
  onState:callback=>ipcRenderer.on('desktop:state',(_event,value)=>callback(value))
}));
