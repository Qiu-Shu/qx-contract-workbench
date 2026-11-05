const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {evaluationPaths}=require('./skill-eval-campaign.cjs');
test('new authorized campaign isolates budget and withheld candidates without changing production discovery',()=>{
 const root=path.resolve(__dirname,'..'),legacy=evaluationPaths(root,{}),next=evaluationPaths(root,{QX_SKILL_EVAL_CAMPAIGN:'skill-resume-20261105'});
 assert.equal(legacy.budgetFile,path.join(root,'docs/checks/skills-quality/model/budget.json'));
 assert.notEqual(next.budgetFile,legacy.budgetFile);
 assert.equal(next.lockFile,legacy.lockFile);
 assert.equal(next.candidateRoot,path.join(root,'.local/skill-resume-20261105/candidate-skills'));
 assert.equal(next.reportRoot,path.join(root,'docs/checks/skill-resume-20261105'));
 assert.equal(evaluationPaths(root,{QX_SKILL_EVAL_CAMPAIGN:'skill-resume-20261105',QX_SKILL_EVAL_SNAPSHOT:'v2'}).candidateRoot,path.join(root,'.local/skill-resume-20261105/candidate-v2'));
 assert.throws(()=>evaluationPaths(root,{QX_SKILL_EVAL_SNAPSHOT:'../../other'}),/snapshot/);
 for(const name of ['../other','unknown','skill-resume-20261105/../escape'])assert.throws(()=>evaluationPaths(root,{QX_SKILL_EVAL_CAMPAIGN:name}),/authorized campaign/);
});
test('program-repair candidate uses the existing authorized ledger and rejects arbitrary snapshots',()=>{
 const root=path.resolve(__dirname,'..'),env={QX_SKILL_EVAL_CAMPAIGN:'skill-resume-20261105'};
 const next=evaluationPaths(root,{...env,QX_SKILL_EVAL_SNAPSHOT:'v4'});
 assert.equal(next.budgetFile,evaluationPaths(root,env).budgetFile);
 assert.equal(next.candidateRoot,path.join(root,'.local/skill-resume-20261105/candidate-v4'));
 const v5=evaluationPaths(root,{...env,QX_SKILL_EVAL_SNAPSHOT:'v5'});
 assert.equal(v5.budgetFile,next.budgetFile);assert.equal(v5.lockFile,next.lockFile);
 assert.equal(v5.candidateRoot,path.join(root,'.local/skill-resume-20261105/candidate-v5'));
 assert.equal(evaluationPaths(root,{...env,QX_SKILL_EVAL_SNAPSHOT:'v6'}).budgetFile,next.budgetFile);
 for(const snapshot of ['v7','../candidate-v4','v4/../../x'])assert.throws(()=>evaluationPaths(root,{...env,QX_SKILL_EVAL_SNAPSHOT:snapshot}),/snapshot/);
 assert.throws(()=>evaluationPaths(root,{QX_SKILL_EVAL_SNAPSHOT:'v4'}),/snapshot/);
});
