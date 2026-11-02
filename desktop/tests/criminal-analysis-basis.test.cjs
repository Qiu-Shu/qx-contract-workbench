const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validMaterialBasis}=require('../material-basis.cjs');
const id='11111111-2222-4333-8444-555555555555',hash='a'.repeat(64);
function basis(){return {request_id:id,expected_scope:{input_revision:1},expected_composer_revision:0,
  parent_business_run_id:id,input_format:'material-business-v1',manifest_sha256:hash,
  system_sha256:hash,config_sha256:hash,wire_sha256:hash,wire_bytes:1000,
  manifest:{input_format:'material-business-v1',workflow:'case',stable_task_id:id,
    parent_business_run_id:id,question:'刑事案件分析。当前阶段：审查起诉',
    materials:[{name:'合成.docx',original_sha256:hash,parse_revision:1,unread_parts:[]}],
    sources:[{source_id:hash,reference:{kind:'message',quote:'刑事案件分析。当前阶段：审查起诉'}}],
    criminal_analysis:{method_id:'criminal-analysis-v1',method_sha256:hash,stage:'prosecution',stage_source_id:hash,
      material_policy:'synthetic-only-v1',method_sources:['case_analysis','defense_strategy'].map(method_id=>({
        method_id,method_sha256:hash,source_reference:'upstream audit',license_notice:'Apache-2.0'}))}}};}
test('native accepts criminal candidate basis and old field omission',()=>{
  const v=basis();assert.equal(validMaterialBasis(v),true);
  v.manifest.criminal_analysis.stage='unknown';v.manifest.criminal_analysis.stage_source_id=null;
  assert.equal(validMaterialBasis(v),true);
  v.manifest.criminal_analysis.method_sources.pop();
  assert.equal(validMaterialBasis(v),true);
  delete v.manifest.criminal_analysis;assert.equal(validMaterialBasis(v),true);
});
for(const damage of ['workflow','legacy_method','unknown_version','policy','approval','stage','stage_source','source_kind','duplicate_method']){
  test('native rejects criminal basis '+damage,()=>{
    const v=basis(),m=v.manifest,c=m.criminal_analysis;
    if(damage==='workflow')m.workflow='court';
    if(damage==='legacy_method')m.case_method={method_id:'case-evidence-v1',method_sha256:hash};
    if(damage==='unknown_version')c.method_id='criminal-analysis-v2';
    if(damage==='policy')c.material_policy='approved';
    if(damage==='approval')c.approved=true;
    if(damage==='stage')c.stage='convicted';
    if(damage==='stage_source')c.stage_source_id='b'.repeat(64);
    if(damage==='source_kind')m.sources[0].reference={kind:'document',anchor:{quote:'阶段说明'}};
    if(damage==='duplicate_method')c.method_sources[1]=c.method_sources[0];
    assert.equal(validMaterialBasis(v),false);
  });
}
