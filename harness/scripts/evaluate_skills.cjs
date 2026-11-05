// Explicit developer evaluation only. No application startup hook, no real case reads.
const fs=require('node:fs'),path=require('node:path'),{createHash}=require('node:crypto');
const {createBudget,upperBound}=require('./skill-eval-budget.cjs');
const root=path.resolve(__dirname,'..'),args=process.argv.slice(2),phase=args[0];
const campaign=require('./skill-eval-campaign.cjs').evaluationPaths(root);
const thinking=phase?.endsWith('-thinking')?'enabled':'disabled';
if(!/^(baseline|retest\d*|smoke|final-smoke|repair-[a-z0-9-]+)$/.test(phase||''))throw Error('Invalid evaluation phase');
const {app,safeStorage}=require('electron');
const {createModelCredentialStore}=require('../desktop/model-credentials.cjs');
const data=path.join(process.env.APPDATA,'QunxingHarness/.local/desktop-data');
app.setPath('userData',data);
const out=campaign.reportRoot,runDir=path.join(out,'model',phase);
fs.mkdirSync(runDir,{recursive:true});
const progress=require('./skill-eval-log.cjs').createProgressLog(path.join(runDir,'progress.jsonl'));
let budget;
const hash=s=>createHash('sha256').update(s).digest('hex');
const snapshotRoot=path.join(out,'model/baseline-inputs');
const inputs=new Map();
const lifecycleFile=path.join(root,'config/skill-lifecycle.json');
const lifecycle=fs.existsSync(lifecycleFile)?new Map(JSON.parse(fs.readFileSync(lifecycleFile,'utf8')).skills.map(row=>[row.name,row])):new Map();
function capture(relative){
 const normalized=relative.replaceAll('\\','/');
 const candidatePrefix=campaign.candidateRoot&&path.relative(root,campaign.candidateRoot).replaceAll('\\','/')+'/';
 if(!/^(config\/skills\/|workspace\/\.dsh\/skills\/|workspace\/legal-library\/)/.test(normalized)&&normalized!=='config/workspace-AGENTS.md'&&!(candidatePrefix&&normalized.startsWith(candidatePrefix)))throw Error('Not an evaluation instruction path');
 const resolved=path.resolve(root,relative);if(!resolved.startsWith(root+path.sep))throw Error('Outside project');
 if(inputs.has(normalized))return inputs.get(normalized);
 const content=fs.readFileSync(resolved,'utf8');inputs.set(normalized,content);
 const snapshot=path.join(snapshotRoot,normalized);if(!fs.existsSync(snapshot)){fs.mkdirSync(path.dirname(snapshot),{recursive:true});fs.writeFileSync(snapshot,content);}
 if(phase.startsWith('repair-')){const saved=path.join(root,'docs/checks/skills-repair/inputs',hash(content)+'.txt');fs.mkdirSync(path.dirname(saved),{recursive:true});if(!fs.existsSync(saved))fs.writeFileSync(saved,content);}
 return content;
}
function skillInput(name,seen=new Set()){
 if(!/^[a-z0-9-]+$/.test(name))throw Error('Invalid skill name');
 if(seen.has(name)||seen.size>3)throw Error('Cyclic or oversized Skill route');seen.add(name);
 const candidate=campaign.candidateRoot&&path.join(campaign.candidateRoot,name);
 const base=candidate&&fs.existsSync(path.join(candidate,'SKILL.md'))?path.relative(root,candidate).replaceAll('\\','/'):fs.existsSync(path.join(root,'config/skills',name,'SKILL.md'))?'config/skills/'+name:'workspace/.dsh/skills/'+name;
 let text=capture(base+'/SKILL.md');
 if(phase.startsWith('repair-')&&/^disable-model-invocation:\s*true\s*$/m.test(text))throw Error('Disabled Skill must be tested at the runtime boundary, not sent to a paid model: '+name);
 if(fs.existsSync(path.join(root,base,'references/method.md')))text+='\n\n'+capture(base+'/references/method.md');
 for(const resource of ['practice-context.md','source-verification.md'])if(text.includes(resource)&&fs.existsSync(path.join(root,'workspace/legal-library/workbench',resource)))text+='\n\n'+capture('workspace/legal-library/workbench/'+resource);
 const route=lifecycle.get(name);
 if(phase.startsWith('repair-')&&route&&['merge','replace'].includes(route.action)&&typeof route.replacement==='string'&&/^[a-z0-9-]+$/.test(route.replacement)){
  text+='\n\n所路由工作台技能：\n'+skillInput(route.replacement,seen);
 }
 return text;
}
const system=capture('config/workspace-AGENTS.md')+(phase.startsWith('repair-')?'\n\n当前评测参考日期：2026-11-05，时区Asia/Shanghai。用户材料另有明确基准日时按材料，不能自行从无关事件日期推定起算日。':'')+'\n\n本次是隔离的 Skill 行为评测，只使用用户给出的虚构材料。当前没有可执行工具，不联网、不读其他文件、不写入、不发送；不要声称工具已执行或资料已核验。请直接给可完成的业务结果，无法完成的步骤明确说明。不要输出推理过程。';
const cases=args.slice(1).flatMap(file=>JSON.parse(fs.readFileSync(path.resolve(root,file),'utf8'))).filter(c=>phase.endsWith('smoke')?c.kind==='smoke':c.kind!=='smoke');
const unique=new Set();for(const c of cases){
 if(!/^[a-zA-Z0-9_-]+$/.test(c.id)||unique.has(c.id))throw Error('Invalid or duplicate scenario id');unique.add(c.id);
 if(c.controlNoSkill&&!campaign.campaign)throw Error('No-Skill control requires isolated campaign');
 c._skillText=c.controlNoSkill?'本轮未加载专项Skill。':skillInput(c.skill);
 if(c.references){
  if(!Array.isArray(c.references)||c.references.length>3)throw Error('Invalid scenario references');
  for(const reference of c.references){
   if(typeof reference!=='string'||!reference.startsWith('config/skills/'+c.skill+'/references/')||reference.includes('..'))throw Error('Reference must belong to this Skill');
   if(!c.controlNoSkill){const candidate=campaign.candidateRoot&&path.join(campaign.candidateRoot,c.skill,'references',path.basename(reference));c._skillText+='\n\n'+capture(candidate&&fs.existsSync(candidate)?path.relative(root,candidate):reference);}
  }
 }
}
async function evaluate(c,secret){
 const file=path.join(runDir,c.id+'.json');if(fs.existsSync(file))return;
 const maxTokens=campaign.campaign&&phase.endsWith('-extended-thinking')?24576:phase.endsWith('-long-thinking')?16384:thinking==='enabled'?8192:phase.startsWith('repair-')?2600:phase==='final-smoke'?1800:c.kind==='smoke'?850:phase.startsWith('retest')?3200:1600;
 const compact=phase==='final-smoke'?'\n本次只交付不超过450个汉字的关键结果或文稿节选，无需展开完整报告；保留最重要事实、条件和不确定性。':'';
 const messages=[{role:'system',content:system},{role:'user',content:'本轮已加载的技能说明如下：\n<skill>\n'+c._skillText+'\n</skill>\n\n本轮用户任务：\n'+c.prompt+compact}];
 const reservation=budget.reserve(phase+':'+c.id,upperBound(messages,maxTokens));
 const record={id:c.id,skill:c.skill,controlNoSkill:!!c.controlNoSkill,kind:c.kind,phase,model:'deepseek-flash',thinking,reasoningEffort:thinking==='enabled'?'high':'off',prompt:c.prompt+compact,expected:c.expected,systemSha256:hash(system),skillSha256:hash(c._skillText),maxTokens,startedAt:new Date().toISOString(),scope:'Live model instruction evaluation with synthetic inputs; tools deliberately unavailable, not full workbench end-to-end verification'};
 if(phase.startsWith('repair-')){const dir=path.join(root,'docs/checks/skills-repair/inputs');for(const body of [system,c._skillText]){const file=path.join(dir,hash(body)+'.txt');if(!fs.existsSync(file))fs.writeFileSync(file,body);}}
 try{
  const response=await fetch('https://api.deepseek.com/chat/completions',{method:'POST',redirect:'error',headers:{Authorization:'Bearer '+secret,'Content-Type':'application/json'},body:JSON.stringify({model:'deepseek-flash',thinking:{type:thinking},...(thinking==='enabled'?{reasoning_effort:'high'}:{temperature:0}),messages,max_tokens:maxTokens}),signal:AbortSignal.timeout(180000)});
  if(!response.ok)throw Error('DeepSeek HTTP '+response.status);
  const result=await response.json();record.response=result.choices?.[0]?.message?.content??'';record.finishReason=result.choices?.[0]?.finish_reason;record.usage=result.usage;record.responseModel=result.model;record.responseId=result.id;
  record.status=record.response&&record.finishReason==='stop'?'response-received':'incomplete';budget.settle(reservation,result.usage);
 }catch(error){record.status='request-failed';record.error=String(error.message).replaceAll(secret,'[REDACTED]');budget.settle(reservation,null);}
 record.finishedAt=new Date().toISOString();fs.writeFileSync(file,JSON.stringify(record,null,2)+'\n');progress({id:c.id,status:record.status,conservativeCNY:+budget.total().toFixed(5)});
}
app.whenReady().then(async()=>{
 const lock=campaign.lockFile;let handle;
 try{
  handle=fs.openSync(lock,'wx');fs.writeFileSync(handle,String(process.pid));
  budget=createBudget(campaign.budgetFile);
  const store=createModelCredentialStore({dataParent:data,safeStorage});let invoked=false;
  let evaluationError;
  const result=await store.withSecret(async secret=>{invoked=true;let next=0;const workers=await Promise.allSettled(Array.from({length:phase.endsWith('-long-thinking')&&!campaign.campaign?1:3},async()=>{while(next<cases.length){const c=cases[next++];await evaluate(c,secret);}}));evaluationError=workers.find(r=>r.status==='rejected')?.reason;});
  if(!invoked)throw Error('Saved credential unavailable: '+result.status);
  if(evaluationError)throw evaluationError;
  progress({phase,status:'run-completed',cases:cases.length,budgetConservativeCNY:budget.total(),cap:20});
 }catch(error){progress({status:'run-failed',error:String(error.message)});app.exitCode=1;}
 finally{if(handle!==undefined){fs.closeSync(handle);fs.unlinkSync(lock);}app.exit(app.exitCode||0);}
});
