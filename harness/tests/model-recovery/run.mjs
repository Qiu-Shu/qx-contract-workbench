// Real installed Harness/DeepSeek adapter/retry/loop; only a localhost SSE provider is synthetic.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {randomUUID,createHash} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const red=process.argv.includes('--expect-red');
const python=process.env.QX_TEST_PYTHON||'D:/qx-contract-workbench-20261102/.venv/Scripts/python.exe';
const yaml=await import(pathToFileURL(path.join(root,'node_modules/.pnpm/yaml@2.9.1/node_modules/yaml/dist/index.js')));
const patch=yaml.parse(await fs.readFile(path.join(root,'config/cordis.patch.yml'),'utf8'));
const provider=patch.find(entry=>entry.id==='llm-deepseek');
const policy=provider?.config?.retryPolicy;
if(red)assert.ok(!policy?.retryableCodes?.includes('MALFORMED_RESPONSE'),'red run requires the unpatched configuration');
else assert.ok(policy?.retryableCodes?.includes('MALFORMED_RESPONSE'),'project provider policy must include MALFORMED_RESPONSE');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'qx-model-recovery-'));
const workspace=path.join(temp,'workspace');await fs.mkdir(workspace);
const report={mode:red?'red':'green',startedAt:new Date().toISOString(),realModelRequests:0,checks:[],policy:policy??'official defaults'};
const scenarios=new Map();let child,hostTail='';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function sse(response,blocks,earlyEnd=false){
 response.writeHead(200,{'Content-Type':'text/event-stream'});
 const event=value=>response.write(`event: ${value.type}\ndata: ${JSON.stringify(value)}\n\n`);
 event({type:'message_start',message:{id:'synthetic',type:'message',role:'assistant',model:'recovery-model',content:[],usage:{input_tokens:10,output_tokens:0}}});
 blocks.forEach((block,index)=>{
   if(block.type==='text'){
     event({type:'content_block_start',index,content_block:{type:'text',text:''}});
     event({type:'content_block_delta',index,delta:{type:'text_delta',text:block.text}});
   }else{
     event({type:'content_block_start',index,content_block:{type:'tool_use',id:block.id,name:block.name,input:{}}});
     event({type:'content_block_delta',index,delta:{type:'input_json_delta',partial_json:block.args}});
   }
   event({type:'content_block_stop',index});
 });
 if(earlyEnd){response.end();return;}
 event({type:'message_delta',delta:{stop_reason:blocks.some(b=>b.type==='tool')?'tool_use':'end_turn'},usage:{output_tokens:10}});
 event({type:'message_stop'});response.end();
}
const malformed=()=>[{type:'text',text:'SYNTHETIC PARTIAL ANSWER'},
 {type:'tool',id:'bad-call',name:'mcp__recovery__write_file',args:'{"broken":'}];
const server=http.createServer(async(req,res)=>{
 try{
   if(!req.url.endsWith('/messages')){res.writeHead(404);res.end();return;}
   let raw='';for await(const part of req)raw+=part;
   const body=JSON.parse(raw);const scenario=scenarios.get(req.headers['x-deepseek-harness-session-id']);
   if(!scenario)throw Error('Unexpected local model request');
   scenario.requests.push(body);const index=scenario.requests.length;
   if(scenario.kind==='auth'||scenario.kind==='quota'){
     res.writeHead(scenario.kind==='auth'?401:402,{'Content-Type':'application/json'});
     res.end(JSON.stringify({error:{type:scenario.kind==='auth'?'authentication_error':'quota_exceeded',message:'synthetic '+scenario.kind}}));return;
   }
   if(scenario.kind==='recover'&&index===1){
     sse(res,['write_file','present','record_case_note'].map((name,i)=>({type:'tool',id:`saved-${i}`,name:'mcp__recovery__'+name,args:'{}'})));return;
   }
   if(scenario.kind==='recover'&&index>=3){sse(res,[{type:'text',text:'SYNTHETIC RECOVERY COMPLETE'}]);return;}
   if(scenario.kind==='stream_closed'){
     sse(res,[{type:'text',text:index===1?'SYNTHETIC STREAM PARTIAL':'SYNTHETIC STREAM COMPLETE'}],index===1);return;
   }
   sse(res,malformed());
 }catch(error){res.writeHead(500);res.end('synthetic server failure');report.serverError=error.message;}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const port=server.address().port;
const reserve=http.createServer();await new Promise(resolve=>reserve.listen(0,'127.0.0.1',resolve));
const hostPort=reserve.address().port;await new Promise(resolve=>reserve.close(resolve));
const hostHome=path.join(temp,'home');await fs.mkdir(path.join(hostHome,'profiles/web'),{recursive:true});
// A dependency-free profile uses installed official bundles and never invokes package installation.
await fs.writeFile(path.join(hostHome,'profiles/web/package.json'),JSON.stringify({name:'qx-offline-recovery',private:true,dependencies:{},dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}));
const config=[
 {id:'session-title-llm',disabled:true},
 {id:'session-telemetry-otel',disabled:true},
 {id:'agent-default-model',config:{provider:'deepseek-official',model:'recovery-model',reasoningEffort:'off'}},
 {id:'llm-deepseek',config:{baseURL:`http://127.0.0.1:${port}`,apiKeyEnv:'QX_RECOVERY_FAKE_KEY',thinking:'disabled',reasoningEffort:'off',models:[{id:'recovery-model',contextWindow:100000,maxTokens:8000,inputModalities:['text']}],...(policy?{retryPolicy:policy}:{})}},
 {insert:[{id:'recovery-mcp',name:'@deepseek-ai/dsh-mcp-client',config:{transport:'stdio',serverName:'recovery',command:python,args:[path.join(root,'tests/model-recovery/fixture_mcp.py'),workspace],cwd:workspace,env:{PYTHONIOENCODING:'utf-8'},toolCallTimeoutMs:10000}}]}
];
await fs.writeFile(path.join(hostHome,'profiles/web/cordis.patch.yml'),yaml.stringify(config));
const cookies=new Map();let base;
async function request(route,options={}){
 const url=new URL(route,base);assert.equal(url.hostname,'127.0.0.1');assert.equal(url.port,String(hostPort));
 const response=await fetch(url,{...options,redirect:'manual',signal:AbortSignal.timeout(30000),headers:{Origin:url.origin,Cookie:[...cookies].map(([k,v])=>`${k}=${v}`).join('; '),...options.headers}});
 for(const value of response.headers.getSetCookie()){const pair=value.split(';')[0],at=pair.indexOf('=');cookies.set(pair.slice(0,at),pair.slice(at+1));}
 return response;
}
async function rpc(method,args){
 const response=await request('/api/'+method,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args}})});
 const envelope=await response.json();assert.ok(envelope.result?.ok,`${method}: ${JSON.stringify(envelope.result?.error)}`);return envelope.result.value;
}
async function events(sessionId){const value=await rpc('session/events',{request:{address:{kind:'session',sessionId},maxMessages:1000}});return(value.records??value.entries??value.events??[]).map(row=>row.event??row);}
async function scenario(kind){
 const id=`qx-offline-${kind}-${randomUUID()}`,state={kind,requests:[]};scenarios.set(id,state);
 await rpc('session/create',{request:{sessionId:id,cwd:workspace}});
 await rpc('session/prompt',{request:{requestId:randomUUID(),sessionId:id,mode:'queue',content:[{type:'text',text:'SYNTHETIC TASK '+kind}]}});
 const deadline=Date.now()+80000;let all=[],cancelled=false;
 while(Date.now()<deadline){
   all=await events(id);
   if(kind==='cancel'&&!cancelled&&all.some(e=>e.type==='llm/retry')){await rpc('session/cancel',{request:{sessionId:id}});cancelled=true;}
   if(all.some(e=>e.type==='turn/end'))break;
   await sleep(80);
 }
 const end=all.filter(e=>e.type==='turn/end').at(-1);assert.ok(end,kind+' did not settle');
 const entry={kind,requests:state.requests.length,end:end.data.reason,retries:all.filter(e=>e.type==='llm/retry').length,attempts:all.filter(e=>e.type==='assistant/attempt').length};
 report.checks.push(entry);return{all,state,entry};
}
try{
 const env={...process.env,DSH_HOME:hostHome,QX_RECOVERY_FAKE_KEY:'synthetic-not-a-real-key',DSH_TELEMETRY_MODE:'OFF'};
 delete env.DEEPSEEK_API_KEY;
 child=spawn(process.execPath,[path.join(root,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port',String(hostPort)],{cwd:workspace,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
 const ready=new Promise((resolve,reject)=>{
   const timer=setTimeout(()=>reject(Error('isolated host start timeout: '+hostTail.replace(/token=\S+/g,'token=REDACTED'))),45000);
   child.once('exit',code=>{clearTimeout(timer);reject(Error('isolated host exited '+code+': '+hostTail.replace(/token=\S+/g,'token=REDACTED')));});
   child.stdout.on('data',chunk=>{hostTail=(hostTail+chunk).slice(-6000);const match=hostTail.match(/dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
   child.stderr.on('data',chunk=>{hostTail=(hostTail+chunk).slice(-6000);});
 });
 const url=await ready;base=new URL(url).origin;let response=await request(url);
 for(let i=0;i<4&&response.status>=300&&response.status<400;i++)response=await request(response.headers.get('location'));
 assert.equal(response.status,200);
 const recovered=await scenario('recover');
 const effects=(await fs.readFile(path.join(workspace,'effects.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
 for(const name of ['write_file','present','record_case_note'])assert.equal(effects.filter(e=>e.tool===name).length,1,name+' duplicated');
 const artifact=await fs.readFile(path.join(workspace,'result.txt'));
 assert.deepEqual(artifact,Buffer.from('SYNTHETIC SAVED RESULT\n'));report.artifactSha256=createHash('sha256').update(artifact).digest('hex');
 assert.equal(recovered.all.filter(e=>e.type==='user/message'&&JSON.stringify(e.data).includes('SYNTHETIC TASK')).length,1);
 assert.equal(recovered.entry.attempts,1);
 assert.ok(recovered.all.some(e=>e.type==='assistant/attempt'&&JSON.stringify(e.data).includes('SYNTHETIC PARTIAL ANSWER')));
 recovered.entry.savedEffects=Object.fromEntries(['write_file','present','record_case_note'].map(name=>[name,effects.filter(e=>e.tool===name).length]));
 recovered.entry.userMessages=1;recovered.entry.partialAttemptPreserved=true;
 if(red){assert.equal(recovered.entry.requests,2);assert.equal(recovered.entry.retries,0);assert.equal(recovered.entry.end.kind,'error');report.status='expected_red';}
 else{
   assert.equal(recovered.entry.requests,3);assert.equal(recovered.entry.retries,1);assert.equal(recovered.entry.end.kind,'completed');
   const attempt=recovered.all.find(e=>e.type==='assistant/attempt');const retry=recovered.all.find(e=>e.type==='llm/retry');
   assert.equal(attempt.data.step,retry.data.step);
   assert.ok(recovered.all.some(e=>e.type==='assistant/message'&&e.data.step===retry.data.step&&JSON.stringify(e.data).includes('SYNTHETIC RECOVERY COMPLETE')));
   assert.ok(recovered.state.requests[2].messages.some(m=>m.content.some(b=>b.type==='tool_result'&&b.tool_use_id==='saved-0')),'prior saved result missing from retry');
   assert.ok(!JSON.stringify(recovered.state.requests[2].messages).includes('SYNTHETIC PARTIAL ANSWER'),'failed attempt entered model history');
   recovered.entry.sameStepRetry=true;recovered.entry.priorToolResultInRetry=true;
   const closed=await scenario('stream_closed');assert.equal(closed.entry.requests,2);assert.equal(closed.entry.retries,1);assert.equal(closed.entry.end.kind,'completed');
   assert.ok(closed.all.some(e=>e.type==='assistant/attempt'&&JSON.stringify(e.data).includes('SYNTHETIC STREAM PARTIAL')));
   assert.ok(closed.all.some(e=>e.type==='llm/retry'&&e.data.failure.code==='STREAM_CLOSED'));
   closed.entry.partialAttemptPreserved=true;
   for(const kind of ['auth','quota']){const r=await scenario(kind);assert.equal(r.entry.requests,1);assert.equal(r.entry.retries,0);assert.equal(r.entry.end.kind,'error');}
   const cancelled=await scenario('cancel');assert.equal(cancelled.entry.requests,1);assert.equal(cancelled.entry.end.kind,'aborted');
   const permanent=await scenario('permanent');assert.equal(permanent.entry.requests,(policy.maxRetries??5)+1);assert.equal(permanent.entry.end.kind,'error');
   assert.deepEqual(await fs.readFile(path.join(workspace,'result.txt')),artifact);report.status='passed';
 }
}catch(error){report.status='failed';report.error=error.message;process.exitCode=1;}
finally{
 if(child&&child.exitCode===null){child.kill();await Promise.race([new Promise(resolve=>child.once('exit',resolve)),sleep(5000)]);}
 server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
 report.finishedAt=new Date().toISOString();const out=path.join(root,'docs/checks/model-recovery');await fs.mkdir(out,{recursive:true});
 await fs.writeFile(path.join(out,red?'red.json':'green.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));
 assert.equal(path.dirname(path.resolve(temp)),path.resolve(os.tmpdir()));
 assert.ok(path.basename(temp).startsWith('qx-model-recovery-'));
 await fs.rm(temp,{recursive:true,force:true,maxRetries:3});
}
