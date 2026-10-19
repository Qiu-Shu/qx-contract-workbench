(() => {
  const models={'deepseek-flash':'DeepSeek Flash','deepseek-v4-pro':'DeepSeek V4 Pro'};
  const credentialErrors={
    CREDENTIAL_INPUT_INVALID:'密钥格式不正确，未保存。请重新粘贴单行密钥，原有密钥保留。',
    CREDENTIAL_PATH_UNSAFE:'凭据目录无法安全使用。请联系维护人员核对本机资料目录。',
    CREDENTIAL_CORRUPT:'已保存的凭据无法读取。可以重新输入替换，或移除后再保存。',
    CREDENTIAL_STORAGE_UNAVAILABLE:'当前系统保护不可用，不能保存或读取密钥；可以移除已有凭据。',
    CREDENTIAL_ROTATION_REQUIRED:'已保存的凭据需要维护处理，当前不会自动更改。请联系维护人员。',
    CREDENTIAL_STORAGE_FAILED:'操作未完成。请检查本机资料目录权限和可用空间后重试。',
    ACCESS_DENIED:'当前不能执行此操作，请返回工作台后重新打开主模型设置。'
  };
  const runtimeErrors={
    ...credentialErrors,
    BLOCKED_LIVE:'当前不能配置模型。请确认已保存可用密钥，并在正常工作区重新打开设置。',
    MODEL_RUNTIME_FAILED:'无法确认本次运行配置，请重新检查；仍有问题时返回工作台后重新打开设置。',
    STATE_CONFLICT:'另一项设置操作尚未完成，请稍后重新检查。'
  };
  window.createModelSettingsUI=({api,document,window})=>{
    const at=id=>document.querySelector('#'+id);
    const form=at('model-settings'),secret=at('model-secret'),choice=at('model-id');
    let active=false,epoch=0,busy=false,credential='loading',runtime={state:'unavailable',model:null};
    choice.value='deepseek-flash';
    function controls() {
      const locked=!active||busy;
      secret.disabled=locked||['loading','unavailable'].includes(credential);
      at('model-save').disabled=secret.disabled;
      at('model-save').textContent=credential==='saved'?'替换已保存密钥':'保存密钥';
      at('model-remove').disabled=locked||['loading','empty'].includes(credential);
      choice.disabled=locked||runtime.state==='unavailable';
      const sameModel=runtime.state==='configured'&&runtime.model===choice.value;
      at('model-configure').disabled=locked||credential!=='saved'||runtime.state==='unavailable'||
        !Object.hasOwn(models,choice.value)||sameModel;
      at('model-configure').textContent=sameModel?'本次运行已配置':runtime.state==='configured'?'应用所选模型':'配置本次运行';
      at('model-disable').disabled=locked||runtime.state!=='configured';
      at('model-recheck').disabled=locked;
      at('resume').disabled=active&&busy;
      form.setAttribute('aria-busy',String(busy));
    }
    function error(id,code,messages) {
      const node=at(id);node.hidden=!code;
      node.textContent=code?(Object.hasOwn(messages,code)?messages[code]
        :'操作未完成，请重新检查；仍有问题时返回工作台后重新打开设置。'):'';
    }
    function showCredential(result,operation) {
      credential=['empty','saved','unavailable','invalid'].includes(result?.status)?result.status:'unavailable';
      at('model-status').textContent={empty:operation==='remove'?'已移除本机保存的密钥。':'尚未保存主模型密钥。',
        saved:'主模型密钥已保存到本机。',unavailable:'当前无法使用本机凭据保护。',invalid:'本机凭据需要处理。'}[credential];
      error('model-validation',result?.code,credentialErrors);
    }
    function showRuntime(result) {
      const value=result?.runtime;
      runtime=value&&['unavailable','unconfigured','configured'].includes(value.state)&&
        (value.state==='configured'?result.ok===true&&Object.hasOwn(models,value.model):value.model===null)
        ?{state:value.state,model:value.model}:{state:'unavailable',model:null};
      at('model-runtime-status').textContent=runtime.state==='configured'
        ?`本次运行已配置 ${models[runtime.model]}，尚未授权发送。`
        :runtime.state==='unconfigured'?'本次运行未配置模型。':'当前无法配置本次运行，请返回工作台或重新检查。';
      if(runtime.state==='configured')choice.value=runtime.model;
      error('model-runtime-validation',result?.ok===true?null:(result?.code||'MODEL_RUNTIME_FAILED'),runtimeErrors);
    }
    async function action(operation,value) {
      if(!active||busy)return;
      if((operation==='configure'&&at('model-configure').disabled)||
          (operation==='disable'&&at('model-disable').disabled))return;
      const ticket=++epoch;busy=true;secret.value='';
      runtime={state:'unavailable',model:null};
      at('model-runtime-status').textContent=operation==='configure'?'正在配置本次运行…'
        :operation==='disable'?'正在停用本次运行…':'正在检查本次运行配置…';
      error('model-runtime-validation',null,runtimeErrors);controls();
      try {
        let result;
        if(operation==='configure'||operation==='disable') {
          try {result=await (operation==='configure'?api.modelConfigure(value):api.modelDisable());}
          catch {result={ok:false,runtime:{state:'unavailable',model:null},code:'MODEL_RUNTIME_FAILED'};}
          if(ticket!==epoch||!active)return;
          showRuntime(result);return;
        }
        error('model-validation',null,credentialErrors);
        try {result=await (operation==='save'?api.modelSave(value):operation==='remove'?api.modelRemove():api.modelStatus());}
        catch {result={status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'};}
        if(ticket!==epoch||!active)return;
        showCredential(result,operation);
        try {result=await api.modelRuntimeStatus();}
        catch {result={ok:false,runtime:{state:'unavailable',model:null}};}
        if(ticket!==epoch||!active)return;
        showRuntime(result);
      } finally {
        value='';
        if(ticket===epoch){secret.value='';busy=false;controls();}
      }
    }
    function reset() {epoch++;active=false;busy=false;secret.value='';controls();}
    form.addEventListener('submit',event=>{event.preventDefault();const value=secret.value;secret.value='';return action('save',value);});
    at('model-remove').addEventListener('click',()=>action('remove'));
    at('model-recheck').addEventListener('click',()=>action('status'));
    at('model-configure').addEventListener('click',()=>action('configure',choice.value));
    at('model-disable').addEventListener('click',()=>action('disable'));
    choice.addEventListener('change',controls);
    for(const name of ['beforeunload','pagehide'])window.addEventListener(name,reset);
    return {
      render(state) {
        form.hidden=state.mode!=='model-settings';
        if(form.hidden){reset();return;}
        if(!active){active=true;credential='loading';runtime={state:'unavailable',model:null};
          secret.value='';at('model-status').textContent='正在检查本机保存状态…';
          at('model-runtime-status').textContent='正在检查本次运行配置…';
          error('model-validation',null,credentialErrors);error('model-runtime-validation',null,credentialErrors);}
        controls();if(!busy)void action('status');
      },
      leave() {if(active&&busy)return false;reset();return true;}
    };
  };
})();
