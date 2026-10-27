const SHA=/^[0-9a-f]{64}$/,UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const fields=['request_id','expected_scope','expected_composer_revision','parent_business_run_id','input_format','manifest','manifest_sha256','system_sha256','config_sha256','wire_sha256','wire_bytes'];
function validMaterialBasis(v){
  if(!exact(v,fields)||v.input_format!=='material-business-v1'||!UUID.test(v.request_id)||!UUID.test(v.parent_business_run_id)||
      !Number.isSafeInteger(v.expected_composer_revision)||v.expected_composer_revision<0||
      !Number.isSafeInteger(v.wire_bytes)||v.wire_bytes<1||v.wire_bytes>262144||
      !['manifest_sha256','system_sha256','config_sha256','wire_sha256'].every(k=>typeof v[k]==='string'&&SHA.test(v[k])))return false;
  const m=v.manifest;
  return exact(m,['input_format','workflow','stable_task_id','parent_business_run_id','question','materials','sources'])&&
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
