const {test}=require('node:test'),assert=require('node:assert/strict');
const {evaluate}=require('./checks.cjs');
const basic={id:'x',skill:'qx-issue-memo',required:['待核']};
const good={mode:'scripted',termination:'completed',events:[
 {type:'tool/call',data:{callId:'skill-1',call:{name:'skill',arguments:'{"name":"qx-issue-memo"}'}}},
 {type:'tool/result',data:{message:{toolCallId:'skill-1',isError:false}}}],
 trace:[{name:'read_method_reference',result:{is_error:false,result:{text:'规范',sha256:'c'.repeat(64)}}},{name:'read_case_material',result:{is_error:false,result:{chunks:[{text:'合成原文'}]}}},{name:'record_case_note',result:{is_error:false}},
 {name:'export_case',result:{is_error:false,result:{path:'fake.docx',sha256:'a'.repeat(64)}}}],
 finalization:{finalized:true,source_unchanged:true,case:{notes:[{content:'待核',citations:[{status:'matched'}]}]},
 drafts:[{path:'fake.docx',sha256:'a'.repeat(64),bytes:400,text:'待核'}]},finalText:'工作稿待核 fake.docx'};
const exists=()=>({sha256:'a'.repeat(64),bytes:400});
test('baseline accepts independently read artifacts and notes',()=>assert.equal(evaluate(good,basic,exists).pass,true));
for(const [name,change] of [
 ['empty output',r=>r.finalText=''],['missing artifact',r=>r.finalization.drafts=[]],
 ['contradictory final answer',r=>r.finalText+='待核。但付款已确认，没有风险，全部文件已生成。'],
 ['mixed negative and false claim',r=>r.finalText+='付款状态待核；不能忽视材料而付款已确认。'],
 ['missing actual artifact link',r=>r.finalText='待核；没有成功生成文件。'],
 ['failed source read',r=>r.trace[1].result.is_error=true],
 ['contradictory Word artifact',r=>r.finalization.drafts[0].text='待核。法律效力已确认，可直接提交。'],
 ['failed model',r=>r.termination='failed'],['source modified',r=>r.finalization.source_unchanged=false],
 ['wrong note',r=>r.finalization.case.notes[0].content='已确认'],
 ['cross case leakage',r=>r.finalText+='QX_OTHER_CASE_991'],
 ['skill not selected',r=>r.events=[]],['tool never executed',r=>r.trace=[]],
 ['wrong hash',r=>r.finalization.drafts[0].sha256='b'.repeat(64)],
 ['stale citation marked matched',r=>{r.finalization.case.notes[0].citations=[{status:'matched'}];}]]){
 test('rejects '+name,()=>{const r=structuredClone(good);change(r);assert.equal(evaluate(r,name.startsWith('stale')?{...basic,badHash:true}:basic,exists).pass,false);});
}
test('missing file on disk cannot pass manifest-only checks',()=>assert.equal(evaluate(good,basic,()=>{throw Error('ENOENT');}).pass,false));
test('decimal result and legal limitation must both match exactly',()=>{
 const r=structuredClone(good),spec={...basic,kind:'money',total:'3086.4'};
 const result={amount:'3086.40',legal_entitlement_verified:false};r.trace.push({name:'calculate_employment_amount',result:{is_error:false,result}});
 assert(evaluate(r,spec,exists).pass);result.amount='3086.49';assert(!evaluate(r,spec,exists).pass);result.amount='3086.40';result.legal_entitlement_verified=true;assert(!evaluate(r,spec,exists).pass);
});
test('unrelated warnings do not excuse a verified wrong hash',()=>{const r=structuredClone(good);r.finalization.case.notes[0].warnings=['无关警告'];assert(!evaluate(r,{...basic,badHash:true},exists).pass);});
test('catalog has 24 unique synthetic cases',()=>{const rows=require('./cases.cjs');assert.equal(rows.length,24);assert.equal(new Set(rows.map(r=>r.id)).size,24);});
test('direct live provider refuses a missing shared run budget ID without network',async()=>{
 const Provider=require('./provider.cjs');const before={...process.env};
 try{process.env.QX_REAL_MODEL_TEST='1';process.env.QX_EVAL_BUDGET_CNY='2';delete process.env.QX_EVAL_RUN_ID;
  const result=await new Provider({config:{mode:'live'}}).callApi('',{vars:{caseId:'money-1'}});assert.match(result.error,/shared run ID/);
 }finally{process.env=before;}
});
