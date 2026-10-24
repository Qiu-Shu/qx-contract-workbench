import {errorText} from './assistant-render.mjs';

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
  navigate=url=>window.location.assign(url),hash=globalThis.location?.hash||''}={}) {
  const byId=id=>root.getElementById(id);
  let cid=null,page={items:[],unassigned_events:[],binding:null},selected='',closed=false,revoked=false;
  let epoch=0,reading=0,busy=false,pending=null,creating=false,createKey=null,materialKey='';
  let checks=[],writeControls=[];
  const node=(tag,text)=>{const el=root.createElement(tag);if(text!==undefined)el.textContent=text;return el;};
  const tell=text=>{byId('task-notice').textContent=text;};
  const current=()=>page.items.find(item=>item.id===selected);
  const active=()=>!closed&&!revoked;
  const writable=()=>active()&&!readonly&&!busy&&!pending&&!controller.state.loading;
  const token=()=>({cid,epoch});
  const valid=key=>active()&&key.cid===cid&&key.epoch===epoch;
  function button(text,action,{disabled=false}={}) {
    const el=node('button',text);el.type='button';el.className='quiet-button';el.disabled=!writable()||disabled;
    writeControls.push({el,disabled});el.addEventListener('click',()=>guard(action));return el;
  }
  function link(text,url){const el=node('a',text);el.href=url;return el;}
  function controls(){
    const locked=!writable();
    byId('task-instruction').disabled=locked;byId('task-select').disabled=locked;
    byId('task-collect').disabled=locked||['paused','cancelled'].includes(current()?.state);
    byId('task-refresh').disabled=busy||!active();
    byId('task-retry').hidden=!pending;byId('task-retry').disabled=busy||readonly||!active();
    for(const el of checks)el.disabled=locked;
    for(const item of writeControls)item.el.disabled=locked||item.disabled;
  }
  async function guard(action,{write=true}={}){
    if(write?!writable():!active()||busy)return false;
    busy=true;controls();const key=token();
    try {return await action();}
    catch(error){
      if(active()&&(!key.cid||valid(key))){
        if(controller.revoke(error)){revoked=true;clear();}
        else tell(error.code==='NETWORK_UNKNOWN'?(pending?'保存结果尚未确认。保留了本次内容，请点击“重试同一次操作”。':
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
  function clear(){
    ++epoch;++reading;page={items:[],unassigned_events:[],binding:null};selected='';pending=null;
    byId('task-current').replaceChildren();byId('task-unassigned').replaceChildren();
    byId('task-attachments').replaceChildren();byId('task-select').replaceChildren();
    byId('task-instruction').value='';checks=[];writeControls=[];materialKey='';controls();
  }
  async function refresh(){
    if(!cid||!active())return;
    const key=token(),read=++reading;
    let result;
    try{result=await api.request('/api/assistant/conversations/'+encodeURIComponent(cid)+'/task-drafts');}
    catch(error){
      if(valid(key)&&[401,403].includes(error.status)){controller.revoke(error);revoked=true;clear();}
      throw error;
    }
    if(!valid(key)||read!==reading)return;
    page=result;
    if(!selected&&hash.startsWith('#task-')){selected=hash.slice(6);hash='';byId('task-draft-panel').open=true;}
    if(selected&&!page.items.some(item=>item.id===selected))selected='';
    render();
  }
  function renderMaterials(materials){
    const next=JSON.stringify(materials||null);if(next===materialKey)return;materialKey=next;
    const picked=new Set(checks.filter(el=>el.checked).map(el=>el.value));checks=[];
    const host=byId('task-attachments');host.replaceChildren();
    for(const file of materials?.attachments||[]){
      const label=node('label'),check=node('input');check.type='checkbox';check.value=file.id;check.checked=picked.has(file.id);
      label.append(check,node('span',file.original_name));host.append(label);checks.push(check);
    }
    if(!checks.length)host.append(node('p','暂无已上传附件。可先保存指令，再从下方“添加材料”上传合成文件。'));
    controls();
  }
  async function media(file,materials,mediaId=file.id){
    const revision=materials.items?.find(item=>item.attachment_id===file.id)?.parse_revision;
    const supported=file.mime===DOCX||file.mime===PDF;
    const value={media_id:mediaId,name:file.original_name,mime:file.mime,status:supported?'pending':'unsupported',attachment_id:file.id};
    if(supported&&revision){
      const parsed=await api.getParse(cid,file.id,revision);
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
    const binding=page.binding||await api.request('/api/assistant/conversations/'+encodeURIComponent(cid)+'/task-bindings',{method:'POST'});
    if(!valid(key))return;
    const event={event_id:uuid(),text,media:files,...(selected?{task_id:selected}:{start_new:true})};
    await submit('/api/task-bindings/'+binding.id+'/batches','POST',
      {expected_cursor:binding.cursor,next_cursor:binding.cursor+1,events:[event]},result=>{
        byId('task-instruction').value='';for(const el of checks)el.checked=false;
        const draft=result.drafts?.find(item=>item.id===selected)||result.drafts?.[0];if(draft)selected=draft.id;
      });
  }
  const update=(draft,body)=>submit('/api/task-drafts/'+draft.id,'PATCH',{expected_revision:draft.revision,...body});
  function renderMedia(draft,event,original,host){
    const resolution=[...(draft.media_resolutions||[])].reverse().find(item=>item.event_id===event.id&&item.media_id===original.media_id);
    const value=resolution?.replacement||original,excluded=resolution?.action==='exclude';
    const row=node('div');row.className='task-media-row';
    row.append(node('p',original.name+' · '+(excluded?'已排除：'+resolution.reason:value.status==='ready'?'读取就绪':value.status==='unsupported'?'暂不支持读取':'等待读取')));
    if(resolution)row.append(node('small','原始收件记录仍保留。'));
    if(draft.state==='collecting'){
      row.append(button(excluded?'恢复此项并更新读取状态':'更新读取状态',async()=>{
        const materials=await api.getMaterials(cid),file=materials.attachments.find(item=>item.id===original.attachment_id);
        if(!file){tell('尚未找到对应的已上传原件。');return;}
        const replacement=await media(file,materials,original.media_id);
        if(replacement.status!=='ready'){tell(file.mime===PDF?
          '请先在下方材料区完整读取 PDF；扫描、注释等未读项需人工核对，可排除此项或换用完整可读材料。':
          '请先在下方材料区完成 DOCX 读取，再更新此项。');return;}
        await update(draft,{media_resolutions:[{event_id:event.id,media_id:original.media_id,action:'resolve',replacement}]});
      }));
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
          result=>navigate('/matters/'+result.matter_id+'/facts'));
      }));
    }
    if(execution.matter_id){
      host.append(readonly?link('查看恢复案件与原件','/recovery/matters/'+execution.matter_id):
        link('打开事实确认页','/matters/'+execution.matter_id+'/facts'));
      if(execution.state==='awaiting_facts')host.append(button('运行模拟审查',async()=>{
        const key=token(),facts=await api.request('/api/matters/'+execution.matter_id+'/facts');
        if(!valid(key))return;
        if(!facts?.version){tell('请先打开事实确认页并完成确认。');return;}
        await submit('/api/task-executions/'+execution.id+'/review','POST',{
          request_id:uuid(),review:{fact_version:facts.version,document_hashes:execution.document_versions}});
      }));
      if(execution.review_run_id)host.append(readonly?link('查看历史模拟结果','/recovery/task-executions/'+execution.id):
        link('查看模拟审查结果','/matters/'+execution.matter_id+'/review'));
    }
    if(['prepared','creating_matter','awaiting_facts','queued'].includes(execution.state))host.append(button('停止执行此任务',()=>
      submit('/api/task-executions/'+execution.id+'/cancel','POST',undefined)));
    if(execution.error&&!cancelled)host.append(node('p','执行已停止，请核对材料与事实版本后处理。'));
  }
  function render(){
    writeControls=[];const select=byId('task-select');select.replaceChildren();
    const fresh=node('option','新建模拟任务');fresh.value='';select.append(fresh);
    for(const item of page.items){const option=node('option',(labels[item.state]||item.state)+' · '+(item.instruction.slice(0,45)||'待补指令'));option.value=item.id;select.append(option);}
    select.value=selected;
    const host=byId('task-current');host.replaceChildren();const draft=current();
    if(draft){
      host.id='task-current';
      host.append(node('p','第 '+draft.revision+' 版 · '+labels[draft.state]));
      const text=node('p',draft.instruction||'还没有审查指令。');text.className='task-saved-instruction';host.append(text);
      const events=node('details'),summary=node('summary','已收集 '+draft.events.length+' 条记录');events.append(summary);
      for(const event of draft.events){const row=node('div');row.className='task-event';if(event.text)row.append(node('p',event.text));for(const item of event.media)renderMedia(draft,event,item,row);events.append(row);}
      host.append(events);
      if(draft.blockers.length)host.append(node('p','尚需处理：'+draft.blockers.map(code=>blockers[code]||'核对材料与版本').join('；')));
      if(draft.state==='collecting'){
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
          main.value=draft.main_attachment_id||(available.size===1?[...available.keys()][0]:'');
          host.append(button('保存主合同选择',()=>main.value?update(draft,{main_attachment_id:main.value}):tell('请选择主合同。')));
        }
        host.append(button('暂停收集',()=>update(draft,{action:'pause'})),button('取消任务',()=>update(draft,{action:'cancel'})),
          button('冻结材料',()=>submit('/api/task-drafts/'+draft.id+'/freeze','POST',{expected_revision:draft.revision,manifest_sha256:draft.manifest_sha256}),{disabled:draft.blockers.length>0}));
      }else if(['paused','cancelled'].includes(draft.state))host.append(button('恢复收集',()=>update(draft,{action:'resume'})));
      if(draft.execution)renderExecution(draft.execution,host);
    }
    const unassigned=byId('task-unassigned');unassigned.replaceChildren();
    if(page.unassigned_events.length){
      unassigned.append(node('p','有 '+page.unassigned_events.length+' 条记录尚未分配任务。请选择收集中的任务后归入。'));
      for(const event of page.unassigned_events){const row=node('div',event.text||event.media.map(item=>item.name).join('、'));
        if(draft?.state==='collecting')row.append(button('归入当前任务',()=>update(draft,{action:'assign',event_ids:[event.id]})));unassigned.append(row);}
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
  byId('task-select').addEventListener('change',()=>{selected=byId('task-select').value;render();});
  return {
    open(){byId('task-draft-panel').open=true;byId('task-draft-panel').scrollIntoView({block:'start'});byId('task-instruction').focus();},
    refresh,
    hasPending:()=>!!pending||busy||!!byId('task-instruction').value.trim()||checks.some(el=>el.checked),
    state(state){
      if(closed)return;
      if(state.status==='revoked'){revoked=true;cid=null;clear();return;}
      if(state.id!==cid){
        if(!creating)clear();else{++epoch;++reading;}
        cid=state.id;
        if(cid)void refresh().catch(error=>{if(active())tell(errorText(error));});
      }
      renderMaterials(state.materials);
      controls();
    },
    dispose(){closed=true;++epoch;++reading;},
  };
}
