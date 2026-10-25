// Saved profile snapshots and explicit local edits; the backend owns protection and verification.
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

export function bindProfile({controller,api,readonly=false,uuid=()=>crypto.randomUUID(),document=globalThis.document,onOpen=()=>{}}){
  const at=id=>document.getElementById(id),body=at('profile-content'),panel=at('profile-preview'),notice=at('profile-notice');
  let epoch=0,identity=context(controller.state),returnFocus=null,latestRevision=0,displayed=null,ended=false,editor=null,currentView=false;
  const pending=new Map(),scopeStamp=scope=>JSON.stringify([...identities,'input_revision','materials_revision'].map(key=>scope?.[key]));
  const writable=()=>available()&&!readonly&&controller.state.status!=='readonly'&&!controller.state.conflict&&
    !controller.state.view?.archived_at&&typeof api.submitProfileCommit==='function'&&
    typeof api.findProfileReceipt==='function'&&typeof api.getConversation==='function';
  const available=()=>!ended&&controller.state.id&&controller.state.view?.scope?.conversation_id===controller.state.id&&
    !controller.state.loading&&controller.state.status!=='revoked';
  function close(restore=false){
    ++epoch;const wasOpen=!panel.hidden;panel.hidden=true;body.replaceChildren();notice.textContent='';
    panel.removeAttribute('aria-busy');at('show-profile').setAttribute('aria-expanded','false');at('profile-refresh').disabled=false;
    if(wasOpen)document.body.classList.remove('source-open');
    displayed=null;latestRevision=0;editor=null;
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
    if(!saved?.revision){body.append(node(document,'p',writable()?'尚无已保存的档案草稿。可手工登记内容；不会触发生成。':'尚无已保存的档案草稿。此处只读取保存记录。'));editAction();return;}
    editAction();
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
  function control(tag,id,label,parent){
    const wrapper=node(document,'label',label),input=node(document,tag);input.id=id;wrapper.append(input);parent.append(wrapper);return input;
  }
  function editAction(){
    if(pending.has(identity)){
      const button=node(document,'button','查询保存回执','text-button');button.id='profile-check-receipt';button.type='button';
      button.addEventListener('click',()=>lookupPending());body.append(button);return;
    }
    if(!writable()||!currentView||(displayed&&displayed.revision!==latestRevision))return;
    const button=node(document,'button','手工维护档案','text-button');button.id='profile-edit';button.type='button';
    button.addEventListener('click',()=>startEdit());body.append(button);
  }
  async function startEdit(){
    if(!writable()||!currentView||pending.has(identity)||editor)return false;
    const token=++epoch,basis=identity,id=controller.state.id,stamp=scopeStamp(controller.state.view.scope);
    const current=()=>token===epoch&&basis===context(controller.state)&&!panel.hidden&&writable();
    notice.textContent='正在核对档案与接待记录版本…';
    try{
      const view=await api.getConversation(id);if(!current())return false;
      if(scopeStamp(view?.scope)!==stamp||view.archived_at)throw {code:'VERSION_CONFLICT',status:409};
      const target=view.scope.scope_kind==='intake'?view.scope.scope_ref:view.projection_intake_id;
      if(target!==null&&typeof target!=='string')throw {code:'INVALID_RESPONSE'};
      const intake=target?await api.getIntake(target):null;if(!current())return false;
      if(intake&&(intake.id!==target||!nonnegative(intake.revision)||intake.revision<1||intake.matter_id!==null))throw {code:'VERSION_CONFLICT',status:409};
      if(scopeStamp(controller.state.view.scope)!==stamp)throw {code:'VERSION_CONFLICT',status:409};
      editor={scope:{...view.scope},stamp,base:displayed?.revision||0,target,revision:intake?.revision??null};
      renderEditor();notice.textContent='每次保存一项；手工值与明确清空均受保护。仅保存档案，不改写接待登记；事实仍待核验。';return true;
    }catch(error){if(current()){if(controller.revoke(error))return false;await conflictRefresh('当前版本已变化或无法核对，请重新读取后编辑。');}return false;}
  }
  function renderEditor(){
    const basis=editor;body.replaceChildren();
    const form=node(document,'form',undefined,'profile-editor');form.id='profile-edit-form';
    const field=control('select','profile-edit-field','维护项目',form);
    for(const [key,label]of Object.entries(labels)){const option=node(document,'option',label);option.value=key;field.append(option);}field.value='title';
    const values=node(document,'div'),clear=control('input','profile-edit-clear','明确清空此项，并保护空值',form);clear.type='checkbox';
    form.append(values);let input,unit,rows=[];
    function valueControls(){
      clear.checked=false;values.hidden=false;rows=[];values.replaceChildren();const name=field.value;
      const saved=displayed?.fields.find(item=>item.field===name),value=saved?.protected_value??(saved?.candidates.length===1?saved.candidates[0].value:null);
      if(name==='materials'){
        const rowList=node(document,'div');values.append(rowList);
        const paint=()=>{rowList.replaceChildren();rows.forEach((row,index)=>{
          const line=node(document,'div',undefined,'profile-material-row'),nameInput=control('input',`profile-material-name-${index}`,'材料名称',line);
          nameInput.value=row.name;nameInput.maxLength=300;nameInput.addEventListener('input',()=>row.name=nameInput.value);
          const state=control('select',`profile-material-state-${index}`,'材料状态',line);
          for(const [key,label]of Object.entries(materialStates)){const option=node(document,'option',label);option.value=key;state.append(option);}state.value=row.state;
          state.addEventListener('change',()=>row.state=state.value);
          const remove=node(document,'button','移除此材料','text-button');remove.type='button';remove.addEventListener('click',()=>{rows.splice(index,1);paint();});
          line.append(remove);rowList.append(line);row.nameInput=nameInput;row.stateInput=state;
        });};
        rows=(value?.kind==='materials'?value.value:[]).map(row=>({...row}));paint();
        const add=node(document,'button','添加材料','text-button');add.id='profile-material-add';add.type='button';
        add.addEventListener('click',()=>{if(rows.length<30){rows.push({name:'',state:'needed'});paint();}});values.append(add);
      }else{
        input=control(name==='follow_up_at'?'input':'textarea','profile-edit-value',name==='questions'?'每行一项追问':labels[name],values);
        if(name==='follow_up_at'){
          input.type='datetime-local';input.step='1';
          if(value?.kind==='datetime'){const date=new Date(value.value);if(Number.isFinite(date.getTime()))input.value=new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,19);}
          values.append(node(document,'p','按本机时区填写，保存时转换为 UTC。','generation-note'));
        }else input.value=value?.kind==='list'?value.value.join('\n'):value&&value.kind!=='null'?value.value:'';
        if(name.endsWith('_amount')){unit=control('input','profile-edit-unit','币种（三位大写代码）',values);unit.value=value?.kind==='money'?value.unit:'CNY';unit.maxLength=3;input.inputMode='decimal';}
      }
    }
    field.addEventListener('change',valueControls);valueControls();
    clear.addEventListener('change',()=>{values.hidden=clear.checked;});
    const save=node(document,'button','保存手工更正');save.type='submit';
    const cancel=node(document,'button','取消','text-button');cancel.type='button';cancel.addEventListener('click',()=>{editor=null;render(displayed);describe();});form.append(save,cancel);
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(editor!==basis||!writable()||pending.has(identity)||basis.stamp!==scopeStamp(controller.state.view.scope))return false;
      let value={kind:'null',value:null};const name=field.value;
      if(!clear.checked){
        const text=input?.value??'';
        if(name==='materials')value={kind:'materials',value:rows.map(row=>({name:row.nameInput.value.trim(),state:row.stateInput.value}))};
        else if(name==='questions')value={kind:'list',value:text.split(/\r?\n/).map(row=>row.trim()).filter(Boolean)};
        else if(name==='follow_up_at'){
          const date=new Date(text);if(!text||!Number.isFinite(date.getTime())){notice.textContent='请填写有效跟进时间，或选择明确清空。';return false;}
          value={kind:'datetime',value:date.toISOString()};
        }else if(name.endsWith('_amount'))value={kind:'money',value:text.trim(),unit:unit.value.trim()};
        else value={kind:'text',value:text};
        if(!validValue(value,name)||(name==='title'&&!text.trim())||
          value.kind==='list'&&value.value.some(item=>item.length>300)||value.kind==='materials'&&value.value.some(row=>!row.name||row.name.length>300)){
          notice.textContent='请检查内容格式、金额、币种和清单长度；如需清空，请明确选择清空。';return false;
        }
      }
      save.disabled=cancel.disabled=field.disabled=clear.disabled=true;
      return saveEdit(basis,{field:name,value});
    });body.append(form);
  }
  function validReceipt(value,request){
    return value&&value.conversation_id===request.id&&value.request_id===request.key&&nonnegative(value.profile_revision)&&
      typeof value.profile_changed==='boolean'&&value.profile_revision===request.base+Number(value.profile_changed)&&
      value.projection_changed===false&&value.intake_id===request.target&&value.intake_revision===request.revision&&
      (request.target===null?value.intake_sha256===null:sha(value.intake_sha256))&&
      value.audience==='internal'&&nonnegative(value.sequence)&&value.sequence>0&&
      value.event_type===(value.profile_changed?'profile.saved':'profile.unchanged');
  }
  async function conflictRefresh(message){
    const basis=context(controller.state);
    editor=null;if(controller.refresh)await controller.refresh();
    if(basis!==context(controller.state)||!available()||panel.hidden)return false;
    const refreshed=await load();
    if(refreshed&&basis===context(controller.state)&&!panel.hidden)notice.textContent=message;return false;
  }
  async function finishReceipt(receipt,request,token,basis){
    if(!validReceipt(receipt,request))throw {code:'INVALID_RESPONSE'};
    pending.delete(basis);
    if(token!==epoch||basis!==context(controller.state)||panel.hidden)return false;
    const refreshed=await load();
    if(!refreshed||basis!==context(controller.state)||panel.hidden)return false;
    notice.textContent=receipt.event_type==='profile.unchanged'?'已收到回执：内容未变化。':'已收到保存回执；手工更正受保护，事实仍待核验。';return true;
  }
  async function lookupPending(){
    const basis=identity,request=pending.get(basis);if(!request||request.checking||request.sending||!available()||panel.hidden)return false;
    request.checking=true;const token=epoch;
    try{const receipt=await api.findProfileReceipt(request.id,request.key);
      if(receipt)return await finishReceipt(receipt,request,token,basis);
    }catch(error){if(token===epoch&&basis===context(controller.state)&&controller.revoke(error))return false;}
    finally{request.checking=false;}
    if(token===epoch&&basis===context(controller.state)&&!panel.hidden){editor=null;render(displayed);notice.textContent='保存结果尚未确认；只能继续查询该回执，不会重复保存。';}return false;
  }
  async function saveEdit(baseline,edit){
    const token=epoch,basis=identity,id=controller.state.id,request={id,key:uuid(),sending:true,base:baseline.base,target:baseline.target,revision:baseline.revision};pending.set(basis,request);
    const body={request_id:request.key,patch:{scope:baseline.scope,base_profile_revision:baseline.base,changes:[]},
      expected_intake_id:baseline.target,expected_intake_revision:baseline.revision,manual_edits:[edit],project_intake:false};
    notice.textContent='正在保存手工更正…';
    try{return await finishReceipt(await api.submitProfileCommit(id,body),request,token,basis);}
    catch(error){
      request.sending=false;
      const rejected=error.status>=400&&error.status<500&&!['NETWORK_UNKNOWN','INVALID_RESPONSE'].includes(error.code);
      if(rejected)pending.delete(basis);
      if(token!==epoch||basis!==context(controller.state)||panel.hidden)return false;
      if(controller.revoke(error))return false;
      if(rejected){
        if(error.code==='VERSION_CONFLICT')return conflictRefresh('档案或接待记录版本已变化，已重新读取；请核对后重新编辑。');
        editor=null;render(displayed);notice.textContent='更正未保存，请检查内容后重新编辑。';return false;
      }
      return lookupPending();
    }finally{request.sending=false;}
  }
  function describe(){
    if(pending.has(identity)){notice.textContent='保存结果尚未确认；请查询回执，不会重复保存。';return;}
    if(!displayed)return;
    const historical=!currentView||displayed.revision<latestRevision?'历史只读版本':'已保存版本';
    const scope=displayed.scope;
    notice.textContent=`${historical} ${displayed.revision} · 来源输入版本 ${scope.input_revision}、材料版本 ${scope.materials_revision}。`+
      '事实仍待核验；最新整理结果请重新读取。';
  }
  async function load(revision){
    if(!available())return false;
    const token=++epoch,basis=context(controller.state),id=controller.state.id;
    const current=()=>token===epoch&&basis===context(controller.state)&&available()&&!panel.hidden;
    displayed=null;editor=null;currentView=revision===undefined;body.replaceChildren();notice.textContent='正在读取已保存的档案版本…';panel.setAttribute('aria-busy','true');at('profile-refresh').disabled=true;
    try{
      const response=await api.getProfile(id,revision);if(!current())return false;
      if(response===null&&revision===undefined){latestRevision=0;render(null);notice.textContent=writable()?'尚无档案草稿；可手工维护，或在整理完成后重新读取。':'尚无档案草稿；可在整理完成后重新读取。';return true;}
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
    at('show-profile').disabled=!available();
    if(editor&&(!writable()||editor.stamp!==scopeStamp(state.view?.scope))){editor=null;render(displayed);notice.textContent='当前输入或范围已变化，请重新读取后再编辑。';}
    else if(displayed&&!pending.has(identity))describe();
  }
  at('show-profile').addEventListener('click',event=>open(event.currentTarget));
  at('close-profile-preview').addEventListener('click',()=>close(true));
  at('profile-refresh').addEventListener('click',()=>panel.hidden?open():load());
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!panel.hidden){event.preventDefault();close(true);}});
  document.defaultView?.addEventListener('pagehide',()=>{ended=true;close();});
  panel.hidden=true;state(controller.state);
  return {state,open,close};
}
