export const errorText = error=>({
  NETWORK_UNKNOWN:'连接中断，保存结果尚不确定。输入仍在此处，请点击“重试保存”核对。',
  VERSION_CONFLICT:'资料已在另一处更新。请核对两份文字后选择要保留的版本。',
  AUTHORIZATION_REQUIRED:'登录已失效。请重新登录后读取已保存的记录。',
  CROSS_MATTER_DENIED:'当前无权访问此记录，已清除页面内容。',
  BLOCKED_LIVE:'当前副本仅供核对，不能保存或运行任务。',
  STATE_CONFLICT:'保存未完成，请核对输入长度或重新读取记录。',
  REQUEST_FAILED:'请求未完成，请重试或返回工作区。',
}[error?.code] || '请求未完成，输入仍在此处，请重试或返回工作区。');

const runText = {
  queued:'已登记，尚未执行', preparing:'正在准备', routing:'正在选择处理流程',
  retrieving:'正在读取依据', generating:'正在生成', persisting:'正在保存结果',
  completed:'任务已完成', cancelled:'已取消', failed:'执行失败', interrupted:'执行已中断',
  awaiting_input:'等待补充信息', blocked:'已阻断，不能自动续跑',
};
const skillText = {client_reply:'回复客户',material_organize:'整理资料',contract_review:'审查合同',
  content_draft:'创作文案',legal_research:'检索法律资料'};
const node = (tag,text,className)=>{ const element=document.createElement(tag); if(text!==undefined)element.textContent=text;
  if(className)element.className=className; return element; };

export function createRenderer(root=document,{isComposing=()=>false}={}) {
  const byId=id=>root.getElementById(id);
  let previousId=null;
  return {
    state(state,readonly=false) {
      const input=byId('composer');
      if((state.status==='revoked' || !isComposing()) && input.value!==state.text)input.value=state.text;
      input.disabled=readonly || state.loading || state.status==='revoked';
      const messages=state.view?.messages || [];
      const history=byId('history');
      if(previousId!==state.id)history.replaceChildren();
      previousId=state.id;
      const visible=new Set(messages.map(message=>message.id));
      Array.from(history.children).forEach(item=>{if(!visible.has(item.dataset.messageId))item.remove();});
      const existing=new Map(Array.from(history.children).map(item=>[item.dataset.messageId,item]));
      let position=history.firstChild;
      for(const message of messages) {
        let item=existing.get(message.id);
        if(!item) {
          item=node('article',undefined,'message'); item.dataset.messageId=message.id;
          item.append(node('p',message.role==='user'?'律师输入':'已保存的回复 · 需核对','message-meta'),
            node('p',message.content,'message-text'));
        }
        if(item!==position)history.insertBefore(item,position);
        else position=position.nextSibling;
      }
      if(!messages.length)history.replaceChildren();
      document.body.classList.toggle('has-history',messages.length>0);
      byId('home-title').textContent=state.view?.display_title || '今天需要处理什么？';
      const kind=state.view?.scope.scope_kind;
      byId('scope-label').textContent=readonly?'恢复副本 · 只读核对':
        kind==='matter'?'当前范围：关联案件':kind==='intake'?'当前范围：本次接待':'当前范围：本次对话';
      byId('selected-skill').textContent=state.skill?skillText[state.skill]:'自动选择能力';
      byId('clear-skill').hidden=!state.skill;
      root.querySelectorAll('[data-skill]').forEach(button=>{
        button.setAttribute('aria-pressed',String(button.dataset.skill===state.skill));
        button.disabled=readonly || state.loading || state.status==='revoked';
      });
      const labels={idle:'尚未输入',loading:'正在读取记录…',saving:'正在保存…',saved:'草稿已保存到本机',
        error:'尚未确认保存',conflict:'有两份文字需要核对',readonly:'恢复副本仅供核对',revoked:'访问已结束'};
      byId('save-status').textContent=state.dirty && state.status!=='error' && state.status!=='conflict' && state.status!=='saving'
        ?'有尚未保存的输入':labels[state.status] || '';
      byId('notice').textContent=state.error?errorText(state.error):'';
      byId('save-draft').textContent=state.status==='error'?'重试保存':'保存草稿';
      byId('save-draft').disabled=readonly || state.loading || ['saving','conflict','revoked'].includes(state.status);
      byId('older-messages').hidden=!state.view?.next_before;
      byId('older-messages').disabled=state.loading;
      const run=state.view?.latest_run;
      byId('run-status').textContent=run?'最近任务：'+(runText[run.state]||'状态待核对')+(run.cancel_requested && run.state!=='cancelled'?'；已请求取消':''):'';
      byId('refresh-run').hidden=!run;
      byId('refresh-run').disabled=state.loading || state.status==='saving';
      byId('cancel-run').hidden=!run || !['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].includes(run.state);
      byId('cancel-run').disabled=readonly || state.loading || state.status==='saving';
      byId('conflict-panel').hidden=!state.conflict;
      byId('server-draft').textContent=state.conflict?.server || '（服务器草稿为空）';
      byId('new-conversation').disabled=readonly || state.loading || state.status==='saving' || state.status==='revoked';
      byId('send').disabled=true;
      byId('add-material').disabled=true;
    },
    conversations(page,{append=false,selected=null,onSelect}={}) {
      const host=byId('conversation-list');
      if(!append)host.replaceChildren();
      else host.querySelectorAll('p').forEach(element=>element.remove());
      for(const item of page.items) {
        const button=node('button',item.display_title,'conversation-item'); button.type='button';
        button.dataset.conversationId=item.scope.conversation_id;
        if(item.scope.conversation_id===selected)button.setAttribute('aria-current','page');
        button.addEventListener('click',()=>onSelect(item.scope.conversation_id)); host.append(button);
      }
      if(!host.children.length)host.append(node('p','输入后，这里会保留最近记录。','muted'));
      byId('more-conversations').hidden=!page.next_cursor;
    },
    selected(id) {
      root.querySelectorAll('[data-conversation-id].conversation-item').forEach(button=>{
        if(button.dataset.conversationId===id)button.setAttribute('aria-current','page');
        else button.removeAttribute('aria-current');
      });
    },
    capability(catalog) {
      byId('capability-details').textContent=catalog.items?.[0]?.reason || '模型对话与材料上传尚未接入。可以先保存草稿，或进入工作区处理已有材料。';
    },
  };
}
