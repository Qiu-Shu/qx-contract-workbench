(() => {
  const at=id=>document.getElementById(id),api=window.desktopApproval;
  const cancel=at('approval-cancel'),confirm=at('approval-confirm');
  const judgeSection=at('approval-judge'),judgeSelect=at('approval-judge-select');
  const models={'deepseek-flash':'DeepSeek Flash','deepseek-v4-pro':'DeepSeek V4 Pro'};
  const budget=value=>typeof value==='string'&&/^(0|[1-9]\d{0,6})(\.\d{1,12})?$/.test(value)&&
    /[1-9]/.test(value)&&(Number(value.split('.')[0])<1000000||/^1000000(?:\.0{1,12})?$/.test(value));
  let loaded=false,pending=false,gone=false,judgeOffered=false,judgeAvailable=false;
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
  window.addEventListener('pagehide',()=>{gone=true;loaded=false;judgeSelect.checked=false;judgeSelect.disabled=true;at('approval-content').textContent='';});
  Promise.resolve().then(()=>api.state()).then(value=>{
    if(gone)return;
    if(value?.kind==='library_context'){
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
    at('approval-content').textContent=value.content;
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
