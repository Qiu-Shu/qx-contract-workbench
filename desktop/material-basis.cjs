const SHA=/^[0-9a-f]{64}$/,UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const fields=['request_id','expected_scope','expected_composer_revision','parent_business_run_id','input_format','manifest','manifest_sha256','system_sha256','config_sha256','wire_sha256','wire_bytes'];
const MATERIAL_ERRORS=Object.freeze(['MATERIAL_INPUT_TOO_LARGE','CAPABILITY_UNAVAILABLE','HEARING_ROLE_REQUIRED',
  'HEARING_ROLE_CONFLICT','HEARING_RESTART_REQUIRED','HEARING_MATERIAL_LIMIT','KNOWLEDGE_UNAVAILABLE',
  'CRIMINAL_SCOPE_REQUIRED','CRIMINAL_HEARING_UNAVAILABLE','IP_SCOPE_UNSUPPORTED','MATERIAL_INSTRUCTION_CONFLICT',
  'MATERIAL_HISTORY_TOO_LARGE']);
function validKnowledge(k){
  return exact(k,['searches','passages'])&&Array.isArray(k.searches)&&k.searches.length<=3&&
    Array.isArray(k.passages)&&k.passages.length<=8&&k.searches.every(s=>
      exact(s,['origin','query','state','source_count','original_documents','index_sha256','source_reference'])&&
      ['reception','family','public_law'].includes(s.origin)&&['searched','no_match'].includes(s.state)&&
      text(s.query,300)&&SHA.test(s.index_sha256))&&k.passages.every(p=>
      exact(p,['source_id','origin','source_name','source_sha256','index_sha256','locator','text','quote_sha256',
        'source_reference','source_urls','version','review_state','applicability_verified','upstream_status','upstream_effective_date','limitations'])&&
      ['reception','family','public_law'].includes(p.origin)&&['source_id','source_sha256','index_sha256','quote_sha256'].every(key=>SHA.test(p[key]))&&
      text(p.text,1400)&&p.applicability_verified===false&&['user_unverified','unverified_mirror'].includes(p.review_state)&&
      k.searches.some(s=>s.origin===p.origin&&s.state==='searched'&&s.index_sha256===p.index_sha256));
}
const text=(v,max)=>typeof v==='string'&&v.trim().length>0&&[...v].length<=max;
function validCapability(c,workflow){
  const common=['workflow','kind','source_id','version','source_reference','license_notice','method_source','method_sha256'];
  if(!c||c.workflow!==workflow||!text(c.source_id,128)||!text(c.version,128)||!text(c.source_reference,2048)||
      !text(c.license_notice,4000)||!text(c.method_source,240)||!SHA.test(c.method_sha256))return false;
  if(c.kind==='builtin')return workflow==='contract'&&exact(c,common);
  if(c.kind==='local_skill')return ['sales','case'].includes(workflow)&&exact(c,[...common,'metadata_sha256','method_text'])&&
    SHA.test(c.metadata_sha256)&&text(c.method_text,32768);
  const files=['mock_hearing.py','hearing_audit.py','hearing_tracking.py','portable_lock.py','windows_private.py'];
  return c.kind==='local_adapter'&&workflow==='court'&&c.source_id==='chiheng-legal-workbench'&&exact(c,[...common,'code_files'])&&
    Array.isArray(c.code_files)&&c.code_files.length===5&&new Set(c.code_files.map(f=>f?.path)).size===5&&
    c.code_files.every(f=>exact(f,['path','sha256'])&&files.includes(f.path)&&SHA.test(f.sha256));
}
function validHearing(h){
  // Full source, snapshot digest and role-transition validation stays in the backend.
  const roles={issues:['moderator','plaintiff','defendant'],evidence:['plaintiff','defendant'],
    questions:['moderator','plaintiff','defendant'],debate:['plaintiff','defendant'],review:['reviewer']};
  return exact(h,['our_role','synthetic','stage','roles','previous_output_id','previous_session','reset_reason'])&&
    ['plaintiff','defendant'].includes(h.our_role)&&typeof h.synthetic==='boolean'&&Object.hasOwn(roles,h.stage)&&
    JSON.stringify(h.roles)===JSON.stringify(roles[h.stage])&&(h.previous_output_id===null||UUID.test(h.previous_output_id))&&
    [null,'materials_changed','method_changed'].includes(h.reset_reason)&&
    (h.previous_session===null||h.previous_output_id!==null&&h.previous_session?.schema_version===2&&
      h.previous_session.our_role===h.our_role&&h.previous_session.synthetic===h.synthetic&&
      SHA.test(h.previous_session.content_sha256)&&Array.isArray(h.previous_session.turns)&&h.previous_session.turns.length<=20);
}
function validHistory(history,revision,maxBytes=32768){
  if(!Number.isSafeInteger(revision)||revision<1||!Array.isArray(history)||history.length===0||history.length>16||history.length%2||
      Buffer.byteLength(JSON.stringify(history),'utf8')>maxBytes)return false;
  const seen=new Set();let previous=0;
  for(let index=0;index<history.length;index+=2){
    const question=history[index],answer=history[index+1];
    for(const item of [question,answer]){
      if(!exact(item,['message_id','role','source_revision','content'])||typeof item.message_id!=='string'||
          !UUID.test(item.message_id)||seen.has(item.message_id)||typeof item.content!=='string'||
          !item.content.trim()||[...item.content].length>20000)return false;
      seen.add(item.message_id);
    }
    if(question.role!=='user'||answer.role!=='assistant'||!Number.isSafeInteger(question.source_revision)||
        question.source_revision<=previous||question.source_revision>=revision||
        question.source_revision!==answer.source_revision)return false;
    previous=question.source_revision;
  }
  return true;
}
function validContractReview(c,m){
  const methods=['general','nda','vendor'];
  const unique=(a)=>new Set(a).size===a.length;
  if(!exact(c,['method_id','method_sha256','method_sources','routes','playbook_status'])||
      !['contract-review-v1','contract-review-v2','contract-review-v3'].includes(c.method_id)||typeof c.method_sha256!=='string'||!SHA.test(c.method_sha256)||
      c.playbook_status!=='unavailable'||!Array.isArray(c.routes)||c.routes.length<1||c.routes.length>20||
      !Array.isArray(c.method_sources)||c.method_sources.length<1||c.method_sources.length>3||
      !Array.isArray(m.materials)||!Array.isArray(m.sources))return false;
  if(!c.method_sources.every(s=>exact(s,['method_id','method_sha256','source_reference','license_notice'])&&
      methods.includes(s.method_id)&&typeof s.method_sha256==='string'&&SHA.test(s.method_sha256)&&
      text(s.source_reference,2048)&&text(s.license_notice,2000)))return false;
  const registered=c.method_sources.map(s=>s.method_id),routed=c.routes.map(r=>r?.attachment_id);
  return unique(registered)&&unique(routed)&&routed.length===m.materials.length&&c.routes.every(r=>
    exact(r,['attachment_id','methods','evidence_source_ids','uncovered'])&&typeof r.attachment_id==='string'&&UUID.test(r.attachment_id)&&
    m.materials.some(f=>f.attachment_id===r.attachment_id)&&
    Array.isArray(r.methods)&&r.methods.length<=3&&unique(r.methods)&&r.methods.every(v=>registered.includes(v))&&
    Array.isArray(r.evidence_source_ids)&&r.evidence_source_ids.length<=40&&unique(r.evidence_source_ids)&&r.evidence_source_ids.every(v=>
      typeof v==='string'&&SHA.test(v)&&m.sources.some(s=>s.source_id===v&&s.reference?.kind==='document'&&s.reference.attachment_id===r.attachment_id))&&
    Array.isArray(r.uncovered)&&r.uncovered.length<=2&&unique(r.uncovered)&&r.uncovered.every(v=>['saas','dpa'].includes(v)))&&
    registered.every(v=>c.routes.some(r=>r.methods.includes(v)));
}
function validMaterialBasis(v){
  if(!exact(v,fields)||v.input_format!=='material-business-v1'||!UUID.test(v.request_id)||!UUID.test(v.parent_business_run_id)||
      !Number.isSafeInteger(v.expected_composer_revision)||v.expected_composer_revision<0||
      !Number.isSafeInteger(v.wire_bytes)||v.wire_bytes<1||v.wire_bytes>262144||
      !['manifest_sha256','system_sha256','config_sha256','wire_sha256'].every(k=>typeof v[k]==='string'&&SHA.test(v[k])))return false;
  const m=v.manifest;
  const history=Object.hasOwn(m||{},'conversation_history');
  const capability=Object.hasOwn(m||{},'capability'),hearing=Object.hasOwn(m||{},'hearing');
  const knowledge=Object.hasOwn(m||{},'knowledge');
  const caseMethod=Object.hasOwn(m||{},'case_method');
  const contractReview=Object.hasOwn(m||{},'contract_review');
  const criminalAnalysis=Object.hasOwn(m||{},'criminal_analysis');
  const trademarkTriage=Object.hasOwn(m||{},'trademark_triage');
  const historyFormat=Object.hasOwn(m||{},'history_format');
  return exact(m,['input_format','workflow','stable_task_id','parent_business_run_id','question','materials','sources',
    ...(history?['conversation_history']:[]),...(capability?['capability']:[]),...(hearing?['hearing']:[]),...(knowledge?['knowledge']:[]),
    ...(caseMethod?['case_method']:[]),...(contractReview?['contract_review']:[]),...(criminalAnalysis?['criminal_analysis']:[]),
    ...(trademarkTriage?['trademark_triage']:[]),...(historyFormat?['history_format']:[])])&&
    (!historyFormat||m.history_format==='contract-full-text-v1'&&m.workflow==='contract')&&
    (!trademarkTriage||m.workflow==='case'&&!caseMethod&&!criminalAnalysis&&!contractReview&&Boolean(validTrademarkTriage(m.trademark_triage)))&&
    (!criminalAnalysis||m.workflow==='case'&&!caseMethod&&Boolean(validCriminalAnalysis(m.criminal_analysis,m)))&&
    (!contractReview||m.workflow==='contract'&&Boolean(validContractReview(m.contract_review,m)))&&
    (!caseMethod||m.workflow==='case'&&Boolean(exact(m.case_method,['method_id','method_sha256']))&&
      ['case-evidence-v1','case-evidence-v2','case-evidence-v3','case-evidence-v4','case-evidence-v5'].includes(m.case_method.method_id)&&typeof m.case_method.method_sha256==='string'&&SHA.test(m.case_method.method_sha256))&&
    (!knowledge||validKnowledge(m.knowledge))&&
    (!capability||validCapability(m.capability,m.workflow))&&hearing===(m.capability?.kind==='local_adapter')&&
    (!hearing||validHearing(m.hearing))&&
    (!history||validHistory(m.conversation_history,v.expected_scope?.input_revision,
      m.history_format==='contract-full-text-v1'?65536:32768))&&
    m.input_format===v.input_format&&m.parent_business_run_id===v.parent_business_run_id&&UUID.test(m.stable_task_id)&&
    ['sales','case','contract','court'].includes(m.workflow)&&typeof m.question==='string'&&m.question.trim().length>0&&
    Array.isArray(m.materials)&&(m.materials.length>0||m.workflow==='sales')&&m.materials.length<=20&&
    Array.isArray(m.sources)&&m.sources.length>0&&m.sources.length<=2000&&
    m.materials.every(f=>typeof f.name==='string'&&SHA.test(f.original_sha256)&&Number.isSafeInteger(f.parse_revision)&&f.parse_revision>0&&Array.isArray(f.unread_parts))&&
    m.sources.every(s=>exact(s,['source_id','reference'])&&SHA.test(s.source_id)&&
      (s.reference?.kind==='document'?typeof s.reference.anchor?.quote==='string':s.reference?.kind==='message'&&typeof s.reference.quote==='string'))&&
    Buffer.byteLength(JSON.stringify(v),'utf8')<=400000;
}
function validCriminalAnalysis(c,m){
  if(!exact(c,['method_id','method_sha256','method_sources','stage','stage_source_id','material_policy'])||
      c.method_id!=='criminal-analysis-v1'||typeof c.method_sha256!=='string'||!SHA.test(c.method_sha256)||
      c.material_policy!=='synthetic-only-v1'||!['unknown','investigation','prosecution','trial'].includes(c.stage)||
      !Array.isArray(c.method_sources)||![1,2].includes(c.method_sources.length)||
      c.method_sources[0]?.method_id!=='case_analysis'||
      c.method_sources.length===2&&c.method_sources[1]?.method_id!=='defense_strategy')return false;
  if(!c.method_sources.every(s=>exact(s,['method_id','method_sha256','source_reference','license_notice'])&&
      ['case_analysis','defense_strategy'].includes(s.method_id)&&typeof s.method_sha256==='string'&&
      SHA.test(s.method_sha256)&&text(s.source_reference,2048)&&text(s.license_notice,2000)))return false;
  if(c.stage==='unknown')return c.stage_source_id===null;
  return typeof c.stage_source_id==='string'&&SHA.test(c.stage_source_id)&&Array.isArray(m.sources)&&
    m.sources.find(s=>s.reference?.kind==='message')?.source_id===c.stage_source_id;
}
function validTrademarkTriage(c){
  return exact(c,['method_id','method_sha256','right_type','source_reference','license_notice'])&&
    ['trademark-triage-v1','trademark-triage-v2','trademark-triage-v3','trademark-triage-v4','trademark-triage-v5','trademark-triage-v6'].includes(c.method_id)&&typeof c.method_sha256==='string'&&SHA.test(c.method_sha256)&&
    c.right_type==='trademark'&&text(c.source_reference,2048)&&text(c.license_notice,2000);
}
module.exports={validMaterialBasis,MATERIAL_ERRORS};
