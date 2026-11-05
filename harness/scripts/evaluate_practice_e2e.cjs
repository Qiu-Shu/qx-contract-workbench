// Explicit live-model test. Only synthetic workspaces and a fixed MCP allowlist.
const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process'),readline=require('node:readline'),{createHash}=require('node:crypto');
const {app,safeStorage}=require('electron');
const {createModelCredentialStore}=require('../desktop/model-credentials.cjs');
const {createBudget,upperBound}=require('./skill-eval-budget.cjs');
const {assessFunctional}=require('./practice-e2e-checks.cjs');
const root=path.resolve(__dirname,'..'),run=process.argv[2],selected=process.argv.slice(3);
const campaign=require('./skill-eval-campaign.cjs').evaluationPaths(root);
const thinking=run?.endsWith('-thinking')?'enabled':'disabled';
const verifiedDelivery=process.env.QX_VERIFY_DELIVERY==='1';
if(!/^[a-z0-9-]+$/.test(run||'')||!selected.length||selected.some(s=>!/^[a-z0-9-]+$/.test(s)))throw Error('Explicit run/scenario IDs required');
const data=path.join(process.env.APPDATA,'QunxingHarness/.local/desktop-data');app.setPath('userData',data);
const out=path.join(root,'docs/checks/practice-gaps/e2e',run),modelDir=path.join(root,'docs/checks/skills-quality/model');
const progress=require('./skill-eval-log.cjs').createProgressLog(path.join(out,'progress.jsonl'));
const hash=s=>createHash('sha256').update(s).digest('hex');
let budget;
function relay(id){
 const child=spawn('D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe',['-X','utf8',path.join(root,'bridge/practice_eval_session.py'),run,id],{cwd:root,windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8'},stdio:['pipe','pipe','pipe']});
 const pending=[],buffer=[];let stderr='',ended=false;
 child.stderr.on('data',b=>{stderr=(stderr+b.toString()).slice(-5000);});
 const lines=readline.createInterface({input:child.stdout});
 lines.on('line',line=>{let value;try{value=JSON.parse(line);}catch{return;}const next=pending.shift();if(next)next.resolve(value);else buffer.push(value);});
 function fail(error){ended=true;buffer.length=0;for(const waiter of pending.splice(0))waiter.reject(error);}
 child.on('error',error=>fail(error));
 child.on('close',code=>fail(Error('Synthetic MCP relay ended '+code+': '+stderr)));
 function next(){if(ended)return Promise.reject(Error('Relay ended: '+stderr));if(buffer.length)return Promise.resolve(buffer.shift());return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{fail(Error('Relay timeout; refusing potentially misaligned responses'));child.kill();},90000);pending.push({resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});});}
 return {next,send:async value=>{child.stdin.write(JSON.stringify(value)+'\n');return next();},close:()=>{child.stdin.end();setTimeout(()=>{if(!ended)child.kill();},3000).unref();}};
}
async function evaluate(id,secret){
 const file=path.join(out,id+'.json');if(fs.existsSync(file))throw Error('Existing evaluation output; use another explicit run ID');
 const transport=relay(id),record={id,run,model:'deepseek-flash',thinking,reasoningEffort:thinking==='enabled'?'high':'off',startedAt:new Date().toISOString(),scope:'Actual model tool calls through real MCP, synthetic workspace only',rounds:[]};
 try{
  const ready=await transport.next();if(!ready.ready)throw Error('Relay did not initialize');
  const candidate=campaign.candidateRoot&&path.join(campaign.candidateRoot,ready.scenario.skill);
  const directory=candidate&&fs.existsSync(path.join(candidate,'SKILL.md'))?candidate:path.join(root,'config/skills',ready.scenario.skill);
  const method=path.join(directory,'references/method.md');
  const skill=fs.readFileSync(path.join(directory,'SKILL.md'),'utf8')+(fs.existsSync(method)?'\n'+fs.readFileSync(method,'utf8'):'');
  const system=fs.readFileSync(path.join(root,'config/workspace-AGENTS.md'),'utf8')+'\n本次是合成案件实测，日期2026-11-05。仅使用已提供工具与当前案件，不联网、不提交、不对外发送。工具未执行不能称已执行。不输出思考过程。\n已加载专项方法：\n'+skill;
  record.systemSha256=hash(system);record.scenario=ready.scenario;record.case_id=ready.case_id;record.tools=ready.tools;
  const snapshots=path.join(root,'docs/checks/practice-gaps/inputs');fs.mkdirSync(snapshots,{recursive:true});
  const inputFile=path.join(snapshots,record.systemSha256+'.txt');if(!fs.existsSync(inputFile))fs.writeFileSync(inputFile,system);
  const messages=[{role:'system',content:system},{role:'user',content:ready.scenario.prompt+`\n已建立本次合成案件case_id=${ready.case_id}，已关联材料=${ready.material_path}。请实际读取后完成任务，并使用工具保存或生成文件。无需另建案或询问确认。`}];
  let completed=false;
  for(let round=0;round<10;round++){
   const maxTokens=8192,reservation=budget.reserve(`e2e-${run}:${id}:${round}`,upperBound([...messages,{role:'system',content:JSON.stringify(ready.tools)}],maxTokens));
   let result;
   try{
    const response=await fetch('https://api.deepseek.com/chat/completions',{method:'POST',redirect:'error',headers:{Authorization:'Bearer '+secret,'Content-Type':'application/json'},body:JSON.stringify({model:'deepseek-flash',thinking:{type:thinking},...(thinking==='enabled'?{reasoning_effort:'high'}:{temperature:0}),messages,tools:ready.tools,max_tokens:maxTokens}),signal:AbortSignal.timeout(180000)});
    if(!response.ok)throw Error('DeepSeek HTTP '+response.status);
    result=await response.json();budget.settle(reservation,result.usage);
   }catch(error){budget.settle(reservation,null);throw error;}
   const message=result.choices?.[0]?.message;if(!message)throw Error('No model message');
   const {reasoning_content,...visibleMessage}=message;
   record.rounds.push({round,message:visibleMessage,usage:result.usage,finishReason:result.choices[0].finish_reason});
   let deliveredText=message.content||'';
   if(verifiedDelivery){
    const {deliverProviderResponse}=await import('./verified-delivery-harness.mjs');
    const delivery=await deliverProviderResponse(messages,result,ready.workspace);
    record.rounds.at(-1).delivery=delivery;deliveredText=delivery.text;
   }
   messages.push({role:'assistant',content:deliveredText||null,...(reasoning_content?{reasoning_content}:{}),...(message.tool_calls?{tool_calls:message.tool_calls}:{})});
   if(!message.tool_calls?.length){record.rawResponse=message.content||'';record.response=deliveredText;record.verifiedDelivery=verifiedDelivery;completed=result.choices[0].finish_reason==='stop';break;}
   if(message.tool_calls.length>8)throw Error('Too many tool calls in one round');
   for(const call of message.tool_calls){
    let toolResult;try{toolResult=await transport.send({name:call.function.name,arguments:JSON.parse(call.function.arguments)});}catch(error){toolResult={is_error:true,error:String(error.message)};}
    record.rounds.at(-1).toolResults??=[];record.rounds.at(-1).toolResults.push({callId:call.id,name:call.function.name,arguments:call.function.arguments,result:toolResult});
    messages.push({role:'tool',tool_call_id:call.id,content:JSON.stringify(toolResult)});
   }
  }
  record.actual=await transport.send({op:'finalize'});
  record.status=completed?'completed':'round-limit';
  Object.assign(record,assessFunctional({scenario:ready.scenario,completed,actual:record.actual,rounds:record.rounds}));
 }catch(error){record.status='failed';record.error=String(error.message).replaceAll(secret,'[REDACTED]');}
 finally{transport.close();record.finishedAt=new Date().toISOString();fs.mkdirSync(out,{recursive:true});fs.writeFileSync(file,JSON.stringify(record,null,2)+'\n');}
 progress({id,status:record.status,rounds:record.rounds.length,conservativeCNY:budget.total()});
}
app.whenReady().then(async()=>{
 const lock=campaign.lockFile;let handle;
 try{
  if(verifiedDelivery)await import('./verified-delivery-harness.mjs');
  handle=fs.openSync(lock,'wx');fs.writeFileSync(handle,String(process.pid));budget=createBudget(campaign.budgetFile);
  const credentials=createModelCredentialStore({dataParent:data,safeStorage});let used=false;
  await credentials.withSecret(async secret=>{used=true;for(const id of selected)await evaluate(id,secret);});
  if(!used)throw Error('Saved credential unavailable');
 }catch(error){progress({status:'run-failed',error:error.message});app.exitCode=1;}
 finally{if(handle!==undefined){fs.closeSync(handle);fs.unlinkSync(lock);}app.exit(app.exitCode||0);}
});
