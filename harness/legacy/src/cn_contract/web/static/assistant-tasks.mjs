import {errorText} from './assistant-render.mjs';
import {renderTaskContext,renderNewMatter} from './assistant-task-context.mjs';

const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PDF='application/pdf';
const labels={collecting:'收集中',paused:'已暂停',cancelled:'已取消',frozen:'材料已冻结',prepared:'待选择案件',
  awaiting_facts:'等待事实确认',completed:'模拟审查已完成',blocked:'已阻断',failed:'处理失败',running:'正在模拟审查',queued:'等待执行'};
const blockers={instruction_required:'补充审查指令',main_contract_required:'补充完整可读取的 DOCX 或 PDF 主合同',
  main_contract_selection_required:'选择一份主合同',main_contract_unavailable:'重新核对主合同',
  media_pending:'有材料等待读取',media_unsupported:'有材料尚不支持读取',media_not_readable:'有材料未完整读取',
  media_revision_conflict:'同一材料包含不同读取版本'};

// Task text stays separate from the ordinary conversation composer. No model API is used here.
export function bindTaskDrafts({controller,api,root=document,readonly=false,uuid=()=>crypto.randomUUID(),
  navigate=url=>window.location.assign(url),hash=globalThis.location?.hash||'',isBlocked=()=>false,onActivityChange=()=>{}}={}) {
  const byId=id=>root.getElementById(id);
  let cid=null,page={items:[],unassigned_events:[],binding:null},selected='',closed=false,revoked=false;
  let epoch=0,reading=0,busy=false,pending=null,creating=false,createKey=null,materialKey='';
  let checks=[],writeControls=[],materialsView=null,materialScope=null,businessRun=null;
  const mediaChoices=new Map(),mainChoices=new Map();
  const node=(tag,text)=>{const el=root.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
  const tell=text=>{byId('task-notice').textContent=text;};
  const current=()=>page.items.find(item=>item.id===selected);
  const personal=draft=>draft?.synthetic===false||draft?.events?.some(event=>event.channel==='weixin_personal');
  const active=()=>!closed&&!revoked;
  const writable=()=>active()&&!readonly&&!busy&&!pending&&!controller.state.loading&&!isBlocked();
  const token=()=>({cid,epoch});
  const valid=key=>active()&&key.cid===cid&&key.epoch===epoch;
  const edits=()=>JSON.stringify([selected,byId('task-instruction').value,checks.filter(el=>el.checked).map(el=>el.value),
    [...mainChoices],[...mediaChoices].map(([key,value])=>[key,value.attachmentId])]);
  function button(text,action,{disabled=false,mainDraft=null}={}) {
    const el=node('button',text);el.type='button';el.className='quiet-button';el.disabled=!writable()||disabled;
    writeControls.push({el,disabled,mainDraft});el.addEventListener('click',()=>guard(action));return el;
  }
  function link(text,url){const el=node('a',text);el.href=url;return el;}
  function controls(){
    const locked=!writable();
    byId('task-instruction').disabled=locked||personal(current());byId('task-select').disabled=locked;
    byId('task-collect').disabled=locked||personal(current())||['paused','cancelled'].includes(current()?.state);
    byId('task-refresh').disabled=busy||!active();
    byId('task-retry').hidden=!pending;byId('task-retry').disabled=busy||readonly||!active();
    byId('task-retry').textContent=pending?.query?'查询本次关联结果':'重试同一次操作';
    for(const el of checks)el.disabled=locked;
    for(const item of writeControls)item.el.disabled=locked||item.disabled||!!(item.mainDraft&&mainChoices.has(item.mainDraft));
    onActivityChange();
  }
  async function guard(action,{write=true}={}){
    if(write?!writable():!active()||busy)return false;
    busy=true;controls();const key=token();
    try {return await action();}
    catch(error){
      if(active()&&(!key.cid||valid(key))){
        if(controller.revoke(error)){revoked=true;clear();}
        else tell(error.code==='NETWORK_UNKNOWN'?(pending?.query?'关联结果尚未确认，请点击“查询本次关联结果”，不要再次提交。':pending?'保存结果尚未确认。保留了本次内容，请点击“重试同一次操作”。':
          '连接中断，尚未确认保存结果。请保留本次内容，再次点击“保存本次补充”核对。'):errorText(error));
      }
      return false;
    } finally {busy=false;if(active()){render();controls();}}
  }
  async function submit(path,method,body,onSuccess=()=>{}){
    pending={path,method,body:structuredClone(body),onSuccess};return replay();
  }
  async function replay(){
    const operation=pending,key=token();
    if(!operation)return;
    if(operation.query)return replayMedia(operation,key);
    try{
      const result=await api.request(operation.path,{method:operation.method,body:operation.body});
      if(!valid(key))return;
      pending=null;await operation.onSuccess(result);
      await refresh();tell('已保存。');
    }catch(error){
      if(valid(key)&&error.code!=='NETWORK_UNKNOWN'){pending=null;await refresh().catch(()=>{});}
      throw error;
    }
  }
  async function replayMedia(operation,key){
    let saved;
    if(operation.sent){
      const draft=await api.request(operation.path);
      if(!valid(key))return;
      const expected=operation.body.media_resolutions[0];
      saved=(draft.media_resolutions||[]).some(item=>item.revision===operation.body.expected_revision+1&&
        item.event_id===expected.event_id&&item.media_id===expected.media_id&&item.action===expected.action&&
        Object.entries(expected.replacement).every(([name,value])=>item.replacement?.[name]===value));
      if(!saved){tell('尚未查到本次关联结果，请保留待查询状态；不会再次提交。');return;}
    }else{
      operation.sent=true;
      try{await api.request(operation.path,{method:operation.method,body:operation.body});}
      catch(error){if(valid(key)&&error.code!=='NETWORK_UNKNOWN')pending=null;throw error;}
      if(!valid(key))return;
    }
    pending=null;mediaChoices.delete(operation.query);
    try{await refresh();if(valid(key))tell('已保存关联。');}
    catch(error){
      if(!valid(key))return;
      if(controller.revoke(error)){revoked=true;clear();}
      else tell('已保存关联，但列表刷新失败，请刷新任务列表核对。');
    }
  }
  function clear(){
    ++epoch;++reading;page={items:[],unassigned_events:[],binding:null};selected='';pending=null;
    mediaChoices.clear();mainChoices.clear();materialsView=null;materialScope=null;businessRun=null;
    byId('task-current').replaceChildren();byId('task-unassigned').replaceChildren();
    byId('task-attachments').replaceChildren();byId('task-select').replaceChildren();
    byId('task-instruction').value='';checks=[];writeControls=[];materialKey='';controls();
  }
  async function refresh(){
    if(!cid||!active())return;
    const key=token(),read=++reading,local=edits(),write=pending,wasBusy=busy;
    let result;
    try{result=await api.request('/api/assistant/conversations/'+encodeURIComponent(cid)+'/task-drafts');}
    catch(error){
      if(valid(key)&&[401,403].includes(error.status)){controller.revoke(error);revoked=true;clear();}
      throw error;
    }
    if(!valid(key)||read!==reading||local!==edits()||write!==pending||wasBusy!==busy)return;
    const previous=current();page=result;
    for(const [id,value] of mainChoices)if(page.items.some(item=>item.id===id&&item.main_attachment_id===value))mainChoices.delete(id);
    if(previous&&current()?.revision!==previous.revision)mediaChoices.clear();
    if(!selected&&hash.startsWith('#task-')){selected=hash.slice(6);hash='';byId('task-draft-panel').open=true;}
    if(selected&&!page.items.some(item=>item.id===selected))selected='';
    render();
  }
  function renderMaterials(materials){
    const scope=materials?.scope;
    // A direct GET may be newer than the host's next unrelated state notification.
    if(scope?.conversation_id===cid&&materialScope?.conversation_id===cid&&
      ['binding_revision','input_revision','materials_revision'].some(name=>
        Number.isSafeInteger(scope[name])&&Number.isSafeInteger(materialScope[name])&&scope[name]<materialScope[name]))return;
    const next=JSON.stringify(materials||null);if(next===materialKey)return;materialKey=next;
    const hadChoices=mediaChoices.size>0;mediaChoices.clear();materialsView=materials;materialScope=scope?{...scope}:null;
    if(hadChoices&&!pending)tell('材料已更新，请重新选择并核对对应原件。');
    const picked=new Set(checks.filter(el=>el.checked).map(el=>el.value));checks=[];
    const host=byId('task-attachments');host.replaceChildren();
    for(const file of materials?.attachments||[]){
      const label=node('label'),check=node('input');check.type='checkbox';check.value=file.id;check.checked=picked.has(file.id);
      label.append(check,node('span',file.original_name));host.append(label);checks.push(check);
    }
    if(!checks.length)host.append(node('p','暂无已上传附件。可先保存指令，再从下方“添加材料”上传合成文件。'));
    render();
  }
  async function media(file,materials,mediaId=file.id,conversationId=cid){
    const revision=materials.items?.find(item=>item.attachment_id===file.id)?.parse_revision;
    const supported=file.mime===DOCX||file.mime===PDF;
    const value={media_id:mediaId,name:file.original_name,mime:file.mime,status:supported?'pending':'unsupported',attachment_id:file.id};
    if(supported&&revision){
      const parsed=await api.getParse(conversationId,file.id,revision);
      const formatMatches=file.mime===PDF?
        parsed.parser_version==='qx-pdf-attachments-v1'&&parsed.baseline_view==='original':
        parsed.parser_version==='qx-docx-attachments-v1'&&['original','accepted_view','rejected_view'].includes(parsed.baseline_view);
      if(parsed.reading_status==='readable'&&formatMatches)Object.assign(value,{status:'ready',sha256:file.sha256,parse_revision:revision});
    }
    return value;
  }
  async function ensureConversation(){
    if(cid)return;
    creating=true;
    try{
      if(!await controller.save())throw {code:'STATE_CONFLICT'};
      if(!controller.state.id){
        createKey ||= uuid();
        const view=await api.createConversation({request_id:createKey});
        await controller.open(view.scope.conversation_id);createKey=null;
      }
      cid=controller.state.id;
      if(!cid)throw {code:'STATE_CONFLICT'};
    }finally{creating=false;}
  }
  async function collect(){
    if(personal(current()))return;
    const text=byId('task-instruction').value.trim();
    const chosen=checks.filter(el=>el.checked).map(el=>el.value);
    if(!text&&!chosen.length){tell('请输入指令或勾选已上传附件。');return;}
    await ensureConversation();const key=token();
    const materials=await api.getMaterials(cid);
    const files=await Promise.all(chosen.map(id=>{
      const file=materials.attachments.find(item=>item.id===id);
      if(!file)throw {code:'VERSION_CONFLICT'};
      return media(file,materials);
    }));
    if(!valid(key))return;
    const binding=(page.binding?.channel!=='weixin_personal'&&page.binding)||await api.request('/api/assistant/conversations/'+encodeURIComponent(cid)+'/task-bindings',{method:'POST'});
    if(!valid(key))return;
    const event={event_id:uuid(),text,media:files,...(selected?{task_id:selected}:{start_new:true})};
    await submit('/api/task-bindings/'+binding.id+'/batches','POST',
      {expected_cursor:binding.cursor,next_cursor:binding.cursor+1,events:[event]},result=>{
        byId('task-instruction').value='';for(const el of checks)el.checked=false;
        const draft=result.drafts?.find(item=>item.id===selected)||result.drafts?.[0];if(draft)selected=draft.id;
      });
  }
  const update=(draft,body)=>submit('/api/task-drafts/'+draft.id,'PATCH',{expected_revision:draft.revision,...body});
  function mediaKey(draft,event,original){return JSON.stringify([draft.id,event.id,original.media_id]);}
  async function resolveMedia(draft,event,original,attachmentId,choice=null){
    const key=token(),frame=materialKey,revision=draft.revision,choiceKey=mediaKey(draft,event,original);
    const validTarget=()=>valid(key)&&!controller.state.loading&&selected===draft.id&&current()?.revision===revision&&
      current()?.state==='collecting'&&materialKey===frame&&(!choice||mediaChoices.get(choiceKey)===choice&&choice.select.value===attachmentId);
    const materials=await api.getMaterials(key.cid);
    if(!validTarget())return;
    const file=materials.attachments?.find(item=>item.id===attachmentId);
    if(!file){tell('尚未找到对应的已上传原件，请重新选择。');return;}
    if(choice&&JSON.stringify(materials)!==frame){renderMaterials(materials);tell('材料已更新，请重新选择并核对对应原件。');return;}
    const replacement=await media(file,materials,original.media_id,key.cid);
    if(!validTarget())return;
    if(replacement.status!=='ready'){
      tell(file.mime===PDF?'请先在下方材料区完整读取 PDF；扫描、注释等未读项需人工核对，可排除此项或换用完整可读材料。':
        '请先在下方材料区完成 DOCX 读取，再更新此项。');return;
    }
    const body={expected_revision:revision,media_resolutions:[{event_id:event.id,media_id:original.media_id,action:'resolve',replacement}]};
    if(choice){pending={path:'/api/task-drafts/'+draft.id,method:'PATCH',body,query:choiceKey,sent:false};await replay();}
    else await update(draft,{media_resolutions:body.media_resolutions});
  }
  function renderMedia(draft,event,original,host){
    const resolution=[...(draft.media_resolutions||[])].reverse().find(item=>item.event_id===event.id&&item.media_id===original.media_id);
    const value=resolution?.replacement||original,excluded=resolution?.action==='exclude';
    const row=node('div');row.className='task-media-row';
    row.append(node('p',original.name+' · '+(excluded?'已排除：'+resolution.reason:value.status==='ready'?'读取就绪':value.status==='unsupported'?'暂不支持读取':'等待读取')));
    if(resolution)row.append(node('small','原始收件记录仍保留。'));
    if(!original.attachment_id){
      const choiceKey=mediaKey(draft,event,original),label=node('label','已上传原件'),select=node('select');
      const empty=node('option','请选择对应原件，不会按同名自动关联');empty.value='';select.append(empty);
      const files=(materialsView?.attachments||[]).filter(file=>[DOCX,PDF].includes(file.mime));
      for(const file of files){const option=node('option',file.original_name);option.value=file.id;select.append(option);}
      let choice=mediaChoices.get(choiceKey);
      select.value=choice?.attachmentId||'';if(choice)choice.select=select;
      writeControls.push({el:select,disabled:draft.state!=='collecting'});label.append(select);row.append(label);
      row.append(node('small',files.length?'请核对收件文件名与所选原件，确认属于同一材料后再关联。':'请先从下方“添加材料”上传 DOCX 或 PDF，并完成读取。'));
      const associate=button('关联所选原件并更新读取状态',()=>{
        const picked=mediaChoices.get(choiceKey);if(!picked?.attachmentId){tell('请选择要关联的已上传原件。');return;}
        return resolveMedia(draft,event,original,picked.attachmentId,picked);
      },{disabled:!select.value||draft.state!=='collecting'});
      row.append(associate);
      select.addEventListener('change',()=>{
        if(!writable()||draft.state!=='collecting')return;
        if(select.value)mediaChoices.set(choiceKey,{attachmentId:select.value,select});else mediaChoices.delete(choiceKey);
        tell('');const control=writeControls.find(item=>item.el===associate);if(control)control.disabled=!select.value;
        controls();
      });
    }
    if(draft.state==='collecting'){
      if(value.attachment_id)row.append(button(excluded?'恢复此项并更新读取状态':'更新读取状态',()=>
        resolveMedia(draft,event,original,value.attachment_id)));
      if(!excluded){
        const label=node('label','排除原因'),reason=node('input');reason.type='text';reason.maxLength=1000;reason.disabled=!writable();label.append(reason);
        row.append(label,button('记录原因并排除此项',()=>{
          if(!reason.value.trim()){tell('请先填写排除原因。');return;}
          return update(draft,{media_resolutions:[{event_id:event.id,media_id:original.media_id,action:'exclude',reason:reason.value.trim()}]});
        }));
      }
    }
    host.append(row);
  }
  function renderExecution(execution,host){
    const cancelled=execution.error==='TASK_CANCELLED';
    host.append(node('p',cancelled?'已取消':labels[execution.state]||'执行状态待核对'));
    if(execution.state==='prepared'){
      const label=node('label','已有空案件'),select=node('select');label.append(select);host.append(label);
      const key=token();
      select.append(node('option','正在读取案件…'));select.disabled=true;
      api.request('/api/matters').then(matters=>{
        if(!valid(key))return;
        select.replaceChildren();const empty=node('option','选择一个尚无材料的案件');empty.value='';select.append(empty);
        for(const matter of matters){const option=node('option',matter.title);option.value=matter.id;select.append(option);}
        select.disabled=!writable();
      }).catch(error=>{if(valid(key))tell(errorText(error));});
      host.append(button('准备材料并确认事实',()=>{
        if(!select.value){tell('请选择已有空案件；可从合同工作台新建后刷新本页。');return;}
        return submit('/api/task-executions/'+execution.id+'/prepare','POST',{matter_id:select.value,request_id:uuid()},
          ()=>tell('材料已准备，可在本对话逐项核对事实。'));
      }));
      renderNewMatter({execution,host,node,button,submit,tell});
    }
    if(execution.matter_id){
      const key=token(),container=node('section');host.append(container);
      renderTaskContext({execution,host:container,api,node,button,submit,tell,readonly,
        valid:()=>valid(key)&&container.parentNode===host}).catch(error=>{if(valid(key))tell(errorText(error));});
    }
    if(['prepared','creating_matter','awaiting_facts','queued'].includes(execution.state))host.append(button('停止执行此任务',()=>
      submit('/api/task-executions/'+execution.id+'/cancel','POST',undefined)));
    if(execution.error&&!cancelled)host.append(node('p','执行已停止，请核对材料与事实版本后处理。'));
  }
  function render(){
    writeControls=[];const select=byId('task-select');select.replaceChildren();
    const fresh=node('option','新建模拟任务');fresh.value='';select.append(fresh);
    for(const item of page.items){const option=node('option',(personal(item)?'本人微信 · ':'合成演练 · ')+(labels[item.state]||item.state)+' · '+(item.instruction.slice(0,45)||'待补指令'));option.value=item.id;select.append(option);}
    select.value=selected;
    const host=byId('task-current');host.replaceChildren();const draft=current();
    for(const [id,value] of mainChoices){
      const saved=page.items.find(item=>item.id===id),file=saved?.events.flatMap(event=>event.media).find(item=>item.attachment_id===value);
      host.append(node('p','未保存的主合同选择：'+(file?.name||value||'尚未选择')+'。'+
        (saved?.state==='collecting'||personal(saved)&&saved?.state==='paused'?'请保存或明确放弃此选择。':'任务当前不可编辑，请明确放弃本地选择后继续。')),
        button('放弃本地主合同选择',()=>{mainChoices.delete(id);tell('已放弃本地主合同选择，使用已保存的任务版本。');}));
    }
    if(draft){
      host.id='task-current';
      host.append(node('p',(personal(draft)?'本人微信收件 · ':'合成演练 · ')+'第 '+draft.revision+' 版 · '+labels[draft.state]));
      if(personal(draft))host.append(node('p','此任务使用本人微信通道。分析状态和成果见当前聊天；可在此选择主合同或明确收件归属，补充材料可在微信中发送。'+
        (draft.state==='paused'?'正在等待后续材料；明确恢复收集后才继续处理。':'')));
      const text=node('p',draft.instruction||'还没有审查指令。');text.className='task-saved-instruction';host.append(text);
      const events=node('details'),summary=node('summary','已收集 '+draft.events.length+' 条记录');events.append(summary);
      for(const event of draft.events){const row=node('div');row.className='task-event';if(event.text)row.append(node('p',event.text));for(const item of event.media){
        if(personal(draft)){
          const resolved=[...(draft.media_resolutions||[])].reverse().find(value=>value.event_id===event.id&&value.media_id===item.media_id);
          row.append(node('p',item.name+' · '+(resolved?.action==='exclude'?'已排除':(resolved?.replacement||item).status==='ready'?'读取就绪':'等待读取')));
        }else renderMedia(draft,event,item,row);
      }events.append(row);}
      host.append(events);
      if(draft.blockers.length)host.append(node('p','尚需处理：'+draft.blockers.map(code=>blockers[code]||'核对材料与版本').join('；')));
      if(draft.state==='collecting'||personal(draft)&&draft.state==='paused'){
        const available=new Map();
        for(const event of draft.events)for(const original of event.media){
          const resolved=[...(draft.media_resolutions||[])].reverse().find(item=>item.event_id===event.id&&item.media_id===original.media_id);
          const value=resolved?.replacement||original;
          if(resolved?.action!=='exclude'&&value.status==='ready'&&[DOCX,PDF].includes(value.mime))available.set(value.attachment_id,value);
        }
        if(available.size){
          const label=node('label','主合同'),main=node('select');main.disabled=!writable();label.append(main);host.append(label);
          const empty=node('option','选择主合同');empty.value='';main.append(empty);
          for(const file of available.values()){const option=node('option',file.name);option.value=file.attachment_id;main.append(option);}
          const saved=draft.main_attachment_id||(available.size===1?[...available.keys()][0]:'');
          main.value=mainChoices.has(draft.id)?mainChoices.get(draft.id):saved;
          writeControls.push({el:main,disabled:false});
          main.addEventListener('change',()=>{
            if(!writable())return;
            if(main.value===saved)mainChoices.delete(draft.id);else mainChoices.set(draft.id,main.value);
            controls();
          });
          host.append(button('保存主合同选择',()=>main.value?update(draft,{main_attachment_id:main.value}):tell('请选择主合同。')));
        }
        if(draft.state==='collecting')host.append(button('暂停收集',()=>update(draft,{action:'pause'})),button('取消任务',()=>update(draft,{action:'cancel'})));
        if(!personal(draft))host.append(button('冻结材料',()=>mainChoices.has(draft.id)?tell('请先保存或放弃本地主合同选择，再冻结材料。'):
            submit('/api/task-drafts/'+draft.id+'/freeze','POST',{expected_revision:draft.revision,manifest_sha256:draft.manifest_sha256}),
          {disabled:draft.blockers.length>0,mainDraft:draft.id}));
      }
      if(['paused','cancelled'].includes(draft.state))host.append(button('恢复收集',()=>update(draft,{action:'resume'}),{mainDraft:draft.id}));
      if(draft.execution&&!personal(draft))renderExecution(draft.execution,host);
    }
    const unassigned=byId('task-unassigned');unassigned.replaceChildren();
    if(page.unassigned_events.length){
      unassigned.append(node('p','有 '+page.unassigned_events.length+' 条记录尚未分配任务。请选择收集中或已暂停的任务后归入。'));
      for(const event of page.unassigned_events){const row=node('div',event.text||event.media.map(item=>item.name).join('、'));
        const sameSource=personal(draft)?event.channel==='weixin_personal'&&draft.events.some(item=>item.binding_id===event.binding_id):event.channel!=='weixin_personal';
        if(sameSource&&(draft?.state==='collecting'||personal(draft)&&draft?.state==='paused'))row.append(button('归入当前任务',()=>update(draft,{action:'assign',event_ids:[event.id]}),{mainDraft:draft.id}));unassigned.append(row);}
    }
    controls();
  }
  byId('task-collect').addEventListener('click',()=>guard(collect));
  byId('task-refresh').addEventListener('click',()=>guard(refresh,{write:false}));
  byId('task-retry').addEventListener('click',async()=>{
    if(!pending||busy||readonly||!active())return;
    busy=true;controls();try{await replay();}catch(error){if(controller.revoke(error)){revoked=true;clear();}else tell(errorText(error));}
    finally{busy=false;if(active())render();}
  });
  byId('task-select').addEventListener('change',()=>{if(selected!==byId('task-select').value)mediaChoices.clear();selected=byId('task-select').value;render();});
  return {
    updateControls:controls,
    open(){byId('task-draft-panel').open=true;byId('task-draft-panel').scrollIntoView({block:'start'});byId('task-instruction').focus();},
    refresh,
    hasPending:()=>!!pending||busy||mediaChoices.size>0||mainChoices.size>0||!!byId('task-instruction').value.trim()||checks.some(el=>el.checked),
    state(state){
      if(closed)return;
      if(state.status==='revoked'){revoked=true;cid=null;clear();return;}
      if(state.id!==cid){
        if(!creating)clear();else{++epoch;++reading;}
        cid=state.id;
        if(cid)void refresh().catch(error=>{if(active())tell(errorText(error));});
      }
      renderMaterials(state.materials);
      const latest=state.business?.items?.filter(item=>item.contract_draft_id).at(-1);
      if(latest&&latest.run_id!==businessRun&&!busy&&!pending){
        businessRun=latest.run_id;selected=latest.contract_draft_id;
        void refresh().catch(error=>{if(active())tell(errorText(error));});
      }
      controls();
    },
    dispose(){closed=true;++epoch;++reading;mediaChoices.clear();mainChoices.clear();pending=null;},
  };
}
