import {renderResearch,researchStatusText} from './assistant-citations.mjs';
import {savedCitations} from './assistant-context.mjs';
export const errorText = error=>({
  NETWORK_UNKNOWN:'连接中断，本次保存尚未确认。输入仍保留在当前页面，请点“重试保存”核对结果。',
  VERSION_CONFLICT:'资料已在另一处更新。请核对两份文字后选择要保留的版本。',
  AUTHORIZATION_REQUIRED:'登录已失效。请重新登录后读取已保存的记录。',
  CROSS_MATTER_DENIED:'当前无权访问此记录，已清除页面内容。',
  BLOCKED_LIVE:'当前副本仅供核对，不能保存或运行任务。',
  STATE_CONFLICT:'保存未完成，请核对输入长度或重新读取记录。',
  ARCHIVE_UNKNOWN:'删除结果尚未确认。请点该记录的“查询删除结果”，确认前保留当前页面。',
  PERSONAL_WEIXIN_CONNECTED:'该对话仍连接本人微信。请返回该聊天，先断开连接，再删除对话。',
  ASSISTANT_BUSY:'该对话有正在处理的任务。请先停止任务并刷新状态，再删除对话。',
  MATERIAL_INPUT_TOO_LARGE:'选中的完整材料超出本次模型输入上限。请减少选中的材料后重试，不会自动截断发送。',
  MATERIAL_NOT_READABLE:'有材料尚未读取，请先解析并核对读取范围。',
  FILE_LIMIT:'材料超过本机接收上限。请缩小文件或分开处理。',
  FILE_UNSUPPORTED:'暂时无法读取这份文件，请选择完整的 DOCX。',
  DATA_POLICY_UNAPPROVED:'此材料尚未获准在当前环境处理，请核对当前环境的材料处理范围。',
  REQUEST_FAILED:'请求未完成，请重试或返回工作区。',
}[error?.code] || '请求未完成，输入仍在此处，请重试或返回工作区。');

const runText = {
  queued:'已登记，尚未执行', preparing:'正在准备', routing:'正在选择处理流程',
  retrieving:'正在读取依据', generating:'正在生成', persisting:'正在保存结果',
  completed:'任务已完成', cancelled:'已取消', failed:'执行失败', interrupted:'执行已中断',
  awaiting_input:'等待补充信息', blocked:'已阻断，不能自动续跑',
};
const skillText = {client_reply:'回复客户',material_organize:'整理资料',contract_review:'审查合同',
  content_draft:'创作文案',legal_research:'检索法律资料',mock_trial:'庭审准备'};
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
  MATERIAL_INPUT_TOO_LARGE:'完整材料与来源信息超过本次模型输入上限。请减少所选材料后重试；不会截断或自动重发。',
  PROVIDER_ERROR:'本次生成未取得可用结果，请核对任务与费用记录。',
}[error?.code] || '生成状态未能确认。请刷新记录后核对。');
const attemptText = {
  reserved:'生成已登记，等待处理。',sending:'正在生成，等待返回。',
  sent_unknown:'发送结果未知，停止自动续发；实际费用仍待核对。',
  received:'已收到响应，未形成可展示的内部草稿。',failed_before_send:'发送前已停止，未生成草稿。',
};
const contextPhaseText = {
  checking:'正在核对将发送的内容…',
  confirming:'正在核对本次问题、资料范围与模型设置…',
  submitting:'正在提交资料辅助回答…',
  unknown:'发送结果尚不确定。请查找发送结果，避免重复发送。',
  tracking:'资料辅助回答已登记，正在核对结果…',
};
const contextErrorText = error=>({
  NETWORK_UNKNOWN:'发送结果尚不确定。请查找发送结果，避免重复发送。',
  NATIVE_CONFIRMATION_FAILED:'本次发送确认未完成，尚未提交请求。请重新核对将发送的内容后再次确认；输入仍保留。',
  INPUT_CHANGED:'输入或选片已变化，尚未提交请求。请重新核对将发送的内容。',
  NOT_SUPPORTED:'当前材料或输入范围不支持资料辅助回答。',
  BLOCKED_LIVE:'发送未获准。请核对当前环境、授权与预算。',
  AUTHORIZATION_REQUIRED:'登录已失效。请重新登录后核对结果。',
  CROSS_MATTER_DENIED:'所选片段不属于当前范围，已清除选择。',
  VERSION_CONFLICT:'输入或材料版本已变化。请重新读取记录并核对。',
  STATE_CONFLICT:'当前状态暂不能发送。请刷新记录后核对。',
}[error?.code] || '发送状态未能确认。请刷新记录后核对。');
const node = (tag,text,className)=>{ const element=document.createElement(tag); if(text!==undefined)element.textContent=text;
  if(className)element.className=className; return element; };

function renderAttempt(attempt,visible,onCitation) {
  const section=node('section',undefined,'generation-result');
  section.dataset.attemptId=attempt.id;section.setAttribute('aria-label','生成结果与费用');
  const output=attempt.state==='received' && attempt.output?.audience==='internal' &&
    attempt.output.review_status==='unverified' ? attempt.output : null;
  const materialBound=attempt.input_format==='material-business-v1';
  const sourceBound=attempt.input_format==='library-context-v1' || attempt.input_format==='library-context-v2';
  section.append(node('p',output?(materialBound?'材料分析 · 有出处的律师待核草稿':sourceBound?'资料辅助回答 · 内部草稿 · 待核对':'模型生成 · 内部草稿 · 待核对'):'模型生成 · 状态记录','generation-meta'));
  if(output) {
    let readableText=output.candidate.text;
    const displayedCitations=materialBound?[...new Set([...(output.candidate.citations||[]),
      ...(output.manifest?.sources||[]).filter(source=>readableText.includes('['+source.source_id+']')).map(source=>source.source_id)])]
      :output.candidate.citations||[];
    if(materialBound)for(const [index,id] of displayedCitations.entries())
      readableText=readableText.split('['+id+']').join('【来源 '+(index+1)+'】');
    section.append(node('p','未经律师审核，不是正式法律意见。','generation-note'),
      node('p',readableText,'generation-text'));
    const links=node('div',undefined,'generation-sources');
    for(const citation of displayedCitations) {
      if(materialBound){
        const source=output.manifest?.sources?.find(s=>s.source_id===citation);
        if(!source)continue;
        if(source.reference.kind==='message'){
          const detail=node('details');detail.append(node('summary',`来源 ${displayedCitations.indexOf(citation)+1} · 聊天原始陈述`),node('p',source.reference.quote,'generation-text'));links.append(detail);continue;
        }
        const file=output.manifest.materials.find(f=>f.attachment_id===source.reference.attachment_id);
        const number=displayedCitations.indexOf(citation)+1;
        const detail=node('details'),summary=node('summary',`来源 ${number} · ${file?.name||'材料'} · 原文出处`);
        detail.append(summary,node('p',source.reference.anchor.quote,'generation-text'),node('small',`解析版本 ${source.reference.parse_revision}`));links.append(detail);continue;
      }
      if(citation.saved_citation_id) {
        const button=node('button','核对已保存片段','citation-link');button.type='button';
        button.setAttribute('aria-label','核对本次回答引用的已保存片段');
        button.addEventListener('click',()=>onCitation(citation.saved_citation_id,button));
        links.append(button);continue;
      }
      if(!visible.has(citation.message_id))continue;
      const link=node('a','核对本次输入原文');link.href='#message-'+citation.message_id;
      links.append(link);
    }
    if(links.children.length)section.append(links);
    else section.append(node('p','未提供可定位到当前记录的原文引用。','generation-note'));
    if(materialBound){
      const download=node('a','下载可编辑草稿（DOCX）','text-button');
      download.href='/api/assistant/conversations/'+encodeURIComponent(attempt.scope.conversation_id)+
        '/material-generations/'+encodeURIComponent(attempt.id)+'/document';
      download.download='材料分析草稿.docx';section.append(download);
    }
  } else section.append(node('p',attemptText[attempt.state] || '生成状态待核对。','generation-note'));
  if(attempt.input_format==='profile-text-v1' && output) {
    const saved=attempt.profile_save,receipt=saved?.receipt;
    let text='档案保存状态尚未确认，请重新读取记录。';
    if(saved?.outcome==='blocked')text='本次档案草稿未保存；回答已保留，请核对资料后再处理。';
    else if(receipt?.conversation_id===attempt.scope.conversation_id &&
        Number.isSafeInteger(receipt.profile_revision) && receipt.profile_revision>=0) {
      if(saved?.outcome==='applied' && receipt.event_type==='profile.saved') {
        text=receipt.profile_changed?`档案草稿已更新 · 版本 ${receipt.profile_revision} · 待核对。`:'档案内容无需更新。';
        if(receipt.projection_changed && Number.isSafeInteger(receipt.intake_revision) && receipt.intake_revision>0)
          text+=` 接待草稿已更新 · 版本 ${receipt.intake_revision}。`;
      } else if(saved?.outcome==='unchanged' && receipt.event_type==='profile.unchanged')
        text=`档案无需更新 · 版本 ${receipt.profile_revision}；未新增修订。`;
    }
    section.append(node('p',text,'generation-note'));
  }
  const receipt=attempt.receipt;
  if(receipt?.error_code)section.append(node('p',generationErrorText({code:receipt.error_code}),'generation-note'));
  const cost=receipt?.cost_status==='estimated' && receipt.estimated_cost_usd!==null
    ?'估算费用 '+receipt.estimated_cost_usd+' USD；实际扣费待核对。'
    :receipt?.cost_status==='not_sent'?'已确认未发送，费用 0 USD。'
      :'费用未知；预算预留 '+attempt.reserved_usd+' USD，不代表实际扣费。';
  section.append(node('p',cost,'generation-cost'));return section;
}

export function createRenderer(root=document,{isComposing=()=>false,onCitation=()=>{},
    onToggleCitation=()=>{},onPreviewContext=()=>{},onGenerateMaterial=()=>{}}={}) {
  const byId=id=>root.getElementById(id);
  const renderedAttempts=new WeakMap();
  let previousId=null;
  function drawContextPanel(state,readonly) {
    const panel=byId('context-panel');
    if(!panel)return;
    const context=state.context;
    const revoked=state.status==='revoked';
    const show=!readonly && !revoked && root.body.dataset.libraryEnabled==='true';
    panel.hidden=!show;
    if(!show)return;
    const host=byId('context-citations');
    const selected=context?.selected || [];
    const busy=state.loading || ['saving','conflict'].includes(state.status) ||
      ['checking','confirming','submitting','unknown'].includes(context?.phase);
    const items=savedCitations(state);
    host.replaceChildren();
    if(!items.length)host.append(node('p','尚无已保存的引用片段。先用“检索法律资料”查询，片段保存后即可在此选择。','muted'));
    for(const citation of items) {
      const checked=selected.includes(citation.id);
      const label=node('label',undefined,'context-citation');
      const box=node('input');box.type='checkbox';box.checked=checked;
      box.disabled=busy || (!checked && selected.length>=8) || Boolean(state.skill) ||
        Boolean(state.materials?.items?.length);
      box.addEventListener('change',()=>onToggleCitation(citation.id));
      label.append(box,node('span',`${citation.title} · ${citation.kind==='law_markdown'?'法规':'案例'} · 第 ${citation.line_start}–${citation.line_end} 行 · 待核对`));
      host.append(label);
    }
    byId('context-count').textContent=selected.length?`已选 ${selected.length}/8 条；发送时问题为当前已保存草稿。`:'';
    byId('preview-context').disabled=!context?.canPreview;
    const box=byId('context-preview-box');
    const preview=context?.preview?.response;
    box.replaceChildren();
    if(preview) {
      box.hidden=false;
      const text={ready:`将发送：当前问题与所选 ${selected.length} 条片段；线上内容共 ${preview.wire_bytes} 字节（上限 ${preview.max_input_bytes} 字节）。发送时按模型设置核对当前资料版本。`,
        input_too_large:'所选内容与问题合并后超过当前模型的输入上限。请减少选片或缩短问题。',
        not_configured:'尚未配置模型。可核对内容，但当前环境不能发送。'}[preview.state] || '预览状态待核对。';
      box.append(node('p',text,'generation-note'));
    } else box.hidden=true;
    byId('context-status').textContent=busy&&context?.phase&&contextPhaseText[context.phase]?
      contextPhaseText[context.phase]:context?.phase==='error'?contextErrorText(context.error):
      context?.phase==='unknown'?contextPhaseText.unknown:'';
    byId('context-status').dataset.kind=['unknown','error'].includes(context?.phase)?'error':'';
  }
  return {
    state(state,readonly=false) {
      const input=byId('composer');
      if((state.status==='revoked' || !isComposing()) && input.value!==state.text)input.value=state.text;
      input.disabled=readonly || state.loading || state.status==='revoked';
      const revoked=state.status==='revoked';
      const sourceMessages=revoked || (state.view?.scope?.conversation_id && state.view.scope.conversation_id!==state.id)
        ?[]:state.view?.messages || [];
      const generation=state.generation,research=state.research;
      const materialParents=new Map(),completedBusiness=new Set(),hiddenMessages=new Set();
      for(const item of generation?.items||[]){
        const attempt=item.attempt,manifest=attempt.output?.manifest;
        if(attempt.input_format!=='material-business-v1'||attempt.state!=='received'||attempt.scope?.conversation_id!==state.id||!manifest)continue;
        const parent=state.business?.items?.find(value=>value.run_id===manifest.parent_business_run_id);
        const original=sourceMessages.find(value=>value.id===parent?.message_id&&value.role==='user');
        const duplicate=sourceMessages.find(value=>value.id===item.message_id&&value.role==='user');
        if(!parent||!original||!duplicate||original.content!==manifest.question||duplicate.content!==manifest.question)continue;
        materialParents.set(item.message_id,original.id);completedBusiness.add(parent.run_id);
        if(duplicate.id!==original.id)hiddenMessages.add(duplicate.id);
        for(const value of sourceMessages)if(value.role==='assistant'&&value.source_revision===parent.scope.input_revision&&value.content===parent.text)
          hiddenMessages.add(value.id);
      }
      const messages=sourceMessages.filter(value=>!hiddenMessages.has(value.id));
      const local=state.skill==='legal_research';
      const history=byId('history');
      if(previousId!==state.id)history.replaceChildren();
      previousId=state.id;
      const visible=new Set(messages.map(message=>message.id));
      const visibleKey=Array.from(visible).join(',');
      const attemptsByMessage=new Map();
      for(const item of generation?.items || []) {
        const messageId=materialParents.get(item.message_id)||item.message_id;
        if(!visible.has(messageId) || item.attempt.scope?.conversation_id!==state.id)continue;
        if(!attemptsByMessage.has(messageId))attemptsByMessage.set(messageId,[]);
        attemptsByMessage.get(messageId).push(item.attempt);
      }
      Array.from(history.children).forEach(item=>{if(!visible.has(item.dataset.messageId))item.remove();});
      const existing=new Map(Array.from(history.children).map(item=>[item.dataset.messageId,item]));
      let position=history.firstChild;
      for(const message of messages) {
        let item=existing.get(message.id);
        if(!item) {
          item=node('article',undefined,'message'); item.dataset.messageId=message.id;item.dataset.role=message.role;item.id='message-'+message.id;
          item.setAttribute('tabindex','-1');
          item.append(node('p',message.role==='user'?'律师输入':'已保存的回复 · 需核对','message-meta'),
            node('p',message.content,'message-text'));
        }
        const attempts=message.role==='user'?attemptsByMessage.get(message.id) || []:[];
        const searches=(research?.items||[]).filter(item=>item.message_id===message.id).map(item=>item.research);
        const business=(state.business?.items||[]).find(result=>result.message_id===message.id);
        const signature=JSON.stringify([visibleKey,attempts,searches,business,state.materialGeneration,state.view?.scope]);
        if(renderedAttempts.get(item)!==signature) {
          item.querySelectorAll('.generation-result').forEach(element=>element.remove());
          item.querySelectorAll('.research-result').forEach(element=>element.remove());
          item.querySelectorAll('.material-generation-action').forEach(element=>element.remove());
          for(const attempt of attempts)item.append(renderAttempt(attempt,visible,onCitation));
          for(const result of searches)item.append(renderResearch(root,result,onCitation));
          if(business?.task_id&&business.workflow&&!completedBusiness.has(business.run_id)&&(state.materials?.items?.length||business.workflow==='sales')){
            const action=node('div',undefined,'material-generation-action'),button=node('button',business.workflow==='sales'&&!state.materials?.items?.length?'用咨询文字生成 AI 接待草稿':'用当前材料生成 AI 草稿','text-button');button.type='button';
            const phase=state.materialGeneration?.phase;
            button.disabled=readonly||!state.materialGeneration?.available||['confirming','submitting','unknown'].includes(phase)||
              business.scope.materials_revision!==state.view.scope.materials_revision;
            button.addEventListener('click',()=>onGenerateMaterial(business.run_id));action.append(button);
            if(phase==='unknown'){
              const retry=node('button','查找本次 AI 发送结果','text-button');retry.type='button';retry.addEventListener('click',()=>onGenerateMaterial(business.run_id));action.append(retry);
            }
            if(phase==='confirming')action.append(node('p','正在核对模型设置与本次材料范围…','generation-note'));
            if(!state.materialGeneration?.available)action.append(node('p','请在桌面应用配置模型和材料分析范围。','generation-note'));
            if(state.materialGeneration?.error)action.append(node('p',generationErrorText(state.materialGeneration.error),'generation-note'));
            item.append(action);
          }
          renderedAttempts.set(item,signature);
        }
        if(item!==position)history.insertBefore(item,position);
        else position=position.nextSibling;
      }
      if(!messages.length)history.replaceChildren();
      document.body.classList.toggle('has-history',messages.length>0);
      byId('home-title').textContent=state.view?.display_title || '把事情，一件件理清。';
      const kind=state.view?.scope.scope_kind;
      byId('scope-label').textContent=readonly?'恢复副本 · 只读核对':
        kind==='matter'?'当前范围：关联案件':kind==='intake'?'当前范围：本次接待':'当前范围：本次对话';
      byId('selected-skill').textContent=state.skill?skillText[state.skill]:'自动选择能力';
      byId('clear-skill').hidden=!state.skill;
      root.querySelectorAll('[data-skill]').forEach(button=>{
        button.setAttribute('aria-pressed',String(button.dataset.skill===state.skill));
        button.disabled=readonly || state.loading || state.status==='revoked';
      });
      const labels={idle:'尚未输入 · 可以从一段咨询开始。',loading:'正在读取记录…',saving:'正在保存…',saved:'草稿已保存到本机',
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
      byId('refresh-run').hidden=!run && generation?.phase!=='error' && research?.phase!=='error' && state.context?.phase!=='error' && state.context?.phase!=='unknown';
      byId('refresh-run').disabled=state.loading || state.status==='saving';
      byId('cancel-run').hidden=!run || !['queued','preparing','routing','retrieving','generating','persisting','awaiting_input'].includes(run.state);
      byId('cancel-run').disabled=readonly || state.loading || state.status==='saving';
      byId('conflict-panel').hidden=!state.conflict;
      byId('server-draft').textContent=state.conflict?.server || '（服务器草稿为空）';
      byId('new-conversation').disabled=readonly || state.loading || state.status==='saving' || state.status==='revoked';
      const showingResearch=local || ['unknown','error','tracking'].includes(research?.phase);
      const contextMode=!local && !state.skill && (state.context?.selected.length>0 ||
        ['confirming','submitting','unknown','tracking'].includes(state.context?.phase));
      const businessMode=state.business?.active===true;
      const workflow=businessMode?state.business:showingResearch?research:contextMode?state.context:generation;
      const phase=workflow?.phase || 'idle';
      const nativeConfirmation=!businessMode && !showingResearch && (generation?.nativeConfirmation===true || contextMode);
      byId('send').textContent=businessMode?'发送':local?'本机检索':contextMode?'发送资料回答':'发送';
      byId('send').disabled=workflow?.canSend!==true || readonly || state.loading || Boolean(state.skill && !local && !businessMode) ||
        ['saving','conflict','readonly','revoked'].includes(state.status) || ['checking','confirming','submitting','unknown','tracking'].includes(phase);
      byId('generation-note').textContent=revoked?'访问已结束。':readonly || state.status==='readonly'
        ?generationCapabilityText.restored_read_only:businessMode?'自动关联任务和材料，按模型设置分析；结果与来源保存在本对话。':local
          ?state.materials?.items?.length?'本机关键词检索暂不接受附件，请先将材料移出本次。': [...state.text].length>200
            ?'关键词超过 200 字。请缩短后检索；原有文字仍保留。':'输入不超过 200 字的关键词，仅查询本机资料库；不会发送给模型。'
          :contextMode
            ?`已选 ${state.context.selected.length} 条已保存片段。可先点“核对将发送的内容”；发送时按模型设置核对问题与片段版本，结果仍需律师核对。`
          :state.skill?'该能力尚未接入执行。取消选择后可核对普通文字的生成条件。'
          :nativeConfirmation && ['unapproved','ready','budget_exhausted'].includes(generation?.capability?.state)
            ?generation.profileMode?'发送后按模型设置生成回复，并整理本机待核档案草稿；实际保存以结果回执为准。'
              :'发送时按主模型设置核对本次文字与费用上限；结果仍需律师核对。'
            :generationCapabilityText[generation?.capability?.state] || '输入并保存文字后，将核对当前生成条件。';
      const phaseText={checking:'正在核对生成条件…',confirming:'正在核对本次文字、模型设置与费用上限…',submitting:'正在提交生成请求…',
        unknown:'发送结果尚不确定。请查找发送结果，避免重复发送。',tracking:'生成已登记，正在核对结果…'};
      byId('generation-status').textContent=revoked?'':showingResearch?researchStatusText(research):
        contextMode?(contextPhaseText[phase] || (phase==='error'?contextErrorText(state.context?.error):'')):
        phaseText[phase] || (phase==='error'?generationErrorText(workflow?.error):'');
      byId('generation-status').dataset.kind=['unknown','error'].includes(phase)?'error':'';
      byId('recover-generation').hidden=revoked || phase!=='unknown';
      byId('recover-generation').disabled=state.loading || revoked;
      byId('input-help').textContent='Enter 发送，'+'Shift+Enter 换行；'+
        (byId('send').disabled?'当前发送不可用。':local?'发送后查询本机资料。':'发送后生成内部待核草稿。');
      input.placeholder=local?'输入关键词，例如：合成买卖纠纷':'先记下客户的情况、你想核对的问题，或希望完成的工作…';
      byId('add-material').disabled=readonly || state.loading || ['saving','conflict','revoked'].includes(state.status);
      const switcher=byId('switch-model'),desktopModel=state.desktopModel;
      switcher.hidden=!desktopModel?.available;
      if(desktopModel?.available){
        switcher.disabled=readonly || state.loading || desktopModel.busy===true ||
          ['saving','conflict','revoked'].includes(state.status);
        switcher.textContent=desktopModel.busy===true?'正在切换模型…':
          desktopModel.model==='deepseek-v4-pro'?'模型：DeepSeek V4 Pro':
          desktopModel.model==='deepseek-flash'?'模型：DeepSeek V4.1 Flash':'切换模型';
      }
      drawContextPanel(state,readonly);
    },
    conversations(page,{append=false,selected=null,onSelect,onDelete,readonly=false}={}) {
      const host=byId('conversation-list');
      if(!append)host.replaceChildren();
      else host.querySelectorAll('p').forEach(element=>element.remove());
      for(const item of page.items) {
        const button=node('button',item.display_title,'conversation-item'); button.type='button';
        button.dataset.conversationId=item.scope.conversation_id;
        if(item.scope.conversation_id===selected)button.setAttribute('aria-current','page');
        button.addEventListener('click',()=>onSelect(item.scope.conversation_id));
        const row=node('div','','conversation-row'),remove=node('button','删除','conversation-delete');
        remove.type='button';remove.dataset.deleteConversationId=item.scope.conversation_id;
        remove.setAttribute('aria-label','删除对话：'+item.display_title);remove.disabled=readonly;
        remove.addEventListener('click',()=>onDelete?.(item));row.append(button,remove);host.append(row);
      }
      if(!host.children.length)host.append(node('p','这里会保留你的事项记录，方便下次接着处理。','muted'));
      byId('more-conversations').hidden=!page.next_cursor;
    },
    selected(id) {
      root.querySelectorAll('[data-conversation-id].conversation-item').forEach(button=>{
        if(button.dataset.conversationId===id)button.setAttribute('aria-current','page');
        else button.removeAttribute('aria-current');
      });
    },
    archiveControls(state,readonly) {
      root.querySelectorAll('[data-delete-conversation-id]').forEach(button=>{
        const pending=state.archivePending?.id===button.dataset.deleteConversationId;
        button.textContent=pending?'查询删除结果':state.archiving===button.dataset.deleteConversationId?'正在删除…':'删除';
        button.disabled=readonly || state.status==='revoked' || Boolean(state.archiving) || state.loading&&!pending;
      });
    },
    capability(catalog) {
      byId('capability-details').textContent='可整理客户接待、案件材料、合同审查和庭审准备草稿；实际生成范围以当前模型设置和材料读取状态为准。“检索法律资料”使用已连接的本机资料库，结果保留来源与待核对状态。';
    },
  };
}
