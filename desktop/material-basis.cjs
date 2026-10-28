const SHA=/^[0-9a-f]{64}$/,UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const fields=['request_id','expected_scope','expected_composer_revision','parent_business_run_id','input_format','manifest','manifest_sha256','system_sha256','config_sha256','wire_sha256','wire_bytes'];
function validHistory(history,revision){
  if(!Number.isSafeInteger(revision)||revision<1||!Array.isArray(history)||history.length===0||history.length>16||history.length%2||
      Buffer.byteLength(JSON.stringify(history),'utf8')>32768)return false;
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
function validMaterialBasis(v){
  if(!exact(v,fields)||v.input_format!=='material-business-v1'||!UUID.test(v.request_id)||!UUID.test(v.parent_business_run_id)||
      !Number.isSafeInteger(v.expected_composer_revision)||v.expected_composer_revision<0||
      !Number.isSafeInteger(v.wire_bytes)||v.wire_bytes<1||v.wire_bytes>262144||
      !['manifest_sha256','system_sha256','config_sha256','wire_sha256'].every(k=>typeof v[k]==='string'&&SHA.test(v[k])))return false;
  const m=v.manifest;
  const history=Object.hasOwn(m||{},'conversation_history');
  return exact(m,['input_format','workflow','stable_task_id','parent_business_run_id','question','materials','sources',
    ...(history?['conversation_history']:[])])&&
    (!history||validHistory(m.conversation_history,v.expected_scope?.input_revision))&&
    m.input_format===v.input_format&&m.parent_business_run_id===v.parent_business_run_id&&UUID.test(m.stable_task_id)&&
    ['sales','case','contract','court'].includes(m.workflow)&&typeof m.question==='string'&&m.question.trim().length>0&&
    Array.isArray(m.materials)&&(m.materials.length>0||m.workflow==='sales')&&m.materials.length<=20&&
    Array.isArray(m.sources)&&m.sources.length>0&&m.sources.length<=2000&&
    m.materials.every(f=>typeof f.name==='string'&&SHA.test(f.original_sha256)&&Number.isSafeInteger(f.parse_revision)&&f.parse_revision>0&&Array.isArray(f.unread_parts))&&
    m.sources.every(s=>exact(s,['source_id','reference'])&&SHA.test(s.source_id)&&
      (s.reference?.kind==='document'?typeof s.reference.anchor?.quote==='string':s.reference?.kind==='message'&&typeof s.reference.quote==='string'))&&
    Buffer.byteLength(JSON.stringify(v),'utf8')<=400000;
}
module.exports={validMaterialBasis};
