const fs=require('node:fs'),path=require('node:path'),{randomUUID}=require('node:crypto');
const locations=require('./data-location.cjs'),runtime=require('./backup-runtime.cjs');
function fail(code){throw Object.assign(Error(code),{code});}
function createBackupController(options){
 const {anchor,data,payload}=options;
 function recoverySelection(){try{return locations.readSelection(anchor);}catch{return null;}}
 const local=()=>require(path.join(payload,'desktop-runner/local-backup.cjs'));
 const activation=()=>require(path.join(payload,'desktop-runner/restore-activation.cjs'));
 const invoke={backup:request=>local().createLocalBackup(request),restore:request=>local().restoreLocalBackup(request),
  inspect:request=>activation().inspectRestoreActivation(request),prepare:request=>activation().prepareRestoreActivation(request),
  initialize:target=>require('./installed-runtime.cjs').initializePreparedRestore(payload,target),
  select:target=>locations.selectDataLocation(anchor,target),rollback:()=>options.selectionError&&!recoverySelection()?.previousData?locations.returnToOriginalData(anchor):locations.rollbackDataLocation(anchor),
  prepareEngine:()=>runtime.prepareEngine({anchor,payload}),engineReady:()=>runtime.engineReady(anchor),...options};
 let maintenance=Boolean(options.selectionError),stopped=false,busy=false,review=null,prepared=null,error=options.selectionError?'资料目录暂不可用，请进入维护后撤回原目录。':'',message='',lastResult=null;
 const selected={};
 const kinds=new Set(['backupParent','bundle','restoreParent','reviewRoot','activationParent']);
 function previous(){const selected=recoverySelection();return selected?.previousData||(options.selectionError?anchor:null);}
 async function state(){return {data,previousData:previous(),maintenance,stopped,busy,engineReady:invoke.engineReady(),selected:{...selected},review,prepared,credentialStatus:await options.credentialStatus(),error,message,lastResult};}
 const target=kind=>{if(!selected[kind])fail('BACKUP_PATH_REQUIRED');const parent=locations.normalized(selected[kind]);if(!fs.statSync(parent).isDirectory())fail('BACKUP_INVALID_PATH');return parent;};
 const newFolder=(kind,name)=>path.join(target(kind),name+'-'+new Date().toISOString().slice(0,10)+'-'+randomUUID().slice(0,8));
 const configuration=()=>({data,python:path.join(payload,'runtime/python/python.exe'),restic:runtime.enginePath(anchor),pgTools:runtime.findPgTools(data,payload)});
 async function perform(operation){
  if(busy)return {ok:false};busy=true;error='';message='';
  try{await operation();return {ok:true};}
  catch(cause){error=/^(BACKUP|RESTORE|LOCATION)_[A-Z_]+$/.test(cause.code)?cause.code:'操作未完成，请检查目录、后台状态和可用空间后重试。';return {ok:false};}
  finally{busy=false;}
 }
 async function choose(kind){return perform(async()=>{
  if(!kinds.has(kind))fail('BACKUP_INVALID_ACTION');const picked=await options.pick(kind);if(!picked)return;
  const directory=locations.normalized(picked);if(!fs.statSync(directory).isDirectory())fail('BACKUP_INVALID_PATH');selected[kind]=directory;
  if(kind==='reviewRoot'){review=null;prepared=null;}if(kind==='activationParent')prepared=null;
 });}
 async function act(action,input={}){return perform(async()=>{
  if(!input||typeof input!=='object'||Array.isArray(input))fail('BACKUP_INVALID_ACTION');
  if(['pause','activate','rollback'].includes(action)&&input.confirm!==true)fail('BACKUP_CONFIRM_REQUIRED');
  if(action==='prepareEngine'){await invoke.prepareEngine();message='备份组件已准备并校验。';return;}
  if(action==='pause'){
   if(options.isStarting?.())fail('BACKUP_HOST_BUSY');maintenance=true;stopped=false;options.setMaintenance(true);
   await options.stop();stopped=true;message='后台已停止，可以备份、恢复和检查资料。';return;
  }
  if(!maintenance)fail('BACKUP_MAINTENANCE_REQUIRED');
  if(action==='resume'){
   if(options.selectionError)fail('LOCATION_MISSING');
   maintenance=false;stopped=false;options.setMaintenance(false);await options.resume();message='维护已结束。';return;
  }
  if(!stopped)fail('BACKUP_STOP_UNCONFIRMED');
  if(['backup','restore'].includes(action)){
   if(!invoke.engineReady())fail('BACKUP_ENGINE_UNVERIFIED');
   if(typeof input.password!=='string'||input.password.length<12||input.password.length>128||/[\r\n\x00]/.test(input.password))fail('BACKUP_PASSWORD_REQUIRED');
   if(action==='backup'){
    if(input.password!==input.passwordConfirm)fail('BACKUP_PASSWORD_MISMATCH');const bundle=newFolder('backupParent','backup');
    lastResult={...await invoke.backup({...configuration(),bundle,password:input.password}),action,bundle};message='加密备份已创建，并完成读回校验。';
   }else{
    const destination=newFolder('restoreParent','restore');
    lastResult={...await invoke.restore({...configuration(),bundle:target('bundle'),destination,password:input.password}),action,destination};
    selected.reviewRoot=destination;review=null;prepared=null;message='已恢复到独立目录，请继续检查与启用。';
   }return;
  }
  if(action==='review'){review=null;prepared=null;review=await invoke.inspect({...configuration(),root:target('reviewRoot'),payload});message='恢复副本检查完成，请核对设置和待处理任务。';return;}
  if(action==='prepare'){
   if(!review||input.reviewToken!==review.reviewToken)fail('BACKUP_REVIEW_STALE');
   if(!input.decisions||typeof input.decisions!=='object'||Array.isArray(input.decisions)||(review.pending||[]).some(item=>!['hold','draft','cancel'].includes(input.decisions[item.id])))fail('BACKUP_PENDING_CHOICE_INVALID');
   prepared=null;const destination=newFolder('activationParent','ready');
   prepared=await invoke.prepare({...configuration(),root:target('reviewRoot'),destination,payload,reviewToken:review.reviewToken,applySettings:input.applySettings===true,decisions:input.decisions});
   lastResult={action,destination};message='启用副本已准备。确认启用后程序会重新打开，账号需要重新连接。';return;
  }
  if(action==='activate'){
   if(!prepared?.destination)fail('BACKUP_RESTORE_NOT_PREPARED');await invoke.initialize(prepared.destination);
   await invoke.select(prepared.destination);options.relaunch();return;
  }
  if(action==='rollback'){await invoke.rollback();options.relaunch();return;}
  if(action==='openDrafts'){
   const root=prepared?.destination||data;const folder=locations.normalized(path.join(root,'workspace/drafts'));
   if(!fs.existsSync(folder))fail('BACKUP_NO_DRAFTS');await options.openDrafts(folder);return;
  }
  fail('BACKUP_INVALID_ACTION');
 });}
 return {state,choose,act,isBusy:()=>busy,isMaintenance:()=>maintenance};
}
module.exports={createBackupController};
