// Real pinned Harness, HTTP routes, agent loop and durable sessions.
// Content API and model replies are explicitly synthetic; no real credentials are read.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {randomUUID,createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {INTERVAL_MS} from '../../plugins/content-watch/core.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../..');
const [nodeMajor,nodeMinor]=process.versions.node.split('.').map(Number);
assert.ok(nodeMajor>24||nodeMajor===24&&nodeMinor>=9,'Harness requires an ordinary Node >=24.9 capable of loading its native binding');
const modules=process.env.QX_TEST_HARNESS_MODULES||path.resolve(root,'../.local/content-watch-harness-runtime/node_modules');
const binary=path.join(modules,'@deepseek-ai/dsh/lib/bin.js');
assert.equal(JSON.parse(await fs.readFile(path.join(modules,'@deepseek-ai/dsh/package.json'),'utf8')).version,'0.2.2-alpha.2');
// Match the checked-in pnpm lock: Cordis alpha.2 changes the preset registry's service shape.
assert.equal(JSON.parse(await fs.readFile(path.join(modules,'@deepseek-ai/cordis/package.json'),'utf8')).version,'4.0.6-alpha.1','Use the repository-locked Cordis version');
const temp=await fs.mkdtemp(path.join(os.tmpdir(),'qx-content-harness-'));
const workspace=path.join(temp,'workspace'),home=path.join(temp,'home'),profile=path.join(home,'profiles/web'),stateDir=path.join(temp,'content-watch');
const reportPath=process.env.QX_CONTENT_HARNESS_REPORT||path.join(root,'.local/checks/content-watch-harness',new Date().toISOString().replaceAll(/[:.]/g,'-')+'.json');
const sessionId='qx-content-watch',fakeToken='synthetic-content-harness-token';
const report={startedAt:new Date().toISOString(),runtime:'@deepseek-ai/dsh 0.2.2-alpha.2',node:process.version,
  data:'synthetic content and synthetic model; real local Harness and application modules',realProviderRequests:0,checks:[]};
const requests=[],modelRequests=[];let generation=1,child,base,hostTail='',cookies=new Map();
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const scrub=text=>String(text).replace(/([?&]token=)[^\s"'<>]+/g,'$1[REDACTED]');
const phase=name=>console.log(JSON.stringify({phase:name}));
const check=(name,evidence={})=>{report.checks.push({name,...evidence});phase(name);};
const note=id=>({id,title:'合成劳动争议选题 '+id,desc:'合成正文：企业负责人关注劳动关系变更中的沟通问题。',type:'normal',
  user:{nickname:'合成作者'},liked_count:'88',comments_count:'9',collected_count:'12',shared_count:'1',timestamp:Math.floor(Date.now()/1000),time:Math.floor(Date.now()/1000)});
function sse(response,text){
  response.writeHead(200,{'content-type':'text/event-stream'});
  const event=value=>response.write('event: '+value.type+'\ndata: '+JSON.stringify(value)+'\n\n');
  event({type:'message_start',message:{id:'synthetic-'+randomUUID(),type:'message',role:'assistant',model:'content-fixture',content:[],usage:{input_tokens:100,output_tokens:0}}});
  event({type:'content_block_start',index:0,content_block:{type:'text',text:''}});
  event({type:'content_block_delta',index:0,delta:{type:'text_delta',text}});
  event({type:'content_block_stop',index:0});
  event({type:'message_delta',delta:{stop_reason:'end_turn'},usage:{output_tokens:30}});
  event({type:'message_stop'});response.end();
}
const fixture=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url,'http://127.0.0.1');
    if(url.pathname.endsWith('/messages')){
      let raw='';for await(const chunk of req)raw+=chunk;
      const body=JSON.parse(raw);assert.ok(JSON.stringify(body).includes('劳动争议'));assert.ok(JSON.stringify(body).includes('企业负责人'));
      assert.ok(!JSON.stringify(body).includes(fakeToken));modelRequests.push(body);
      sse(res,`合成模型报告（第 ${modelRequests.length} 次）：劳动争议与企业负责人相关；本内容只用于真实会话持久化验收，不是法律分析。`);return;
    }
    assert.equal(req.method,'GET');assert.equal(url.searchParams.get('token'),fakeToken);
    if(url.pathname==='/api/xiaohongshu/search-note/v4'){
      assert.equal(url.searchParams.get('timeFilter'),'ONE_WEEK');
      assert.ok(['popularity_descending','time_descending'].includes(url.searchParams.get('sortType')));
      assert.match(url.searchParams.get('keyword'),/劳动争议/);
      requests.push({kind:'search',keyword:url.searchParams.get('keyword'),sort:url.searchParams.get('sortType')});
      res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({code:0,data:{notes:[note('fixture-note-1'),...(generation>1?[note('fixture-note-2')]:[])]}}));return;
    }
    assert.equal(url.pathname,'/api/xiaohongshu/get-note-detail/v1');
    const id=url.searchParams.get('noteId');assert.ok(['fixture-note-1','fixture-note-2'].includes(id));requests.push({kind:'detail',id});
    res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({code:0,data:[{model_type:'note',note_list:[note(id)]}]}));
  }catch(error){report.fixtureError=scrub(error.message);res.writeHead(500);res.end('synthetic fixture rejected request');}
});
async function listen(server){await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});return server.address().port;}
async function request(route,options={}){
  const url=new URL(route,base);assert.equal(url.origin,base);assert.equal(url.hostname,'127.0.0.1');
  const response=await fetch(url,{...options,redirect:'manual',signal:AbortSignal.timeout(20000),headers:{Origin:base,
    Cookie:[...cookies].map(([k,v])=>k+'='+v).join('; '),...options.headers}});
  for(const header of response.headers.getSetCookie()){const pair=header.split(';',1)[0],at=pair.indexOf('=');cookies.set(pair.slice(0,at),pair.slice(at+1));}
  return response;
}
async function rpc(method,args){
  const response=await request('/api/'+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args}})});
  assert.ok(response.ok,'RPC HTTP '+response.status);const body=await response.json();assert.ok(body.result?.ok,method+': '+JSON.stringify(body.result?.error));return body.result.value;
}
async function api(endpoint,data){
  const response=await request('/api/qx-content-watch/'+endpoint,{method:data?'POST':'GET',headers:{'x-qx-content-watch':'1',...(data?{'content-type':'application/json'}:{})},...(data?{body:JSON.stringify(data)}:{})});
  assert.ok(response.ok,'content API HTTP '+response.status);return response.json();
}
async function events(){const value=await rpc('session/events',{request:{address:{kind:'session',sessionId},maxMessages:1000}});return (value.records??value.entries??value.events??[]).map(row=>row.event??row);}
async function settle(predicate,timeout=60000){
  const deadline=Date.now()+timeout;let state;
  do{state=await api('status');if(predicate(state))return state;if(['error','provider_unavailable','token_invalid'].includes(state.status)||state.status==='ready'&&state.lastReport?.submitted&&state.lastReport.pending)throw Error('content task: '+state.message);await delay(200);}while(Date.now()<deadline);
  throw Error('content task timed out: '+JSON.stringify({status:state?.status,message:state?.message}));
}
async function stopHost(){
  if(!child||child.exitCode!==null)return;
  const stopped=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');
  await Promise.race([stopped,delay(5000)]);
  if(child.exitCode===null){child.kill('SIGKILL');await stopped;}
  child=null;
}
async function startHost(){
  const reserve=http.createServer(),port=await listen(reserve);await new Promise(resolve=>reserve.close(resolve));
  cookies=new Map();hostTail='';
  const env={...process.env,DSH_HOME:home,DSH_TELEMETRY_MODE:'OFF',NARB_NATIVE_CACHE_DIR:path.join(temp,'native-cache'),QX_CONTENT_FAKE_KEY:'synthetic-model-fixture',
    HTTP_PROXY:'',HTTPS_PROXY:'',ALL_PROXY:'',http_proxy:'',https_proxy:'',all_proxy:'',NO_PROXY:'127.0.0.1,localhost,::1'};
  delete env.DEEPSEEK_API_KEY;delete env.QX_INSTALL_DATA;
  child=spawn(process.execPath,['--import',path.join(here,'network-guard.mjs'),binary,'web','--no-open','--host','127.0.0.1','--port',String(port)],{cwd:workspace,env,stdio:['ignore','pipe','pipe']});
  const url=await new Promise((resolve,reject)=>{
    let settled=false;const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);};
    const timer=setTimeout(()=>finish(Error('isolated host timeout: '+scrub(hostTail))),45000);
    child.once('error',error=>finish(error));child.once('exit',code=>finish(Error('isolated host exited '+code+': '+scrub(hostTail))));
    const capture=chunk=>{hostTail=(hostTail+chunk).slice(-12000);const match=hostTail.match(/dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);if(match)finish(null,match[1]);};
    child.stdout.on('data',capture);child.stderr.on('data',capture);
  });
  base=new URL(url).origin;let response=await request(url);
  for(let i=0;i<4&&response.status>=300&&response.status<400;i++)response=await request(response.headers.get('location'));
  assert.equal(response.status,200);await api('status');phase('real Harness ready');
}
try{
  await fs.mkdir(workspace,{recursive:true});await fs.mkdir(profile,{recursive:true});
  const fixturePort=await listen(fixture),fixtureApi='http://127.0.0.1:'+fixturePort;
  await fs.writeFile(path.join(profile,'package.json'),JSON.stringify({name:'qx-content-harness-synthetic',private:true,dependencies:{},dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}));
  await fs.symlink(path.resolve(modules),path.join(profile,'node_modules'),process.platform==='win32'?'junction':'dir');
  await fs.writeFile(path.join(profile,'cordis.yml'),'[]\n');
  await fs.writeFile(path.join(profile,'cordis.patch.yml'),JSON.stringify([
    {id:'session-title-llm',disabled:true},{id:'session-telemetry-otel',disabled:true},
    {id:'agent-default-model',config:{provider:'deepseek-official',model:'content-fixture',reasoningEffort:'off'}},
    {id:'llm-deepseek',config:{baseURL:fixtureApi,apiKeyEnv:'QX_CONTENT_FAKE_KEY',thinking:'disabled',reasoningEffort:'off',models:[{id:'content-fixture',contextWindow:100000,maxTokens:8000,inputModalities:['text']}]}},
    {insert:[{id:'preset-qunxing',name:'@deepseek-ai/dsh-agent-preset',config:{id:'qunxing',plugins:[{id:'synthetic-persona',name:'@deepseek-ai/dsh-persona',config:{prefix:'合成内容测试，不提供真实法律分析。'}}]}},
      {id:'qx-content-harness-fixture',name:path.join(here,'host-plugin.mjs'),config:{workspace,stateDir,fixtureApi}}]},
  ],null,2));
  await startHost();
  await api('connection',{provider:'justone',token:fakeToken});
  await api('profile',{practice:'劳动争议',targetClients:'企业负责人',enabled:true});
  await api('action',{action:'run'});
  const first=await settle(state=>state.status==='ready'&&state.lastReport?.submitted&&!state.lastReport.pending);
  assert.equal(requests.filter(r=>r.kind==='search').length,4);assert.deepEqual(requests.filter(r=>r.kind==='detail').map(r=>r.id),['fixture-note-1']);
  assert.equal(modelRequests.length,1);assert.ok(first.nextRunAt-first.lastRunAt>=INTERVAL_MS&&first.nextRunAt-first.lastRunAt<INTERVAL_MS+1000);
  const firstEvents=await events(),messages=firstEvents.filter(e=>e.type==='user/message'&&e.data.source?.kind==='qx-content-watch');
  assert.equal(messages.length,1);assert.equal(firstEvents.filter(e=>e.type==='turn/end').at(-1)?.data.reason.kind,'completed');
  assert.match(first.lastReport.content,/合成模型报告/);assert.ok(!JSON.stringify(first).includes(fakeToken));
  const firstPath=path.join(stateDir,'reports',first.lastReport.id+'.md'),firstBytes=await fs.readFile(firstPath);
  assert.match(firstBytes.toString(),/fixture-note-1/);assert.match(firstBytes.toString(),/合成模型报告/);
  check('real HTTP collection and agent completed',{searches:4,details:1,userMessages:1,nextIntervalMs:first.nextRunAt-first.lastRunAt});

  await stopHost();await startHost();
  const restored=await api('status');assert.equal(restored.lastReport.id,first.lastReport.id);assert.deepEqual(await fs.readFile(firstPath),firstBytes);
  assert.equal((await events()).filter(e=>e.type==='user/message'&&e.data.source?.kind==='qx-content-watch').length,1);
  phase('waiting for production 30-second startup tick while not due');await delay(32000);
  assert.equal(requests.length,5);assert.equal(modelRequests.length,1);assert.equal((await api('status')).lastReport.id,first.lastReport.id);
  check('restart restores report and not-due startup tick does not recollect',{reportSha256:createHash('sha256').update(firstBytes).digest('hex')});

  await stopHost();
  const stateFile=path.join(stateDir,'state.json'),saved=JSON.parse(await fs.readFile(stateFile,'utf8'));
  assert.equal(saved.active,null);saved.nextRunAt=Date.now()-INTERVAL_MS*3;await fs.writeFile(stateFile,JSON.stringify(saved)+'\n');generation=2;
  await startHost();phase('waiting for production startup tick after simulated missed periods');
  const second=await settle(state=>state.status==='ready'&&state.lastReport?.id!==first.lastReport.id&&state.lastReport?.submitted&&!state.lastReport.pending,45000);
  assert.equal(requests.filter(r=>r.kind==='search').length,8);assert.deepEqual(requests.filter(r=>r.kind==='detail').map(r=>r.id),['fixture-note-1','fixture-note-2']);
  assert.equal(modelRequests.length,2);assert.deepEqual(second.lastReport.items.map(item=>item.id),['fixture-note-2']);
  const secondEvents=await events();assert.equal(secondEvents.filter(e=>e.type==='user/message'&&e.data.source?.kind==='qx-content-watch').length,2);
  assert.equal(secondEvents.filter(e=>e.type==='turn/end').at(-1)?.data.reason.kind,'completed');assert.deepEqual(await fs.readFile(firstPath),firstBytes);
  check('overdue restart runs one current occurrence and skips old detail reads',{searches:8,details:2,userMessages:2});

  await api('action',{action:'run'});
  const duplicate=await settle(state=>state.status==='ready'&&requests.length===14);
  assert.match(duplicate.message,/没有新增/);assert.equal(duplicate.lastReport.id,second.lastReport.id);assert.equal(modelRequests.length,2);
  assert.equal((await events()).filter(e=>e.type==='user/message'&&e.data.source?.kind==='qx-content-watch').length,2);
  check('repeat collection does not repeat detail or session submission',{searches:12,details:2,userMessages:2});
  assert.equal(report.fixtureError,undefined);report.status='passed';
}catch(error){
  report.status='failed';report.error=scrub(error.stack||error.message);report.hostTail=scrub(hostTail);process.exitCode=1;
  if(base)try{report.sessionEnds=(await events()).filter(event=>event.type==='turn/end').map(event=>event.data);}catch{}
}
finally{
  await stopHost();fixture.closeAllConnections();if(fixture.listening)await new Promise(resolve=>fixture.close(resolve));
  report.finishedAt=new Date().toISOString();report.calls={search:requests.filter(r=>r.kind==='search').length,detail:requests.filter(r=>r.kind==='detail').length,syntheticModel:modelRequests.length};
  await fs.mkdir(path.dirname(reportPath),{recursive:true});await fs.writeFile(reportPath,JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,report:reportPath,checks:report.checks.length,calls:report.calls,...report.error?{error:report.error.split('\n')[0]}:{}}));
  assert.equal(path.dirname(temp),path.resolve(os.tmpdir()));assert.ok(path.basename(temp).startsWith('qx-content-harness-'));await fs.rm(temp,{recursive:true,force:true,maxRetries:3});
}
