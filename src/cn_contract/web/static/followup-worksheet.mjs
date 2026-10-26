// These records support manual follow-up; they do not verify legal facts or send messages.
const statuses={open:'待补',requested:'已催补',received:'收到待核',completed:'已处理',cancelled:'不再跟进'};
const fields={'title':300,'reason':1000,'impact':1000,'next-action':1000,'result':2000};
const scopeKey=s=>JSON.stringify([s?.conversation_id,s?.workspace_id,s?.scope_kind,s?.scope_ref,s?.binding_revision]);
const fixed=s=>JSON.stringify([s.id,scopeKey(s.view?.scope)]);
const clone=value=>structuredClone(value);
const validRevision=n=>Number.isSafeInteger(n)&&n>=0;
const validDate=value=>!value||/^\d{4}-\d{2}-\d{2}$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
function validItem(item){
 return item&&typeof item.id==='string'&&item.id&&Object.hasOwn(statuses,item.status)&&
  Object.entries(fields).every(([field,max])=>typeof item[field==='next-action'?'next_action':field]==='string'&&[...item[field==='next-action'?'next_action':field]].length<=max)&&
  item.title.trim()&&item.reason.trim()&&item.impact.trim()&&(item.due_date===null||typeof item.due_date==='string'&&validDate(item.due_date))&&
  (!['completed','cancelled'].includes(item.status)||item.result.trim())&&
  Array.isArray(item.facts)&&Array.isArray(item.materials)&&item.facts.length<=10&&item.materials.length<=10&&item.facts.length+item.materials.length>0&&
  item.facts.every(ref=>validRevision(ref.evidence_revision)&&ref.evidence_revision>0&&typeof ref.fact_id==='string'&&ref.fact_id)&&
  item.materials.every(ref=>typeof ref.attachment_id==='string'&&ref.attachment_id&&/^[0-9a-f]{64}$/.test(ref.original_sha256)&&(ref.parse_revision===null||validRevision(ref.parse_revision)&&ref.parse_revision>0));
}
const validItems=items=>Array.isArray(items)&&items.length<=100&&items.every(validItem)&&new Set(items.map(item=>item.id)).size===items.length;

export function bindFollowupWorksheet({controller,api,document=globalThis.document,readonly=false,uuid=()=>crypto.randomUUID()}){
 const at=id=>document.getElementById(id),el=name=>at('followup-'+name),panel=el('panel');
 const node=(tag,text)=>{const result=document.createElement(tag);if(text!==undefined)result.textContent=text;return result;};
 const option=(value,text)=>{const result=node('option',text);result.value=value;return result;};
 let identity='',contextIdentity='',epoch=0,detailEpoch=0,snapshot=null,items=[],baseline='[]',busy=false,pending=null,history=0,historicalItems=[],editing=null,linkedFacts=[],linkedMaterials=[],disposed=false,blocked=false,bindingConflict=false;
 const listeners=[];
 const listen=(element,name,handler)=>{element.addEventListener(name,handler);listeners.push([element,name,handler]);};
 const note=text=>{el('notice').textContent=text;};
 const available=()=>!disposed&&Boolean(controller.state.id&&controller.state.view)&&controller.state.status!=='revoked'&&!controller.state.loading;
 const dirty=()=>JSON.stringify(items)!==baseline;
 const selected=name=>Array.from(el(name).selectedOptions||[]).map(value=>value.value);
 const formDirty=()=>Boolean(editing||linkedFacts.length||linkedMaterials.length||Object.keys(fields).some(name=>el(name).value)||el('due-date').value||el('status').value!=='open'||selected('facts').length||selected('materials').length);
 const writable=()=>available()&&!readonly&&snapshot?.writable===true&&!busy&&!pending&&!history&&!bindingConflict&&!controller.state.materialAction;
 const hasPending=()=>!disposed&&Boolean(busy||pending||dirty()||formDirty());
 const active=(token,cid)=>token===epoch&&cid===controller.state.id&&available();
 function controls(){
  at('show-followups').disabled=!available();
  for(const name of [...Object.keys(fields),'due-date','status','facts','materials','link-selected','add','cancel-edit'])el(name).disabled=!writable();
  el('save').disabled=!writable()||!dirty()||formDirty();
  for(const name of ['refresh','discard'])el(name).disabled=!available()||busy||Boolean(pending);
  el('history').disabled=!available()||busy||Boolean(pending)||bindingConflict||dirty()||formDirty();
  el('history-version').disabled=el('history').disabled;
  el('lookup').hidden=!pending;el('lookup').disabled=!available()||busy;
  el('filter').disabled=!available()||busy;
 }
 function resetForm(){
  editing=null;linkedFacts=[];linkedMaterials=[];
  for(const name of [...Object.keys(fields),'due-date'])el(name).value='';
  el('status').value='open';
  for(const name of ['facts','materials'])for(const child of el(name).children)child.selected=false;
  el('linked').textContent='尚未关联依据。请先选择事实或现有原件，再点击“关联所选”。';
  el('link-selected').textContent='关联所选事实和材料';
  el('add').textContent='加入跟进清单（尚未保存）';controls();
 }
 function reset(){
  ++epoch;++detailEpoch;snapshot=null;items=[];baseline='[]';busy=false;pending=null;history=0;historicalItems=[];bindingConflict=false;
  el('facts').replaceChildren();el('materials').replaceChildren();resetForm();
  for(const name of ['rows','source-detail'])el(name).replaceChildren();
  el('version').textContent='';el('filter').value='todo';note('');panel.open=false;controls();
 }
 function check(value){
  if(!value||value.scope?.conversation_id!==controller.state.id||scopeKey(value.scope)!==scopeKey(controller.state.view?.scope)||
   !validRevision(value.revision)||value.revision>200||!validRevision(value.profile_revision)||!validRevision(value.evidence_revision)||
   !validItems(value.items)||typeof value.writable!=='boolean'||!Array.isArray(value.facts)||!Array.isArray(value.materials)||
   value.facts.some(fact=>!fact||typeof fact.id!=='string'||!fact.id||typeof fact.content!=='string')||value.facts.length>0&&value.evidence_revision<1||
   value.materials.some(material=>!material?.attachment||typeof material.attachment.id!=='string'||!material.attachment.id||typeof material.attachment.original_name!=='string'||!/^[0-9a-f]{64}$/.test(material.attachment.sha256)||!(material.parse_revision===null||material.parse_revision===undefined||validRevision(material.parse_revision)&&material.parse_revision>0))||
   !Array.isArray(value.attention)||value.attention.some(entry=>typeof entry.item_id!=='string'||!Array.isArray(entry.reasons)||entry.reasons.some(reason=>typeof reason!=='string')))throw {code:'INVALID_RESPONSE'};
  return value;
 }
 function failed(error){if(!controller.revoke(error))note(error.code==='VERSION_CONFLICT'?'版本已变化，本地编辑仍保留。请核对最新来源；跟进版本变化时，请先比较，再明确放弃本地改动。':'本次操作未完成，请核对来源和权限后重试。');}
 function directory(){
  const previousFacts=selected('facts'),previousMaterials=selected('materials');
  el('facts').replaceChildren(...snapshot.facts.map(fact=>option(fact.id,`事实版本${snapshot.evidence_revision} · ${fact.content||fact.id}`)));
  el('materials').replaceChildren(...snapshot.materials.filter(material=>material.selected!==false).map(material=>option(material.attachment.id,`${material.attachment.original_name} · ${material.parse_revision?'解析版本'+material.parse_revision:'原件'}`)));
  for(const child of el('facts').children)child.selected=previousFacts.includes(child.value);
  for(const child of el('materials').children)child.selected=previousMaterials.includes(child.value);
 }
 function linkedLabel(){el('linked').textContent=`已固定关联 ${linkedFacts.length} 条事实${linkedFacts.length?'（版本 '+[...new Set(linkedFacts.map(ref=>ref.evidence_revision))].join('、')+'）':''}、${linkedMaterials.length} 份原件。${editing?'保留原引用；只有明确点击关联按钮才会替换。':'加入清单后才进入本次编辑。'}`;}
 function button(text,action,{write=true}={}){const result=node('button',text);result.type='button';result.disabled=write?!writable():!available();result.addEventListener('click',action);return result;}
 function draw(){
  const host=el('rows');host.replaceChildren();
  const attention=new Map((snapshot?.attention||[]).map(entry=>[entry.item_id,entry.reasons]));
  const displayed=history?historicalItems:items;
  const filter=el('filter').value||'todo';
  const visible=displayed.filter(item=>filter==='all'||filter==='todo'&&(!['completed','cancelled'].includes(item.status)||item.status==='completed'&&!history&&attention.has(item.id))||filter===item.status);
  for(const item of visible){
   const entry=node('article');entry.className='followup-item';entry.append(node('h3',`${statuses[item.status]} · ${item.title}`));
   for(const [label,value]of [['待补原因',item.reason],['影响',item.impact],['下一步',item.next_action],['期限',item.due_date||'待定'],['处理结果',item.result]])if(value)entry.append(node('p',label+'：'+value));
   entry.append(node('p',`固定依据：${item.facts.length} 条事实、${item.materials.length} 份原件`));
   if(!history&&attention.has(item.id))entry.append(node('p','需人工重新核对：'+attention.get(item.id).join('；')));
   entry.append(button('回查关联事实与原件',()=>void openSources(item.id),{write:false}));
   if(!history)entry.append(button('编辑这条',()=>editItem(item.id)),button('移出当前版，保留历史',()=>removeItem(item.id)));
   host.append(entry);
  }
  if(!visible.length)host.append(node('p',displayed.length?'当前筛选没有事项。':'还没有登记跟进事项。可先关联已知事实，再写明尚未收到的材料和下一步。'));
  el('version').textContent=(history?'历史跟进版本 '+history+' · 只读':'当前跟进版本 '+(snapshot?.revision||0))+` · ${visible.length}/${displayed.length} 项`;
 }
 async function refresh({discard=false,minimumRevision=0}={}){
  if(!available()||busy||pending)return false;
  if(bindingConflict&&!discard&&(dirty()||formDirty())){note('本对话绑定已变化，本地编辑和原引用仍保留，暂不能写入。请比较后明确放弃本地改动并读取最新。');return false;}
  const cid=controller.state.id,token=++epoch;busy=true;controls();
  try{
   const value=await api.getFollowups(cid);if(!active(token,cid))return false;const next=check(value);
   if(next.revision<minimumRevision)throw {code:'INVALID_RESPONSE'};
   if(!discard&&snapshot&&(dirty()||formDirty())&&next.revision!==snapshot.revision){note('另一份跟进版本已保存，本地清单和表单仍保留。请先比较，再明确放弃本地改动以读取最新。');return false;}
   const keep=!discard&&(dirty()||formDirty());++detailEpoch;el('source-detail').replaceChildren();snapshot=next;history=0;historicalItems=[];bindingConflict=false;
   if(!keep){items=clone(next.items);baseline=JSON.stringify(items);resetForm();}
   directory();draw();note(keep?'已核对最新来源，编辑和固定引用仍保留。来源变化请人工重核。':'已读取保存版本；登记状态不表示自动核实法律事实。');return true;
  }catch(error){if(active(token,cid))failed(error);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function open(){if(!available())return false;panel.open=true;if(!snapshot||!hasPending())return refresh();controls();return true;}
 function linkSelected(){
  if(!writable())return false;
  const facts=selected('facts'),materials=selected('materials');
  if(facts.length>10||materials.length>10||!facts.length&&!materials.length){note('请至少选择一条事实或一份现有原件；每类最多关联10条。');return false;}
  const factRefs=facts.map(id=>snapshot.facts.find(fact=>fact.id===id)).filter(Boolean).map(fact=>({evidence_revision:snapshot.evidence_revision,fact_id:fact.id}));
  const materialRefs=materials.map(id=>snapshot.materials.find(material=>material.attachment.id===id&&material.selected!==false)).filter(Boolean).map(material=>({attachment_id:material.attachment.id,original_sha256:material.attachment.sha256,parse_revision:material.parse_revision||null}));
  if(factRefs.length!==facts.length||materialRefs.length!==materials.length){note('所选依据已变化，请重新核对后关联。');return false;}
  linkedFacts=factRefs;linkedMaterials=materialRefs;linkedLabel();controls();note('已固定关联所选依据。未收到的材料请写在标题中，收到后再关联现有原件。');return true;
 }
 function addItem(){
  if(!writable())return false;
  const item={id:editing||uuid(),title:el('title').value,reason:el('reason').value,impact:el('impact').value,next_action:el('next-action').value,due_date:el('due-date').value||null,status:el('status').value,result:el('result').value,facts:clone(linkedFacts),materials:clone(linkedMaterials)};
  if(!validItem(item)){note('请填写标题、待补原因和影响，明确关联事实或原件，并检查文字长度和日期；已处理或不再跟进必须填写处理结果。');return false;}
  if(!editing&&items.length>=100){note('当前版最多登记100项。');return false;}
  items=editing?items.map(current=>current.id===editing?item:current):[...items,item];resetForm();draw();controls();note('已加入当前编辑清单；点击保存跟进清单后才写入本机。');return true;
 }
 function editItem(id){
  if(!writable()||formDirty()){if(writable())note('请先加入或取消正在编辑的事项。');return false;}
  const item=items.find(current=>current.id===id);if(!item)return false;
  editing=id;linkedFacts=clone(item.facts);linkedMaterials=clone(item.materials);
  for(const name of Object.keys(fields))el(name).value=item[name==='next-action'?'next_action':name];
  el('due-date').value=item.due_date||'';el('status').value=item.status;linkedLabel();
  el('link-selected').textContent='关联当前所选事实和材料（替换原引用）';
  el('add').textContent='更新这条事项（尚未保存）';controls();return true;
 }
 function removeItem(id){if(!writable())return false;const found=items.some(item=>item.id===id);if(!found)return false;items=items.filter(item=>item.id!==id);if(editing===id)resetForm();draw();controls();note('已移出本地当前版，保存后生效；先前保存版本仍可回看。');return true;}
 function cancelEdit(){if(!writable())return false;resetForm();return true;}
 function setFilter(filter){if(!['todo','all',...Object.keys(statuses)].includes(filter))return false;el('filter').value=filter;draw();return true;}
 async function openSources(value){
  if(!available())return false;
  const item=(history?historicalItems:items).find(current=>current.id===(typeof value==='string'?value:value?.id));if(!item)return false;
  const cid=controller.state.id,token=epoch,detail=++detailEpoch,host=el('source-detail');host.replaceChildren(node('p','正在回查固定依据…'));
  const current=()=>active(token,cid)&&detail===detailEpoch;
  try{
   const contents=[node('h3',item.title+' · 固定依据'),node('p','这些记录供人工核对，不表示自动核实法律事实。')];
   for(const revision of new Set(item.facts.map(ref=>ref.evidence_revision))){
    const version=await api.getEvidenceVersion(cid,revision);if(!current())return false;
    if(version?.scope?.conversation_id!==cid||version.revision!==revision||!Array.isArray(version.rows))throw {code:'INVALID_RESPONSE'};
    for(const ref of item.facts.filter(ref=>ref.evidence_revision===revision)){
     const fact=version.rows.find(fact=>fact.id===ref.fact_id);if(!fact)throw {code:'INVALID_RESPONSE'};
     contents.push(node('h4',`事实版本 ${revision} · ${ref.fact_id}`),node('p',fact.content));
     const quote=fact.source?.quote||fact.source?.anchor?.quote;if(quote)contents.push(node('pre',quote));
    }
   }
   for(const ref of item.materials){
    const material=snapshot?.materials?.find(material=>material.attachment.id===ref.attachment_id&&material.attachment.sha256===ref.original_sha256);
    contents.push(node('p',`${material?.attachment.original_name||ref.attachment_id} · 原件摘要 ${ref.original_sha256} · ${ref.parse_revision?'固定解析版本 '+ref.parse_revision:'仅关联原件'}`));
    const link=node('a','下载对应原件，人工核对');link.href=api.originalUrl(cid,ref.attachment_id);link.download='';contents.push(link);
   }
   if(!current())return false;host.replaceChildren(...contents);return true;
  }catch(error){if(current()){host.replaceChildren();failed(error);}return false;}
 }
 function validReceipt(receipt){return receipt&&pending&&receipt.conversation_id===controller.state.id&&receipt.request_id===pending.request_id&&receipt.revision===pending.base_revision+1&&/^[0-9a-f]{64}$/.test(receipt.snapshot_sha256)&&typeof receipt.created_at==='string'&&Number.isFinite(Date.parse(receipt.created_at));}
 function acknowledge(receipt){pending=null;baseline=JSON.stringify(items);snapshot={...snapshot,revision:receipt.revision,items:clone(items)};}
 async function save(){
  if(!writable()||!dirty()||formDirty())return false;
  if(snapshot.revision>=200){note('已达到200次保存上限。请保留现有历史。');return false;}
  const cid=controller.state.id,token=++epoch;
  pending={request_id:uuid(),expected_scope:clone(snapshot.scope),expected_profile_revision:snapshot.profile_revision,expected_evidence_revision:snapshot.evidence_revision,base_revision:snapshot.revision,items:clone(items)};busy=true;controls();
  try{
   const receipt=await api.saveFollowups(cid,pending);if(!active(token,cid))return false;
   if(!validReceipt(receipt))throw {code:'INVALID_RESPONSE'};
   acknowledge(receipt);busy=false;return await refresh({minimumRevision:receipt.revision});
  }catch(error){
   if(!active(token,cid))return false;
   const rejected=error.status>=400&&error.status<500&&!['NETWORK_UNKNOWN','INVALID_RESPONSE'].includes(error.code);
   if(rejected){pending=null;failed(error);}else note('保存结果尚不确定，请查询本次回执；不会重复提交。');return false;
  }finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function lookup(){
  if(!pending||busy||!available())return false;
  const cid=controller.state.id,token=++epoch;busy=true;controls();
  try{
   const receipt=await api.findFollowupReceipt(cid,pending.request_id);if(!active(token,cid))return false;
   if(!receipt){note('暂未查到本次回执，原请求号和编辑仍保留，请继续查询。');return false;}
   if(!validReceipt(receipt))throw {code:'INVALID_RESPONSE'};
   acknowledge(receipt);busy=false;return await refresh({minimumRevision:receipt.revision});
  }catch(error){if(active(token,cid))failed(error);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function loadVersion(version){
  if(!available()||bindingConflict||hasPending())return false;
  version=version===undefined?Number(el('history-version').value):Number(version);
  if(!Number.isSafeInteger(version)||version<1||version>200)return false;
  const cid=controller.state.id,token=++epoch;busy=true;controls();
  try{
   const value=await api.getFollowupVersion(cid,version);if(!active(token,cid))return false;
   if(value?.scope?.conversation_id!==cid||value.revision!==version||!validItems(value.items))throw {code:'INVALID_RESPONSE'};
   ++detailEpoch;el('source-detail').replaceChildren();history=version;historicalItems=clone(value.items);draw();note('正在查看历史跟进版本，只读；点击核对最新来源返回当前版。');return true;
  }catch(error){if(active(token,cid))failed(error);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 for(const name of [...Object.keys(fields),'due-date'])listen(el(name),'input',controls);
 for(const name of ['facts','materials','status'])listen(el(name),'change',controls);
 listen(at('show-followups'),'click',()=>void open());
 listen(panel,'toggle',()=>{if(panel.open&&!snapshot&&!busy)void refresh();});
 for(const [name,action]of Object.entries({'link-selected':linkSelected,add:addItem,save,lookup,'cancel-edit':cancelEdit,refresh:()=>void refresh(),discard:()=>void refresh({discard:true}),history:()=>void loadVersion()}))listen(el(name),'click',action);
 listen(el('filter'),'change',draw);
 return {open,refresh,save,lookup,loadVersion,hasPending,addItem,editItem,removeItem,linkSelected,openSources,setFilter,cancelEdit,
  state(state){const next=fixed(state),nextContext=JSON.stringify([state.id,state.view?.scope?.workspace_id]);
   if(next!==identity||state.status==='revoked'){
    const preserve=state.status!=='revoked'&&nextContext===contextIdentity&&(dirty()||formDirty()||pending);
    identity=next;contextIdentity=nextContext;
    if(preserve){++epoch;++detailEpoch;busy=false;bindingConflict=true;el('source-detail').replaceChildren();note(pending?'本对话绑定已变化，编辑和原请求号仍保留，暂不能写入。请仅查询原请求回执。':'本对话绑定已变化，本地编辑和原引用仍保留，暂不能写入。请比较后明确放弃本地改动并读取最新。');}
    else reset();
   }
   const nextBlocked=Boolean(state.loading||state.materialAction);if(nextBlocked&&!blocked){++epoch;++detailEpoch;busy=false;el('source-detail').replaceChildren();}blocked=nextBlocked;controls();if(snapshot)draw();},
  dispose(){disposed=true;for(const [element,name,handler]of listeners)element.removeEventListener(name,handler);reset();}};
}
