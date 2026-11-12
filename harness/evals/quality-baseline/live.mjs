// Explicit opt-in only. Same Harness/tool chain; expectations and scripted notes are never sent.
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import {openSync,closeSync,unlinkSync} from 'node:fs';
const require=createRequire(import.meta.url);
const {createBudget,upperBound}=require('../../scripts/skill-eval-budget.cjs');
const {modelFetch}=require('./network-policy.cjs');
export function responder(directory){
 if(process.env.QX_REAL_MODEL_TEST!=='1'||!process.env.DEEPSEEK_API_KEY)throw Error('Real model disabled');
 const cap=Number(process.env.QX_EVAL_BUDGET_CNY);
 if(!(cap>0.5&&cap<=20))throw Error('Explicit run budget must be >0.5 and <=20 CNY');
 // Run serially: all 24 cases share one existing budget ledger, never reset per case.
 const budgetFile=join(dirname(directory),'live-budget.json'),lockFile=budgetFile+'.lock';let count=0;
 return async options=>{
  const messages=options.messages.map(m=>{
   const text=m.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
   if(m.role==='tool')return {role:'tool',tool_call_id:m.toolCallId,content:text};
   if(m.role==='assistant')return {role:'assistant',content:text||null,...(m.content.some(b=>b.type==='tool-call')?{tool_calls:m.content.filter(b=>b.type==='tool-call').map(b=>({id:b.id,type:'function',function:{name:b.name,arguments:b.arguments}}))}:{})};
   return {role:m.role==='developer'?'user':m.role,content:text};
  });
  const tools=(options.tools||[]).map(t=>({type:'function',function:{name:t.name,description:t.description,parameters:t.parameters}}));
  const body={model:'deepseek-flash',messages,tools,max_tokens:4096,thinking:{type:'disabled'}};
  const lock=openSync(lockFile,'wx');let budget,row,usage;
  try{
   budget=createBudget(budgetFile,cap);row=budget.reserve(directory+':'+(++count),upperBound(body,4096));
   const response=await modelFetch('https://api.deepseek.com/chat/completions',{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+process.env.DEEPSEEK_API_KEY},body:JSON.stringify(body),signal:AbortSignal.any([options.signal,AbortSignal.timeout(60000)])});
   if(!response.ok)throw Error('Model HTTP '+response.status);
   const data=await response.json();usage=data.usage;const choice=data.choices?.[0];
   if(!choice||!['stop','tool_calls'].includes(choice.finish_reason))throw Error('Incomplete model response');
   const blocks=[];if(choice.message.content)blocks.push({type:'text',text:choice.message.content});
   for(const call of choice.message.tool_calls||[])blocks.push({type:'tool-call',id:call.id,name:call.function.name,arguments:call.function.arguments});
   if(!blocks.length)throw Error('Empty model response');return {blocks};
  }finally{try{if(row)budget.settle(row,usage);}finally{closeSync(lock);unlinkSync(lockFile);}}
 };
}
