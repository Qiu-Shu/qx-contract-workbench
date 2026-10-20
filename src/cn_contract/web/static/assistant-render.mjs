import {renderResearch,researchStatusText} from './assistant-citations.mjs';
export const errorText = error=>({
  NETWORK_UNKNOWN:'连接中断，保存结果尚不确定。输入仍在此处，请点击“重试保存”核对。',
  VERSION_CONFLICT:'资料已在另一处更新。请核对两份文字后选择要保留的版本。',
  AUTHORIZATION_REQUIRED:'登录已失效。请重新登录后读取已保存的记录。',
  CROSS_MATTER_DENIED:'当前无权访问此记录，已清除页面内容。',
  BLOCKED_LIVE:'当前副本仅供核对，不能保存或运行任务。',
  STATE_CONFLICT:'保存未完成，请核对输入长度或重新读取记录。',
  FILE_LIMIT:'材料超过本机接收上限。请缩小文件或分开处理。',
  FILE_UNSUPPORTED:'暂时无法读取这份文件，请选择完整的 DOCX。',
  DATA_POLICY_UNAPPROVED:'此材料尚未获准在当前环境处理，请核对本机处理选项。',
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
const generationCapabilityText = {
  unconfigured:'当前环境未配置或未启用模型生成。可以继续保存本机草稿。',
  unapproved:'这份已保存的文字尚未取得有效的生成授权。请核对授权范围与有效期。',
  empty:'先输入并保存文字，再核对能否生成。',
  unsupported:'当前材料或输入范围不支持生成。含 DOCX 的对话暂不参与模型生成。',
  busy:'当前有任务正在处理，暂不能再次发送。可刷新最近任务状态。',
  budget_exhausted:'本次授权的预算或调用次数已用尽，暂不能发送。',
  restored_read_only:'恢复副本只读，可核对已有结果，不能发送或继续历史任务。',
  ready:'可为这份已保存且获准的文字生成内部草稿；结果仍需律师核对。',
};
const generationErrorText = error=>({
  NETWORK_UNKNOWN:'发送结果尚不确定。请查找发送结果，避免重复发送。',
  NATIVE_CONFIRMATION_FAILED:'本次发送确认未完成，尚未提交生成请求。请刷新记录后重新确认；输入仍保留。',
  INPUT_CHANGED:'输入、材料或当前范围已变化，尚未提交生成请求。请保存后重新确认要发送的文字。',
  NOT_SUPPORTED:'当前选择的能力或材料范围尚未接入生成。',
  BLOCKED_LIVE:'生成未获准。请核对当前环境、授权与预算。',
  AUTHORIZATION_REQUIRED:'登录已失效。请重新登录后核对生成结果。',
  CROSS_MATTER_DENIED:'当前无权访问生成结果，已清除页面内容。',
  VERSION_CONFLICT:'输入或材料版本已变化。请重新读取记录并核对生成条件。',
  STATE_CONFLICT:'当前状态暂不能生成。请刷新记录后核对。',
  MODEL_OUTPUT_INVALID:'已收到响应，但内容未通过校验，未形成可展示草稿。',
  PROVIDER_ERROR:'本次生成未取得可用结果，请核对任务与费用记录。',
}[error?.code] || '生成状态未能确认。请刷新记录后核对。');
const attemptText = {
  reserved:'生成已登记，等待处理。',sending:'正在生成，等待返回。',
  sent_unknown:'发送结果未知，停止自动续发；实际费用仍待核对。',
  received:'已收到响应，未形成可展示的内部草稿。',failed_before_send:'发送前已停止，未生成草稿。',
};
const node = (tag,text,className)=>{ const element=document.createElement(tag); if(text!==undefined)element.textContent=text;
  if(className)element.className=className; return element; };

function renderAttempt(attempt,visible) {
  const section=node('section',undefined,'generation-result');
  section.dataset.attemptId=attempt.id;section.setAttribute('aria-label','生成结果与费用');
  const output=attempt.state==='received' && attempt.output?.audience==='internal' &&
    attempt.output.review_status==='unverified' ? attempt.output : null;
  section.append(node('p',output?'模型生成 · 内部草稿 · 待核对':'模型生成 · 状态记录','generation-meta'));
  if(output) {
    section.append(node('p','未经律师审核，不是正式法律意见。','generation-note'),
      node('p',output.candidate.text,'generation-text'));
    const links=node('div',undefined,'generation-sources');
    for(const citation of output.candidate.citations || []) {
      if(!visible.has(citation.message_id))continue;
      const link=node('a','核对本次输入原文');link.href='#message-'+citation.message_id;
      links.append(link);
    }
    if(links.children.length)section.append(links);
    else section.append(node('p','未提供可定位到当前记录的原文引用。','generation-note'));
  } else section.append(node('p',attemptText[attempt.state] || '生成状态待核对。','generation-note'));
  const receipt=attempt.receipt;
  if(receipt?.error_code)section.append(node('p',generationErrorText({code:receipt.error_code}),'generation-note'));
  const cost=receipt?.cost_status==='estimated' && receipt.estimated_cost_usd!==null
    ?'估算费用 '+receipt.estimated_cost_usd+' USD；实际扣费待核对。'
    :receipt?.cost_status==='not_sent'?'已确认未发送，费用 0 USD。'
      :'费用未知；预算预留 '+attempt.reserved_usd+' USD，不代表实际扣费。';
  section.append(node('p',cost,'generation-cost'));return section;
}

export function createRenderer(root=document,{isComposing=()=>false,onCitation=()=>{}}={}) {
  const byId=id=>root.getElementById(id);
  const renderedAttempts=new WeakMap();
  let previousId=null;
  return {
    state(state,readonly=false) {
      const input=byId('composer');
      if((state.status==='revoked' || !isComposing()) && input.value!==state.text)input.value=state.text;
      input.disabled=readonly || state.loading || state.status==='revoked';
      const revoked=state.status==='revoked';
      const messages=revoked || (state.view?.scope?.conversation_id && state.view.scope.conversation_id!==state.id)
        ?[]:state.view?.messages || [];
      const generation=state.generation,research=state.research;
      const local=state.skill==='legal_research';
      const history=byId('history');
      if(previousId!==state.id)history.replaceChildren();
      previousId=state.id;
      const visible=new Set(messages.map(message=>message.id));
      const visibleKey=Array.from(visible).join(',');
      const attemptsByMessage=new Map();
      for(const item of generation?.items || []) {
        if(!visible.has(item.message_id) || item.attempt.scope?.conversation_id!==state.id)continue;
        if(!attemptsByMessage.has(item.message_id))attemptsByMessage.set(item.message_id,[]);
        attemptsByMessage.get(item.message_id).push(item.attempt);
      }
      Array.from(history.children).forEach(item=>{if(!visible.has(item.dataset.messageId))item.remove();});
      const existing=new Map(Array.from(history.children).map(item=>[item.dataset.messageId,item]));
      let position=history.firstChild;
      for(const message of messages) {
        let item=existing.get(message.id);
        if(!item) {
          item=node('article',undefined,'message'); item.dataset.messageId=message.id;item.id='message-'+message.id;
          item.setAttribute('tabindex','-1');
          item.append(node('p',message.role==='user'?'律师输入':'已保存的回复 · 需核对','message-meta'),
            node('p',message.content,'message-text'));
        }
        const attempts=message.role==='user'?attemptsByMessage.get(message.id) || []:[];
        const searches=(research?.items||[]).filter(item=>item.message_id===message.id).map(item=>item.research);
        const signature=JSON.stringify([visibleKey,attempts,searches]);
        if(renderedAttempts.get(item)!==signature) {
          item.querySelectorAll('.generation-result').forEach(element=>element.remove());
          item.querySelectorAll('.research-result').forEach(element=>element.remove());
          for(const attempt of attempts)item.append(renderAttempt(attempt,visible));
          for(const result of searches)item.append(renderResearch(root,result,onCitation));
          renderedAttempts.set(item,signature);
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
      byId('refresh-run').hidden=!run && generation?.phase!=='error' && research?.phase!=='error';
      byId('refresh-run').disabled=state.loading || state.status==='saving';
      byId('cancel-run').hidden=!run || !['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].includes(run.state);
      byId('cancel-run').disabled=readonly || state.loading || state.status==='saving';
      byId('conflict-panel').hidden=!state.conflict;
      byId('server-draft').textContent=state.conflict?.server || '（服务器草稿为空）';
      byId('new-conversation').disabled=readonly || state.loading || state.status==='saving' || state.status==='revoked';
      const showingResearch=local || ['unknown','error','tracking'].includes(research?.phase);
      const operation=showingResearch?research:generation;
      const phase=operation?.phase || 'idle';
      const nativeConfirmation=!showingResearch && generation?.nativeConfirmation===true;
      byId('send').textContent=local?'本机检索':nativeConfirmation?'确认并发送':'发送';
      byId('send').disabled=(local?research:generation)?.canSend!==true || readonly || state.loading || Boolean(state.skill && !local) ||
        ['saving','conflict','readonly','revoked'].includes(state.status) || ['checking','confirming','submitting','unknown','tracking'].includes(phase);
      byId('generation-note').textContent=revoked?'访问已结束。':readonly || state.status==='readonly'
        ?generationCapabilityText.restored_read_only:local
          ?state.materials?.items?.length?'本机关键词检索暂不接受附件，请先将材料移出本次。': [...state.text].length>200
            ?'关键词超过 200 字。请缩短后检索；原有文字仍保留。':'输入不超过 200 字的关键词，仅查询本机资料库；不会发送给模型。'
          :state.skill?'该能力尚未接入执行。取消选择后可核对普通文字的生成条件。'
          :nativeConfirmation && ['unapproved','ready','budget_exhausted'].includes(generation?.capability?.state)
            ?'点击“确认并发送”后，在原生确认窗口核对完整文字、接收方与费用上限；确认后才发送，结果仍需律师核对。'
            :generationCapabilityText[generation?.capability?.state] || '输入并保存文字后，将核对当前生成条件。';
      const phaseText={checking:'正在核对生成条件…',confirming:'请在原生确认窗口核对本次文字、接收方与费用上限；尚未发送。',submitting:'正在提交生成请求…',
        unknown:'发送结果尚不确定。请查找发送结果，避免重复发送。',tracking:'生成已登记，正在核对结果…'};
      byId('generation-status').textContent=revoked?'':showingResearch?researchStatusText(research):phaseText[phase] ||
        (phase==='error'?generationErrorText(generation?.error):'');
      byId('generation-status').dataset.kind=['unknown','error'].includes(phase)?'error':'';
      byId('recover-generation').hidden=revoked || phase!=='unknown';
      byId('recover-generation').disabled=state.loading || revoked;
      byId('input-help').textContent=(nativeConfirmation?'Enter 打开发送确认，':'Enter 发送，')+'Shift+Enter 换行；'+
        (byId('send').disabled?'当前发送不可用。':local?'发送后查询本机资料。':'发送后生成内部待核草稿。');
      input.placeholder=local?'输入关键词，例如：合成买卖纠纷':'例如：客户遇到了什么问题，需要我们帮忙处理什么……';
      byId('add-material').disabled=readonly || state.loading || ['saving','conflict','revoked'].includes(state.status);
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
      byId('capability-details').textContent='“检索法律资料”支持本机关键词查询，结果保留来源与待核对状态。其他所选能力尚未接入执行；普通文字生成以当前对话的条件为准。';
    },
  };
}
