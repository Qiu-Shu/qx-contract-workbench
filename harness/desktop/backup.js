function createBackupController({api,onState}){
  let state={selected:{},busy:true},loaded=false,pending=false,localError='',operation='';
  const kinds=new Set(['backupParent','bundle','restoreParent','reviewRoot','activationParent']);
  const actions=new Set(['prepareEngine','pause','backup','restore','review','prepare','activate','rollback','resume','openDrafts']);
  const emit=()=>onState({...state,busy:pending||state.busy,loaded,error:localError||state.error||'',operation});
  async function refresh(){
    try{
      const value=await api.state();
      if(!value||typeof value!=='object')throw Error('State unavailable');
      state={selected:{},...value};loaded=true;
    }catch{state={...state,busy:false};localError='无法读取维护状态。请重新打开此窗口后重试。';}
    emit();return state;
  }
  function validate(action,input){
    if(!loaded)return '维护状态尚未读完，请稍后重试。';
    if(!actions.has(action))return '无法识别这项操作，请重新打开此窗口。';
    if(['pause','activate','rollback'].includes(action)&&input.confirm!==true)return '请先勾选确认，再执行这项操作。';
    if(!['prepareEngine','pause'].includes(action)&&!state.maintenance)return '请先确认任务已结束，并停止后台进入维护。';
    if(!['prepareEngine','pause','resume'].includes(action)&&state.stopped===false)return '后台尚未确认停止，请再次停止后台后重试。';
    if(['backup','restore'].includes(action)&&!state.engineReady)return '请先下载并准备备份组件。';
    const needed={backup:['backupParent'],restore:['bundle','restoreParent'],review:['reviewRoot'],prepare:['activationParent']}[action]||[];
    if(needed.some(kind=>!state.selected?.[kind]))return '请先选择本次操作需要的文件夹。';
    if(['backup','restore'].includes(action)){
      if(typeof input.password!=='string'||input.password.length<12||input.password.length>128||/[\r\n\x00]/.test(input.password))return '口令需为 12–128 个字符，不能包含换行。请重新输入。';
      if(action==='backup'&&input.password!==input.passwordConfirm)return '两次输入的备份口令不一致，请重新输入。';
    }
    if(action==='prepare'){
      if(!state.review?.reviewToken||input.reviewToken!==state.review.reviewToken)return '检查结果已变化，请重新检查恢复副本。';
      if((state.review.pending||[]).some(item=>!['hold','draft','cancel'].includes(input.decisions?.[item.id])))return '请为每一项待处理任务选择处理方式。';
    }
    if(action==='activate'&&!state.prepared?.destination)return '请先检查并准备启用副本。';
    if(action==='rollback'&&!state.previousData)return '当前没有可撤回的原资料目录。';
    return '';
  }
  function inputFor(action,input){
    if(action==='backup')return {password:input.password,passwordConfirm:input.passwordConfirm};
    if(action==='restore')return {password:input.password};
    if(['pause','activate','rollback'].includes(action))return {confirm:input.confirm===true};
    if(action==='prepare')return {reviewToken:input.reviewToken,applySettings:input.applySettings===true,
      decisions:Object.fromEntries((state.review.pending||[]).map(item=>[item.id,input.decisions[item.id]]))};
    return {};
  }
  async function perform(run,name){
    pending=true;operation=name;localError='';emit();
    let result;
    try{result=await run();}
    catch{localError='操作未完成。请重新检查所选文件夹和维护状态后重试。';}
    await refresh();
    if(result?.ok===false&&!state.error&&!localError)localError='操作未完成，请查看提示并重试。';
    pending=false;operation='';emit();return result;
  }
  return {
    refresh,
    async choose(kind){
      if(pending||state.busy||!loaded||!kinds.has(kind))return;
      return perform(()=>api.choose(kind),'choose');
    },
    async act(action,input={}){
      if(pending||state.busy&&loaded)return;
      const error=validate(action,input||{});
      if(error){localError=error;emit();return;}
      return perform(()=>api.act(action,inputFor(action,input||{})),action);
    },
  };
}

if(typeof module!=='undefined'&&module.exports)module.exports={createBackupController};

if(typeof document!=='undefined'){
  const $=id=>document.getElementById(id),app=$('backup-app');
  const operations={choose:'正在选择文件夹…',prepareEngine:'正在下载并校验备份组件…',pause:'正在停止后台，请等待维护状态确认…',
    backup:'正在创建并校验加密备份，请保持窗口打开…',restore:'正在恢复并校验独立副本，请保持窗口打开…',review:'正在检查恢复副本…',
    prepare:'正在按你的选择准备启用副本…',activate:'正在确认启用并重新打开程序…',rollback:'正在撤回并重新打开程序…',resume:'正在结束维护并连接工作台…',openDrafts:'正在打开恢复草稿…'};
  const folderIds={backupParent:'backup-parent-path',bundle:'bundle-path',restoreParent:'restore-parent-path',reviewRoot:'review-root-path',activationParent:'activation-parent-path'};
  const folderEmpty={backupParent:'尚未选择保存位置',bundle:'尚未选择备份',restoreParent:'尚未选择恢复位置',reviewRoot:'尚未选择恢复副本',activationParent:'尚未选择启用副本位置'};
  const settingsNames={'desktop-locale':'界面语言','harness-profile':'工作台配置','wechat-preferences':'微信显示与交付偏好'};
  const reauthNames={'model-api-keys':'模型 API Key','wechat-login':'微信账号登录','other-profile-secrets':'其他服务的密钥与登录状态','content-provider-login':'内容来源账号登录'};
  const errors={BACKUP_ENGINE_FAILED:'备份口令不正确，或备份组件未能完成校验。请核对口令和备份文件夹后重试。',
    BACKUP_SOURCE_BUSY:'资料仍被其他程序占用。请关闭正在编辑这些资料的程序后重试。',BACKUP_HOST_BUSY:'后台仍在运行，请等待停止完成后重试。',
    BACKUP_STOP_UNCONFIRMED:'尚未确认后台已停止，请重新进入维护后重试。',BACKUP_FILE_HASH_MISMATCH:'恢复副本的内容已变化。请重新恢复，再进行检查。',
    BACKUP_TARGET_EXISTS:'目标目录已存在，请选择其他位置后重试。',BACKUP_PASSWORD_REQUIRED:'请填写 12–128 个字符的备份口令。',
    BACKUP_POSTGRES_TOOLS_REQUIRED:'此备份包含增强记忆数据，需要准备相应的校验组件后重试。',BACKUP_ENGINE_UNVERIFIED:'备份组件未通过校验，请重新准备组件后重试。',
    BACKUP_PREPARED_CHANGED:'副本已变化或初始化未完成，请重新检查原恢复副本，并准备新的启用副本。'};
  let current={selected:{}},reviewIdentity='',preparedIdentity='',previousIdentity='',wasMaintenance=false,decisions=new Map(),poll;
  function text(id,value){$(id).textContent=typeof value==='string'?value:'';}
  function message(id,value){text(id,value);$(id).hidden=!value;}
  function showTab(name,focus=false){
    for(const tab of document.querySelectorAll('[role=tab]')){
      const selected=tab.id==='tab-'+name;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
      $(tab.getAttribute('aria-controls')).hidden=!selected;if(selected&&focus)tab.focus();
    }
  }
  function renderList(id,values,empty){
    const list=$(id);list.replaceChildren();
    for(const value of values.length?values:[empty]){const item=document.createElement('li');item.textContent=value;list.append(item);}
  }
  function renderReview(review){
    $('review-details').hidden=!review;
    if(!review)return;
    const counts=review.counts||{};
    const summaries=[];
    for(const [name,field,label] of [['fileCount','files','文件'],['databaseCount','databases','数据库'],['settingsCount','settings','设置']]){
      const value=counts[field]??counts[name]??review[name];if(Number.isSafeInteger(value)&&value>=0)summaries.push(`${label} ${value} 项`);
    }
    summaries.push(`待处理任务 ${Array.isArray(review.pending)?review.pending.length:0} 项`);
    text('review-counts',summaries.join(' · '));
    renderList('settings-list',(review.settings||[]).map(item=>settingsNames[item.id]||'其他受支持设置'),'本次没有可迁移的设置。');
    renderList('reauthorization-list',(review.reauthorization||[]).map(item=>reauthNames[item]||'其他服务授权'),'模型 API Key 与账号登录需要重新确认。');
    if(reviewIdentity===review.reviewToken)return;
    reviewIdentity=review.reviewToken;decisions=new Map();$('apply-settings').checked=false;
    const list=$('pending-list');list.replaceChildren();
    if(!review.pending?.length){const empty=document.createElement('p');empty.className='pending-empty';empty.textContent='未发现需要你选择处理方式的任务。';list.append(empty);return;}
    for(const [index,item] of review.pending.entries()){
      const row=document.createElement('div');row.className='pending-item';
      const title=document.createElement('h4');title.textContent=item.label||'待处理任务';row.append(title);
      if(item.preview){const preview=document.createElement('p');preview.className='pending-preview';preview.textContent=String(item.preview);row.append(preview);}
      const label=document.createElement('label');label.htmlFor='pending-choice-'+index;label.textContent='这项任务如何处理';row.append(label);
      const select=document.createElement('select');select.id=label.htmlFor;select.required=true;select.setAttribute('aria-label',`${title.textContent}：处理方式`);
      for(const [value,labelText] of [['','请选择处理方式'],['hold','保留待处理'],['draft','继续为草稿'],['cancel','取消这项任务']]){
        const option=document.createElement('option');option.value=value;option.textContent=labelText;select.append(option);
      }
      select.addEventListener('change',()=>{decisions.set(item.id,select.value);render(current);});row.append(select);list.append(row);
    }
  }
  function render(state){
    current=state;const busy=Boolean(state.busy),ready=state.loaded&&!busy,maintenance=Boolean(state.maintenance),stopped=state.stopped===undefined?maintenance:state.stopped===true,selected=state.selected||{};
    if(wasMaintenance!==maintenance)$('pause-confirm').checked=false;wasMaintenance=maintenance;
    app.setAttribute('aria-busy',String(busy));
    text('data-path',state.data||'资料目录暂不可用');text('maintenance-state',stopped?'后台已停止 · 维护中':maintenance?'维护已锁定 · 待确认后台停止':'后台尚未进入维护');
    text('previous-path',state.previousData||'');$('previous-row').hidden=!state.previousData;$('rollback-section').hidden=!state.previousData;
    $('resume-row').hidden=!maintenance;$('pause-section').hidden=stopped;$('engine-section').hidden=!state.loaded||Boolean(state.engineReady);
    message('busy-message',busy?(operations[state.operation]||'正在读取本机维护状态…'):'');
    message('result-message',!busy&&typeof state.message==='string'?state.message:'');
    const result=state.lastResult,details=[];
    if(result&&typeof result==='object'){
      for(const [name,label] of [['fileCount','文件'],['databaseCount','数据库']])if(Number.isSafeInteger(result[name])&&result[name]>=0)details.push(`${label} ${result[name]} 项`);
      const location=result.destination||result.bundle;if(typeof location==='string')details.push(location);
    }
    message('result-details',!busy&&!state.error?details.join(' · '):'');
    const error=typeof state.error==='string'?state.error:state.error?.code;
    message('error-message',!busy&&error?(errors[error]||(/^[A-Z][A-Z0-9_]+$/.test(error)?'操作未完成。请重新检查所选文件夹和维护状态后重试。':error)):'');
    for(const [kind,id] of Object.entries(folderIds)){text(id,selected[kind]||folderEmpty[kind]);$(id).classList.toggle('empty',!selected[kind]);}
    renderReview(state.review);
    if(!state.review){reviewIdentity='';decisions.clear();}
    const prepared=state.prepared?.destination||'';
    if(prepared!==preparedIdentity){$('activate-confirm').checked=false;preparedIdentity=prepared;}
    if(state.previousData!==previousIdentity){$('rollback-confirm').checked=false;previousIdentity=state.previousData;}
    $('prepared-section').hidden=!prepared;text('prepared-path',prepared);
    for(const control of app.querySelectorAll('input,select,button:not([role=tab])'))control.disabled=!ready;
    for(const field of ['backup-password','backup-password-confirm','restore-password'])$(field).disabled=!ready||!stopped;
    $('pause').disabled=!ready||!$('pause-confirm').checked;$('resume').disabled=!ready||!maintenance;
    $('backup-submit').disabled=!ready||!stopped||!state.engineReady||!selected.backupParent;
    $('restore-submit').disabled=!ready||!stopped||!state.engineReady||!selected.bundle||!selected.restoreParent;
    $('review').disabled=!ready||!stopped||!selected.reviewRoot;
    $('apply-settings').disabled=!ready||!stopped||Boolean(prepared)||!state.review?.settings?.length;
    for(const control of $('pending-list').querySelectorAll('select'))control.disabled=!ready||!stopped||Boolean(prepared);
    $('prepare').disabled=!ready||!stopped||!selected.activationParent||!state.review?.reviewToken||
      (state.review.pending||[]).some(item=>!['hold','draft','cancel'].includes(decisions.get(item.id)));
    $('activate').disabled=!ready||!stopped||!prepared||!$('activate-confirm').checked;
    $('open-drafts').disabled=!ready||!stopped||!prepared;
    $('rollback').disabled=!ready||!stopped||!state.previousData||!$('rollback-confirm').checked;
    clearTimeout(poll);if(state.loaded&&state.busy&&!state.operation)poll=setTimeout(()=>void controller.refresh(),1500);
  }
  const controller=createBackupController({api:window.qxBackup||{state:async()=>{throw Error('Unavailable');}},onState:render});
  for(const tab of document.querySelectorAll('[role=tab]')){
    tab.addEventListener('click',()=>showTab(tab.id.slice(4)));
    tab.addEventListener('keydown',event=>{
      const tabs=[...document.querySelectorAll('[role=tab]')],index=tabs.indexOf(tab);
      const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:null;
      if(next!==null){event.preventDefault();showTab(tabs[next].id.slice(4),true);}
    });
  }
  for(const button of document.querySelectorAll('[data-choose]'))button.addEventListener('click',()=>void controller.choose(button.dataset.choose));
  for(const id of ['pause-confirm','activate-confirm','rollback-confirm'])$(id).addEventListener('change',()=>render(current));
  $('pause').addEventListener('click',()=>void controller.act('pause',{confirm:$('pause-confirm').checked}));
  $('prepare-engine').addEventListener('click',()=>void controller.act('prepareEngine'));
  $('resume').addEventListener('click',()=>void controller.act('resume'));
  $('review').addEventListener('click',()=>void controller.act('review'));
  $('prepare').addEventListener('click',()=>void controller.act('prepare',{reviewToken:current.review?.reviewToken,
    applySettings:$('apply-settings').checked,decisions:Object.fromEntries(decisions)}));
  $('activate').addEventListener('click',()=>void controller.act('activate',{confirm:$('activate-confirm').checked}));
  $('rollback').addEventListener('click',()=>void controller.act('rollback',{confirm:$('rollback-confirm').checked}));
  $('open-drafts').addEventListener('click',()=>void controller.act('openDrafts'));
  $('backup-form').addEventListener('submit',async event=>{
    event.preventDefault();const password=$('backup-password').value,passwordConfirm=$('backup-password-confirm').value;
    const request=controller.act('backup',{password,passwordConfirm});$('backup-password').value='';$('backup-password-confirm').value='';await request;
  });
  $('restore-form').addEventListener('submit',async event=>{
    event.preventDefault();const password=$('restore-password').value;const request=controller.act('restore',{password});$('restore-password').value='';await request;
  });
  window.addEventListener('beforeunload',()=>clearTimeout(poll));
  void controller.refresh();
}
