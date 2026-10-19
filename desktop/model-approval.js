(() => {
  const at=id=>document.getElementById(id),api=window.desktopApproval;
  const cancel=at('approval-cancel'),confirm=at('approval-confirm');
  const models={'deepseek-flash':'DeepSeek Flash','deepseek-v4-pro':'DeepSeek V4 Pro'};
  let loaded=false,pending=false,gone=false;
  async function decide(value) {
    if(gone||pending||(value&&!loaded))return;
    pending=true;cancel.disabled=true;confirm.disabled=true;
    try {if(await api.decide(value)===true)return;}catch{}
    if(gone)return;
    loaded=false;pending=false;cancel.disabled=false;cancel.focus({preventScroll:true});
    at('approval-status').textContent='本次确认已失效，请取消后回到工作台重新发送。';
  }
  cancel.addEventListener('click',()=>decide(false));
  confirm.addEventListener('click',()=>decide(true));
  window.addEventListener('pagehide',()=>{gone=true;loaded=false;at('approval-content').textContent='';});
  Promise.resolve().then(()=>api.state()).then(value=>{
    if(gone)return;
    if(!value||typeof value.content!=='string'||!Object.hasOwn(models,value.model)||
        value.recipient!=='DeepSeek（api.deepseek.com）'||typeof value.max_total_usd!=='string')throw Error();
    at('approval-content').textContent=value.content;
    at('approval-recipient').textContent=value.recipient;
    at('approval-model').textContent=`${models[value.model]}（${value.model}）`;
    at('approval-budget').textContent=`USD ${value.max_total_usd}（本次一次调用）`;
    at('approval-status').textContent='请核对完整文字与费用上限，再决定是否发送。';
    loaded=true;confirm.disabled=false;cancel.disabled=false;cancel.focus({preventScroll:true});
  }).catch(()=>{
    if(gone)return;
    at('approval-status').textContent='确认内容无法读取，请取消后重新尝试发送。';
    cancel.disabled=false;cancel.focus({preventScroll:true});
  });
})();
