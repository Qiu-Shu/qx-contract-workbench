const path=require('node:path');
function evaluationPaths(root,env=process.env){
 const campaign=env.QX_SKILL_EVAL_CAMPAIGN;
 if(campaign&&campaign!=='skill-resume-20261105')throw Error('Unknown authorized campaign');
 const snapshot=env.QX_SKILL_EVAL_SNAPSHOT;
 if(snapshot&&(!campaign||!['v2','v4','v5','v6'].includes(snapshot)))throw Error('Unknown evaluation snapshot');
 const modelRoot=path.join(root,'docs/checks/skills-quality/model');
 const reportRoot=path.join(root,'docs/checks',campaign||'skills-quality');
 return {campaign,reportRoot,lockFile:path.join(modelRoot,'run.lock'),
  budgetFile:campaign?path.join(reportRoot,'budget.json'):path.join(modelRoot,'budget.json'),
  candidateRoot:campaign?path.join(root,'.local',campaign,snapshot?'candidate-'+snapshot:'candidate-skills'):null};
}
module.exports={evaluationPaths};
