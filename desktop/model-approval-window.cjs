const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const {canonicalProfileBasis}=require('./profile-basis.cjs');

function approvalDetails(value) {
  const budget=value=>typeof value==='string'&&/^(0|[1-9]\d{0,6})(\.\d{1,12})?$/.test(value)&&
    /[1-9]/.test(value)&&(Number(value.split('.')[0])<1000000||/^1000000(?:\.0{1,12})?$/.test(value));
  if(value?.kind==='profile_draft'){
    if(Object.keys(value).length!==6||
        !['kind','content','basis','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
        typeof value.content!=='string'||!value.content.trim()||Buffer.byteLength(value.content,'utf8')>65536||
        !['deepseek-flash','deepseek-v4-pro'].includes(value.model)||value.recipient!=='DeepSeek（api.deepseek.com）'||
        !budget(value.max_total_usd))return null;
    const basis=canonicalProfileBasis(value.basis);
    if(!basis)return null;
    return {kind:'profile_draft',content:value.content,basis,model:value.model,
      max_total_usd:value.max_total_usd,recipient:value.recipient};
  }
  if(value?.kind==='library_context'){
    if(Object.keys(value).length!==6||
        !['kind','content','sources','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
        typeof value.content!=='string'||!value.content.trim()||Buffer.byteLength(value.content,'utf8')>65536||
        !['deepseek-flash','deepseek-v4-pro'].includes(value.model)||value.recipient!=='DeepSeek（api.deepseek.com）'||
        !budget(value.max_total_usd)||!Array.isArray(value.sources)||!value.sources.length||value.sources.length>8)return null;
    const sources=[];
    for(const source of value.sources){
      if(!source||typeof source!=='object'||Array.isArray(source)||Object.keys(source).length!==5||
          !['saved_citation_id','title','kind','line_start','line_end'].every(key=>Object.hasOwn(source,key))||
          typeof source.saved_citation_id!=='string'||
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(source.saved_citation_id)||
          typeof source.title!=='string'||!source.title.trim()||source.title.length>2000||
          !['case_csv','law_markdown'].includes(source.kind)||
          !Number.isSafeInteger(source.line_start)||!Number.isSafeInteger(source.line_end)||
          source.line_start<1||source.line_end<source.line_start)return null;
      sources.push({saved_citation_id:source.saved_citation_id,title:source.title,kind:source.kind,
        line_start:source.line_start,line_end:source.line_end});
    }
    return {kind:'library_context',content:value.content,sources,model:value.model,
      max_total_usd:value.max_total_usd,recipient:value.recipient};
  }
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==(Object.hasOwn(value,'judge')?5:4)||
      Object.hasOwn(value,'kind')||
      !['content','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
      typeof value.content!=='string'||!value.content.trim()||Buffer.byteLength(value.content,'utf8')>65536||
      !['deepseek-flash','deepseek-v4-pro'].includes(value.model)||value.recipient!=='DeepSeek（api.deepseek.com）'||
      !budget(value.max_total_usd))return null;
  const snapshot={content:value.content,model:value.model,max_total_usd:value.max_total_usd,recipient:value.recipient};
  if(Object.hasOwn(value,'judge')){
    const judge=value.judge;
    if(!judge||typeof judge!=='object'||Array.isArray(judge)||Object.keys(judge).length!==2||
        !Object.hasOwn(judge,'available')||!Object.hasOwn(judge,'max_total_usd')||typeof judge.available!=='boolean'||
        (judge.available?!budget(judge.max_total_usd):judge.max_total_usd!==null))return null;
    snapshot.judge={available:judge.available,max_total_usd:judge.max_total_usd};
  }
  return snapshot;
}

function createModelApprovalWindow({BrowserWindow,ipcMain,session}) {
  const url=pathToFileURL(path.join(__dirname,'model-approval.html')).href;
  const assets=new Set(['model-approval.html','model-approval.css','model-approval.js'].map(
    file=>pathToFileURL(path.join(__dirname,file)).href));
  let active=null;
  const current=job=>{try{return !job.parent.isDestroyed()&&job.guard()===true;}catch{return false;}};
  function finish(job,approved=false) {
    if(active!==job)return;
    active=null;clearTimeout(job.timeout);clearInterval(job.poll);
    for(const [source,event,listener] of job.listeners)source.removeListener(event,listener);
    if(job.window&&!job.window.isDestroyed())job.window.destroy();
    job.details=null;
    if(job.isolated){
      try {job.isolated.webRequest.onBeforeRequest(null);}catch{}
      for(const clear of ['clearStorageData','clearCache'])
        try {void job.isolated[clear]().catch(()=>{});}catch{}
    }
    job.resolve(approved);
  }
  function allowed(event) {
    const job=active,win=job?.window;
    if(!win||win.isDestroyed()||event.sender!==win.webContents||
        event.senderFrame!==win.webContents.mainFrame||event.senderFrame?.url!==url||win.webContents.getURL()!==url)return false;
    if(!current(job)){finish(job);return false;}
    return true;
  }
  ipcMain.handle('desktop:approval-state',(event,...extra)=>{
    if(extra.length||!allowed(event))return null;
    active.presented=true;return active.details;
  });
  ipcMain.handle('desktop:approval-decision',(event,value,...extra)=>{
    if(extra.length||!allowed(event))return false;
    let selection=value;
    if(Object.hasOwn(active.details,'judge')){
      if(value!==false){
        if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==2||
            !Object.hasOwn(value,'main')||!Object.hasOwn(value,'judge')||value.main!==true||
            typeof value.judge!=='boolean'||(value.judge&&!active.details.judge.available))return false;
        selection={main:true,judge:value.judge};
      }
    }else if(typeof value!=='boolean')return false;
    if(selection!==false&&!active.presented)return false;
    finish(active,selection);return true;
  });
  function confirm({parent,details,guard}) {
    const snapshot=approvalDetails(details);
    if(active||!snapshot||typeof guard!=='function'||!current({parent,guard}))return Promise.resolve(false);
    return new Promise(resolve=>{
      const job={parent,guard,details:snapshot,resolve,listeners:[],presented:false};active=job;
      const listen=(source,event,listener)=>{source.on(event,listener);job.listeners.push([source,event,listener]);};
      const cancel=()=>finish(job);
      try {
        const isolated=session.fromPartition('qx-approval-'+randomUUID(),{cache:false});job.isolated=isolated;
        isolated.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
        isolated.setPermissionCheckHandler(()=>false);
        isolated.webRequest.onBeforeRequest({urls:['<all_urls>']},(request,callback)=>callback({cancel:!assets.has(request.url)}));
        listen(isolated,'will-download',event=>event.preventDefault());
        const win=new BrowserWindow({parent,modal:true,width:640,height:snapshot.judge||snapshot.kind?700:540,minWidth:640,minHeight:540,
          show:false,title:'确认本次发送 · 群兴法律工作台',backgroundColor:'#f2f5f8',autoHideMenuBar:true,
          webPreferences:{preload:path.join(__dirname,'model-approval-preload.cjs'),session:isolated,
            sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true,webviewTag:false}});job.window=win;
        win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
        for(const name of ['will-navigate','will-frame-navigate','will-redirect','will-attach-webview'])
          listen(win.webContents,name,event=>event.preventDefault());
        listen(win.webContents,'did-navigate',(_event,target)=>{if(target!==url)cancel();});
        listen(win.webContents,'did-fail-load',cancel);listen(win.webContents,'render-process-gone',cancel);
        listen(win.webContents,'before-input-event',(event,input)=>{
          if(input.type==='keyDown'&&input.key==='Escape'){event.preventDefault();cancel();}
        });
        listen(win,'closed',cancel);listen(parent,'closed',cancel);listen(parent.webContents,'destroyed',cancel);
        listen(win,'ready-to-show',()=>{if(active===job&&current(job))win.show();else cancel();});
        job.poll=setInterval(()=>{if(!current(job))cancel();},250);
        job.timeout=setTimeout(cancel,120000);
        void win.loadURL(url).catch(cancel);
      } catch {cancel();}
    });
  }
  return {confirm,close:()=>{if(active)finish(active);}};
}
module.exports={createModelApprovalWindow};
