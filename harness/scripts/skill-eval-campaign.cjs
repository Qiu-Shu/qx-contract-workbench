const path=require('node:path');
function evaluationPaths(root,env=process.env){
 const campaign=env.QX_SKILL_EVAL_CAMPAIGN;
 if(campaign&&!['skill-resume-20261105','employment-live-20261116'].includes(campaign))throw Error('Unknown authorized campaign');
 const snapshot=env.QX_SKILL_EVAL_SNAPSHOT;
 if(snapshot&&(campaign!=='skill-resume-20261105'||!['v2','v4','v5','v6'].includes(snapshot)))throw Error('Unknown evaluation snapshot');
 const modelRoot=path.join(root,'docs/checks/skills-quality/model');
 const reportRoot=path.join(root,'docs/checks',campaign||'skills-quality');
 if(campaign==='employment-live-20261116')return {campaign,reportRoot,lockFile:path.join(modelRoot,'run.lock'),
  budgetFile:path.join(reportRoot,'budget.json'),candidateRoot:path.join(root,'evals/candidates'),
  cap:10,model:'deepseek-flash',thinking:'enabled',maxTokens:8192,referenceDate:'2026-11-16',allowedSkills:['qx-employment-review']};
 return {campaign,reportRoot,lockFile:path.join(modelRoot,'run.lock'),
  budgetFile:campaign?path.join(reportRoot,'budget.json'):path.join(modelRoot,'budget.json'),
  candidateRoot:campaign?path.join(root,'.local',campaign,snapshot?'candidate-'+snapshot:'candidate-skills'):null};
}
function evaluationMaxTokens(campaign,phase,thinking,kind){
 // Explicit diagnostic phases may reserve a larger output; ordinary runs keep
 // their campaign cap. The same ledger still reserves the entire upper bound.
 if(campaign.campaign&&phase.endsWith('-extended-thinking'))return 24576;
 if(phase.endsWith('-long-thinking'))return 16384;
 return campaign.maxTokens||(thinking==='enabled'?8192:phase.startsWith('repair-')?2600:phase==='final-smoke'?1800:kind==='smoke'?850:phase.startsWith('retest')?3200:1600);
}
module.exports={evaluationPaths,evaluationMaxTokens};
