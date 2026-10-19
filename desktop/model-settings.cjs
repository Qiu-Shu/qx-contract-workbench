const statuses=new Set(['empty','saved','unavailable','invalid']);
const codes=new Set(['CREDENTIAL_INPUT_INVALID','CREDENTIAL_PATH_UNSAFE','CREDENTIAL_CORRUPT',
  'CREDENTIAL_STORAGE_UNAVAILABLE','CREDENTIAL_STORAGE_FAILED','CREDENTIAL_ROTATION_REQUIRED']);
const denied=()=>({status:'unavailable',code:'ACCESS_DENIED'});
const unavailable=()=>({status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'});

function registerModelSettings({ipcMain,store,isAllowed,setBusy}) {
  let pending=null;
  async function run(event,operation,secret) {
    if(pending || !isAllowed(event))return denied();
    setBusy(true);
    const task=Promise.resolve().then(()=>operation==='save'?store.save(secret):store[operation]());
    pending=task;
    try {
      const result=await task;
      if(!statuses.has(result?.status))return unavailable();
      return {status:result.status,...(codes.has(result.code)?{code:result.code}:{})};
    } catch {return unavailable();}
    finally {secret='';pending=null;setBusy(false);}
  }
  ipcMain.handle('desktop:model-status',event=>run(event,'status'));
  ipcMain.handle('desktop:model-save',(event,secret)=>run(event,'save',secret));
  ipcMain.handle('desktop:model-remove',event=>run(event,'remove'));
  return {wait:()=>Promise.allSettled([pending,store.drain?.()])};
}
module.exports={registerModelSettings};
