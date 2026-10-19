const form = document.querySelector('#setup');
const retry = document.querySelector('#retry');
const modelForm=document.querySelector('#model-settings'),modelSecret=document.querySelector('#model-secret');
let current,modelEpoch=0,modelBusy=false,modelStatus='loading';
function modelControls() {
  const locked=modelBusy || current?.mode!=='model-settings';
  modelSecret.disabled=locked || ['loading','unavailable'].includes(modelStatus);
  document.querySelector('#model-save').disabled=modelSecret.disabled;
  document.querySelector('#model-save').textContent=modelStatus==='saved'?'替换已保存密钥':'保存密钥';
  document.querySelector('#model-remove').disabled=locked || ['loading','empty'].includes(modelStatus);
  document.querySelector('#model-recheck').disabled=locked;
  document.querySelector('#resume').disabled=modelBusy;
}
async function modelAction(operation,secret) {
  if(current?.mode!=='model-settings' || modelBusy)return;
  const epoch=++modelEpoch;modelBusy=true;modelSecret.value='';modelControls();
  document.querySelector('#model-validation').hidden=true;
  try {
    let result;
    try {result=await (operation==='save'?window.desktopSetup.modelSave(secret):operation==='remove'
      ?window.desktopSetup.modelRemove():window.desktopSetup.modelStatus());}
    catch {result={status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'};}
    if(epoch!==modelEpoch || current?.mode!=='model-settings')return;
    modelStatus=['empty','saved','unavailable','invalid'].includes(result?.status)?result.status:'unavailable';
    document.querySelector('#model-status').textContent={empty:operation==='remove'?'已移除本机保存的密钥。':'未配置主模型密钥。',
      saved:'主模型密钥已保存到本机。',unavailable:'当前无法使用本机凭据保护。',invalid:'本机凭据需要处理。'}[modelStatus];
    const messages={CREDENTIAL_INPUT_INVALID:'密钥格式不正确，未保存。请重新粘贴单行密钥，原有密钥保留。',
      CREDENTIAL_PATH_UNSAFE:'凭据目录无法安全使用。请联系维护人员核对本机资料目录。',
      CREDENTIAL_CORRUPT:'已保存的凭据无法读取。可以重新输入替换，或移除后再保存。',
      CREDENTIAL_STORAGE_UNAVAILABLE:'当前系统保护不可用，不能保存或读取密钥；可以移除已有凭据。',
      CREDENTIAL_ROTATION_REQUIRED:'已保存的凭据需要维护处理，当前不会自动更改。请联系维护人员。',
      CREDENTIAL_STORAGE_FAILED:'操作未完成。请检查本机资料目录权限和可用空间后重试。',
      ACCESS_DENIED:'当前不能执行此操作，请返回工作台后重新打开主模型设置。'};
    const error=document.querySelector('#model-validation');error.hidden=!result?.code;
    error.textContent=result?.code?(messages[result.code] || '操作未完成，请重新打开主模型设置后核对。'):'';
  } finally {
    secret='';
    if(epoch===modelEpoch){modelSecret.value='';modelBusy=false;modelControls();}
  }
}
function render(state) {
  if (!state) return;
  const changedMode=current?.mode!==state.mode;
  if(changedMode){modelEpoch++;modelBusy=false;modelSecret.value='';modelStatus='loading';}
  current = state;
  form.hidden = state.mode !== 'setup';
  retry.hidden = state.mode !== 'error';
  const maintaining=['backup','restore'].includes(state.mode);
  document.querySelector('#maintenance').hidden=!maintaining;
  document.querySelector('#maintenance-result').hidden=state.mode!=='maintenance-done';
  document.querySelector('#resume').hidden=!maintaining&&state.mode!=='maintenance-done'&&state.mode!=='model-settings';
  modelForm.hidden=state.mode!=='model-settings';
  document.querySelector('#backup-confirmation').hidden=state.mode!=='backup';
  document.querySelector('#backup-confirm').required=state.mode==='backup';
  document.querySelector('#maintenance-title').textContent=state.mode==='restore'?'从备份建立核对副本':'案件资料备份';
  document.querySelector('#maintenance-submit').textContent=state.mode==='restore'?'选择备份并恢复':'选择位置并备份';
  document.querySelector('#result-detail').textContent=state.detail||'';
  document.querySelector('#result-path').textContent=state.resultPath||'';
  document.querySelector('#status').textContent = state.message || '';
  document.querySelector('#library-path').textContent = state.library || '尚未连接。已有案例、法规库可直接选择目录。';
  document.querySelector('#data-path').textContent = state.dataParent || '';
  for (const button of document.querySelectorAll('button')) button.disabled = state.mode === 'loading';
  if(state.mode==='model-settings') {
    modelControls();
    if(!modelBusy){document.querySelector('#model-status').textContent='正在检查本机保存状态…';void modelAction('status');}
  }
}
window.desktopSetup.onState(render);
window.desktopSetup.state().then(render);
document.querySelector('#library').addEventListener('click',()=>window.desktopSetup.chooseLibrary());
retry.addEventListener('click',()=>window.desktopSetup.start());
document.querySelector('#resume').addEventListener('click',()=>{modelSecret.value='';return window.desktopSetup.resume();});
modelForm.addEventListener('submit',event=>{event.preventDefault();const secret=modelSecret.value;modelSecret.value='';return modelAction('save',secret);});
document.querySelector('#model-remove').addEventListener('click',()=>{modelSecret.value='';return modelAction('remove');});
document.querySelector('#model-recheck').addEventListener('click',()=>modelAction('status'));
for(const name of ['beforeunload','pagehide'])window.addEventListener(name,()=>{modelEpoch++;modelSecret.value='';});
document.querySelector('#maintenance').addEventListener('submit',async event=>{
  event.preventDefault();const secret=document.querySelector('#backup-secret'),confirm=document.querySelector('#backup-confirm');
  const error=document.querySelector('#backup-validation');
  if(current.mode==='backup'&&secret.value!==confirm.value){error.hidden=false;error.textContent='两次备份口令不一致，请重新输入。';confirm.focus();return;}
  error.hidden=true;const passphrase=secret.value;secret.value='';confirm.value='';
  await window.desktopSetup.maintenance({passphrase});
});
form.addEventListener('submit',async event=>{
  event.preventDefault();
  const error = document.querySelector('#validation');
  const username = document.querySelector('#username').value;
  const password = document.querySelector('#password').value;
  if (username !== username.trim() || !username || /[\p{Cc}\p{Cf}]/u.test(username)) {
    error.hidden = false; error.textContent = '用户名不能有首尾空格或控制字符。'; return;
  }
  if (password !== document.querySelector('#confirm').value) {
    error.hidden = false; error.textContent = '两次密码不一致，请重新输入。'; document.querySelector('#confirm').focus(); return;
  }
  error.hidden = true;
  const pending = window.desktopSetup.start({username,password});
  document.querySelector('#password').value = ''; document.querySelector('#confirm').value = '';
  render({...current,mode:'loading',message:'正在建立账户…'});
  await pending;
});
