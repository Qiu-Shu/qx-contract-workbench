const fs=require('node:fs');
const path=require('node:path');

// 2026-11-04 official Flash peak rates, deliberately ignoring cache/off-peak discounts.
const RATES={input:2,output:8};
function upperBound(messages,maxTokens){
  const bytes=Buffer.byteLength(JSON.stringify(messages),'utf8')+4096;
  return (bytes*RATES.input+maxTokens*RATES.output)/1e6;
}
function usageCost(usage){
  if(!usage||!Number.isSafeInteger(usage.prompt_tokens)||!Number.isSafeInteger(usage.completion_tokens)||usage.prompt_tokens<0||usage.completion_tokens<0)return null;
  return (usage.prompt_tokens*RATES.input+usage.completion_tokens*RATES.output)/1e6;
}
function createBudget(file,cap=20){
  if(!(cap>0&&cap<=20))throw Error('Budget cap must be within the authorized 20 CNY');
  fs.mkdirSync(path.dirname(file),{recursive:true});
  const state=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{cap,rateSource:'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',rates:RATES,requests:[]};
  if(state.cap!==cap)throw Error('Existing budget cap mismatch');
  const write=()=>{fs.writeFileSync(file+'.tmp',JSON.stringify(state,null,2)+'\n');fs.renameSync(file+'.tmp',file);};
  const total=()=>state.requests.reduce((sum,r)=>sum+(r.cost??r.reserved),0);
  return {state,total,reserve(id,amount){
    if(state.requests.some(r=>r.id===id))throw Error('Duplicate evaluation id');
    if(!Number.isFinite(amount)||amount<=0||total()+amount>cap-0.5)throw Error('Budget protection stopped further calls');
    const row={id,reserved:amount,startedAt:new Date().toISOString()};state.requests.push(row);write();return row;
  },settle(row,usage){
    const cost=usageCost(usage);if(cost!==null){row.cost=cost;row.usage=usage;}
    row.finishedAt=new Date().toISOString();write();
  }};
}
module.exports={createBudget,upperBound,usageCost};
