// Local evidence edits never grant model, network, or delivery permissions.
const categories={agreement:'借款约定/陈述',disbursement:'实际交付',repayment:'还款',other:'其他/相反说法'};
const states={pending:'待核',reviewed:'律师登记已核对',disputed:'存在争议'};
const fixed=s=>JSON.stringify([s.id,s.view?.scope?.workspace_id,s.view?.scope?.scope_kind,s.view?.scope?.scope_ref,s.view?.scope?.binding_revision]);
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
export function bindEvidenceWorksheet({controller,api,document=globalThis.document,readonly=false,uuid=()=>crypto.randomUUID()}){
 const at=id=>document.getElementById(id),panel=at('evidence-panel');
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 let identity='',epoch=0,sourceEpoch=0,detailEpoch=0,snapshot=null,rows=[],baseline='[]',busy=false,pending=null,history=false,editing=null,selectedSource=null,anchors=[],disposed=false;
 const note=text=>{at('evidence-notice').textContent=text;};
 const available=()=>!disposed&&controller.state.id&&controller.state.view&&controller.state.status!=='revoked';
 const formDirty=()=>Boolean(editing||['content','date','note','manual-location','manual-quote'].some(n=>at('evidence-'+n).value));
 const dirty=()=>JSON.stringify(rows)!==baseline;
 const writable=()=>available()&&!readonly&&snapshot?.writable&&!busy&&!pending&&!history&&!controller.state.materialAction&&!controller.state.loading;
 const hasPending=()=>Boolean(busy||pending||dirty()||formDirty());
 const active=(token,cid)=>token===epoch&&cid===controller.state.id&&available();
 function controls(){
  at('show-evidence').disabled=!available();
  for(const id of ['source','anchor','category','content','date','review','note','manual-location','manual-quote','add','choose-source','cancel-edit'])at('evidence-'+id).disabled=!writable();
  at('evidence-save').disabled=!writable()||!dirty()||formDirty();
  at('evidence-refresh').disabled=!available()||busy||Boolean(pending);
  at('evidence-discard').disabled=!available()||busy||Boolean(pending);
  at('evidence-history').disabled=!available()||busy||Boolean(pending)||dirty()||formDirty();
  at('evidence-history-version').disabled=at('evidence-history').disabled;
  at('evidence-lookup').hidden=!pending;at('evidence-lookup').disabled=busy;
 }
 function resetForm(){editing=null;selectedSource=null;anchors=[];++sourceEpoch;
  for(const n of ['content','date','note','manual-location','manual-quote'])at('evidence-'+n).value='';
  at('evidence-category').value='agreement';at('evidence-review').value='pending';at('evidence-source').value='';
  at('evidence-anchor').replaceChildren();at('evidence-source-text').textContent='';at('evidence-add').textContent='加入事实清单（尚未保存）';controls();
 }
 function reset(){++epoch;++sourceEpoch;++detailEpoch;snapshot=null;rows=[];baseline='[]';busy=false;pending=null;history=false;
  resetForm();at('evidence-rows').replaceChildren();at('evidence-materials').replaceChildren();at('evidence-source-detail').replaceChildren();at('evidence-version').textContent='';note('');panel.open=false;controls();
 }
 function check(v){if(!v||v.scope?.conversation_id!==controller.state.id||!Number.isSafeInteger(v.revision)||v.revision<0||
  !Number.isSafeInteger(v.profile_revision)||v.profile_revision<0||!Array.isArray(v.rows)||v.rows.length>100||
  new Set(v.rows.map(r=>r.id)).size!==v.rows.length||typeof v.writable!=='boolean'||!Array.isArray(v.materials))throw {code:'INVALID_RESPONSE'};return v;}
 function failed(error){if(!controller.revoke(error))note(error.code==='VERSION_CONFLICT'?'版本已变化，编辑仍保留。请核对最新来源；事实版本冲突时先放弃本地改动再读取最新。':'本次操作未完成，请核对来源和权限后重试。');}
 function option(value,text){const e=node('option',text);e.value=value;return e;}
 function directory(){
  const host=at('evidence-materials'),select=at('evidence-source');host.replaceChildren();select.replaceChildren(option('','选择依据'));
  if(snapshot.statement)select.append(option('statement','已保存接待原话'));
  select.append(option('retained','编辑时保留该条原有依据'));
  for(const item of snapshot.materials){const a=item.attachment,entry=node('div');
   const label=!item.selected?'未选入当前材料':item.reading_status==='readable'?'已读取 · 内容待核':item.reading_status==='partial'?'部分可读 · 请检查缺口':item.reading_status?'读取有缺口':'未读取';
   entry.append(node('strong',a.original_name),node('p',label));const link=node('a','下载原件核对');link.href=api.originalUrl(controller.state.id,a.id);link.download='';entry.append(link);host.append(entry);
   if(item.selected){if(item.parse_revision&&['readable','partial'].includes(item.reading_status))select.append(option('doc:'+a.id,a.original_name+' · 解析原文'));
    select.append(option('manual:'+a.id,a.original_name+' · 人工摘录'));}
  }
  if(!snapshot.materials.length)host.append(node('p','尚无材料。可先在下方“添加材料”保存原件，再读取DOCX或文字PDF；图片可人工摘录。'));
 }
 function button(text,action){const e=node('button',text);e.type='button';e.disabled=!writable();e.addEventListener('click',action);return e;}
 function draw(){
  const host=at('evidence-rows');host.replaceChildren();
  const ordered=[...rows].sort((a,b)=>(a.event_date||'9999').localeCompare(b.event_date||'9999'));
  for(const row of ordered){const e=node('article');e.className='evidence-fact';
   e.append(node('h3',`${categories[row.category]} · ${row.event_date||'日期待核'} · ${states[row.review_state]}`),node('p',row.content));
   const kind=row.source.kind==='statement'?'客户陈述':row.source.kind==='document'?'材料解析记载':'人工摘录（未自动识别）';
   e.append(node('p',kind+(snapshot?.historical_ids?.includes(row.id)?' · 来源已移出或变更，请重新核对':'')));
   if(row.note)e.append(node('p','核对备注/相反说法：'+row.note));
   const source=node('button','回查这条依据');source.type='button';source.addEventListener('click',()=>void openSource(row));e.append(source);
   if(!history){e.append(button('编辑这条',()=>edit(row)),button('移出当前版，保留历史',()=>{if(!writable())return;rows=rows.filter(x=>x.id!==row.id);if(editing===row.id)resetForm();draw();controls();}));}
   host.append(e);
  }
  if(!rows.length)host.append(node('p','还没有登记事实。可先选择依据，再录入一条待核事实。'));
  at('evidence-version').textContent=(history?'历史版本 ':'当前事实版本 ')+(history||snapshot?.revision||0)+' · 按日期查看；无日期排在后面。';
 }
 async function refresh({discard=false}={}){
  if(!available()||busy||pending)return false;
  const cid=controller.state.id,token=++epoch;busy=true;controls();
  try{const v=check(await api.getEvidence(cid));if(!active(token,cid))return false;
   if(!discard&&snapshot&&(dirty()||formDirty())&&v.revision!==snapshot.revision){note('另一份事实版本已保存，本地编辑仍保留。请先比较，放弃本地改动后读取最新版本。');return false;}
   const keep=!discard&&(dirty()||formDirty());++detailEpoch;at('evidence-source-detail').replaceChildren();snapshot=v;history=false;
   if(!keep){rows=structuredClone(v.rows);baseline=JSON.stringify(rows);resetForm();}
   directory();draw();note(keep?'已核对最新来源，编辑内容保留；旧来源会保留历史标记。':'已读取保存版本。');return true;
  }catch(e){if(active(token,cid))failed(e);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function open(){if(!available())return false;panel.open=true;if(!snapshot)return refresh();controls();return true;}
 async function chooseSource(){
  if(!writable())return false;const choice=at('evidence-source').value,cid=controller.state.id,token=++sourceEpoch;
  if(choice==='retained'&&editing&&selectedSource)return true;
  selectedSource=null;anchors=[];at('evidence-source-text').textContent='';at('evidence-anchor').replaceChildren();
  if(choice==='statement'&&snapshot.statement){selectedSource={kind:'statement',profile_revision:snapshot.profile_revision,start:0,end:[...snapshot.statement].length,quote:snapshot.statement};at('evidence-source-text').textContent=snapshot.statement;return true;}
  const [kind,id]=choice.split(':'),item=snapshot.materials.find(x=>x.attachment.id===id&&x.selected);if(!item)return false;
  if(kind==='manual'){selectedSource={kind:'manual_excerpt',attachment_id:id,original_sha256:item.attachment.sha256};note('请填写人工摘录位置和原话；这不表示系统已识别或验证原件内容。');return true;}
  if(kind!=='doc'||!item.parse_revision)return false;
  busy=true;controls();try{const p=await api.getParse(cid,id,item.parse_revision);
   if(token!==sourceEpoch||!available()||cid!==controller.state.id||choice!==at('evidence-source').value)return false;
   if(p.attachment_id!==id||p.conversation_id!==cid||p.revision!==item.parse_revision||!p.result||!p.result_sha256)throw {code:'INVALID_RESPONSE'};
   anchors=p.result.anchors;selectedSource={kind:'document',conversation_id:cid,attachment_id:id,original_sha256:item.attachment.sha256,parse_revision:p.revision,result_sha256:p.result_sha256,anchor:anchors[0]};
   at('evidence-anchor').replaceChildren(...anchors.map((a,i)=>option(String(i),`${a.page?'第'+a.page+'页 · ':''}${a.element_id} · ${a.quote.slice(0,55)}`)));at('evidence-anchor').value='0';
   at('evidence-source-text').textContent=anchors[0]?.quote||'没有可用原文位置';return Boolean(anchors.length);
  }catch(e){if(token===sourceEpoch&&cid===controller.state.id)failed(e);return false;}finally{if(token===sourceEpoch){busy=false;controls();draw();}}
 }
 function addFact(){if(!writable())return false;
  let source=selectedSource?structuredClone(selectedSource):null;
  if(source?.kind==='manual_excerpt'){source.location=at('evidence-manual-location').value;source.quote=at('evidence-manual-quote').value;}
  if(!source||source.kind==='document'&&!source.anchor||source.kind==='manual_excerpt'&&(!source.location.trim()||!source.quote.trim())||!at('evidence-content').value.trim()){note('请先选定依据，并填写事实；人工摘录需要位置和原话。');return false;}
  const row={id:editing||uuid(),category:at('evidence-category').value||'agreement',content:at('evidence-content').value,event_date:at('evidence-date').value||null,review_state:at('evidence-review').value||'pending',note:at('evidence-note').value,source};
  if(!editing&&rows.length>=100){note('本片最多登记100条事实。');return false;}
  rows=editing?rows.map(r=>r.id===editing?row:r):[...rows,row];resetForm();draw();controls();note('已加入当前编辑清单，点击保存事实底稿后才会写入本机。');return true;
 }
 function edit(row){if(!writable()||formDirty()){note('请先加入或取消正在编辑的事实。');return;}
  editing=row.id;selectedSource=structuredClone(row.source);at('evidence-source').value='retained';
  for(const [id,value]of Object.entries({content:row.content,date:row.event_date||'',review:row.review_state,category:row.category,note:row.note,'manual-location':row.source.location||'','manual-quote':row.source.kind==='manual_excerpt'?row.source.quote:''}))at('evidence-'+id).value=value;
  at('evidence-source-text').textContent=row.source.quote||row.source.anchor?.quote||'';at('evidence-add').textContent='更新这条事实（尚未保存）';controls();
 }
 async function openSource(row){if(!available())return false;const cid=controller.state.id,token=epoch,detail=++detailEpoch,host=at('evidence-source-detail'),ref=row.source;host.replaceChildren(node('p','正在核对依据…'));
  try{if(ref.kind==='document'){const p=await api.getParse(cid,ref.attachment_id,ref.parse_revision);if((!active(token,cid)||detail!==detailEpoch))return false;
    if(p.result_sha256!==ref.result_sha256||!p.result?.anchors.some(a=>equal(a,ref.anchor)))throw {code:'INVALID_RESPONSE'};}
   if((!active(token,cid)||detail!==detailEpoch))return false;host.replaceChildren(node('h3',ref.kind==='statement'?'已保存客户陈述 · 档案版本'+ref.profile_revision:ref.kind==='manual_excerpt'?'人工摘录 · '+ref.location:'解析原文 · '+(ref.anchor.page?'第'+ref.anchor.page+'页 · ':'')+ref.anchor.element_id),node('pre',ref.quote||ref.anchor.quote));
   if(ref.kind!=='statement'){const link=node('a','下载对应原件核对');link.href=api.originalUrl(cid,ref.attachment_id);link.download='';host.append(link);}return true;
  }catch(e){if(active(token,cid)&&detail===detailEpoch){host.replaceChildren();failed(e);}return false;}
 }
 function validReceipt(r){return r&&r.conversation_id===controller.state.id&&r.request_id===pending?.request_id&&r.revision===pending.base_revision+1&&/^[0-9a-f]{64}$/.test(r.snapshot_sha256);}
 async function save(){if(!writable()||!dirty()||formDirty())return false;const cid=controller.state.id,token=++epoch;
  pending={request_id:uuid(),expected_scope:snapshot.scope,expected_profile_revision:snapshot.profile_revision,base_revision:snapshot.revision,rows:structuredClone(rows)};busy=true;controls();
  try{const r=await api.saveEvidence(cid,pending);if(!active(token,cid))return false;if(!validReceipt(r))throw {code:'INVALID_RESPONSE'};
   pending=null;baseline=JSON.stringify(rows);busy=false;return await refresh();
  }catch(e){if(!active(token,cid))return false;const rejected=e.status>=400&&e.status<500&&!['NETWORK_UNKNOWN','INVALID_RESPONSE'].includes(e.code);if(rejected)pending=null;
   if(rejected)failed(e);else note('保存结果尚不确定，请查询本次回执；不会重复提交。');return false;
  }finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function lookup(){if(!pending||busy||!available())return false;const cid=controller.state.id,token=++epoch;busy=true;controls();
  try{const r=await api.findEvidenceReceipt(cid,pending.request_id);if(!active(token,cid))return false;if(!r){note('暂未查到本次回执，编辑与请求号仍保留，请继续查询。');return false;}
   if(!validReceipt(r))throw {code:'INVALID_RESPONSE'};pending=null;baseline=JSON.stringify(rows);busy=false;return refresh();
  }catch(e){if(active(token,cid))failed(e);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 async function loadVersion(){if(!available()||hasPending())return false;const version=Number(at('evidence-history-version').value);if(!Number.isSafeInteger(version)||version<1)return false;
  const cid=controller.state.id,token=++epoch;busy=true;controls();try{const v=await api.getEvidenceVersion(cid,version);if(!active(token,cid))return false;
   if(v.scope?.conversation_id!==cid||v.revision!==version||!Array.isArray(v.rows))throw {code:'INVALID_RESPONSE'};++detailEpoch;at('evidence-source-detail').replaceChildren();history=version;rows=structuredClone(v.rows);baseline=JSON.stringify(rows);resetForm();draw();note('正在查看历史版本，只读；点击核对最新来源返回当前版。');return true;
  }catch(e){if(active(token,cid))failed(e);return false;}finally{if(token===epoch){busy=false;controls();draw();}}
 }
 for(const n of ['content','date','note','manual-location','manual-quote'])at('evidence-'+n).addEventListener('input',controls);
 at('show-evidence').addEventListener('click',open);panel.addEventListener('toggle',()=>{if(panel.open&&!snapshot&&!busy)void refresh();});
 at('evidence-choose-source').addEventListener('click',chooseSource);at('evidence-add').addEventListener('click',addFact);at('evidence-save').addEventListener('click',save);
 at('evidence-lookup').addEventListener('click',lookup);at('evidence-refresh').addEventListener('click',()=>void refresh());at('evidence-history').addEventListener('click',loadVersion);
 at('evidence-cancel-edit').addEventListener('click',resetForm);at('evidence-discard').addEventListener('click',()=>void refresh({discard:true}));
 at('evidence-anchor').addEventListener('change',()=>{if(!writable()||selectedSource?.kind!=='document')return;const anchor=anchors[Number(at('evidence-anchor').value)];if(anchor){selectedSource={...selectedSource,anchor};at('evidence-source-text').textContent=anchor.quote;}});
 return {open,refresh,save,lookup,chooseSource,addFact,loadVersion,hasPending,state(s){const next=fixed(s);if(next!==identity||s.status==='revoked'){identity=next;reset();}controls();},dispose(){disposed=true;reset();}};
}
