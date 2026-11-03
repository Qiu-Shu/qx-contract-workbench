import {getSavedCitation} from './assistant-api.mjs';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const context=state=>JSON.stringify([state.id,...['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision']
  .map(key=>state.view?.scope?.[key])]);
const node=(root,tag,text,style)=>{const item=root.createElement(tag);if(text!==undefined)item.textContent=text;
  if(style)item.className=style;return item;};
const pageText={not_configured:'本机尚未连接法律资料库，未执行查询。',
  not_ready:'本机资料库暂不可用，本次未取得可核对结果。',timeout:'本次检索已超时，以下仅保留已取得的片段；结果可能不完整。'};
export const researchStatusText=state=>({checking:'正在读取已保存的本机检索记录…',submitting:'正在登记本机关键词检索…',
  unknown:'本机检索是否登记尚不确定。请查找发送结果，避免重复查询。',tracking:'已登记本机检索，正在核对结果…',
  error:state.error?.code==='INPUT_CHANGED'?'输入或选择已变化，本次未查询。请核对关键词后重新发送。':
    '本机检索状态未能确认。请刷新记录后核对；不会自动重新查询。'}[state?.phase]||'');

const knowledgeHits=page=>[...(page?.groups?.law||[]),...(page?.groups?.case||[])];
const knowledgeNote=page=>(page?.degraded||[]).map(item=>item.message).filter(Boolean).join(' ');
const kindText=kind=>kind==='law'?'法规':'案例';

export function renderResearch(root,research,onCitation=()=>{}) {
  const section=node(root,'section',undefined,'research-result');section.setAttribute('aria-label','本机检索结果');
  const knowledge=research.receipts.some(receipt=>receipt.result.result.knowledge_page);
  section.append(node(root,'h3',knowledge?'法律资料检索':'本机法律资料检索'),
    node(root,'p','原文片段 · 适用性待核对；本次未调用模型。','generation-note'));
  if(!research.receipts.length){
    const text={completed:'任务已结束，未保存可用的检索回执。',cancelled:'本次检索已取消。',failed:'本次检索未完成。',
      interrupted:'本次检索已中断，不会自动续跑。',blocked:'本次检索已阻断，不会自动续跑。'};
    section.append(node(root,'p',text[research.run.state]||'正在读取本机资料库…','generation-note'));
  }
  for(const receipt of research.receipts){
    const result=receipt.result.result,ids=receipt.result.citation_ids;
    if(result.knowledge_page){
      // 只读知识服务：法条与案例分两组，顺序必须与服务端保存 citation_ids 的顺序一致。
      const page=result.knowledge_page,hits=knowledgeHits(page);
      if(!hits.length)section.append(node(root,'p','本次关键词未命中资料。可调整关键词后重新查询。','generation-note'));
      const note=knowledgeNote(page);
      if(note)section.append(node(root,'p',note,'generation-note'));
      const list=node(root,'ol',undefined,'research-hits');
      hits.forEach((citation,index)=>{
        if(!uuid.test(ids[index]))return;
        const row=node(root,'li'),button=node(root,'button',citation.title||'未命名资料','citation-link');
        button.type='button';button.dataset.savedCitation=ids[index];
        button.setAttribute('aria-label',`查看已保存片段：${citation.title||'未命名资料'}`);
        button.addEventListener('click',()=>onCitation(ids[index],button));
        const loc=citation.location;
        row.append(button,node(root,'p',
          `${kindText(citation.kind)} · 第 ${loc.line_start}–${loc.line_end} 行 · 待核对`,'generation-note'));
        list.append(row);
      });
      if(list.children.length)section.append(list);
      continue;
    }
    const page=result.page;
    if(page.state!=='ready')section.append(node(root,'p',pageText[page.state]||'本次检索结果待核对。','generation-note'));
    else if(!page.citations.length)section.append(node(root,'p','本次关键词未命中资料。可调整关键词后重新查询。','generation-note'));
    if(page.omitted_hits)section.append(node(root,'p',`${page.omitted_hits} 条命中未能形成可回查片段，本次不展示为引用。`,'generation-note'));
    const list=node(root,'ol',undefined,'research-hits');
    page.citations.forEach((citation,index)=>{
      if(!uuid.test(ids[index]))return;
      const row=node(root,'li'),button=node(root,'button',citation.title||'未命名资料','citation-link');
      button.type='button';button.dataset.savedCitation=ids[index];
      button.setAttribute('aria-label',`查看已保存片段：${citation.title||'未命名资料'}`);
      button.addEventListener('click',()=>onCitation(ids[index],button));
      row.append(button,node(root,'p',`${citation.kind==='law_markdown'?'法规':'案例'} · 第 ${citation.line_start}–${citation.line_end} 行 · 待核对`,'generation-note'));
      if(!citation.match_in_quote)row.append(node(root,'p','关键词命中标题或其他位置，片段可能不含关键词。','generation-note'));
      list.append(row);
    });
    if(list.children.length)section.append(list);
  }
  return section;
}

export function bindCitations({controller,root=document,onOpen=()=>{},read=getSavedCitation}) {
  const at=id=>root.getElementById(id),body=at('citation-preview-content');
  let epoch=0,identity=context(controller.state),returnFocus=null;
  function close(restore=false){
    ++epoch;at('citation-preview').hidden=true;body.replaceChildren();at('citation-preview-title').textContent='已保存的引用片段';
    root.body.classList.remove('source-open');
    if(restore)(returnFocus?.isConnected?returnFocus:at('composer')).focus();returnFocus=null;
  }
  // 只读知识服务的引用：先展示检索时保存的片段，再按需回读来源原文（带版本绑定）。
  function showKnowledge(saved,stamp){
    const kc=saved.knowledge_citation,loc=kc.location;
    at('citation-preview-title').textContent=kc.title||'未命名资料';body.replaceChildren();
    body.append(node(root,'p','这是检索时保存的历史片段，不是全文，也不代表当前法规效力或适用性已确认。','citation-boundary'),
      node(root,'p','原文哈希与登记版本已核对；支持关系与适用性仍待律师核对。','generation-note'),
      node(root,'p',kc.snippet.text,'citation-quote'));
    const details=node(root,'dl',undefined,'citation-details');
    for(const [label,value]of [['原文位置',`第 ${loc.line_start}–${loc.line_end} 行；字符 ${loc.char_start}–${loc.char_end}`],
      ['来源标识',kc.source_id],['资料版本',kc.source_version.sha256],
      ['版本校验',kc.source_version.verified||'未声明'],['定位方式',loc.basis],['保存时间',saved.created_at]])
      details.append(node(root,'dt',label),node(root,'dd',value));
    const slot=node(root,'div',undefined,'citation-details');
    const button=node(root,'button','打开来源原文','citation-link');button.type='button';
    button.addEventListener('click',async()=>{
      slot.replaceChildren(node(root,'p','正在校验版本并回读原文…','generation-note'));
      try{
        const response=await fetch(`/api/knowledge/sources/${encodeURIComponent(kc.source_id)}`
          +`?version=${encodeURIComponent(kc.source_version.sha256)}`,{credentials:'same-origin'});
        let data={};try{data=await response.json();}catch{data={};}
        if(stamp!==epoch)return;
        if(!response.ok){slot.replaceChildren(node(root,'p',data.message||'原文读取未完成，请稍后重试。','generation-note'));return;}
        if(data.source_version?.sha256!==kc.source_version.sha256){
          slot.replaceChildren(node(root,'p','回读到的来源版本与检索时不一致，已阻断显示，请重新检索。','generation-note'));return;}
        slot.replaceChildren(node(root,'p',data.content.text,'citation-quote'));
      }catch{
        if(stamp!==epoch)return;
        slot.replaceChildren(node(root,'p','原文读取未完成，请稍后重试。','generation-note'));
      }
    });
    body.append(details,button,slot);return true;
  }
  async function open(id,trigger){
    if(!uuid.test(id) || !controller.state.id || controller.state.loading || controller.state.status==='revoked')return false;
    onOpen();const stamp=++epoch,basis=context(controller.state);returnFocus=trigger;
    const current=()=>stamp===epoch && basis===context(controller.state) && !controller.state.loading && controller.state.status!=='revoked';
    at('citation-preview-title').textContent='已保存的引用片段';
    at('citation-preview').hidden=false;root.body.classList.add('source-open');
    body.replaceChildren(node(root,'p','正在读取已保存的引用…'));at('close-citation-preview').focus();
    try{
      const saved=await read(id);if(!current())return false;
      if(saved?.id!==id || saved.scope?.conversation_id!==controller.state.id ||
          saved.scope?.workspace_id!==controller.state.view?.scope.workspace_id ||
          (!saved.citation && !saved.knowledge_citation))throw {code:'INVALID_RESPONSE'};
      if(saved.knowledge_citation)return showKnowledge(saved,stamp);
      const citation=saved.citation;
      at('citation-preview-title').textContent=citation.title||'未命名资料';body.replaceChildren();
      body.append(node(root,'p','这是检索时保存的历史片段，不是全文，也不代表当前法规效力或适用性已确认。','citation-boundary'),
        node(root,'p','来源内容匹配；支持关系与适用性仍待律师核对。','generation-note'),
        node(root,'p',citation.quote,'citation-quote'));
      const details=node(root,'dl',undefined,'citation-details');
      const fields=[['原文位置',`第 ${citation.line_start}–${citation.line_end} 行；字符 ${citation.start}–${citation.end}`],
        ['来源标识',citation.source_id],['资料版本',citation.version_id],['索引代际',citation.generation_id],['保存时间',saved.created_at]];
      if(citation.article)fields.unshift(['条文位置',citation.article+(citation.ambiguous?'（位置有歧义，待核对）':'')]);
      for(const [label,value]of fields)details.append(node(root,'dt',label),node(root,'dd',value));
      body.append(details);return true;
    }catch(error){if(current() && !controller.revoke(error))body.replaceChildren(node(root,'p','暂时无法读取此片段。请关闭后刷新记录，再核对访问权限。'));return false;}
  }
  at('close-citation-preview').addEventListener('click',()=>close(true));
  const escape=event=>{if(event.key==='Escape' && !at('citation-preview').hidden){event.preventDefault();close(true);}};
  root.addEventListener('keydown',escape);
  return {open,close,state(state){const next=context(state);if(next!==identity || state.loading || state.status==='revoked')close();identity=next;},
    dispose(){close();root.removeEventListener('keydown',escape);}};
}
