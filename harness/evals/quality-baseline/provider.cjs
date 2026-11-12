const fs=require('node:fs'),path=require('node:path'),{spawn}=require('node:child_process');
const {createInterface}=require('node:readline'),{randomUUID}=require('node:crypto');
const root=path.resolve(__dirname,'../..');
const cases=require('./cases.cjs');
function relay(spec,workspace){
 const child=spawn(process.env.QX_TEST_PYTHON||(process.platform==='win32'?'python':'python3'),[path.join(__dirname,'relay.py')],
  {cwd:root,windowsHide:true,env:{...process.env,PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1',
   DEEPSEEK_API_KEY:'',OPENAI_API_KEY:'',ANTHROPIC_API_KEY:'',QX_HINDSIGHT_URL:'',QX_HINDSIGHT_TOKEN:''},stdio:['pipe','pipe','pipe']});
 const lines=createInterface({input:child.stdout}),queue=[],waiting=[];let failure,stderr='';
 const exited=new Promise(resolve=>child.once('exit',resolve));
 child.stderr.on('data',x=>stderr=(stderr+x).slice(-3000));
 function fail(error){failure=error;for(const w of waiting.splice(0))w.reject(error);}
 child.on('error',fail);child.on('exit',code=>{if(waiting.length)fail(Error(`MCP relay exited ${code}: ${stderr}`));});
 lines.on('line',line=>{try{const value=JSON.parse(line);const next=waiting.shift();if(next)next.resolve(value);else queue.push(value);}catch{fail(Error('MCP relay returned invalid JSON'));}});
 function next(){if(queue.length)return Promise.resolve(queue.shift());if(failure)return Promise.reject(failure);
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{child.kill();reject(Error('MCP relay timeout'));},90000);waiting.push({resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});});}
 const send=value=>child.stdin.write(JSON.stringify(value)+'\n');
 send({...spec,workspace});
 return {ready:next(),async call(name,args){send({name,arguments:args});return next();},async finalize(){send({op:'finalize'});return next();},async close(){child.stdin.end();let timer;try{await Promise.race([exited,new Promise(resolve=>{timer=setTimeout(()=>{child.kill();resolve();},5000);})]);}finally{clearTimeout(timer);lines.close();}}};
}
function scripted(spec,ready){
 let cursor=0;
 const actions=[['skill',()=>({name:spec.skill})],['read_method_reference',()=>({})],['read_case_material',()=>({case_id:ready.case_id,path:'合成材料.txt'})]];
 if(spec.kind==='scope')actions.push(['read_case_material',()=>({case_id:ready.case_id,path:'他案材料.txt'})]);
 if(spec.kind==='money')actions.push(['calculate_employment_amount',()=>({base:spec.base,years:spec.years,multiplier:'1',assumptions:'仅合成情景算术，法律适用待核'})]);
 if(spec.kind==='date')actions.push(['calculate_calendar_date',()=>({base_date:spec.date,offset_days:spec.days,rule_source:'合成用户指定的自然日偏移；法律规则待核'})]);
 if(!spec.noDraft){
  actions.push(['record_case_note',()=>({case_id:ready.case_id,kind:spec.kind==='research'?'legal_research_'+spec.skill.slice(3).replaceAll('-','_'):'internal_note',
   content:spec.note,source:'完全虚构的离线评测材料',citations:spec.kind==='unavailable'?[]:[{path:'合成材料.txt',quote:spec.material.split('\n')[0],sha256:spec.badHash?'0'.repeat(64):ready.source_sha256}],request_id:spec.id})]);
  if(spec.kind==='retry')actions.push(actions.at(-1));
  if(['retry','reopen'].includes(spec.kind))actions.push(['read_case_note',trace=>({case_id:ready.case_id,note_id:(trace.find(t=>t.name.endsWith('record_case_note')).result.result.note||trace.find(t=>t.name.endsWith('record_case_note')).result.result).id})]);
  if(spec.kind==='partial')actions.push(['export_case',()=>({case_id:ready.case_id,audience:'client',filename:'客户稿.docx'})]);
  actions.push(['export_case',()=>({case_id:ready.case_id,audience:'internal',filename:'评测工作稿.docx'})]);
 }
 return async(_request,trace)=>{
  if(cursor<actions.length){const [name,args]=actions[cursor++];return {blocks:[{type:'tool-call',id:'eval-'+cursor,name:['skill','read_method_reference'].includes(name)?name:'mcp__qx_legal__'+name,arguments:JSON.stringify(args(trace))}]};}
  if(spec.noDraft)throw Error('Synthetic interruption before export');
  const artifact=trace.findLast(t=>t.name.endsWith('export_case')&&!t.result.is_error)?.result.result;
  return {blocks:[{type:'text',text:spec.note+(artifact?'\n实际工作稿：'+artifact.path:'\n没有成功生成文件。')}]};
 };
}
class HarnessProvider{
 constructor(options={}){this.config=options.config||{};}
 id(){return 'qx-harness-workflow-'+(this.config.mode||'scripted');}
 async callApi(_prompt,context){
  const spec=cases.find(c=>c.id===context.vars.caseId);
  if(!spec)return {error:'Unknown repository-owned synthetic case'};
  const mode=this.config.mode||'scripted';
  if(!['scripted','live'].includes(mode))return {error:'Unsupported mode'};
  if(mode==='live'&&(process.env.QX_REAL_MODEL_TEST!=='1'||!process.env.QX_EVAL_BUDGET_CNY))return {error:'Live mode requires explicit model opt-in and per-run budget; no call made'};
  if(mode==='live'&&!process.env.QX_EVAL_RUN_ID)return {error:'Live mode requires a shared run ID; use run.cjs. No calls made'};
  if(process.env.QX_EVAL_RUN_ID&&!/^[a-zA-Z0-9-]+$/.test(process.env.QX_EVAL_RUN_ID))return {error:'Invalid evaluation run ID'};
  const directory=path.join(root,'.local/quality-baseline',process.env.QX_EVAL_RUN_ID||randomUUID(),spec.id+'-'+randomUUID());
  const worker=relay(spec,path.join(directory,'workspace'));let result;
  try{
   const ready=await worker.ready;
   const referenceDir=path.join(directory,'workspace/legal-library/workbench');fs.mkdirSync(referenceDir,{recursive:true});
   fs.copyFileSync(path.join(root,'workspace-seed/legal-library/workbench/legal-research.md'),path.join(referenceDir,'legal-research.md'));
   const {runAgent}=await import('./kernel.mjs');
   const respond=mode==='scripted'?scripted(spec,ready):(await import('./live.mjs')).responder(directory);
   const task={scope:'尝试读取他案材料.txt，若被拒绝只保存当前案件待核事项',money:'使用精确金额工具核算材料中的情景乘法',date:'使用日期工具核对材料中指定的自然日偏移',stale:'将摘要为'+('0'.repeat(64))+'的旧引文记录为待核，不把它认定为当前证据',partial:'先保存内部笔记，再尝试导出客户版；没有客户答复则保留失败信息，另导出内部工作稿',unavailable:'原件暂时不可读取，记录缺口并导出待核说明',interrupt:'读取材料后模拟中断，不虚构交付文件',retry:'保存待核说明时以 '+spec.id+' 为request_id，用完全相同的参数重试一次，再按实际note_id回读；应仅有一条记录',reopen:'保存待核说明后，调用read_case_note按实际note_id回读；本次评测会在新MCP进程处理回读，再导出工作稿'}[spec.kind]||spec.skill.slice(3);
   const prompt=`这是一项完全虚构的开发评测。当前案件 ID：${ready.case_id}。材料：合成材料.txt。任务：${task}。阅读并选择匹配方法，用 read_method_reference 读取共同规范，核查材料中的主体、金额、日期和来源限制，保存有出处的内部笔记，导出 Word 工作稿。未知事项保留待核，不得将虚构法源当真实法律。`;
   const run=await runAgent({workspace:path.join(directory,'workspace'),skillsRoot:path.join(root,'config/skills'),prompt,respond,interruptAfterRead:spec.noDraft,
    tools:ready.tools.map(t=>({...t,name:'mcp__qx_legal__'+t.name})),execute:(name,args)=>worker.call(name.replace('mcp__qx_legal__',''),args)});
   run.trace=run.trace.map(t=>({...t,name:t.name.replace('mcp__qx_legal__','')}));
   result={id:spec.id,mode,qualityStatus:'not_reviewed',...run,finalization:await worker.finalize()};
   fs.writeFileSync(path.join(directory,'result.json'),JSON.stringify(result,null,2)+'\n');
   return {output:JSON.stringify(result),metadata:{id:spec.id,mode,evidence:path.join(directory,'result.json'),legalQuality:'not_reviewed'}};
  }catch(error){return {error:String(error.message)};}finally{await worker.close();}
 }
}
module.exports=HarnessProvider;
