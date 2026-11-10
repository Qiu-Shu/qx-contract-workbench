const {contextBridge,ipcRenderer}=require('electron');
const expectedOrigin=process.argv.find(arg=>arg.startsWith('--qx-origin='))?.slice('--qx-origin='.length);
const unavailableUrl=process.argv.find(arg=>arg.startsWith('--qx-unavailable='))?.slice('--qx-unavailable='.length);
if(process.isMainFrame&&(location.origin===expectedOrigin||location.href===unavailableUrl)){
  let current={phase:'connected'},host,text,button,busy=false,pagePhase=null;
  let startup=null,startupReceived=false;
  const localPage=location.href===unavailableUrl;
  if(localPage){
    ipcRenderer.on('qx:startup-state',(_event,state)=>{startupReceived=true;startup=state;render()});
    ipcRenderer.invoke('qx:startup-state').then(state=>{if(!startupReceived){startup=state;render()}}).catch(()=>{});
    const timer=setInterval(()=>render(),1000);addEventListener('pagehide',()=>clearInterval(timer),{once:true});
  }
  const labels={
    recovering:['后台连接已断开，正在恢复。请保留当前页面，未发送的内容不会自动重发。',''],
    disconnected:['本机后台暂时无法连接，正在检查。请先保留未发送的内容。','重试连接'],
    ready:['后台已恢复，正在自动连接。当前输入保留，中断的任务不会自动重发。',''],
    'auto-reconnect-failed':['自动连接暂未完成，当前输入仍保留。可以重试连接。','重试连接'],
    failed:['后台未能恢复，已暂停自动重试。请先保留未发送的内容，再重试恢复。','重试恢复'],
    stopped:['后台已停止。如需继续使用，请先保留未发送的内容，再启动后台。','启动后台'],
    'page-loading':['正在打开工作台，请稍候…',''],
    'load-timeout':['界面尚未加载完成。可以重新连接；已保存的聊天和材料会保留。','重新连接'],
    'page-empty':['界面显示中断。请重新连接，已保存的聊天和材料会保留。','重新连接'],
  };
  function render(){
    if(!document.body)return;
    if(localPage){
      const heading=document.getElementById('qx-startup-heading'),detail=document.getElementById('qx-startup-detail');
      const retry=document.getElementById('qx-startup-retry'),logs=document.getElementById('qx-startup-logs');
      if(!heading||!retry)return;
      const active=startup&&startup.phase!=='failed';
      const stages={checking:'正在检查本机连接。',starting:'正在准备本机服务。首次启动或更新后可能需要更长时间。',connecting:'正在等待本机服务就绪。连接成功后会自动进入工作台。',opening:'本机服务已就绪，正在打开工作台。'};
      heading.textContent=active?'正在打开工作台':'本机服务暂未连接';
      detail.textContent=active?(stages[startup.phase]||'正在连接…'):startup?.errorCode==='SERVICE_UNAVAILABLE'
        ?'后台进程已运行，但工作台组件未就绪。请打开运行日志查看组件加载错误，再重试连接。'
        :startup?.errorCode==='HOST_EXITED'?'本机服务启动时退出了。请打开运行日志查看原因，再重试连接。'
        :'暂时无法连接本机服务。可以重试连接，或打开运行日志查看原因。';
      retry.disabled=Boolean(active||busy);retry.textContent=retry.disabled?'正在连接…':'重试连接';
      const seconds=startup?.startedAt?Math.max(0,Math.floor((Date.now()-startup.startedAt)/1000)):0;
      document.getElementById('qx-startup-time').textContent=active?`已等待 ${seconds} 秒${seconds>=20?' · 仍在准备，可打开日志查看进展':''}`:'';
      if(!retry.dataset.bound){
        retry.dataset.bound='1';retry.addEventListener('click',async()=>{
          if(busy)return;busy=true;render();
          try{await ipcRenderer.invoke('qx:reconnect')}finally{busy=false;render()}
        });
        logs.addEventListener('click',()=>void ipcRenderer.invoke('qx:open-logs').catch(()=>{}));
      }
      return;
    }
    if(!host?.isConnected){
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
    const label=labels[current?.phase]||labels[pagePhase];host.hidden=!label;
    if(!label)return;
    text.textContent=label[0];button.textContent=busy?'正在连接…':label[1];button.hidden=!label[1];button.disabled=busy;
  }
  let received=false;
  ipcRenderer.on('qx:connection-state',(_event,state)=>{received=true;current=state;render()});
  ipcRenderer.invoke('qx:connection-state').then(state=>{if(!received&&state){current=state;render()}}).catch(()=>{});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',render,{once:true});else render();
  if(location.origin===expectedOrigin){
    let hadContent=false,timedOut=false,pending;
    const reported=new Set();
    const report=(phase,extra={})=>{
      const key=phase+':'+(extra.reason||'')+':'+(extra.errorName||'');
      if(reported.has(key))return;reported.add(key);
      ipcRenderer.send('qx:page-state',{phase,...extra});
    };
    function inspectPage(){
      const root=document.getElementById('root');
      if(!root&&!hadContent)return;
      const content=Boolean(root&&(root.childElementCount||root.textContent.trim()));
      const next=content?null:hadContent?'page-empty':timedOut?'load-timeout':'page-loading';
      if(content&&!hadContent){hadContent=true;report('page-ready');}
      if(next!==pagePhase){pagePhase=next;if(next)report(next);render();}
    }
    function watchPage(){
      inspectPage();
      const observer=new MutationObserver(records=>{
        const root=document.getElementById('root');
        if(!records.some(r=>r.target===root||[...r.addedNodes,...r.removedNodes].some(n=>n.id==='root')))return;
        clearTimeout(pending);pending=setTimeout(inspectPage,200);
      });
      observer.observe(document.body,{childList:true,subtree:true});
      const timeout=setTimeout(()=>{timedOut=true;inspectPage();},15000);
      addEventListener('pagehide',()=>{observer.disconnect();clearTimeout(timeout);clearTimeout(pending);},{once:true});
    }
    // Page content and exception messages can contain client material; log types only.
    addEventListener('error',event=>{
      const reason=event.target instanceof HTMLScriptElement?'script-resource':event instanceof ErrorEvent?'script-error':null;
      if(!reason)return;
      const errorName=['TypeError','SyntaxError','ReferenceError','RangeError','URIError'].includes(event.error?.name)?event.error.name:'Error';
      report('page-error',{reason,errorName});
    },true);
    addEventListener('unhandledrejection',()=>report('page-error',{reason:'promise-error'}));
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',watchPage,{once:true});else watchPage();
  }
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
