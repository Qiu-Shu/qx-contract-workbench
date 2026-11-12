const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const input={messages:[{role:'user',content:[{type:'text',text:'完全虚构的预算检查'}]}],tools:[],signal:new AbortController().signal};
test('live adapter shares and settles a run ledger across cases without network',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-eval-budget-')),before={...process.env},fetch=global.fetch;
 try{
  process.env.QX_REAL_MODEL_TEST='1';process.env.QX_EVAL_BUDGET_CNY='2';process.env.DEEPSEEK_API_KEY='synthetic-never-valid';
  let calls=0;global.fetch=async(url,options)=>{calls++;assert.equal(url,'https://api.deepseek.com/chat/completions');assert.equal(JSON.parse(options.body).model,'deepseek-flash');
   return {ok:true,json:async()=>({choices:[{finish_reason:'stop',message:{content:'待核'}}],usage:{prompt_tokens:20,completion_tokens:10}})};};
  const {responder}=await import('./live.mjs');
  await responder(path.join(tmp,'first'))(input);await responder(path.join(tmp,'second'))(input);
  const ledger=fs.readFileSync(path.join(tmp,'live-budget.json'),'utf8');assert.equal(JSON.parse(ledger).requests.length,2);assert.equal(calls,2);
  assert(!ledger.includes(process.env.DEEPSEEK_API_KEY));assert(!fs.existsSync(path.join(tmp,'live-budget.json.lock')));
 }finally{global.fetch=fetch;process.env=before;fs.rmSync(tmp,{recursive:true,force:true});}
});
test('live adapter denies concurrent budget access before a second request',async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'qx-eval-lock-')),before={...process.env},fetch=global.fetch;
 let release,entered;const ready=new Promise(r=>entered=r);const gate=new Promise(r=>release=r);
 try{
  process.env.QX_REAL_MODEL_TEST='1';process.env.QX_EVAL_BUDGET_CNY='2';process.env.DEEPSEEK_API_KEY='synthetic-never-valid';
  let calls=0;global.fetch=async()=>{calls++;entered();await gate;return {ok:true,json:async()=>({choices:[{finish_reason:'stop',message:{content:'待核'}}]})};};
  const {responder}=await import('./live.mjs');const first=responder(path.join(tmp,'first'))(input);await ready;
  await assert.rejects(responder(path.join(tmp,'second'))(input),/EEXIST/);assert.equal(calls,1);release();await first;
  const ledger=JSON.parse(fs.readFileSync(path.join(tmp,'live-budget.json'),'utf8'));assert.equal(ledger.requests.length,1);assert(ledger.requests[0].reserved>0);assert.equal(ledger.requests[0].cost,undefined);
 }finally{release?.();global.fetch=fetch;process.env=before;fs.rmSync(tmp,{recursive:true,force:true});}
});
