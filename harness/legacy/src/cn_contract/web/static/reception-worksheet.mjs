// The worksheet edits existing protected profile fields; all model sends use the composer.
const fields={consultation:['worksheet-source','接待原始陈述'],internal_notes:['worksheet-notes','事项底稿'],
  questions:['worksheet-questions','当前追问'],materials:['worksheet-materials','材料要求'],client_reply:['worksheet-client-reply','客户回复']};
const header='【接待追问任务：借贷咨询】';
const identity=state=>JSON.stringify([state.id,...['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision'].map(k=>state.view?.scope?.[k])]);
const sameScope=(a,b)=>['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'].every(k=>a?.[k]===b?.[k]);
const intent=state=>JSON.stringify([['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'].map(k=>state.view?.scope?.[k]),
  state.skill,state.context?.selected||[],state.materialAction||null,state.materials?.items||[]]);
const invalid=()=>({code:'INVALID_RESPONSE',status:0});
const nonnegative=x=>Number.isSafeInteger(x)&&x>=0;

function formatted(value,field){
  if(value===null || value?.kind==='null')return '';
  if(field==='questions'){
    if(value?.kind!=='list'||!Array.isArray(value.value)||!value.value.every(x=>typeof x==='string'))throw invalid();
    return value.value.join('\n');
  }
  if(field==='materials'){
    if(value?.kind!=='materials'||!Array.isArray(value.value)||!value.value.every(x=>typeof x.name==='string'&&['needed','received','checked'].includes(x.state)))throw invalid();
    return value.value.map(x=>x.name).join('\n');
  }
  if(value?.kind!=='text'||typeof value.value!=='string')throw invalid();return value.value;
}
function chosen(field){
  if(!field)return null;
  if(field.protected_value!==null)return field.protected_value;
  const unique=new Map(field.candidates.filter(x=>x.value.kind!=='null').map(x=>[JSON.stringify(x.value),x.value]));
  return unique.size===1?[...unique.values()][0]:null;
}

export function bindReceptionWorksheet({controller,api,document=globalThis.document,readonly=false,
    uuid=()=>crypto.randomUUID(),onPrepared=()=>{}}){
  const at=id=>document.getElementById(id),panel=at('worksheet-panel');
  let key=null,epoch=0,snapshot=null,baseline={},dirty=false,busy=false,pending=null,conflict=null,disposed=false,completedKey='';
  let candidateButtons=[],templateButtons=[];
  const adopted=new Set();
  const note=text=>{at('worksheet-notice').textContent=text;};
  const available=()=>!disposed&&controller.state.id&&controller.state.view&&controller.state.status!=='revoked';
  const active=(token,cid)=>token===epoch&&available()&&cid===controller.state.id&&key===identity(controller.state);
  const writable=()=>available()&&!readonly&&snapshot?.writable&&!busy&&!pending&&!conflict;
  const hasPending=()=>dirty||Boolean(pending)||busy;
  function controls(){
    at('show-worksheet').disabled=!available()||controller.state.loading;
    for(const [id]of Object.values(fields))at(id).disabled=!writable();
    for(const id of ['worksheet-from-composer','worksheet-outline'])at(id).disabled=!writable();
    at('worksheet-save').disabled=!writable()||!dirty;
    at('worksheet-suggest').disabled=!writable()||dirty;
    at('worksheet-prepare').disabled=!writable()||dirty;
    at('worksheet-refresh').disabled=!available()||busy||Boolean(pending);
    at('worksheet-lookup').hidden=!pending;at('worksheet-lookup').disabled=busy;
    at('worksheet-conflict').hidden=!conflict;
    for(const id of ['worksheet-keep-local','worksheet-use-server'])at(id).disabled=busy||!conflict;
    at('worksheet-discard').disabled=!available()||busy||Boolean(pending)||!dirty;
    for(const button of [...candidateButtons,...templateButtons])button.disabled=!writable();
  }
  function changed(){dirty=adopted.size>0||Object.entries(fields).some(([name,[id]])=>at(id).value!==(baseline[name]??''));
    if(at('worksheet-source').value!==(baseline.consultation??'')){at('worksheet-suggestions').replaceChildren();templateButtons=[];}controls();}
  function clear(){
    ++epoch;snapshot=null;baseline={};dirty=false;busy=false;pending=null;conflict=null;completedKey='';adopted.clear();
    for(const [id]of Object.values(fields))at(id).value='';
    for(const id of ['worksheet-candidates','worksheet-suggestions'])at(id).replaceChildren();candidateButtons=[];templateButtons=[];
    at('worksheet-version').textContent='';note('');panel.open=false;controls();
  }
  function checked(value){
    const state=controller.state,current=state.view?.scope;
    if(!value||value.scope?.conversation_id!==state.id||!current||
        ['workspace_id','scope_kind','scope_ref','binding_revision'].some(k=>value.scope[k]!==current[k])||
        !nonnegative(value.profile_revision)||!nonnegative(value.composer_revision)||typeof value.writable!=='boolean'||
        !Array.isArray(value.fields)||value.fields.length>5||new Set(value.fields.map(f=>f.field)).size!==value.fields.length||
        value.fields.some(f=>!Object.hasOwn(fields,f.field)||!Array.isArray(f.candidates)))throw invalid();
    for(const field of value.fields){formatted(chosen(field),field.field);for(const item of field.candidates)formatted(item.value,field.field);}
    return value;
  }
  function node(tag,text){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;}
  function candidates(){
    const host=at('worksheet-candidates');host.replaceChildren();candidateButtons=[];
    for(const field of snapshot.fields){
      for(const item of field.candidates){
        const text=formatted(item.value,field.field);if(!text)continue;
        const details=node('details'),summary=node('summary',fields[field.field][1]+' · 已保存待核候选');details.append(summary,node('p',text));
        const sources=(item.source_refs||[]).map(ref=>ref.kind==='message'?ref.quote:ref.anchor?.quote).filter(Boolean);
        if(sources.length)details.append(node('p','候选所据原话（仍待核）：\n'+sources.join('\n')));
        const use=node('button','采用这项候选');use.type='button';use.disabled=!writable();candidateButtons.push(use);
        use.addEventListener('click',()=>{if(!writable())return;at(fields[field.field][0]).value=text;adopted.add(field.field);changed();note('候选已放入编辑区，核对后点击保存底稿；尚未保存。');});
        details.append(use);host.append(details);
      }
    }
  }
  function fill(value){
    snapshot=checked(value);baseline={};conflict=null;dirty=false;adopted.clear();
    for(const [name,[id]]of Object.entries(fields)){
      const field=snapshot.fields.find(f=>f.field===name);baseline[name]=formatted(chosen(field),name);at(id).value=baseline[name];
    }
    at('worksheet-version').textContent=`已保存档案版本 ${snapshot.profile_revision} · 录入与整理内容仍待核验。`;
    at('worksheet-suggestions').replaceChildren();templateButtons=[];controls();candidates();
  }
  function failure(error){
    if(controller.revoke(error))return;
    note(error.code==='VERSION_CONFLICT'?'保存版本或输入已变化，编辑内容已保留。请核对最新版本。':
      error.code==='NOT_SUPPORTED'?'本片AI准备仅支持文字接待；含附件时请先核对材料，不会自动发送。':
      error.code==='BLOCKED_LIVE'?'当前副本只读，不能准备或保存新的接待任务。':
      error.code==='FILE_LIMIT'?'内容超过当前文字上限，请缩短后再核对。':
      '操作未完成。请先保存接待原始陈述并核对版本；不会因此调用模型。');
  }
  async function refresh(){
    if(!available()||busy||pending)return false;
    const token=++epoch,cid=controller.state.id;busy=true;note('正在读取接待底稿…');controls();
    try{
      const value=checked(await api.getWorksheet(cid));if(!active(token,cid))return false;
      if(dirty){conflict=value;note('最新保存版本已读取，你的编辑保留在原处。请选择保留编辑，或采用已保存版本。');}
      else{fill(value);note(!readonly&&snapshot.writable?'可手工填写并保存。模板建议不会调用模型；AI任务需放入输入框核对后发送。':
        '当前为只读记录，可核对保存内容；不能编辑、准备模型任务或继续历史执行。');}
      return true;
    }catch(error){if(active(token,cid))failure(error);return false;}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function open(){if(!available())return false;panel.open=true;if(!snapshot&&!busy)return refresh();controls();return true;}
  function editedValue(name){
    const text=at(fields[name][0]).value;
    if(name==='questions')return {kind:'list',value:text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)};
    if(name==='materials'){
      const prior=chosen(snapshot.fields.find(f=>f.field===name));
      return {kind:'materials',value:text.split(/\r?\n/).map(x=>x.trim()).filter(Boolean).map(name=>({name,
        state:prior?.kind==='materials'?prior.value.find(x=>x.name===name)?.state || 'needed':'needed'}))};
    }
    return text.trim()?{kind:'text',value:text}:{kind:'null',value:null};
  }
  function validReceipt(value,request){
    return value&&value.conversation_id===request.cid&&value.request_id===request.body.request_id&&
      value.audience==='internal'&&value.projection_changed===false&&typeof value.profile_changed==='boolean'&&
      value.profile_revision===request.body.patch.base_profile_revision+Number(value.profile_changed)&&
      value.intake_id===request.body.expected_intake_id&&value.intake_revision===request.body.expected_intake_revision&&
      value.event_type===(value.profile_changed?'profile.saved':'profile.unchanged');
  }
  async function finish(receipt,request,token){
    if(!validReceipt(receipt,request))throw invalid();
    if(!active(token,request.cid))return false;
    // The original commit is confirmed even if reading the latest view then fails.
    pending=null;dirty=false;
    try{const latest=await api.getWorksheet(request.cid);if(!active(token,request.cid))return false;fill(latest);
      note('已确认保存回执，人工修改与明确清空受保护；内容仍待核验。');return true;
    }catch(error){if(active(token,request.cid)){snapshot=null;failure(error);note('本次保存回执已确认，最新视图未读取成功。请重新读取，不要重复保存。');}return false;}
  }
  async function lookup(){
    if(!pending||busy||!available())return false;
    const request=pending,token=++epoch;busy=true;controls();
    try{const value=await api.findWorksheetReceipt(request.cid,request.body.request_id);
      if(!active(token,request.cid))return false;
      if(value)return await finish(value,request,token);
      note('本次保存结果尚未确认，请继续查询同一回执，不会重复保存。');return false;
    }catch(error){if(active(token,request.cid))failure(error);return false;}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function save(){
    if(pending)return lookup();
    if(!writable()||!dirty)return false;
    const edits=Object.entries(fields).filter(([name,[id]])=>adopted.has(name)||at(id).value!==baseline[name]).map(([field])=>({field,value:editedValue(field)}));
    if(edits.some(e=>(e.value.kind==='list'||e.value.kind==='materials')&&(e.value.value.length>30||e.value.value.some(x=>(typeof x==='string'?x:x.name).length>300)))){
      note('追问和材料最多各30项，每项最多300字。');return false;
    }
    const cid=controller.state.id,token=++epoch;
    const request={cid,body:{request_id:uuid(),patch:{scope:snapshot.scope,base_profile_revision:snapshot.profile_revision,changes:[]},
      expected_intake_id:snapshot.expected_intake_id,expected_intake_revision:snapshot.expected_intake_revision,
      manual_edits:edits,project_intake:false}};
    pending=request;busy=true;note('正在保存底稿…');controls();
    try{return await finish(await api.commitWorksheet(cid,request.body),request,token);}
    catch(error){
      if(!active(token,cid))return false;
      const rejected=error.status>=400&&error.status<500&&!['NETWORK_UNKNOWN','INVALID_RESPONSE'].includes(error.code);
      if(rejected)pending=null;
      if(controller.revoke(error))return false;
      if(rejected&&error.code==='VERSION_CONFLICT'){
        try{const value=checked(await api.getWorksheet(cid));if(!active(token,cid))return false;conflict=value;}
        catch(readError){if(active(token,cid))failure(readError);return false;}
        note('版本已变化，编辑内容保留。请比较后选择保留编辑或采用已保存版本。');
      }else if(rejected)failure(error);
      else note('保存结果尚不确定，请查询本次回执；不会重复提交。');
      return false;
    }finally{if(token===epoch){busy=false;controls();}}
  }
  async function suggest(){
    if(!writable()||dirty)return false;
    const token=++epoch,cid=controller.state.id,saved=snapshot;busy=true;controls();
    try{
      const value=await api.suggestWorksheet(cid,{expected_scope:saved.scope,base_profile_revision:saved.profile_revision});
      if(!active(token,cid))return false;
      if(!sameScope(value?.scope,saved.scope)||value.profile_revision!==saved.profile_revision||value.origin!=='template'||value.model_called!==false||!Array.isArray(value.items))throw invalid();
      const source=baseline.consultation;const host=at('worksheet-suggestions');templateButtons=[];host.replaceChildren(node('p','本地模板建议 · 未调用模型 · 采用后仍需核对并保存。'));
      for(const item of value.items){
        if(typeof item.question!=='string'||typeof item.reason!=='string'||typeof item.quote!=='string'||!item.quote||
            !source.includes(item.quote)||!Array.isArray(item.materials)||!item.materials.every(x=>typeof x==='string'))throw invalid();
        const card=node('section');card.append(node('p',item.question),node('p','追问理由：'+item.reason),node('p','所据已保存原话：'+item.quote));
        const use=node('button','采用此追问');use.type='button';templateButtons.push(use);
        use.addEventListener('click',()=>{
          if(!writable()||snapshot!==saved)return;
          const questions=at('worksheet-questions'),line=item.question+'（'+item.reason+'）';
          const lines=questions.value.split(/\r?\n/).filter(Boolean);if(!lines.includes(line))lines.push(line);questions.value=lines.join('\n');
          const materials=at('worksheet-materials'),names=materials.value.split(/\r?\n/).filter(Boolean);
          materials.value=[...new Set([...names,...item.materials])].join('\n');changed();note('已放入追问和材料编辑区，核对后保存；没有自动认定事实。');
        });card.append(use);host.append(card);
      }
      note('模板根据已保存的文字线索提供建议，未调用模型。');return true;
    }catch(error){if(active(token,cid)){at('worksheet-suggestions').replaceChildren();failure(error);}return false;}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function prepare(){
    if(!writable()||dirty)return false;
    if(controller.state.context?.selected?.length){note('请先取消资料辅助回答的选片，再准备本片文字接待任务。');return false;}
    const token=++epoch,cid=controller.state.id,saved=snapshot,choice=intent(controller.state);busy=true;note('正在核对底稿和本轮补充文字…');controls();
    const sameIntent=()=>{if(intent(controller.state)===choice)return true;note('能力、选片或材料已变化，保留新选择；未替换为旧准备结果。');return false;};
    try{
      if(!await controller.save()||!active(token,cid)||!sameIntent())return false;
      const text=controller.state.text,composer=controller.state.view.composer_revision;
      const latest=checked(await api.getWorksheet(cid));if(!active(token,cid)||!sameIntent())return false;
      if(latest.profile_revision!==saved.profile_revision){conflict=latest;note('档案版本已变化，请核对后重新准备。');return false;}
      const value=await api.prepareWorksheet(cid,{expected_scope:latest.scope,base_profile_revision:latest.profile_revision,expected_composer_revision:latest.composer_revision});
      if(!active(token,cid)||!sameIntent())return false;
      if(controller.state.text!==text||controller.state.dirty||controller.state.view.composer_revision!==composer){note('输入已变化，保留新文字；未替换为旧准备结果。');return false;}
      if(value?.model_called!==false||!sameScope(value.scope,latest.scope)||value.profile_revision!==saved.profile_revision||
          value.composer_revision!==composer||typeof value.content!=='string'||!value.content.startsWith(header))throw invalid();
      if(controller.state.skill)controller.selectSkill(null);
      controller.edit(value.content);onPrepared();
      const stored=await controller.save();if(!active(token,cid))return false;
      note(stored?'任务已放入并保存为输入框草稿，尚未发送或调用模型。请核对全文后发送；回答完成后可重新读取底稿查看候选。':
        '准备文字保留在输入框，但草稿保存未确认；请先核对保存状态，不会自动发送。');return Boolean(stored);
    }catch(error){if(active(token,cid))failure(error);return false;}
    finally{if(token===epoch){busy=false;controls();}}
  }
  async function useServer(){if(!conflict||busy||pending)return false;fill(conflict);note('已采用最新保存版本。');return true;}
  async function keepLocal(){if(!conflict||busy||pending)return false;
    const edits=Object.entries(fields).filter(([name,[id]])=>adopted.has(name)||at(id).value!==baseline[name]).map(([name,[id]])=>[name,at(id).value]);
    const chosenFields=new Set(adopted);fill(conflict);for(const [name,value]of edits){at(fields[name][0]).value=value;if(chosenFields.has(name))adopted.add(name);}
    changed();note('编辑已保留，未编辑字段采用最新保存值；点击保存底稿确认。');return true;}
  for(const [id]of Object.values(fields))at(id).addEventListener('input',changed);
  at('show-worksheet').addEventListener('click',open);
  panel.addEventListener('toggle',()=>{if(panel.open&&!snapshot&&!busy)void refresh();});
  at('worksheet-refresh').addEventListener('click',refresh);
  at('worksheet-save').addEventListener('click',save);at('worksheet-lookup').addEventListener('click',lookup);
  at('worksheet-suggest').addEventListener('click',suggest);at('worksheet-prepare').addEventListener('click',prepare);
  at('worksheet-use-server').addEventListener('click',useServer);at('worksheet-keep-local').addEventListener('click',keepLocal);
  at('worksheet-discard').addEventListener('click',()=>{if(busy||pending||!snapshot)return;fill(snapshot);note('已放弃未保存编辑，显示已保存版本。');});
  at('worksheet-from-composer').addEventListener('click',()=>{if(!writable()||!controller.state.text.trim())return;
    const e=at('worksheet-source');e.value+=(e.value?'\n\n':'')+controller.state.text;changed();});
  at('worksheet-outline').addEventListener('click',()=>{if(!writable())return;const e=at('worksheet-notes');
    e.value+=(e.value?'\n\n':'')+'客户诉求：\n我方立场：\n已知陈述（待核）：\n待核问题：\n下一步：';changed();});
  return {open,refresh,save,suggest,prepare,lookup,useServer,keepLocal,hasPending,
    state(state){const next=identity(state);if(next!==key||state.status==='revoked'){key=next;clear();}
      const received=JSON.stringify((state.generation?.items||[]).filter(x=>x.attempt?.state==='received'&&x.attempt?.input_format==='profile-text-v1').map(x=>x.attempt.id));
      if(received!==completedKey){const before=completedKey;completedKey=received;if(before&&panel.open&&snapshot&&!hasPending())void refresh();}
      controls();},dispose(){disposed=true;clear();}};
}
