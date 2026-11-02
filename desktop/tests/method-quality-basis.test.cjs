const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validMaterialBasis}=require('../material-basis.cjs');
const id='11111111-2222-4333-8444-555555555555',hash='a'.repeat(64);
function envelope(workflow,question){
  return {request_id:id,expected_scope:{input_revision:1},expected_composer_revision:0,
    parent_business_run_id:id,input_format:'material-business-v1',manifest_sha256:hash,
    system_sha256:hash,config_sha256:hash,wire_sha256:hash,wire_bytes:1000,
    manifest:{input_format:'material-business-v1',workflow,stable_task_id:id,parent_business_run_id:id,question,
      materials:[{attachment_id:id,name:'独立虚构.docx',original_sha256:hash,parse_revision:1,unread_parts:[]}],
      sources:[{source_id:hash,reference:{kind:'document',attachment_id:id,anchor:{quote:'独立虚构材料'}}}]}};
}
const SNAPSHOTS=[
  {field:'case_method',prefix:'case-evidence',workflow:'case',basis:()=>envelope('case','整理虚构材料时间线'),
    build:(method_id,method_sha256)=>({method_id,method_sha256})},
  {field:'contract_review',prefix:'contract-review',workflow:'contract',basis:()=>envelope('contract','审查虚构合同'),
    build:(method_id,method_sha256)=>({method_id,method_sha256,playbook_status:'unavailable',
      method_sources:[{method_id:'nda',method_sha256:hash,source_reference:'https://example.invalid/source',license_notice:'合成出处'}],
      routes:[{attachment_id:id,methods:['nda'],evidence_source_ids:[hash],uncovered:[]}]})},
  {field:'trademark_triage',prefix:'trademark-triage',workflow:'case',basis:()=>envelope('case','请做商标侵权初筛。'),
    build:(method_id,method_sha256)=>({method_id,method_sha256,right_type:'trademark',
      source_reference:'pinned upstream audit',license_notice:'Apache-2.0'})},
];
const OTHER_WORKFLOWS=['sales','case','contract','court'];
for(const s of SNAPSHOTS){
  const versions=s.field==='case_method'?['v1','v2','v3','v4','v5']:
    s.field==='trademark_triage'?['v1','v2','v3','v4','v5','v6']:['v1','v2','v3'];
  const nextVersion=s.field==='case_method'?'v6':s.field==='trademark_triage'?'v7':'v4';
  test(`${s.field}: supported method ids accepted`,()=>{
    for(const version of versions){
      const value=s.basis();value.manifest[s.field]=s.build(`${s.prefix}-${version}`,hash);
      assert.equal(validMaterialBasis(value),true,`${s.prefix}-${version}`);
    }
  });
  test(`${s.field}: unknown and malformed method ids rejected`,()=>{
    for(const method_id of [`${s.prefix}-${nextVersion}`,`${s.prefix}-v0`,`${s.prefix}`,`${s.prefix}-v1-v2`,
      `${s.prefix}-V2`,`${s.prefix}-v2 `,'unknown']){
      const value=s.basis();value.manifest[s.field]=s.build(method_id,hash);
      assert.equal(validMaterialBasis(value),false,method_id);
    }
  });
  test(`${s.field}: supported ids only usable in ${s.workflow}`,()=>{
    for(const workflow of OTHER_WORKFLOWS){
      if(workflow===s.workflow)continue;
      for(const version of versions){
        const value=s.basis();value.manifest.workflow=workflow;
        value.manifest[s.field]=s.build(`${s.prefix}-${version}`,hash);
        assert.equal(validMaterialBasis(value),false,`${s.prefix}-${version} in ${workflow}`);
      }
    }
  });
  test(`${s.field}: foreign method ids rejected in this slot`,()=>{
    for(const other of SNAPSHOTS){
      if(other.field===s.field)continue;
      for(const version of ['v1','v2','v3','v4','v5']){
        const value=s.basis();value.manifest[s.field]=s.build(`${other.prefix}-${version}`,hash);
        assert.equal(validMaterialBasis(value),false,`${other.prefix}-${version} in ${s.field}`);
      }
    }
  });
  test(`${s.field}: null and partial snapshots rejected`,()=>{
    for(const snapshot of [null,{},{method_id:`${s.prefix}-v2`},{method_sha256:hash}]){
      const value=s.basis();value.manifest[s.field]=snapshot;
      assert.equal(validMaterialBasis(value),false,JSON.stringify(snapshot));
    }
  });
  test(`${s.field}: extra fields rejected for supported ids`,()=>{
    for(const version of versions){
      const value=s.basis();
      value.manifest[s.field]={...s.build(`${s.prefix}-${version}`,hash),approved:true};
      assert.equal(validMaterialBasis(value),false,`${s.prefix}-${version}`);
    }
  });
  test(`${s.field}: method hash form enforced for supported ids`,()=>{
    for(const version of versions){
      for(const method_sha256 of ['A'.repeat(64),'a'.repeat(63),'a'.repeat(65),'forged','',`${hash}a`,null,64]){
        const value=s.basis();value.manifest[s.field]=s.build(`${s.prefix}-${version}`,method_sha256);
        assert.equal(validMaterialBasis(value),false,`${s.prefix}-${version} hash ${String(method_sha256).slice(0,8)}`);
      }
    }
  });
  test(`${s.field}: legacy manifest without snapshot still accepted`,()=>{
    const value=s.basis();delete value.manifest[s.field];
    assert.equal(validMaterialBasis(value),true);
  });
}
