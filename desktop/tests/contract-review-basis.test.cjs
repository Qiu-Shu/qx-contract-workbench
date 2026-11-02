const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validMaterialBasis}=require('../material-basis.cjs');
const id='11111111-2222-4333-8444-555555555555',hash='a'.repeat(64);
function basis(){
  return {request_id:id,expected_scope:{input_revision:1},expected_composer_revision:0,
    parent_business_run_id:id,input_format:'material-business-v1',manifest_sha256:hash,
    system_sha256:hash,config_sha256:hash,wire_sha256:hash,wire_bytes:1000,
    manifest:{input_format:'material-business-v1',workflow:'contract',stable_task_id:id,
      parent_business_run_id:id,question:'审查虚构合同',
      materials:[{attachment_id:id,name:'合成.docx',original_sha256:hash,parse_revision:1,unread_parts:[]}],
      sources:[{source_id:hash,reference:{kind:'document',attachment_id:id,anchor:{quote:'独立虚构材料'}}}],
      contract_review:{method_id:'contract-review-v1',method_sha256:hash,playbook_status:'unavailable',
        method_sources:[{method_id:'nda',method_sha256:hash,source_reference:'https://example.invalid/source',license_notice:'合成出处'}],
        routes:[{attachment_id:id,methods:['nda'],evidence_source_ids:[hash],uncovered:[]}]}}};
}
test('new contract snapshot and old manifest both pass shape validation',()=>{
  const value=basis();assert.equal(validMaterialBasis(value),true);
  delete value.manifest.contract_review;assert.equal(validMaterialBasis(value),true);
});
test('unread attachment is retained with no impossible analysis method',()=>{
  const value=basis(),emptyId='22222222-2222-4333-8444-555555555555';
  value.manifest.materials.push({...value.manifest.materials[0],attachment_id:emptyId,name:'扫描附件.pdf'});
  value.manifest.contract_review.routes.push({attachment_id:emptyId,methods:[],evidence_source_ids:[],uncovered:[]});
  assert.equal(validMaterialBasis(value),true);
});
for(const [label,mutate] of [
  ['null',v=>v.manifest.contract_review=null],
  ['wrong workflow',v=>v.manifest.workflow='case'],
  ['unknown method',v=>v.manifest.contract_review.routes[0].methods=['external-script']],
  ['duplicate route',v=>v.manifest.contract_review.routes.push(v.manifest.contract_review.routes[0])],
  ['missing route',v=>v.manifest.contract_review.routes=[]],
  ['wrong material',v=>v.manifest.contract_review.routes[0].attachment_id='22222222-2222-4333-8444-555555555555'],
  ['unknown source',v=>v.manifest.contract_review.routes[0].evidence_source_ids=['b'.repeat(64)]],
  ['bad digest',v=>v.manifest.contract_review.method_sha256='A'.repeat(64)],
  ['approval',v=>v.manifest.contract_review.playbook_status='approved'],
  ['extra permission',v=>v.manifest.contract_review.approved=true],
  ['missing method source',v=>v.manifest.contract_review.method_sources=[]],
  ['unknown coverage',v=>v.manifest.contract_review.routes[0].uncovered=['court']],
  ['case conflict',v=>v.manifest.case_method={method_id:'case-evidence-v1',method_sha256:hash}],
]){
  test('reject contract snapshot: '+label,()=>{const value=basis();mutate(value);assert.equal(Boolean(validMaterialBasis(value)),false);});
}
test('contract review v2 and v3 snapshots pass with unchanged fields',()=>{
  const value=basis();
  for(const method_id of ['contract-review-v2','contract-review-v3']){
    value.manifest.contract_review.method_id=method_id;
    assert.equal(validMaterialBasis(value),true);
  }
});
test('reject contract snapshot: unknown contract review version',()=>{
  const value=basis();
  value.manifest.contract_review.method_id='contract-review-v4';
  assert.equal(Boolean(validMaterialBasis(value)),false);
});
