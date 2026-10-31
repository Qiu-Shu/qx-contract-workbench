(() => {
  const variants=[
    {prefix:'model',name:'主模型',models:{'deepseek-flash':'DeepSeek V4.1 Flash','deepseek-v4-pro':'DeepSeek V4 Pro'},initial:'deepseek-flash'},
    {prefix:'judge',name:'Jev',models:{'jev-1.13.0':'Jev 1.13.0'},initial:'jev-1.13.0'}
  ];
  const credentialErrors={
    CREDENTIAL_INPUT_INVALID:'密钥格式不正确，未保存。请重新粘贴单行密钥，原有密钥保留。',
    CREDENTIAL_PATH_UNSAFE:'凭据目录无法安全使用。请联系维护人员核对本机资料目录。',
    CREDENTIAL_CORRUPT:'已保存的凭据无法读取。可以重新输入替换，或移除后再保存。',
    CREDENTIAL_STORAGE_UNAVAILABLE:'当前系统保护不可用，不能保存或读取密钥；可以移除已有凭据。',
    CREDENTIAL_ROTATION_REQUIRED:'已保存的凭据需要维护处理，当前不会自动更改。请联系维护人员。',
    CREDENTIAL_STORAGE_FAILED:'操作未完成。请检查本机资料目录权限和可用空间后重试。',
    ACCESS_DENIED:'当前不能执行此操作，请返回工作台后重新打开模型设置。'
  };
  const runtimeErrors={
    ...credentialErrors,
    BLOCKED_LIVE:'当前不能配置模型。请确认已保存可用密钥，并在正常工作区重新打开设置。',
    MODEL_RUNTIME_FAILED:'无法确认本次运行配置，请重新检查；仍有问题时返回工作台后重新打开设置。',
    JUDGE_RUNTIME_FAILED:'无法确认本次运行配置，请重新检查；仍有问题时返回工作台后重新打开设置。',
    STATE_CONFLICT:'另一项设置操作尚未完成，请稍后重新检查。'
  };
  window.createModelSettingsUI=({api,document,window})=>{
    const at=id=>document.querySelector('#'+id);
    let active=false,epoch=0,busy=false;
    const automatic=at('model-automatic-analysis');
    automatic.checked=true;
    const sections=variants.map(variant=>{
      const section={...variant,at:name=>at(variant.prefix+'-'+name),credential:'loading',runtime:{state:'unavailable',model:null}};
      section.at('id').value=variant.initial;
      return section;
    });
    function clearSecrets() {for(const section of sections)section.at('secret').value='';}
    function controls() {
      const locked=!active||busy;
      for(const section of sections) {
        const {credential,runtime,models}=section,choice=section.at('id'),secret=section.at('secret');
        secret.disabled=locked||['loading','unavailable'].includes(credential);
        section.at('save').disabled=secret.disabled;
        section.at('save').textContent=credential==='saved'?'替换已保存密钥':'保存密钥';
        section.at('remove').disabled=locked||['loading','empty'].includes(credential);
        choice.disabled=locked||runtime.state==='unavailable';
        const sameModel=runtime.state==='configured'&&runtime.model===choice.value&&
          (section.prefix!=='model'||Boolean(runtime.automatic_analysis)===automatic.checked);
        section.at('configure').disabled=locked||credential!=='saved'||runtime.state==='unavailable'||
          !Object.hasOwn(models,choice.value)||sameModel;
        section.at('configure').textContent=sameModel?'本次运行已配置':runtime.state==='configured'?'应用所选模型':'配置本次运行';
        section.at('disable').disabled=locked||runtime.state!=='configured';
        section.at('recheck').disabled=locked;
        section.at('settings').setAttribute('aria-busy',String(busy));
      }
      automatic.disabled=locked||sections[0].credential!=='saved'||sections[0].runtime.state==='unavailable';
      at('model-automatic-limit').textContent='每次分析最多调用 1 次，不设费用上限；费用与未知结果仍会记录。';
      at('resume').disabled=active&&busy;
    }
    function error(node,code,messages) {
      node.hidden=!code;
      node.textContent=code?(typeof code==='string'&&Object.hasOwn(messages,code)?messages[code]
        :'操作未完成，请重新检查；仍有问题时返回工作台后重新打开设置。'):'';
    }
    function showCredential(section,result,operation) {
      section.credential=['empty','saved','unavailable','invalid'].includes(result?.status)?result.status:'unavailable';
      section.at('status').textContent={empty:operation==='remove'?'已移除本机保存的密钥。':`尚未保存${section.name}密钥。`,
        saved:`${section.name}密钥已保存到本机。`,unavailable:'当前无法使用本机凭据保护。',invalid:'本机凭据需要处理。'}[section.credential];
      error(section.at('validation'),result?.code,credentialErrors);
    }
    function showRuntime(section,result) {
      const value=result?.runtime;
      const runtime=value&&['unavailable','unconfigured','configured'].includes(value.state)&&
        (value.state==='configured'?result.ok===true&&typeof value.model==='string'&&Object.hasOwn(section.models,value.model):value.model===null)
        ?{state:value.state,model:value.model,...(section.prefix==='model'&&typeof value.automatic_analysis==='boolean'
          ?{automatic_analysis:value.automatic_analysis}:{})}
          :{state:'unavailable',model:null};
      section.runtime=runtime;
      section.at('runtime-status').textContent=runtime.state==='configured'
        ?`本次运行已配置 ${section.models[runtime.model]}，${section.prefix==='judge'?'尚未批准发送':runtime.automatic_analysis?'已开启当前任务材料自动分析':'可手动发送，当前任务材料自动分析关闭'}。`
        :runtime.state==='unconfigured'?(section.prefix==='judge'?'本次运行未配置 Jev，尚未批准发送。':'本次运行未配置模型。')
          :'当前无法配置本次运行，请返回工作台或重新检查。';
      if(runtime.state==='configured')section.at('id').value=runtime.model;
      if(section.prefix==='model'&&(runtime.state==='configured'||typeof runtime.automatic_analysis==='boolean'))
        automatic.checked=runtime.automatic_analysis===true;
      error(section.at('runtime-validation'),result?.ok===true?null:(result?.code||'MODEL_RUNTIME_FAILED'),runtimeErrors);
    }
    async function action(section,operation,value) {
      if(!active||busy)return;
      if(['save','remove','configure','disable'].includes(operation)&&section.at(operation).disabled)return;
      if(operation==='configure'&&!Object.hasOwn(section.models,value))return;
      const automaticAnalysis=section?.prefix==='model'&&automatic.checked;
      const ticket=++epoch;busy=true;clearSecrets();
      const targets=section?[section]:sections;
      for(const target of targets) {
        target.runtime={state:'unavailable',model:null};
        target.at('runtime-status').textContent=operation==='configure'?'正在配置本次运行…'
          :operation==='disable'?'正在停用本次运行…':'正在检查本次运行配置…';
        error(target.at('runtime-validation'),null,runtimeErrors);
      }
      controls();
      try {
        let result;
        if(operation==='configure'||operation==='disable') {
          try {result=await (operation==='configure'?api[section.prefix+'Configure'](value,automaticAnalysis):api[section.prefix+'Disable']());}
          catch {result={ok:false,runtime:{state:'unavailable',model:null},code:'MODEL_RUNTIME_FAILED'};}
          if(ticket!==epoch||!active)return;
          showRuntime(section,result);return;
        }
        // Both providers share the native control pipe; reads also stay serial.
        for(const target of targets) {
          error(target.at('validation'),null,credentialErrors);
          try {
            const pending=operation==='save'?api[target.prefix+'Save'](value)
              :operation==='remove'?api[target.prefix+'Remove']():api[target.prefix+'Status']();
            value='';result=await pending;
          } catch {result={status:'unavailable',code:'CREDENTIAL_STORAGE_FAILED'};}
          if(ticket!==epoch||!active)return;
          showCredential(target,result,operation);
          try {result=await api[target.prefix+'RuntimeStatus']();}
          catch {result={ok:false,runtime:{state:'unavailable',model:null}};}
          if(ticket!==epoch||!active)return;
          showRuntime(target,result);
        }
      } finally {
        value='';
        if(ticket===epoch){clearSecrets();busy=false;controls();}
      }
    }
    function reset() {epoch++;active=false;busy=false;automatic.checked=true;clearSecrets();controls();}
    for(const section of sections) {
      section.at('settings').addEventListener('submit',event=>{
        event.preventDefault();const value=section.at('secret').value;section.at('secret').value='';return action(section,'save',value);
      });
      section.at('remove').addEventListener('click',()=>action(section,'remove'));
      section.at('recheck').addEventListener('click',()=>action(section,'status'));
      section.at('configure').addEventListener('click',()=>action(section,'configure',section.at('id').value));
      section.at('disable').addEventListener('click',()=>action(section,'disable'));
      section.at('id').addEventListener('change',controls);
    }
    automatic.addEventListener('change',controls);
    for(const name of ['beforeunload','pagehide'])window.addEventListener(name,reset);
    return {
      render(state) {
        for(const section of sections)section.at('settings').hidden=state.mode!=='model-settings';
        if(state.mode!=='model-settings'){reset();return;}
        if(!active){active=true;clearSecrets();for(const section of sections) {
          section.credential='loading';section.runtime={state:'unavailable',model:null};
          section.at('status').textContent='正在检查本机保存状态…';
          section.at('runtime-status').textContent='正在检查本次运行配置…';
          error(section.at('validation'),null,credentialErrors);error(section.at('runtime-validation'),null,credentialErrors);
        }}
        controls();if(!busy)void action(null,'status');
      },
      leave() {if(active&&busy)return false;reset();return true;}
    };
  };
})();
