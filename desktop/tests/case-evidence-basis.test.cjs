const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validMaterialBasis}=require('../material-basis.cjs');
const id='11111111-2222-4333-8444-555555555555';
const hash='a'.repeat(64);
function basis(){
  return {request_id:id,expected_scope:{input_revision:1},expected_composer_revision:0,
    parent_business_run_id:id,input_format:'material-business-v1',manifest_sha256:hash,
    system_sha256:hash,config_sha256:hash,wire_sha256:hash,wire_bytes:1000,
    manifest:{input_format:'material-business-v1',workflow:'case',stable_task_id:id,
      parent_business_run_id:id,question:'整理虚构材料时间线',
      materials:[{name:'合成.docx',original_sha256:hash,parse_revision:1,unread_parts:[]}],
      sources:[{source_id:hash,reference:{kind:'document',anchor:{quote:'独立虚构材料'}}}]}};
}
test('case method passes native shape validation and leaves old manifests accepted',()=>{
  const value=basis();assert.equal(validMaterialBasis(value),true);
  value.manifest.case_method={method_id:'case-evidence-v1',method_sha256:hash};
  assert.equal(validMaterialBasis(value),true);
});
for(const method of [null,{}, {method_id:'unknown',method_sha256:hash},
  {method_id:'case-evidence-v1',method_sha256:'A'.repeat(64)},
  {method_id:'case-evidence-v1',method_sha256:hash,approved:true}]){
  test('native rejects malformed case method '+JSON.stringify(method),()=>{
    const value=basis();value.manifest.case_method=method;
    assert.equal(validMaterialBasis(value),false);
  });
}
for(const workflow of ['sales','contract','court']){
  test('case method cannot be used in '+workflow,()=>{
    const value=basis();value.manifest.workflow=workflow;
    value.manifest.case_method={method_id:'case-evidence-v1',method_sha256:hash};
    assert.equal(validMaterialBasis(value),false);
  });
}
