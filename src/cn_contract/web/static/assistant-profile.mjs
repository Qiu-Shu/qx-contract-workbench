// Read-only profile snapshots. The backend owns edits, protection and verification.
const identities=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision'];
const context=state=>JSON.stringify([state.id,...identities.map(key=>state.view?.scope?.[key])]);
const nonnegative=value=>Number.isSafeInteger(value)&&value>=0;
const sha=value=>typeof value==='string'&&/^[0-9a-f]{64}$/i.test(value);
const labels={title:'事项标题',contact:'联系方式',consultation:'咨询经过',questions:'待追问事项',materials:'材料清单',
  follow_up_at:'跟进时间',follow_up_note:'跟进备注',client_reply:'客户回复',internal_notes:'律师内部意见',
  principal_amount:'本金',interest_amount:'利息',payment_amount:'已付款项'};
const states={unknown:'未知 · 尚无可用内容',unverified:'待核验',conflicted:'存在冲突 · 候选并列保留'};
const origins={user_statement:'对话中的陈述',document_statement:'材料中的陈述',model_inference:'模型整理候选'};
const materialStates={needed:'待补充',received:'已收到 · 内容待核对',checked:'律师标记已核对'};
const node=(document,tag,text,style)=>{const item=document.createElement(tag);if(text!==undefined)item.textContent=text;
  if(style)item.className=style;return item;};
function validValue(value,field,proposed=false){
  if(!value||typeof value!=='object')return false;
  if(value.kind==='null')return true;
  if(proposed&&field==='contact')return false;
  const kind={questions:'list',materials:'materials',follow_up_at:'datetime',principal_amount:'money',interest_amount:'money',payment_amount:'money'}[field]||'text';
  if(value.kind!==kind)return false;
  if(kind==='list')return Array.isArray(value.value)&&value.value.length<=30&&value.value.every(x=>typeof x==='string');
  if(kind==='materials')return Array.isArray(value.value)&&value.value.length<=30&&value.value.every(x=>
    typeof x?.name==='string'&&Object.hasOwn(materialStates,x.state)&&(!proposed||x.state!=='checked'));
  if(kind==='money')return typeof value.value==='string'&&/^\d+(?:\.\d+)?(?:E[+-]?\d+)?$/i.test(value.value)&&
    typeof value.unit==='string'&&/^[A-Z]{3}$/.test(value.unit);
  return typeof value.value==='string';
}
function validRef(ref,scope){
  if(!ref||ref.conversation_id!==scope.conversation_id)return false;
  const range=source=>typeof source.quote==='string'&&source.quote.length>0&&sha(source.quote_sha256)&&
    nonnegative(source.start)&&nonnegative(source.end)&&source.end-source.start===[...source.quote].length;
  if(ref.kind==='message')return typeof ref.message_id==='string'&&nonnegative(ref.source_revision)&&
    ref.source_revision>0&&ref.source_revision<=scope.input_revision&&range(ref);
  if(ref.kind!=='document')return false;
  const anchor=ref.anchor;
  return typeof ref.attachment_id==='string'&&sha(ref.original_sha256)&&sha(ref.result_sha256)&&
    nonnegative(ref.parse_revision)&&ref.parse_revision>0&&ref.parse_revision<=scope.materials_revision&&
    anchor&&anchor.document_version_id===ref.attachment_id&&typeof anchor.id==='string'&&
    typeof anchor.part_name==='string'&&typeof anchor.element_id==='string'&&typeof anchor.kind==='string'&&range(anchor);
}
function checked(saved,current,requested){
  if(!saved?.scope||!identities.every(key=>saved.scope[key]===current[key])||
    !['input_revision','materials_revision'].every(key=>nonnegative(saved.scope[key])&&nonnegative(current[key])&&saved.scope[key]<=current[key])||
    !nonnegative(saved.revision)||(requested!==undefined&&saved.revision!==requested)||
    !Array.isArray(saved.fields)||saved.fields.length>12||(saved.revision===0&&saved.fields.length)||
    new Set(saved.fields.map(field=>field?.field)).size!==saved.fields.length)throw {code:'INVALID_RESPONSE'};
  for(const field of saved.fields){
    if(!Object.hasOwn(labels,field.field)||!Object.hasOwn(states,field.verification)||
      !Array.isArray(field.candidates)||field.candidates.length>60||
      (field.protected_value!==null&&!validValue(field.protected_value,field.field)))throw {code:'INVALID_RESPONSE'};
    for(const candidate of field.candidates){
      if(candidate.field!==field.field||candidate.verification!=='unverified'||!Object.hasOwn(origins,candidate.origin)||
        !validValue(candidate.value,field.field,true)||!Array.isArray(candidate.source_refs)||candidate.source_refs.length>40||
        (candidate.value.kind!=='null'&&!candidate.source_refs.length)||
        !candidate.source_refs.every(ref=>validRef(ref,saved.scope)))throw {code:'INVALID_RESPONSE'};
    }
  }
  return saved;
}

export function bindProfile({controller,api,document=globalThis.document,onOpen=()=>{}}){
  const at=id=>document.getElementById(id),body=at('profile-content'),panel=at('profile-preview'),notice=at('profile-notice');
  let epoch=0,identity=context(controller.state),returnFocus=null,latestRevision=0,displayed=null,ended=false;
  const available=()=>!ended&&controller.state.id&&controller.state.view?.scope?.conversation_id===controller.state.id&&
    !controller.state.loading&&controller.state.status!=='revoked';
  function close(restore=false){
    ++epoch;const wasOpen=!panel.hidden;panel.hidden=true;body.replaceChildren();notice.textContent='';
    panel.removeAttribute('aria-busy');at('show-profile').setAttribute('aria-expanded','false');at('profile-refresh').disabled=false;
    if(wasOpen)document.body.classList.remove('source-open');
    displayed=null;latestRevision=0;
    if(restore)(returnFocus?.isConnected?returnFocus:at('composer'))?.focus();returnFocus=null;
  }
  function valueView(value,protectedValue=false){
    if(value.kind==='null')return node(document,'p',protectedValue?'律师已明确清空此项；此更正受保护。':'未知；未据此补写内容。');
    if(value.kind==='list'||value.kind==='materials'){
      const list=node(document,'ul');
      for(const item of value.value)list.append(node(document,'li',value.kind==='list'?item:`${item.name} · ${materialStates[item.state]}`));
      if(!value.value.length)list.append(node(document,'li','空清单'));
      return list;
    }
    return node(document,'p',value.kind==='money'?`${value.value} ${value.unit}`:value.value);
  }
  function sourceView(ref){
    const details=node(document,'details'),source=ref.kind==='message'?ref:ref.anchor;
    details.append(node(document,'summary',ref.kind==='message'?'查看对话原文与位置':'查看材料原文与锚点'),
      node(document,'p',source.quote,'citation-quote'));
    const pairs=ref.kind==='message'?
      [['消息标识',ref.message_id],['输入版本',ref.source_revision]]:
      [['附件标识',ref.attachment_id],['原件摘要',ref.original_sha256],['读取版本',ref.parse_revision],['读取结果摘要',ref.result_sha256],
        ['锚点标识',source.id],['文档版本',source.document_version_id],['文件部分',source.part_name],['段落位置',source.element_id],['锚点类型',source.kind]];
    pairs.push(['所属对话',ref.conversation_id],['字符位置',`[${source.start}, ${source.end}) · 从 0 开始，末位不含`],['原文摘要',source.quote_sha256]);
    if(ref.kind==='document'){
      if(source.table!==null||source.row!==null||source.cell!==null)pairs.push(['表格位置',`表 ${source.table} · 行 ${source.row} · 列 ${source.cell}（从 0 开始）`]);
      if(source.page!==null)pairs.push(['页码',source.page]);
      if(source.bbox!==null)pairs.push(['页面坐标',JSON.stringify(source.bbox)]);
    }
    const metadata=node(document,'dl',undefined,'citation-details');
    for(const [label,value]of pairs)metadata.append(node(document,'dt',label),node(document,'dd',String(value)));
    details.append(metadata);return details;
  }
  function render(saved){
    body.replaceChildren();
    if(!saved?.revision){body.append(node(document,'p','尚无已保存的档案草稿。此处仅展示已保存记录，不会触发生成。'));return;}
    const summary=node(document,'p','档案草稿 · 内容待核验。律师更正受保护，但不等于事实已经核实。','generation-note');body.append(summary);
    const form=node(document,'form',undefined,'profile-history'),label=node(document,'label','查看历史版本 '),input=node(document,'input');
    input.type='number';input.min='1';input.max=String(latestRevision);input.step='1';input.value=String(saved.revision);
    input.setAttribute('aria-label',`档案版本，1 至 ${latestRevision}`);label.append(input);
    const button=node(document,'button','读取此版本','text-button');button.type='submit';form.append(label,button);
    form.addEventListener('submit',async event=>{
      event.preventDefault();const text=input.value;
      if(!/^\d+$/.test(text)||!Number.isSafeInteger(Number(text))||Number(text)<1||Number(text)>latestRevision){
        notice.textContent=`请输入 1 至 ${latestRevision} 之间的整数版本。`;return false;
      }
      return load(Number(text));
    });body.append(form);
    if(!saved.fields.length)body.append(node(document,'p','此版本没有字段内容。原有历史版本仍可读取。'));
    for(const field of saved.fields){
      const section=node(document,'section');section.append(node(document,'h3',labels[field.field]),node(document,'p',states[field.verification],'generation-note'));
      if(field.protected_value!==null)section.append(node(document,'p','律师更正 · 受保护','source-location'),valueView(field.protected_value,true));
      if(!field.candidates.length&&field.protected_value===null)section.append(node(document,'p','尚无可用内容；保留未知状态。'));
      field.candidates.forEach((candidate,index)=>{
        const candidateView=node(document,'div');candidateView.append(node(document,'p',`候选 ${index+1} · ${origins[candidate.origin]} · 待核验`,'source-location'),valueView(candidate.value));
        for(const ref of candidate.source_refs)candidateView.append(sourceView(ref));section.append(candidateView);
      });body.append(section);
    }
  }
  function describe(){
    if(!displayed)return;
    const historical=displayed.revision<latestRevision?'历史版本':'已保存版本';
    const scope=displayed.scope;
    notice.textContent=`${historical} ${displayed.revision} · 来源输入版本 ${scope.input_revision}、材料版本 ${scope.materials_revision}。`+
      '这里只读取保存记录；最新整理结果请重新读取。';
  }
  async function load(revision){
    if(!available())return false;
    const token=++epoch,basis=context(controller.state),id=controller.state.id;
    const current=()=>token===epoch&&basis===context(controller.state)&&available()&&!panel.hidden;
    displayed=null;body.replaceChildren();notice.textContent='正在读取已保存的档案版本…';panel.setAttribute('aria-busy','true');at('profile-refresh').disabled=true;
    try{
      const response=await api.getProfile(id,revision);if(!current())return false;
      if(response===null&&revision===undefined){latestRevision=0;render(null);notice.textContent='尚无档案草稿；可在整理完成后重新读取。';return true;}
      const saved=checked(response,controller.state.view.scope,revision);
      if(revision===undefined)latestRevision=saved.revision;
      displayed=saved;render(saved);describe();return true;
    }catch(error){
      if(current()){
        if(controller.revoke(error)){close();return false;}
        body.replaceChildren();notice.textContent='未能读取档案版本，当前保存结果尚未确认。请重新读取；不会自动生成或重复保存。';
      }
      return false;
    }finally{if(current()){panel.removeAttribute('aria-busy');at('profile-refresh').disabled=false;}}
  }
  async function open(trigger){
    if(!available())return false;
    onOpen();returnFocus=trigger||at('show-profile');panel.hidden=false;document.body.classList.add('source-open');
    at('show-profile').setAttribute('aria-expanded','true');at('close-profile-preview').focus();return load();
  }
  function state(state){
    const next=context(state);
    const incompatible=displayed&&['input_revision','materials_revision'].some(key=>
      !nonnegative(state.view?.scope?.[key])||displayed.scope[key]>state.view.scope[key]);
    if(next!==identity||!state.view||state.loading||state.status==='revoked'||incompatible)close();identity=next;
    at('show-profile').disabled=!available();if(displayed)describe();
  }
  at('show-profile').addEventListener('click',event=>open(event.currentTarget));
  at('close-profile-preview').addEventListener('click',()=>close(true));
  at('profile-refresh').addEventListener('click',()=>panel.hidden?open():load());
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!panel.hidden){event.preventDefault();close(true);}});
  document.defaultView?.addEventListener('pagehide',()=>{ended=true;close();});
  panel.hidden=true;state(controller.state);
  return {state,open,close};
}
