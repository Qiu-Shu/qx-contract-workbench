const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {createBudget,upperBound,usageCost}=require('./skill-eval-budget.cjs');
test('reserves in-flight and unknown requests across restarts and stops below cap',t=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'qx-budget-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'budget.json'),budget=createBudget(file);const first=budget.reserve('a',10);budget.reserve('b',9);
 assert.throws(()=>budget.reserve('c',1),/protection/);budget.settle(first,{prompt_tokens:1000,completion_tokens:500});
 const restarted=createBudget(file);assert.equal(restarted.total(),9.006);assert.throws(()=>restarted.reserve('b',1),/Duplicate/);
 assert.equal(usageCost({prompt_tokens:-1,completion_tokens:3}),null);assert.ok(upperBound([{role:'user',content:'虚构案例'}],1000)>0.008);
 assert.throws(()=>createBudget(file,30),/authorized/);
});
