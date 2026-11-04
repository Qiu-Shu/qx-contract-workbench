const {contextBridge,ipcRenderer}=require('electron');
const expectedOrigin=process.argv.find(arg=>arg.startsWith('--qx-origin='))?.slice('--qx-origin='.length);
const unavailableUrl=process.argv.find(arg=>arg.startsWith('--qx-unavailable='))?.slice('--qx-unavailable='.length);
if(process.isMainFrame&&(location.origin===expectedOrigin||location.href===unavailableUrl)){
  let current={phase:'connected'},host,text,button,busy=false;
  const labels={
    recovering:['后台连接已断开，正在恢复。请保留当前页面，未发送的内容不会自动重发。',''],
    disconnected:['本机后台暂时无法连接，正在检查。请先保留未发送的内容。','重试连接'],
    ready:['后台已恢复。请先复制未发送的文字，再重新连接。中断的任务不会自动重发。','重新连接'],
    failed:['后台未能恢复，已暂停自动重试。请先保留未发送的内容，再重试恢复。','重试恢复'],
    stopped:['后台已停止。如需继续使用，请先保留未发送的内容，再启动后台。','启动后台'],
  };
  function render(){
    if(!document.body)return;
    if(!host){
      host=document.createElement('div');host.id='qx-connection-notice';host.hidden=true;
      Object.assign(host.style,{position:'fixed',top:'12px',right:'16px',width:'min(560px, calc(100vw - 32px))',zIndex:'2147483000'});
      const shadow=host.attachShadow({mode:'open'}),style=document.createElement('style');
      style.textContent=':host([hidden]){display:none}.notice{box-sizing:border-box;display:flex;align-items:center;gap:16px;padding:12px 16px;background:#fff7dc;color:#4b3c15;border:1px solid #c9a750;border-radius:8px;font:14px/1.6 system-ui,sans-serif;box-shadow:0 3px 12px #1b243018}.message{flex:1;min-width:0;overflow-wrap:anywhere}button{flex-shrink:0;min-height:40px;padding:7px 12px;border:1px solid #93751d;border-radius:5px;background:#fffdf5;color:#4b3c15;font:inherit;cursor:pointer}button:hover{background:#f7eab9}button:focus-visible{outline:2px solid #394d78;outline-offset:3px}button:disabled{cursor:wait;opacity:.7}button[hidden]{display:none}@media(max-width:480px){.notice{align-items:flex-start;flex-direction:column;gap:8px;padding:12px}button{align-self:flex-end}}';
      const notice=document.createElement('div');notice.className='notice';
      text=document.createElement('span');text.className='message';text.setAttribute('role','status');text.setAttribute('aria-live','polite');
      button=document.createElement('button');button.type='button';
      button.addEventListener('click',async()=>{
        if(busy)return;busy=true;render();
        try{const result=await ipcRenderer.invoke('qx:reconnect');if(!result?.ok&&!result?.cancelled)current={phase:'failed'};}
        catch{current={phase:'failed'}}finally{busy=false;render()}
      });
      notice.append(text,button);shadow.append(style,notice);document.body.append(host);
    }
    const label=labels[current?.phase];host.hidden=!label;
    if(!label)return;
    text.textContent=label[0];button.textContent=busy?'正在连接…':label[1];button.hidden=!label[1];button.disabled=busy;
  }
  let received=false;
  ipcRenderer.on('qx:connection-state',(_event,state)=>{received=true;current=state;render()});
  ipcRenderer.invoke('qx:connection-state').then(state=>{if(!received&&state){current=state;render()}}).catch(()=>{});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});else render();
}
if(process.isMainFrame&&location.origin===expectedOrigin){
  contextBridge.exposeInMainWorld('__QX_UPDATES__',{
    read:()=>ipcRenderer.invoke('qx:update-state'),
    act:action=>['check','download','cancel','install'].includes(action)?ipcRenderer.invoke('qx:update-action',action):Promise.resolve(null),
    subscribe:listener=>{
      const handler=(_event,state)=>listener(state);ipcRenderer.on('qx:update-state',handler);
      return()=>ipcRenderer.removeListener('qx:update-state',handler);
    },
  });
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
