'use strict';
// Untrusted text only reaches textContent/value. Templates and URLs are local.
const section = document.body.dataset.section;
const matter = document.body.dataset.matter;
const localMaterial = document.body.dataset.localMaterial === 'true';
const assisted = document.body.dataset.purpose === 'assisted_draft';
const base = '/api/matters/' + encodeURIComponent(matter);
const messages = {AUTHORIZATION_REQUIRED:'请重新登录或联系本案负责人授权。',CROSS_MATTER_DENIED:'当前身份没有此操作权限，或请求缺少有效验证。',FACTS_UNCONFIRMED:'请先核对并确认全部事实。',VERSION_CONFLICT:'材料版本已变化，请刷新核对后重做。',APPROVAL_STALE:'材料或批准已经变化，请刷新并重新核对。',BLOCKED_LIVE:'BLOCKED_LIVE：mock不能正式签发，真实外查和模型未获批准。',UNRESOLVED_HARD_GATE:'高风险草案需要另一名当前复核成员批准。',DATA_POLICY_UNAPPROVED:'材料用途或确认不符合要求。请核对案件类型、文件格式和本次处理确认；本机材料不能进入插件、外查或测试备份。',PARTY_AMBIGUOUS:'请先明确选择主体候选，候选不是实时企业核验。',TOOL_UNBOUND:'工具尚未绑定或批准；保持模拟接口。',STATE_CONFLICT:'当前阶段不允许此操作，请核对任务与事实状态。',QUERY_STATE_UNKNOWN:'查询状态未知，额度和次数保留，不能自动重试。',FILE_LIMIT:'文件或请求超过本机限制。',FILE_UNSUPPORTED:'当前文件结构或格式不支持，需要人工处理。'};
messages.RULE_UNAPPROVED='法律复审尚缺可消费的法源真实性、命题支持或案件适用记录；请保留待核或先完成依据核验。';
messages.SOURCE_VISUAL_CONFIRMATION_REQUIRED='原文存在可见性疑点，请先核对原页；当前尚不能确认或计算该字段。';
messages.OCR_BUSY='已有识别任务正在运行，请稍后重试。';
messages.OCR_CLEANUP_REQUIRED='识别临时文件或隔离环境尚未完成清理，已暂停新识别。请联系本机维护人员核查后再试。';
messages.OCR_STORAGE_LIMIT='识别任务超过本机临时文件限制，或磁盘可用空间不足。请联系本机维护人员处理。';
const coverageNames=new Map([...(document.getElementById('coverage-taxonomy')?.content.querySelectorAll('option')||[])].map(option=>[option.value,option.textContent]));
const coverageStates={reviewed_issue:'发现待处置问题',reviewed_no_issue:'已审阅未发现问题',insufficient_material:'材料不足',unsupported:'当前不支持',not_applicable:'不适用'};
const stateNames={intake:'接待中',parsed:'已解析',awaiting_fact_confirmation:'待确认事实',ready_for_review:'可以开始审查',reviewing:'审查中',awaiting_lawyer:'待律师处置',approved:'已批准',superseded:'已有更新版本',archived:'已归档',failed:'执行失败',queued:'已排队',running:'正在执行',completed:'已完成',blocked:'执行受阻',cancelled:'已取消'};
const typeNames={sales:'买卖',service:'服务',lease:'租赁',nda:'保密',unknown:'需专项审阅'};
const fieldNames={total_price:'合同总价',attachment_price:'附件金额',addendum_price:'附件金额',payment_ratio_1:'第一项付款比例',payment_ratio_2:'第二项付款比例',payment_ratio:'付款比例',contract_period:'期间或期限',other_literal:'其他原文约定'};
const issueNames={untrusted_instruction:'原文包含越权操作指令',missing_appendix:'附件材料缺失',obligation_direction:'通知义务与履行安排',guarantee_material:'保证安排证据待核实',payment_ratio_sum:'付款比例合计不一致',payment_math_insufficient:'付款数学证据不足',amount_conflict:'正文与附件金额冲突',confidentiality_training:'保密义务与训练授权关系',license_termination:'成果许可与终止交接关系'};
const confirmationNames={unconfirmed:'未确认',confirmed:'已确认',corrected:'已更正',rejected:'已拒绝'};
const baselineNames={original:'原始文本',accepted_view:'接受已有修订后的文本',rejected_view:'拒绝已有修订后的文本',confirmed_custom:'已明确自定义基线'};
const severityNames={high:'高风险',medium:'中等风险',low:'低风险',info:'提示'};
const audienceNames={internal:'内部',client:'客户',counterparty:'对方'};
const partyStateNames={unresolved:'待人工明确',ambiguous:'有多项候选，待明确',confirmed:'已明确选择原文候选'};
const decisionNames={accept:'接受意见',edit:'拟订修改',reject:'拒绝意见',request_info:'补充材料',refer:'转专项复核'};
let run=null, documents=[], allAnchors=[], selectedPatches=[], latestBundle=null;
let reparseSnapshot=null;
let candidateOpinions=[],candidateContext=null;
let effectiveText=null,effectiveReview=null;
const effectiveDimensions={legal:'法律依据与修订后的权利义务',amounts:'总价、分期、比例与单位',deadlines:'起算、期限与日期冲突',attachments:'正文与附件旧值',definitions_references:'定义及条款交叉引用'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;}
function clear(id){const n=document.getElementById(id);if(n)n.replaceChildren();return n;}
function tell(text){document.getElementById('message').textContent=text;}
function csrf(){const value=document.cookie.split('; ').find(v=>v.startsWith('qx_csrf='));return value?decodeURIComponent(value.slice(8)):'';}
function key(){return crypto.randomUUID();}
async function api(path,{method='GET',body=null,idempotency=null}={}){const headers={};if(method!=='GET'){headers['X-CSRF-Token']=csrf();if(idempotency)headers['Idempotency-Key']=idempotency;}
  if(body!==null&&!(body instanceof FormData)){headers['Content-Type']='application/json';body=JSON.stringify(body);}
  const response=await fetch(path,{method,headers,body,credentials:'same-origin',cache:'no-store'});
  if(response.status===204)return null;const data=await response.json();if(!response.ok){const error=new Error(messages[data.code]||'请求受阻，需要人工核对。');error.code=data.code;throw error;}return data;}
function guard(fn){return async event=>{event.preventDefault();tell('');const button=event.submitter||event.currentTarget;if(button.tagName==='BUTTON')button.disabled=true;try{await fn(event);}catch(error){tell(error.message);}finally{if(button.tagName==='BUTTON')button.disabled=false;}};}
function on(id,event,fn){const n=document.getElementById(id);if(n)n['on'+event]=guard(fn);}
function link(text,path){const n=el('a',text);n.href=path;return n;}
function detail(parent,label,value){const d=el('details');d.append(el('summary',label),el('pre',typeof value==='string'?value:JSON.stringify(value,null,2)));parent.append(d);}
async function poll(jobId,displayId='job-status'){const display=document.getElementById(displayId);for(let i=0;i<120;i++){const status=await api('/api/jobs/'+encodeURIComponent(jobId));if(display)display.textContent=status.stage+'（'+(stateNames[status.state]||'需核对')+'）';if(status.state==='completed')return status;if(['failed','blocked','cancelled'].includes(status.state))throw new Error(messages[status.error_code]||'任务受阻，需人工核对。');await new Promise(resolve=>setTimeout(resolve,500));}throw new Error('任务仍在运行；刷新查看，不自动重发请求。');}
async function loadMatter(){const data=await api(base);documents=data.documents;reparseSnapshot={document_hashes:Object.fromEntries(documents.map(v=>[v.id,v.sha256])),fact_version:data.matter.active_fact_version||0};const reparsePanel=document.getElementById('reparse-panel');if(reparsePanel)reparsePanel.hidden=!documents.length||data.matter.status==='archived';const summary=document.getElementById('matter-summary');if(summary)summary.textContent='当前阶段：'+(stateNames[data.matter.status]||'需核对')+' · '+(data.matter.review_mode==='post_sign'?'签署后，仅履约或补充建议':'签署前')+' · 事实版本：'+(data.matter.active_fact_version||'待抽取');return data;}
async function loadCases(){const host=clear('cases');for(const m of await api('/api/matters')){const c=el('div',undefined,'card');c.append(link(m.title,'/matters/'+encodeURIComponent(m.id)),el('p','类型：'+typeNames[m.contract_type]+' · 阶段：'+stateNames[m.status],'muted'));host.append(c);}if(!host.children.length)host.append(el('p','暂无有权限的案件。'));}
async function loadDocuments(){await loadMatter();const host=clear('documents');for(const v of documents){const c=el('div',undefined,'card');c.append(el('strong',v.original_name),el('p','基线：'+baselineNames[v.baseline_view]+' · 上传 '+v.byte_size+' 字节（解析状态另见原文页面）'));detail(c,'版本和内容校验详情',{id:v.id,sha256:v.sha256});host.append(c);}}
function readingSummary(host,parsed){
  const gaps=parsed.unsupported_parts||[];
  host.append(el('p',parsed.anchors.length?'已提取 '+parsed.anchors.length+' 处文字；提取结果仍须与原件核对。':'尚未提取到可定位文字。请先打开原件核对，不能视为已读完。',gaps.length?'notice':'muted'));
  if(gaps.length){
    const groups=new Map();
    for(const value of gaps){
      const label=value.includes(':style_dependency:')?'样式依赖待处理':value.includes(':visibility:')||value.includes(':hidden:')?'文字可见性待核对':value.includes(':numbering:')?'自动编号待核对':'其他部件或内容待核对';
      groups.set(label,(groups.get(label)||0)+1);
    }
    const list=el('ul');for(const [label,count] of groups)list.append(el('li',label+'：'+count+' 项'));
    host.append(list,el('p','这些是文件读取限制，与是否运行大模型无关。请核对原件及下列缺口后再确认事实。','muted'));
    detail(host,'查看全部读取缺口（'+gaps.length+' 项）',gaps.join('\n'));
  }
}
async function anchors(){
  await loadMatter();allAnchors=[];const host=clear('anchors');
  for(const v of documents){
    if(host){
      host.append(el('h3',v.original_name),link('下载这一版本的原件核对',base+'/documents/'+encodeURIComponent(v.id)+'/original?sha256='+encodeURIComponent(v.sha256)));
    }
    let parsed;
    try{parsed=await api(base+'/documents/'+encodeURIComponent(v.id)+'/anchors');}
    catch(error){
      if(!host||error.code!=='VERSION_CONFLICT')throw error;
      host.append(el('p','已保存的读取结果与当前解析结果或材料版本不一致。请刷新核对；若仍提示，请使用“重新读取当前文件”。历史记录会保留，事实需要重新确认。','notice'));
      continue;
    }
    allAnchors.push(...parsed.anchors.map(a=>({...a,sourceEligible:!assisted||parsed.eligible_anchor_ids.includes(a.id)})));
    if(!host)continue;
    readingSummary(host,parsed);
    if(v.mime==='application/pdf'){
      const preview=el('button','查看受保护PDF原页');preview.type='button';preview.onclick=()=>window.dispatchEvent(new CustomEvent('qx-pdf-view',{detail:{version:v,page:1}}));host.append(preview);
    }
    for(const a of parsed.anchors){
      const c=el('div',a.quote,'card anchor');c.id='anchor-'+a.id;
      if(v.mime==='application/pdf'&&a.page){const locate=el('button','回到原页位置');locate.type='button';locate.onclick=()=>window.dispatchEvent(new CustomEvent('qx-pdf-view',{detail:{version:v,page:a.page,bbox:a.bbox}}));c.append(locate);}
      if(assisted&&v.mime!=='application/pdf')docxSourceButton(c,v,a,parsed.eligible_anchor_ids.includes(a.id));
      detail(c,'精确位置详情',{id:a.id,part_name:a.part_name,element_id:a.element_id,start:a.start,end:a.end,page:a.page});host.append(c);
    }
    detail(host,'解析范围与质量记录',parsed);
  }
  return allAnchors;
}

function populateCandidateAnchors(id){const choice=clear(id);if(!choice)return;for(const a of allAnchors){const option=el('option',(a.sourceEligible?'':'需原页核对，当前不可消费 · ')+a.quote+'（位置 '+a.element_id+'）');option.value=a.id;option.disabled=!a.sourceEligible;choice.append(option);}}
function docxSourceButton(card,version,anchor,eligible){
  if(!eligible)card.append(el('p','此段存在可见性疑点，提取文字不能直接作为事实依据。请下载原件，用本机Word/WPS核对，另录独立来源；本工作台不宣称已验证其排版。','notice'));
  const button=el('button','独立核对此段来源');button.type='button';card.append(button);
  button.onclick=guard(async()=>{
    if(card.querySelector('form'))return;
    const [facts,records]=await Promise.all([api(base+'/facts'),api(base+'/page-verifications')]);
    const form=el('form');card.append(form);
    const download=link('下载当前原件（本机核对）',base+'/documents/'+encodeURIComponent(version.id)+'/original?sha256='+encodeURIComponent(version.sha256));
    form.append(download,el('p','请根据原件填写，不能用上方提取文字代替原件核对。保存后还需确认事实。'));
    const add=(label,name,tag='input')=>{const wrap=el('label',label),input=el(tag);input.name=name;input.required=true;wrap.append(input);form.append(wrap);return input;};
    const observed=add('原件实际可见文字','observed_text','textarea');observed.maxLength=4000;
    const field=add('事实字段','field');field.value='total_price';field.maxLength=100;
    const kind=add('数值类型','kind','select');for(const [value,label] of [['decimal','精确数值'],['text','文字']]){const option=el('option',label);option.value=value;kind.append(option);}
    const value=add('核对后的值','value');value.maxLength=2000;
    const unit=add('单位（数值必填，如CNY）','unit');unit.maxLength=32;
    kind.onchange=()=>{unit.required=kind.value==='decimal';};
    const reason=add('核对方式与理由','reason','textarea');reason.maxLength=2000;
    const checked=add('我已在本机打开并核对这一版本的原件及此段位置','checked');checked.type='checkbox';
    const save=el('button','保存独立来源候选');save.type='submit';form.append(save);
    form.onsubmit=guard(async()=>{
      const previous=records.find(r=>r.input.document_version_id===version.id&&r.input.source_anchor_id===anchor.id&&r.input.field===field.value&&!records.some(n=>n.input.previous_id===r.id));
      await api(base+'/page-verifications',{method:'POST',idempotency:key(),body:{document_version_id:version.id,document_sha256:version.sha256,
        fact_version:facts.version,page:null,source_anchor_id:anchor.id,source_kind:'lawyer_transcription',observed_text:observed.value,
        field:field.value,typed_value:{kind:kind.value,value:value.value},unit:unit.value||null,reason:reason.value,original_page_checked:checked.checked,
        previous_id:previous?.id||null,candidate_id:null,candidate_sha256:null}});
      await loadFacts();tell('独立来源候选已保存；请确认事实。原提取段落仍保持待核状态。');
    });
    for(const record of records.filter(r=>r.input.source_anchor_id===anchor.id))detail(form,'此前独立来源记录',record);
    observed.focus();
  });
}
function rawValue(f){const v=f.typed_value;return v.kind==='money'||v.kind==='ratio'?String(v.amount??v.value):String(v.value??'');}
async function loadFacts(){clear('anchors');await anchors();const snapshot=await api(base+'/facts');const host=clear('facts');for(const f of snapshot.facts){const c=el('div',undefined,'card');c.dataset.fact=f.id;c.append(el('strong',fieldNames[f.field]||'待核对事实'),el('p','候选来源：'+(f.provenance_type==='document'?'文件原文':f.provenance_type==='source_verification'?'独立来源核对记录（非自动提取原文）':'待核对来源')+' · 状态：'+confirmationNames[f.confirmation_status]));detail(c,'原始字段和类型',{field:f.field,kind:f.typed_value.kind,unit:f.unit});for(const id of f.anchor_ids)c.append(link('定位原文','/matters/'+encodeURIComponent(matter)+'/facts#anchor-'+encodeURIComponent(id)));
    const label=el('label','核对结果');const choice=el('select');choice.name='decision';for(const [v,t] of [['','请选择'],['confirmed','确认原值'],['corrected','更正'],['rejected','拒绝候选']]){const o=el('option',t);o.value=v;choice.append(o);}choice.required=true;label.append(choice);c.append(label);
    const unit={'CNY':'元','元':'元','percent':'%','%':'%','ratio':'比例'}[f.unit]||f.unit||'原文值';const vl=el('label','核对后的值（'+unit+'）');const input=el('input');input.name='value';input.value=rawValue(f);vl.append(input);c.append(vl);
    const rl=el('label','确认或更正理由');const reason=el('input');reason.name='reason';reason.value=localMaterial?'':'已核对独立虚构原文';reason.required=true;rl.append(reason);c.append(rl);host.append(c);
  }if(assisted){populateCandidateAnchors('candidate-fact-anchor');const confirmation=document.querySelector('#facts-form button');confirmation.disabled=!snapshot.facts.length;on('candidate-fact-form','submit',async event=>{const form=new FormData(event.currentTarget);const selected=allAnchors.find(a=>a.id===form.get('anchor_id'));const version=documents.find(v=>v.id===selected?.document_version_id);if(!selected||!version||!selected.sourceEligible)throw new Error('请选择当前可以消费的原文位置。');const kind=form.get('kind'),unit=form.get('unit').trim();if(kind==='decimal'&&!unit)throw new Error('精确数值必须按原文填写单位，不能猜测或自动换算。');await api(base+'/facts/candidates',{method:'POST',idempotency:key(),body:{document_version_id:version.id,document_sha256:version.sha256,fact_version:snapshot.version,candidates:[{field:form.get('field'),typed_value:{kind,value:form.get('value')},unit:unit||null,anchor_ids:[selected.id]}]}});candidateContext=null;await loadFacts();tell('候选已保存为新版本；请逐项核对完整事实快照。');});}on('facts-form','submit',async()=>{const decisions=snapshot.facts.map(f=>{const c=host.querySelector('[data-fact="'+f.id+'"]');const decision=c.querySelector('[name=decision]').value;const typed=structuredClone(f.typed_value);const value=c.querySelector('[name=value]').value;
      if(decision==='corrected'){if(typed.kind==='bool')typed.value=value==='true';else if(typed.kind==='integer')typed.value=Number(value);else if('amount'in typed)typed.amount=value;else typed.value=value;}
      return {fact_id:f.id,decision,confirmed_value:typed,reason:c.querySelector('[name=reason]').value};});const saved=await api(base+'/facts/confirm',{method:'POST',body:{fact_version:snapshot.version,decisions},idempotency:key()});await loadFacts();tell('事实已保存为新版本 '+saved.version+'。可进入18维审查。');});}
async function latestRun(){const list=await api(base+'/reviews');if(!list.length)return null;run=await api(base+'/reviews/'+encodeURIComponent(list[0].id));return run;}
function coverage(){const host=clear('coverage');if(!host)return;for(const item of run.coverage){const c=el('div',undefined,'card');c.append(el('strong',item.coverage_id+' '+(coverageNames.get(item.coverage_id)||'待核对维度')),el('p',coverageStates[item.status]||item.status));if(item.rationale)c.append(el('p',item.rationale,'muted'));host.append(c);}}
function basisEditor(form,previous,sources,nextCursor){
  const details=el('details'),summary=el('summary','本条意见的法源核验与谈判标准');details.append(summary);
  const enabled=el('input');enabled.type='checkbox';enabled.checked=!!previous;enabled.name='basis_enabled';
  const enabledLabel=el('label','随本次律师处置保存核验记录');enabledLabel.prepend(enabled);details.append(enabledLabel);
  details.append(el('p','仅核对所选的一条法源。来源真实性、命题支持、案件适用分别记录；采纳意见不会自动核验法源。退让与升级条件仅进入内部稿。','muted'));
  const fields={};
  function field(name,title,options=null){const label=el('label',title),input=el(options?'select':'textarea');input.name='basis_'+name;
    if(options)for(const [v,t] of options){const option=el('option',t);option.value=v;input.append(option);}else{input.rows=2;input.maxLength=name==='quote'?8000:2000;}
    if(previous?.[name]!=null)input.value=previous[name];fields[name]=input;label.append(input);details.append(label);return input;}
  const kind=field('kind','依据类型',[['law','法源核验'],['business_preference','商业偏好（非法律命令）']]);
  const sourceLabel=s=>s.title+' · '+(s.superseded?'已有后继版本':s.current_verified?'当前受控核验有效':'真实性未核验')+' · '+s.id.slice(0,8);
  const source=field('authority_id','本案已登记来源',[['','请选择来源'],...sources.map(s=>[s.id,sourceLabel(s)])]);
  const more=el('button','加载更多法源');more.type='button';more.hidden=!nextCursor;
  more.addEventListener('click',guard(async()=>{const page=await api(base+'/authority-sources?after='+encodeURIComponent(nextCursor));
    for(const item of page.items){if(!sources.some(s=>s.id===item.id))sources.push(item);if(![...source.options].some(o=>o.value===item.id)){const option=el('option',sourceLabel(item));option.value=item.id;source.append(option);}}
    nextCursor=page.next_cursor;more.hidden=!nextCursor;}));details.append(more);
  const original=el('pre');original.className='quote';details.append(original);
  const showSource=()=>{original.textContent=sources.find(s=>s.id===source.value)?.text_snapshot||'未选法源；可在页面上方登记本机原文。';};source.addEventListener('change',showSource);showSource();
  field('quote','所引原文（须与登记快照逐字一致）');field('proposition','本次核对的命题或商业要求');
  field('support','原文是否支持命题',[['pending','待核'],['supported','支持'],['not_supported','不支持']]);field('support_reason','支持关系核对理由');
  field('applicability','是否适用于本案',[['pending','待核'],['applies','适用'],['not_applies','不适用']]);field('applicability_reason','适用范围、例外及案件事实说明');
  const dateLabel=el('label','核对的法律适用时点'),date=el('input');date.type='date';date.name='basis_event_date';date.value=previous?.event_date||'';fields.event_date=date;dateLabel.append(date);details.append(dateLabel);
  field('standard_position','标准立场（商业偏好必填）');field('fallback_position','退让方案（商业偏好必填）');field('escalation_conditions','升级复核条件（商业偏好必填）');
  const toggle=()=>{for(const [name,input] of Object.entries(fields))input.disabled=!enabled.checked||(kind.value==='business_preference'&&['authority_id','quote','support','applicability','event_date'].includes(name));if(kind.value==='law'){if(!fields.support.value)fields.support.value='pending';if(!fields.applicability.value)fields.applicability.value='pending';}};enabled.addEventListener('change',toggle);kind.addEventListener('change',toggle);toggle();form.append(details);
  return ()=>{if(!enabled.checked)return null;const result={kind:kind.value,policy_sha256:run.manifest.policy_sha256};
    for(const name of ['proposition','support_reason','applicability_reason','standard_position','fallback_position','escalation_conditions'])result[name]=fields[name].value.trim()||null;
    if(['proposition','support_reason','applicability_reason'].some(n=>!result[n]))throw new Error('请填写命题、支持理由和适用说明。');
    if(kind.value==='law'){const selected=sources.find(s=>s.id===source.value);if(!selected||!fields.quote.value.trim()||!date.value)throw new Error('请选择法源并填写原文摘录和适用时点。');Object.assign(result,{authority_id:selected.id,source_sha256:selected.snapshot_sha256,quote:fields.quote.value, event_date:date.value,support:fields.support.value,applicability:fields.applicability.value});}
    else{if(['standard_position','fallback_position','escalation_conditions'].some(n=>!result[n]))throw new Error('商业偏好须填写标准立场、退让方案和升级条件。');Object.assign(result,{support:'not_applicable',applicability:'not_applicable'});}return result;};
}
function sourceRegistration(host){
  const box=el('details');box.id='authority-registration';box.append(el('summary','登记本案法源原文（本机保存，真实性待核）'));
  box.append(el('p','粘贴已取得的原文和来源信息。系统不会访问所填网址，也不会把登记或文本长度当作真实性核验。'));
  const form=el('form'),fields={};
  for(const [name,title,type] of [['title','名称','text'],['issuer','发布机关','text'],['url','来源网址','url'],['article','条号或定位','text'],['text_snapshot','原文快照','textarea'],['promulgated_at','公布日期（可留空）','date'],['effective_from','生效日期（可留空）','date'],['effective_to','失效日期（可留空）','date'],['jurisdiction','适用地域','text']]){
    const label=el('label',title),input=el(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;else input.rows=6;input.name='source_'+name;input.required=!['article','promulgated_at','effective_from','effective_to'].includes(name);input.maxLength=type==='textarea'?100000:2000;label.append(input);form.append(label);fields[name]=input;}
  const rankLabel=el('label','效力层级'),rank=el('select');rank.name='source_legal_rank';for(const [value,title] of [['law','法律'],['administrative_regulation','行政法规'],['judicial_interpretation','司法解释'],['departmental_rule','部门规章'],['local_regulation','地方性法规'],['unknown','待核']]){const option=el('option',title);option.value=value;rank.append(option);}rank.value='unknown';rankLabel.append(rank);form.append(rankLabel);
  const save=el('button','保存未核验来源');save.type='submit';form.append(save);
  form.addEventListener('submit',guard(async()=>{const body={};for(const [name,input] of Object.entries(fields))body[name]=input.value||null;
    const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(body.text_snapshot));body.snapshot_sha256=[...new Uint8Array(hash)].map(b=>b.toString(16).padStart(2,'0')).join('');
    Object.assign(body,{legal_rank:rank.value,fetch_status:'fetched',fetched_at:new Date().toISOString(),verification_status:'unverified',verified_by:null,verified_at:null});
    await api(base+'/authority-sources',{method:'POST',idempotency:key(),body});await loadReview();tell('法源原文已在本案登记；真实性仍待核验，可在意见处置中记录支持关系与适用性。');}));box.append(form);host.append(box);
}
async function loadReview(){
  const info=await loadMatter();if(assisted)await setupCandidateOpinions(info.matter.status);if(!await latestRun())return;coverage();const host=clear('findings');
  const sourcePage=await api(base+'/authority-sources'),authoritySources=sourcePage.items;
  for(const finding of run.decision_snapshot.resolved_findings){const id=finding.human_decision?.basis_review?.authority_id;if(id&&!authoritySources.some(s=>s.id===id))authoritySources.push(await api(base+'/authority-sources/'+encodeURIComponent(id)));}sourceRegistration(host);
  const rechecks=new Set(run.decision_authority.recheck_finding_ids);
  if(rechecks.size)host.append(el('p','处置作者资格或法源核验记录发生变化：标记的意见须由当前律师逐条重新核对；完成全部复核前不能生成或下载当前成果。','notice'));
  for(const f of run.findings){
    const current=run.decision_snapshot.resolved_findings.find(item=>item.id===f.id);
    const decision=current.human_decision;
    let status=!decision?'待律师处置':decision.decision==='edit'&&!decision.edited_analysis?'待完成编辑':decisionNames[decision.decision];
    if(rechecks.has(f.id))status='需当前律师重新复核 · 最近记录：'+status;
    const c=el('article',undefined,'card');c.id='finding-'+f.id;
    c.append(el('h3',(issueNames[f.issue_type]||'待律师核对意见')+' · '+severityNames[f.severity]),
      el('p','当前处置：'+status),el('p','原始候选分析：'+f.analysis),el('p','原始候选业务影响：'+f.business_effect),el('p','原始候选建议：'+f.recommendation));
    if(decision&&decision.decision==='edit'&&decision.edited_analysis){
      c.append(el('p','最近记录的明确编辑分析：'+current.analysis),el('p','最近记录的明确编辑建议：'+current.recommendation));
      if(current.replacement_text)c.append(el('p','拟替换文字（仍须独立批准修改）：'+current.replacement_text));
    }
    for(const id of [...f.anchor_ids,...f.cross_anchor_ids])c.append(link('定位原文','/matters/'+encodeURIComponent(matter)+'/facts#anchor-'+encodeURIComponent(id)));
    const form=el('form',undefined,'decision-form'),label=el('label','人工处置'),select=el('select');select.name='decision';
    for(const [v,t] of [['accept','接受意见'],['edit','编辑分析和建议'],['reject','拒绝意见'],['request_info','补充材料（不自动收费）'],['refer','转专项复核']]){const o=el('option',t);o.value=v;select.append(o);}
    if(decision)select.value=decision.decision;
    label.append(select);form.append(label);
    const edits=el('div'),inputs={};
    for(const [name,title,value,required] of [
      ['edited_analysis','编辑后的分析',current.analysis,true],
      ['edited_recommendation','编辑后的建议',current.recommendation,true],
      ['edited_replacement_text','拟替换文字（可留空；不自动批准修改）',current.replacement_text||'',false]]){
      const field=el('label',title),input=el('textarea');input.name=name;input.value=value;input.maxLength=20000;input.rows=3;input.dataset.editRequired=String(required);inputs[name]=input;field.append(input);edits.append(field);
    }
    const toggle=()=>{edits.hidden=select.value!=='edit';for(const input of Object.values(inputs)){input.disabled=edits.hidden;input.required=!edits.hidden&&input.dataset.editRequired==='true';}};
    select.addEventListener('change',toggle);toggle();form.append(edits);
    const rl=el('label','处置理由（保留在内部历史，不能代替改文）'),reason=el('input');reason.name='reason';reason.required=true;reason.maxLength=2000;reason.value=localMaterial?'':'独立虚构材料核对';rl.append(reason);form.append(rl);
    const button=el('button','保存人工处置');button.type='submit';form.append(button);
    const readBasis=basisEditor(form,decision?.basis_review,authoritySources,sourcePage.next_cursor);
    if(decision?.basis_review)c.append(el('p','本条依据：'+({verified:'法源有受控核验记录',unverified:'法源真实性未核验',not_legal_basis:'商业偏好，非法律命令'}[decision.basis_review.source_status])+'；支持：'+({pending:'待核',supported:'记录支持',not_supported:'不支持',not_applicable:'不适用'}[decision.basis_review.support])+'；适用：'+({pending:'待核',applies:'记录适用',not_applies:'不适用',not_applicable:'商业选择'}[decision.basis_review.applicability]),'notice'));
    form.addEventListener('submit',guard(async()=>{
      const body={run_id:run.id,run_sha256:run.run_sha256,decision:select.value,reason:reason.value};
      body.basis_review=readBasis();
      if(select.value==='edit')for(const [name,input] of Object.entries(inputs))body[name]=(name==='edited_replacement_text'?input.value:input.value.trim())||null;
      await api(base+'/findings/'+encodeURIComponent(f.id)+'/decision',{method:'POST',idempotency:key(),body});
      latestBundle=null;await loadReview();tell(run.decision_authority.status==='recheck_required'
        ?'本条处置已留存；仍有意见需要当前律师重新复核，全部完成后才能重新生成成果。'
        :'人工处置已留存；旧成果已失效，请重新生成预览。修改原文仍须独立批准，当前模式不能正式签发。');
    }));c.append(form);
    for(const d of run.decisions.filter(item=>item.finding_id===f.id)){
      c.append(el('p','历史处置：'+(decisionNames[d.decision.decision]||'待核对处置')+' · '+d.decision.reason,'muted'));
      if(d.decision.edited_analysis)detail(c,'历史改文',{analysis:d.decision.edited_analysis,recommendation:d.decision.edited_recommendation,replacement:d.decision.edited_replacement_text});
    }
    detail(c,'受保护意见标识',f.id);host.append(c);
  }
  for(const note of run.limitations)host.append(el('p',note,'muted'));
}
function candidateLines(value){return value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);}
function candidateFromForm(){const form=document.getElementById('candidate-opinion-form'),data=new FormData(form);const ids=data.getAll('anchor_ids');if(!ids.length||ids.length>8)throw new Error('请为本条候选选择1至8个原文位置。');for(const field of ['analysis','business_effect','recommendation'])if(!data.get(field).trim())throw new Error('请填写分析、业务影响和建议。');const refs=candidateLines(data.get('authority_refs')),unknowns=candidateLines(data.get('unknowns'));if(refs.length>8||unknowns.length>10)throw new Error('待核引用最多8项，未知事项最多10项。');if(refs.length&&data.get('basis_kind')!=='pending_authority')throw new Error('提供法源引用时，请选择“法源依据待核”，不能自行标为已核。');return {coverage_ids:[data.get('coverage_id')],issue_type:'manual_candidate',severity:data.get('severity'),evidence_state:'unconfirmed',anchor_ids:ids.filter(id=>!id.startsWith('verification:')),verification_ids:ids.filter(id=>id.startsWith('verification:')).map(id=>id.slice(13)),analysis:data.get('analysis'),business_effect:data.get('business_effect'),recommendation:data.get('recommendation'),basis_kind:data.get('basis_kind'),authority_refs:refs,unknowns};}
function renderCandidateOpinions(){const host=clear('candidate-opinion-list');if(!host)return;for(const [index,item] of candidateOpinions.entries()){const card=el('div',undefined,'card');card.append(el('strong','候选 '+(index+1)),el('p',item.analysis),el('p','待核引用：'+(item.authority_refs.join('；')||'未提供')),el('p','未知事项：'+(item.unknowns.join('；')||'未另列，不代表完整核验')));const remove=el('button','移除此候选');remove.type='button';remove.addEventListener('click',()=>{candidateOpinions.splice(index,1);renderCandidateOpinions();});card.append(remove);host.append(card);}}
async function setupCandidateOpinions(status){const bridgeButton=document.getElementById('case-bridge-open');if(bridgeButton)bridgeButton.disabled=true;const form=document.getElementById('candidate-opinion-form');if(!form)return;const enabled=status==='ready_for_review';for(const input of form.elements)input.disabled=!enabled;candidateContext=null;if(!enabled){clear('candidate-opinion-list').append(el('p',status==='awaiting_lawyer'?'本轮候选已保存。请在下方逐条处置；修改事实或立场后才能建立新一轮候选。':'请先完成原文及事实确认，再录入本轮候选。'));return;}await anchors();populateCandidateAnchors('candidate-opinion-anchor');const choice=clear('candidate-dimension');for(const [id,name] of coverageNames){const option=el('option',id+' '+name);option.value=id;choice.append(option);}candidateContext=await api(base+'/review-context');const sourceRecords=await api(base+'/page-verifications');const sourceChoice=document.getElementById('candidate-opinion-anchor');for(const record of sourceRecords.filter(r=>(candidateContext.eligible_verification_ids||[]).includes(r.id))){const option=el('option','独立来源核对（非文字层）· '+(record.input.page===null?'DOCX段落 '+record.input.source_anchor_id:'第 '+record.input.page+' 页')+' · '+record.input.observed_text);option.value='verification:'+record.id;sourceChoice.append(option);}if(bridgeButton)bridgeButton.disabled=false;renderCandidateOpinions();on('add-candidate-opinion','click',async()=>{if(candidateOpinions.length>=32)throw new Error('每轮最多32条人工候选。');candidateOpinions.push(candidateFromForm());renderCandidateOpinions();tell('已加入候选清单；尚未保存，也未形成律师处置。');});on('candidate-opinion-form','submit',async()=>{if(!candidateContext)throw new Error('当前上下文不可用，请刷新并核对事实版本。');const opinions=candidateOpinions.length?candidateOpinions:[candidateFromForm()];const examined=[...new Set(opinions.flatMap(item=>item.anchor_ids))];await api(base+'/review-proposals',{method:'POST',idempotency:key(),body:{context_sha256:candidateContext.context_sha256,fact_version:candidateContext.fact_version,document_hashes:candidateContext.document_hashes,examined_anchor_ids:examined,examined_verification_ids:[...new Set(opinions.flatMap(item=>item.verification_ids||[]))],opinions}});candidateOpinions=[];candidateContext=null;latestBundle=null;await loadReview();tell('离线人工候选已保存；未涉及维度保持不足，请逐条律师处置。');});}
async function loadParties(){const host=clear('parties');const select=clear('party-choice');for(const p of await api(base+'/parties')){const c=el('div',undefined,'card');c.append(el('p',p.name_raw),el('p','当前主体状态：'+(partyStateNames[p.resolution_status]||'待人工明确')));for(const candidate of p.candidate_evidence){const b=el('button','明确选择此虚构原文候选');b.addEventListener('click',guard(async()=>{await api(base+'/parties/select',{method:'POST',idempotency:key(),body:{party_id:p.id,candidate_id:candidate.candidate_id,reason:'仅核对虚构原文候选，非企业实时结果'}});tell('虚构候选已明确选择。主体变化使旧审查失效，后续需重新确认事实。');await loadParties();}));c.append(el('p','待人工明确名称的虚构原文候选：'),el('p',candidate.name),b);}if(p.resolution_status==='confirmed'){const option=el('option',p.name_confirmed);option.value=p.id;select.append(option);}host.append(c);}}
async function loadQueries(){await loadMatter();const data=await api(base+'/query-status');clear('query-status').append(el('p','外查关闭 · 自动重试 '+data.auto_retries+' · 最大 '+data.max_calls+' 次 · 默认 '+data.default_pages+' 页'),el('p','预算批准：'+(data.budget.approved===false?'待明确批准':'已批准本机模拟积分预算')));await loadParties();}
function updateAnchorChoice(){const f=run.findings.find(f=>f.id===document.getElementById('finding-choice').value);const choice=clear('anchor-choice');for(const a of allAnchors.filter(a=>[...f.anchor_ids,...f.cross_anchor_ids].includes(a.id))){const option=el('option',a.quote);option.value=a.id;choice.append(option);}updateOld();}
function updateOld(){const a=allAnchors.find(a=>a.id===document.getElementById('anchor-choice').value);document.getElementById('patch-old').textContent=a?a.quote:'无可用原文，需人工核对';}
async function loadExports(){await loadMatter();await anchors();if(!await latestRun()){tell('请先完成事实确认和mock审查。');return;}const choice=clear('finding-choice');for(const f of run.findings){const option=el('option',(issueNames[f.issue_type]||'待核对意见')+'（'+severityNames[f.severity]+'）');option.value=f.id;choice.append(option);}choice.addEventListener('change',updateAnchorChoice);document.getElementById('anchor-choice').addEventListener('change',updateOld);updateAnchorChoice();
  // Current approved patches are read from server; navigation never invents approval.
  selectedPatches=await api(base+'/patches?run_id='+encodeURIComponent(run.id));renderPatches();}
function renderPatches(){const host=clear('patches'),selection=clear('patch-selection');for(const p of selectedPatches){host.append(el('p','已批准草案：'+p.new_text,'card'));const label=el('label');const checkbox=el('input');checkbox.type='checkbox';checkbox.value=p.id;checkbox.name='patch_id';checkbox.checked=true;label.append(checkbox,el('span',p.new_text));selection.append(label);}}
function renderBundle(bundle){latestBundle=bundle;const host=clear('bundles');host.append(el('h3','草案预览 · '+(audienceNames[bundle.audience]||'待核对受众')),el('p','草案未正式签发。'));for(const artifact of bundle.artifacts){const a=link('下载'+(artifact.type==='review_report_docx'?'审查报告':'修改草案')+'（DOCX）',base+'/exports/'+encodeURIComponent(artifact.id)+'/download');a.className='button';host.append(a);}for(const note of bundle.limitations)host.append(el('p',note,'muted'));detail(host,'校验清单',bundle.manifest_sha256);}
function unresolvedDraftFindings(){return run?run.decision_snapshot.resolved_findings.filter(f=>['request_info','refer'].includes(f.human_decision?.decision)):[];}
function renderDraftUnresolved(){const host=clear('working-draft-unresolved');if(!host)return;const findings=unresolvedDraftFindings();host.append(el('p',findings.length?'本版保留的待办范围：':'本版没有处置为待补资料或转专项的意见；其他材料、法源及法律限制仍保留。'));for(const f of findings)host.append(el('p',(f.human_decision.decision==='refer'?'转专项：':'待补资料：')+f.analysis));clear('working-draft-status');}
async function loadEffectiveText(){
  effectiveText=null;effectiveReview=null;
  const host=clear('effective-text'),form=document.getElementById('effective-review-form');
  if(!host||!form)return;
  form.hidden=true;form.reset();clear('effective-review-status');clear('effective-review-fields');
  if(latestBundle.audience!=='internal'){host.append(el('p','对外人工修改表没有已落实的修订全文。请在内部草案完成全文复审；对外文件仍需人工核对，不能登记为已复审修订合同。'));return;}
  effectiveText=await api(base+'/bundles/'+encodeURIComponent(latestBundle.id)+'/effective-text');
  for(const limitation of effectiveText.limitations)host.append(el('p','待核限制：'+limitation,'notice'));
  const signals={number:'数值线索',deadline:'期限线索',reference:'引用/定义线索',old_value_remaining:'旧值仍在其他位置出现，请核对是否冲突'};
  for(const doc of effectiveText.documents){
    const block=el('details');block.open=true;block.append(el('summary',doc.original_name+' · '+doc.paragraphs.length+'个可读位置'),el('p','源文件基线：'+baselineNames[doc.baseline_view]+'；当前展示：'+(doc.artifact_id?'实际导出文件接受全部修订后的文字（包括已有修订）':'源文件已选基线文字')));
    for(const limitation of doc.limitations)block.append(el('p','读取限制：'+limitation,'notice'));
    doc.paragraphs.forEach((p,index)=>{const card=el('div',undefined,'card');card.id='effective-'+p.anchor_id;card.append(el('strong','位置 '+(index+1)+(p.patch_id?' · 本版已修改':p.text!==p.original_text?' · 已有修订接受视图变化':'')),el('p',p.location,'muted'));if(p.patch_id||p.text!==p.original_text)card.append(el('p','源基线文字：'+(p.original_text||'本位置在源基线中没有可读文字')));card.append(el('p',p.text));
      const items=effectiveText.signals.filter(s=>s.anchor_id===p.anchor_id);for(const kind of Object.keys(signals)){const texts=items.filter(s=>s.kind===kind).map(s=>s.quote);if(texts.length)card.append(el('p',signals[kind]+'：'+texts.join('、'),'muted'));}block.append(card);});host.append(block);
  }
  const fields=clear('effective-review-fields');
  for(const [name,label] of Object.entries(effectiveDimensions)){const field=el('fieldset');field.append(el('legend',label));const choice=el('select');choice.name=name;choice.setAttribute('aria-label',label+'结论');for(const [value,text] of [['pending','待核，保留为后续事项'],['reviewed','律师已核对本版所列范围']]){const option=el('option',text);option.value=value;choice.append(option);}const note=el('textarea');note.name=name+'_reason';note.required=true;note.maxLength=2000;note.rows=2;note.setAttribute('aria-label',label+'核对依据或待核事项');const noteLabel=el('label','核对依据或待核事项');noteLabel.append(note);field.append(choice,noteLabel);fields.append(field);}
  form.hidden=false;
}
on('effective-review-form','submit',async event=>{if(!effectiveText||!latestBundle)throw new Error('请重新生成并读取这一版内部草案。');const form=new FormData(event.currentTarget);const body={bundle_id:latestBundle.id,effective_text_sha256:effectiveText.sha256};for(const name of Object.keys(effectiveDimensions))body[name]={status:form.get(name),reason:form.get(name+'_reason')};effectiveReview=await api(base+'/effective-text-reviews',{method:'POST',idempotency:key(),body});clear('effective-review-status').append(el('p',effectiveReview.status==='pending'?'复审记录已保存，仍有待核项或读取限制。':'已记录律师在本版可读范围内的复审；非正式签发。'));clear('working-draft-status');tell('本版复审记录已保存，可继续核对实际工作稿。');});
on('login-form','submit',async event=>{const form=new FormData(event.currentTarget);await api('/api/login',{method:'POST',body:{username:form.get('username'),password:form.get('password')}});const session=await api('/api/session');location.assign(['/workspace','/assistant','/recovery'].includes(session.home_url)?session.home_url:'/workspace');});
on('logout','click',async()=>{await api('/api/logout',{method:'POST'});location.assign('/login');});
on('case-bridge-form','submit',async event=>{const element=event.currentTarget;const form=new FormData(element);if(form.get('share_with_chat')!=='on')throw new Error('请先明确同意开放本案虚构材料。');if(!candidateContext)throw new Error('请先完成事实确认并刷新当前审查页面。');const context=candidateContext;const saved=await api(base+'/case-bridge',{method:'POST',body:{context_sha256:context.context_sha256,share_with_chat:true,allow_candidate_submission:form.get('allow_candidate_submission')==='on'}});element.reset();clear('case-bridge-status').append(el('p',(saved.read_only?'本案只读连接已开放，至 ':'本案读取及一轮候选提交已开放，至 ')+new Date(saved.expires_at).toLocaleString('zh-CN')+'。可在已加载新工具的聊天调用 read_selected_case。'));tell(saved.read_only?'仅开放当前版本读取；尚未提交意见。':'仅允许一轮候选提交；提交后请刷新本页，由律师逐条处置。');});
on('case-bridge-revoke','click',async()=>{await api(base+'/case-bridge',{method:'DELETE'});clear('case-bridge-status').append(el('p','本次连接已撤销。'));tell('插件不能继续读取本次连接。');});
on('create-form','submit',async event=>{const form=new FormData(event.currentTarget);const saved=await api('/api/matters',{method:'POST',idempotency:key(),body:{title:form.get('title'),contract_type:form.get('contract_type'),position:form.get('position'),review_mode:form.get('review_mode'),objectives:[form.get('objectives')],reviewer_username:form.get('reviewer_username')||null,...(form.has('material_mode')?{material_mode:form.get('material_mode')}:{})}});location.assign('/matters/'+encodeURIComponent(saved.id));});
on('reparse-form','submit',async event=>{
  if(!reparseSnapshot||!documents.length)throw new Error('请先读取本案当前材料。');
  const form=event.currentTarget,data=new FormData(form);
  const sent=await api(base+'/documents/reparse',{method:'POST',idempotency:key(),body:{...reparseSnapshot,reason:data.get('reason'),reconfirmation_acknowledged:data.get('reconfirmation_acknowledged')==='on'}});
  await poll(sent.job_id,'reparse-status');form.reset();
  if(section==='facts')await loadFacts();else await loadDocuments();
  tell('当前文件已重新读取，历史记录保留。仍有读取疑点的内容须核对原件；事实已回到待确认。');
});
on('upload-form','submit',async event=>{const form=event.currentTarget;const saved=await api(base+'/documents',{method:'POST',body:new FormData(form),idempotency:key()});await poll(saved.job_id);if(localMaterial)form.elements.local_processing_confirmed.checked=false;tell(localMaterial?'本机原文已保存；请核对原文并录入人工事实，模型未运行。':assisted?'虚构合同原文已保存；请录入原文绑定的候选事实，再逐项确认。':'虚构合同已解析，候选事实待逐项确认。');await loadDocuments();});
on('start-review','click',async()=>{await loadMatter();const facts=await api(base+'/facts');const hashes=Object.fromEntries(documents.map(v=>[v.id,v.sha256]));const saved=await api(base+'/reviews',{method:'POST',idempotency:key(),body:{fact_version:facts.version,document_hashes:hashes}});await poll(saved.job_id);tell('mock审查已完成；法律规则待批，仍需律师核对。');await loadReview();});
on('party-candidates','click',async()=>{await api(base+'/parties/candidates',{method:'POST',idempotency:key()});await loadParties();});
on('q0-form','submit',async event=>{const form=new FormData(event.currentTarget);const plan=await api(base+'/query-plans',{method:'POST',idempotency:key(),body:{matter_id:matter,party_id:form.get('party_id'),purpose:form.get('purpose'),items:[],authorization_id:null,scope:'Q0'}});const host=clear('query-plans');host.append(el('p','Q0计划已保存；费用0，调用0。'));const b=el('button','批准并运行Q0关闭计划');b.addEventListener('click',guard(async()=>{await api(base+'/query-plans/'+encodeURIComponent(plan.id)+'/approve',{method:'POST',idempotency:key(),body:{plan_sha256:plan.plan_sha256}});const queued=await api(base+'/query-plans/'+encodeURIComponent(plan.id)+'/execute',{method:'POST',idempotency:key(),body:{plan_sha256:plan.plan_sha256}});await poll(queued.job_id);tell('Q0已完成，未外发或收费。');}));host.append(b);});
on('patch-form','submit',async event=>{if(!run)throw new Error('先完成mock审查。');const form=new FormData(event.currentTarget);const saved=await api(base+'/patches/approve',{method:'POST',idempotency:key(),body:{run_id:run.id,run_sha256:run.run_sha256,finding_id:form.get('finding_id'),anchor_id:form.get('anchor_id'),new_text:form.get('new_text'),reason:form.get('reason'),audiences:form.getAll('audience')}});selectedPatches.push(saved);renderPatches();tell('精确草案修改已批准；不代表正式签发。');});
on('preview-form','submit',async event=>{if(!run)throw new Error(assisted?'请先保存候选并完成律师处置。':'先完成mock审查。');const form=new FormData(event.currentTarget);const saved=await api(base+'/exports/preview',{method:'POST',idempotency:key(),body:{run_id:run.id,run_sha256:run.run_sha256,audience:form.get('audience'),patch_ids:form.getAll('patch_id')}});if(assisted){run=await api(base+'/reviews/'+encodeURIComponent(run.id));renderDraftUnresolved();const check=document.getElementById('working-draft-form');check.reset();}renderBundle(saved);await loadEffectiveText();tell('已生成受众草案，可下载核对。');});
on('working-draft-form','submit',async event=>{if(!run||!latestBundle)throw new Error('请先生成并打开这一版实际草案文件。');const form=new FormData(event.currentTarget);if(form.get('actual_file_checked')!=='on'||form.get('scope_checked')!=='on')throw new Error('请自行核对实际文件和待办范围后勾选。');const saved=await api(base+'/working-draft-confirmations',{method:'POST',idempotency:key(),body:{bundle_id:latestBundle.id,bundle_manifest_sha256:latestBundle.manifest_sha256,decision_snapshot_sha256:run.decision_snapshot.sha256,audience:latestBundle.audience,acknowledged_unresolved_finding_ids:unresolvedDraftFindings().map(f=>f.id),reason:form.get('reason'),effective_text_review_id:effectiveReview?.id||null}});clear('working-draft-status').append(el('p','这一版工作稿已记录核对（非正式签发）。'),el('p','核对记录：'+saved.id),el('p',saved.effective_text_review_status==='pending'?'全文复审仍有待核项或读取限制。':saved.effective_text_review_status?'复审范围见本版记录。':'本次仅为报告版本核对，未记录修订全文复审。'));tell('已保存当前工作稿的版本核对记录；内容或处置变化后需要重新生成和核对。');});
on('formal-approve','click',async()=>{if(!latestBundle)throw new Error('请先生成草案预览。');await api(base+'/approvals',{method:'POST',idempotency:key(),body:{bundle_id:latestBundle.id,artifact_manifest_hash:latestBundle.manifest_sha256,review_snapshot_hash:run.run_sha256,scope:latestBundle.audience}});});
const loaders={cases:loadCases,intake:loadDocuments,facts:loadFacts,review:loadReview,queries:loadQueries,exports:loadExports};if(loaders[section])loaders[section]().catch(error=>tell(error.message));

window.addEventListener('qx-proofreading-saved',()=>{void loadFacts().catch(error=>tell(error.message));});
