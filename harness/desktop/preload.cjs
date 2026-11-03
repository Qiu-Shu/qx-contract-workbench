const {contextBridge,ipcRenderer}=require('electron');
const expectedOrigin=process.argv.find(arg=>arg.startsWith('--qx-origin='))?.slice('--qx-origin='.length);
if(process.isMainFrame&&location.origin===expectedOrigin){
  contextBridge.exposeInMainWorld('__DSH_LOCALE__',{
    read:()=>ipcRenderer.invoke('qx:locale'),
    onChange:locale=>ipcRenderer.send('qx:locale-change',locale),
  });
  contextBridge.exposeInMainWorld('__DSH_DIRECTORY_PICKER__',{pick:()=>ipcRenderer.invoke('qx:pick-directory')});
  let pending=false;
  function notice(message){
    if(!message)return;
    let element=document.getElementById('qx-paste-notice');
    if(!element){element=document.createElement('div');element.id='qx-paste-notice';element.setAttribute('role','status');
      Object.assign(element.style,{position:'fixed',bottom:'20px',left:'50%',transform:'translateX(-50%)',padding:'10px 16px',
        background:'#26334a',color:'white',borderRadius:'10px',font:'14px system-ui',zIndex:'10000',maxWidth:'80vw'});document.body.append(element);}
    element.textContent=message;setTimeout(()=>element.remove(),6000);
  }
  // Native File/image clipboard events already work in Harness and remain untouched.
  document.addEventListener('paste',async event=>{
    if(!event.isTrusted||pending||!(event.target instanceof Element)||!event.target.closest('[data-composer-input]'))return;
    if(event.clipboardData?.files.length||event.clipboardData?.getData('text/plain'))return;
    const input=event.target.closest('[data-composer-card]')?.querySelector('input[type="file"]');
    const sessionId=document.documentElement.dataset.qxSessionId;
    if(!input||input.disabled||!sessionId)return;
    const marker=crypto.randomUUID();input.dataset.qxPasteRequest=marker;pending=true;
    try{const result=await ipcRenderer.invoke('qx:paste-files',{marker,sessionId});if(!result.ok)notice(result.message);}
    finally{if(input.dataset.qxPasteRequest===marker)delete input.dataset.qxPasteRequest;pending=false;}
  },true);
}
