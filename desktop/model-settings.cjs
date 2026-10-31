const statuses=new Set(['empty','saved','unavailable','invalid']);
const codes=new Set(['CREDENTIAL_INPUT_INVALID','CREDENTIAL_PATH_UNSAFE','CREDENTIAL_CORRUPT',
  'CREDENTIAL_STORAGE_UNAVAILABLE','CREDENTIAL_STORAGE_FAILED','CREDENTIAL_ROTATION_REQUIRED']);
const denied=()=>({status:'unavailable',code:'ACCESS_DENIED'});
const unavailable=()=>({status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'});
const runtimeCodes=new Set([...codes,'ACCESS_DENIED','BLOCKED_LIVE','STATE_CONFLICT','VERSION_CONFLICT',
  'BUDGET_EXCEEDED','CROSS_MATTER_DENIED']);
const runtimeDenied=(code='BLOCKED_LIVE')=>({ok:false,runtime:{state:'unavailable',model:null},code});
const check=guard=>{try{return guard()===true;}catch{return false;}};
function runtimeResult(result,kind) {
  const state=result?.runtime?.state,model=result?.runtime?.model;
  if(typeof result?.ok!=='boolean' || !['unavailable','unconfigured','configured'].includes(state) ||
      (state==='configured' ? !(kind==='judge'?['jev-1.13.0']:['deepseek-flash','deepseek-v4-pro']).includes(model) : model!==null))return runtimeDenied();
  return {ok:result.ok,runtime:{state,model,
    ...(kind==='main' && result.ok && ((state==='configured' && result.runtime.automatic_analysis===true) ||
      (state==='unconfigured' && typeof result.runtime.automatic_analysis==='boolean'))
      ?{automatic_analysis:result.runtime.automatic_analysis}:{})},
    ...(runtimeCodes.has(result.code)?{code:result.code}:{})};
}

function registerModelSettings({ipcMain,store,runtime,isAllowed,isCurrent,captureGuard,setBusy,kind='main'}) {
  if(!['main','judge'].includes(kind))throw new TypeError('MODEL_KIND_INVALID');
  const prefix=kind==='judge'?'judge':'model';
  let pending=null;
  async function run(event,operation,value,modelOperation=false,automaticAnalysis=false) {
    const deny=()=>modelOperation ? runtimeDenied('ACCESS_DENIED') : denied();
    if(pending || !check(()=>isAllowed(event)))return deny();
    let guard;
    try{guard=captureGuard ? captureGuard(event) : ()=>isCurrent ? isCurrent(event) : true;}
    catch{return deny();}
    if(typeof guard!=='function' || !check(guard))return deny();
    setBusy(true);
    const task=Promise.resolve().then(async()=>{
      if(!check(guard))return deny();
      if(modelOperation){
        if(!runtime)return runtimeDenied();
        if(typeof automaticAnalysis!=='boolean' || (kind==='judge'&&automaticAnalysis))return runtimeDenied();
        const result=await (operation==='configure' ? runtime.configure(value,guard,automaticAnalysis) : runtime[operation](guard));
        return check(guard) ? runtimeResult(result,kind) : deny();
      }
      if(operation!=='status' && runtime){
        const cleared=await runtime.beforeCredentialChange(guard);
        if(!check(guard))return deny();
        if(cleared?.ok!==true)return unavailable();
      }
      if(!check(guard))return deny();
      const result=await (operation==='save' ? store.save(value) : store[operation]());
      if(!check(guard))return deny();
      if(!statuses.has(result?.status))return unavailable();
      return {status:result.status,...(codes.has(result.code)?{code:result.code}:{})};
    });
    pending=task;
    try{return await task;}
    catch{return modelOperation ? runtimeDenied() : unavailable();}
    finally{value='';pending=null;setBusy(false);}
  }
  ipcMain.handle(`desktop:${prefix}-status`,event=>run(event,'status'));
  ipcMain.handle(`desktop:${prefix}-save`,(event,secret)=>run(event,'save',secret));
  ipcMain.handle(`desktop:${prefix}-remove`,event=>run(event,'remove'));
  ipcMain.handle(`desktop:${prefix}-runtime-status`,event=>run(event,'status',undefined,true));
  ipcMain.handle(`desktop:${prefix}-configure`,(event,model,automaticAnalysis=kind==='main')=>run(event,'configure',model,true,automaticAnalysis));
  ipcMain.handle(`desktop:${prefix}-disable`,event=>run(event,'disable',undefined,true));
  return {wait:()=>Promise.allSettled([pending,store.drain?.()])};
}
module.exports={registerModelSettings};
