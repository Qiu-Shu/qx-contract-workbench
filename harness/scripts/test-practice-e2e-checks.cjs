const {test}=require('node:test'),assert=require('node:assert/strict');
function assessFunctional(value){assert.ok(require('node:fs').existsSync(require('node:path').join(__dirname,'practice-e2e-checks.cjs')),'Missing actual-output evaluator');return require('./practice-e2e-checks.cjs').assessFunctional(value);}
function fixture(){return {scenario:{required_tools:['read_case_material','write_word_draft'],expected_kind:'corporate_record'},completed:true,
 actual:{finalized:true,source_unchanged:true,notes_complete:true,case:{notes:[{kind:'corporate_record',content:'实质记录'}]},drafts:[{path:'isolated/draft.docx',text:'实际正文',sha256:'abc'}]},
 rounds:[{toolResults:[{name:'read_case_material',result:{executed:true,is_error:false,result:{chunks:[{text:'实际材料'}]}}},{name:'write_word_draft',result:{executed:true,is_error:false,result:{path:'isolated/draft.docx',sha256:'abc'}}}]}]};}
test('real successful tool output must correspond to inspected Word',()=>{const f=fixture();assert.equal(assessFunctional(f).functionalPassed,true);f.actual.drafts[0].path='isolated/unrelated.docx';assert.equal(assessFunctional(f).functionalPassed,false);});
test('empty files, changed hashes, unexecuted calls and changed sources fail',()=>{for(const mutate of [f=>f.actual.drafts[0].text='',f=>f.actual.drafts[0].sha256='changed',f=>f.rounds[0].toolResults[0].result.executed=false,f=>f.actual.source_unchanged=false,f=>f.actual.notes_complete=false]){const f=fixture();mutate(f);assert.equal(assessFunctional(f).functionalPassed,false);}});
test('functional completion never certifies semantic quality',()=>{const result=assessFunctional(fixture());assert.equal(result.qualityStatus,'not_reviewed');assert.equal(result.qualityPassed,null);});
test('failed save flags and truncated note observations cannot pass',()=>{const f=fixture();f.scenario.required_tools.push('save_evidence_analysis');f.rounds[0].toolResults.push({name:'save_evidence_analysis',result:{executed:true,is_error:false,result:{saved:false}}});assert.equal(assessFunctional(f).functionalPassed,false);});
test('generic case notes accept legitimate alternative kinds only with matching persisted id',()=>{const f=fixture();f.actual.case.notes=[{id:'actual-note',kind:'corporate_record_draft',content:'会议记录正文'}];f.rounds[0].toolResults.push({name:'record_case_note',result:{executed:true,is_error:false,result:{id:'actual-note'}}});assert.equal(assessFunctional(f).functionalPassed,true);f.actual.case.notes[0].id='unrelated-note';assert.equal(assessFunctional(f).functionalPassed,false);});
test('a rejected correction is not a successful required save even when an older note exists',()=>{
 const f=fixture();f.scenario.required_tools.push('assess_employment_termination');
 f.rounds[0].toolResults.push({name:'assess_employment_termination',result:{executed:true,is_error:false,result:{recorded:false,reason:'supersedes conflict'}}});
 assert.equal(assessFunctional(f).functionalPassed,false);
});
