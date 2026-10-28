(() => {
  const at=id=>document.getElementById(id),api=window.desktopApproval;
  const cancel=at('approval-cancel'),confirm=at('approval-confirm');
  const judgeSection=at('approval-judge'),judgeSelect=at('approval-judge-select');
  const models={'deepseek-flash':'DeepSeek Flash','deepseek-v4-pro':'DeepSeek V4 Pro'};
  const budget=value=>typeof value==='string'&&/^(0|[1-9]\d{0,6})(\.\d{1,12})?$/.test(value)&&
    /[1-9]/.test(value)&&(Number(value.split('.')[0])<1000000||/^1000000(?:\.0{1,12})?$/.test(value));
  let loaded=false,pending=false,gone=false,judgeOffered=false,judgeAvailable=false;
  at('approval-profile').hidden=true;
  judgeSelect.checked=false;judgeSelect.disabled=true;judgeSection.hidden=true;
  async function decide(value) {
    if(gone||pending||(value&&!loaded))return;
    pending=true;cancel.disabled=true;confirm.disabled=true;judgeSelect.disabled=true;
    try {if(await api.decide(value)===true)return;}catch{}
    if(gone)return;
    loaded=false;pending=false;cancel.disabled=false;cancel.focus({preventScroll:true});
    at('approval-status').textContent='本次确认已失效，请取消后回到工作台重新发送。';
  }
  cancel.addEventListener('click',()=>decide(false));
  confirm.addEventListener('click',()=>decide(judgeOffered?{main:true,judge:judgeAvailable&&judgeSelect.checked===true}:true));
  window.addEventListener('pagehide',()=>{
    gone=true;loaded=false;judgeSelect.checked=false;judgeSelect.disabled=true;
    for(const id of ['approval-content','approval-profile-target','approval-profile-intake'])at(id).textContent='';
  });
  Promise.resolve().then(()=>api.state()).then(value=>{
    if(gone)return;
    if(value?.kind==='material_business'){
      const manifest=value.basis?.manifest;
      if(!manifest||value.basis.input_format!=='material-business-v1'||!Array.isArray(manifest.materials)||
          !Array.isArray(manifest.sources)||!Object.hasOwn(models,value.model)||!budget(value.max_total_usd))throw Error();
      at('approval-intro').textContent=manifest.materials.length===0?'本次仅咨询文字，发送给下列模型后生成待核接待草稿。取消不会发送。':'本次将发送下列选中材料的可读原文、读取范围和问题，生成有出处的律师待核草稿。取消不会调用模型。';
      if(manifest.conversation_history?.length)
        at('approval-intro').textContent+='同时包含下列同任务历史问答（最多最近8轮、32KiB），历史回答仍待核对。';
      at('approval-text-title').textContent='本次问题与全部发送片段';
      const list=at('approval-sources-list');
      for(const file of manifest.materials){
        const item=document.createElement('li');
        item.textContent=`${file.name} · 解析版本 ${file.parse_revision} · ${file.reading_status==='partial'?'部分可读':'可读'} · 未读部分：${file.unread_parts.join('、')||'无已登记未读部分'} · 原件 ${file.original_sha256}`;
        list.append(item);
      }
      at('approval-sources').hidden=false;
      at('approval-sources-title').textContent=`本次选中的材料（${manifest.materials.length} 份）`;
    } else if(value?.kind==='profile_draft'){
      // The isolated window receives a fully validated basis from the main process.
      // Recheck the fields used for display before enabling a decision.
      const basis=value.basis,uuid=v=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(v);
      if(Object.keys(value).length!==6||
          !['kind','content','basis','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
          typeof value.content!=='string'||!value.content.trim()||!Object.hasOwn(models,value.model)||
          value.recipient!=='DeepSeek（api.deepseek.com）'||!budget(value.max_total_usd)||
          !basis||basis.purpose!=='reply_and_profile_draft'||basis.handler_id!=='profile.save'||
          !Number.isSafeInteger(basis.base_profile_revision)||basis.base_profile_revision<0||
          typeof basis.project_intake!=='boolean'||
          !(basis.expected_intake_id===null&&basis.expected_intake_revision===null||
            uuid(basis.expected_intake_id)&&Number.isSafeInteger(basis.expected_intake_revision)&&basis.expected_intake_revision>0))throw Error();
      at('approval-profile-target').textContent=`本次对话的档案草稿 · 当前版本 ${basis.base_profile_revision}`;
      at('approval-profile-intake').textContent=!basis.project_intake?'本次不同步接待记录。':
        basis.expected_intake_id?`尝试同步至已关联接待 · 当前版本 ${basis.expected_intake_revision} · 标识 ${basis.expected_intake_id}`:
          '有可用于接待的字段并形成有效变更时，尝试创建接待草稿；没有变更时不新建。';
      at('approval-profile').hidden=false;
      at('approval-intro').textContent=basis.conversation_history?.length?
        '本次发送包含下列同会话历史与当前文字，最多最近8轮、32KiB历史。只包含确认窗列出的内容；档案提案仍只引用当前文字，本机附件与法库资料不随此请求发送。':
        '只发送下列本次文字；本次未包含历史问答。历史过长或没有可用的同会话完整问答时不自动带入。本机附件与法库资料不会随本次请求发送。';
    } else if(value?.kind==='library_context'){
      if(Object.keys(value).length!==6||
          !['kind','content','sources','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
          typeof value.content!=='string'||!value.content.trim()||!Object.hasOwn(models,value.model)||
          value.recipient!=='DeepSeek（api.deepseek.com）'||!budget(value.max_total_usd)||
          !Array.isArray(value.sources)||!value.sources.length||value.sources.length>8)throw Error();
      const list=at('approval-sources-list');
      for(const source of value.sources){
        if(!source||typeof source!=='object'||Array.isArray(source)||Object.keys(source).length!==5||
            typeof source.title!=='string'||!source.title.trim()||
            !['case_csv','law_markdown'].includes(source.kind)||
            !Number.isSafeInteger(source.line_start)||!Number.isSafeInteger(source.line_end)||
            source.line_start<1||source.line_end<source.line_start)throw Error();
        const item=document.createElement('li');
        item.textContent=`${source.title} · ${source.kind==='law_markdown'?'法规':'案例'} · 第 ${source.line_start}–${source.line_end} 行 · 待核对`;
        list.append(item);
      }
      at('approval-sources').hidden=false;
      at('approval-sources-title').textContent=`随问题发送的已保存片段（${value.sources.length} 条）`;
      at('approval-intro').textContent='只发送下列问题与所列已保存片段；本机原附件与其他内容不会发送。结果保存为内部待核草稿。';
      at('approval-text-title').textContent='本次发送的问题全文';
    } else if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).length!==(Object.hasOwn(value,'judge')?5:4)||
        Object.hasOwn(value,'kind')||
        !['content','model','max_total_usd','recipient'].every(key=>Object.hasOwn(value,key))||
        typeof value.content!=='string'||!value.content.trim()||!Object.hasOwn(models,value.model)||
        value.recipient!=='DeepSeek（api.deepseek.com）'||!budget(value.max_total_usd))throw Error();
    if(Object.hasOwn(value,'judge')){
      const judge=value.judge;
      if(!judge||typeof judge!=='object'||Array.isArray(judge)||Object.keys(judge).length!==2||
          !Object.hasOwn(judge,'available')||!Object.hasOwn(judge,'max_total_usd')||typeof judge.available!=='boolean'||
          (judge.available?!budget(judge.max_total_usd):judge.max_total_usd!==null))throw Error();
      judgeOffered=true;judgeAvailable=judge.available;judgeSection.hidden=false;
      judgeSelect.checked=false;judgeSelect.disabled=!judgeAvailable;
      at('approval-judge-budget').textContent=judgeAvailable?
        `程序将预留 USD ${judge.max_total_usd} 预算；这不是供应商收费上限，实际费用尚未核对。`:
        'Jev 辅助判断尚未启用，本次不会发送给 TypeSafe；你仍可确认主模型发送。';
    }
    const history=value.kind==='material_business'?value.basis.manifest.conversation_history:
      value.kind==='profile_draft'?value.basis.conversation_history:null;
    const previous=history?.length?history.map(item=>`${item.role==='user'?'历史提问':'历史回答（待核）'} · 输入版本 ${item.source_revision}\n${item.content}`).join('\n\n')+'\n\n本次文字\n':'';
    at('approval-content').textContent=previous+value.content+(value.kind==='material_business'?'\n\n'+
      value.basis.manifest.sources.map(s=>'['+s.source_id+']\n'+(s.reference.anchor?.quote??s.reference.quote)).join('\n\n'):'');
    at('approval-recipient').textContent=value.recipient;
    at('approval-model').textContent=`${models[value.model]}（${value.model}）`;
    at('approval-budget').textContent=`USD ${value.max_total_usd}（本次一次调用）`;
    at('approval-status').textContent='请核对接收方、完整文字与程序预算，再决定是否发送。';
    loaded=true;confirm.disabled=false;cancel.disabled=false;cancel.focus({preventScroll:true});
  }).catch(()=>{
    if(gone)return;
    at('approval-status').textContent='确认内容无法读取，请取消后重新尝试发送。';
    cancel.disabled=false;cancel.focus({preventScroll:true});
  });
})();
