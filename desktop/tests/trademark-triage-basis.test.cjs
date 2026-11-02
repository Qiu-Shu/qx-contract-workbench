const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validMaterialBasis}=require('../material-basis.cjs');
const id='11111111-2222-4333-8444-555555555555',hash='a'.repeat(64);
function basis(){return {request_id:id,expected_scope:{input_revision:1},expected_composer_revision:0,
  parent_business_run_id:id,input_format:'material-business-v1',manifest_sha256:hash,
  system_sha256:hash,config_sha256:hash,wire_sha256:hash,wire_bytes:1000,
  manifest:{input_format:'material-business-v1',workflow:'case',stable_task_id:id,
    parent_business_run_id:id,question:'请做商标侵权初筛。',
    materials:[{name:'独立虚构.docx',original_sha256:hash,parse_revision:1,unread_parts:[]}],
    sources:[{source_id:hash,reference:{kind:'message',quote:'请做商标侵权初筛。'}}],
    trademark_triage:{method_id:'trademark-triage-v1',method_sha256:hash,right_type:'trademark',
      source_reference:'pinned upstream audit',license_notice:'Apache-2.0'}}};}
test('native accepts trademark factor basis and legacy omission',()=>{
  const v=basis();assert.equal(validMaterialBasis(v),true);
  delete v.manifest.trademark_triage;assert.equal(validMaterialBasis(v),true);
});
for(const version of ['trademark-triage-v2','trademark-triage-v3','trademark-triage-v4','trademark-triage-v5','trademark-triage-v6']){
  test('native accepts explicitly supported trademark revision '+version,()=>{
    const v=basis();v.manifest.trademark_triage.method_id=version;
    assert.equal(validMaterialBasis(v),true);
  });
}
for(const damage of ['workflow','case_method','criminal','version','right_type','approval','hash','notice']){
  test('native rejects trademark basis '+damage,()=>{
    const v=basis(),m=v.manifest,c=m.trademark_triage;
    if(damage==='workflow')m.workflow='court';
    if(damage==='case_method')m.case_method={method_id:'case-evidence-v1',method_sha256:hash};
    if(damage==='criminal')m.criminal_analysis={method_id:'criminal-analysis-v1',method_sha256:hash,
      stage:'unknown',stage_source_id:null,material_policy:'synthetic-only-v1',method_sources:[{
        method_id:'case_analysis',method_sha256:hash,source_reference:'pinned',license_notice:'Apache-2.0'}]};
    if(damage==='version')c.method_id='trademark-triage-v99';
    if(damage==='right_type')c.right_type='patent';
    if(damage==='approval')c.approved=true;
    if(damage==='hash')c.method_sha256='forged';
    if(damage==='notice')c.license_notice='';
    assert.equal(validMaterialBasis(v),false);
  });
}
