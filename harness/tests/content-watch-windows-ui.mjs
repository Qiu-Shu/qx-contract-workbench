// Windows Chrome drives the real installed Harness UI; only external providers are synthetic.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';

assert.equal(process.platform,'win32','This acceptance exercises Windows DPAPI and an installed Windows payload.');
const here=path.dirname(fileURLToPath(import.meta.url)),sourceRoot=path.resolve(here,'..');
const app=path.resolve(process.env.QX_TEST_APP||''),packaged=process.env.QX_TEST_PACKAGED==='1';
assert.ok(process.env.QX_TEST_APP,'Set QX_TEST_APP to the installed resources/workbench directory.');
const productRoot=packaged?app:sourceRoot;
const integration=packaged?path.join(app,'node_modules/@qunxing/desktop-session'):path.join(sourceRoot,'desktop/integration');
const require=createRequire(import.meta.url),{chromium}=require(process.env.QX_TEST_PLAYWRIGHT_MODULE||'playwright');
const evidenceRoot=path.resolve(process.env.QX_TEST_OUTPUT_ROOT||'D:/CodexChecks/AI-Shixiong-content-merge-20261113/ui');
assert.ok(/^[d-z]:[\\/]/i.test(evidenceRoot),'Acceptance evidence and temporary data must be off C:.');
await fs.mkdir(evidenceRoot,{recursive:true});
const data=await fs.mkdtemp(path.join(evidenceRoot,packaged?'installed-':'source-preflight-'));
process.env.TEMP=path.join(data,'temp');process.env.TMP=process.env.TEMP;
await fs.mkdir(process.env.TEMP,{recursive:true});
const workspace=path.join(data,'deepseek-harness/default-workspace'),home=path.join(data,'home'),profile=path.join(home,'profiles/web'),stateDir=path.join(data,'.local/content-watch');
const reportPath=path.join(data,'report.json'),guardLog=path.join(data,'network-denied.jsonl');
const fakeToken='synthetic-ui-content-token-never-real',sessionId='qx-content-watch',interval=72*60*60*1000;
const report={status:'running',startedAt:new Date().toISOString(),packaged,app,productRoot,integration,
  boundaries:{real:packaged?'Installed Windows payload Node/Harness, desktop integration UI, content task, DPAPI, knowledge and persistent sessions':'Existing Windows runtime with current source desktop integration and content task; real DPAPI, knowledge and persistent sessions',synthetic:'Isolated profile and minimal agent preset, JustOneAPI HTTP responses, DeepSeek SSE responses, account balance placeholder',paidProviderRequests:0},checks:[],pageErrors:[],blockedBrowserRequests:[]};
const contentRequests=[],modelRequests=[],publicResponses=[];let child,browser,context,page,base,hostUrl,hostTail='',cookies=new Map();
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const systemEnvironment=()=>Object.fromEntries(Object.entries(process.env).filter(([key])=>['path','systemroot','windir','comspec','pathext','userprofile'].includes(key.toLowerCase())));
const scrub=value=>String(value).replace(/([?&]token=)[^\s"'<>]+/g,'$1[REDACTED]').replaceAll(fakeToken,'[SYNTHETIC-TOKEN]');
const check=(name,evidence={})=>{report.checks.push({name,...evidence});console.log(JSON.stringify({phase:name}));};
const note={id:'synthetic-ui-note',title:'合成劳动争议沟通选题',desc:'合成正文：企业负责人关注劳动关系变更中的沟通问题。',type:'normal',user:{nickname:'合成作者'},liked_count:'88',comments_count:'9',collected_count:'12',shared_count:'1'};
const currentNote=()=>({...note,timestamp:Math.floor(Date.now()/1000),time:Math.floor(Date.now()/1000)});
function sse(response,text){
  response.writeHead(200,{'content-type':'text/event-stream'});
  const event=value=>response.write('event: '+value.type+'\ndata: '+JSON.stringify(value)+'\n\n');
  event({type:'message_start',message:{id:'synthetic-'+randomUUID(),type:'message',role:'assistant',model:'content-ui-fixture',content:[],usage:{input_tokens:100,output_tokens:0}}});
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
      let raw='';for await(const chunk of req){raw+=chunk;assert.ok(raw.length<2*1024*1024);}
      const body=JSON.parse(raw);assert.ok(raw.includes('劳动争议'));assert.ok(raw.includes('企业负责人'));assert.ok(!raw.includes(fakeToken));
      modelRequests.push(body);
      sse(res,'合成模型报告：劳动争议与企业负责人相关。原文来自合成作者，仅读取合成正文。建议围绕沟通清单形成原创选题；本内容仅用于安装界面验收，不是法律分析。');return;
    }
    assert.equal(req.method,'GET');assert.equal(url.searchParams.get('token'),fakeToken);
    if(url.pathname==='/api/xiaohongshu/search-note/v4'){
      assert.equal(url.searchParams.get('timeFilter'),'ONE_WEEK');assert.match(url.searchParams.get('keyword'),/劳动争议/);
      contentRequests.push({kind:'search',keyword:url.searchParams.get('keyword'),sort:url.searchParams.get('sortType')});
      res.writeHead(200,{'content-type':'application/json'});res.end(JSON.stringify({code:0,data:{notes:[currentNote()]}}));return;
    }
    assert.equal(url.pathname,'/api/xiaohongshu/get-note-detail/v1');assert.equal(url.searchParams.get('noteId'),note.id);
    contentRequests.push({kind:'detail',id:note.id});res.writeHead(200,{'content-type':'application/json'});
    res.end(JSON.stringify({code:0,data:[{model_type:'note',note_list:[currentNote()]}]}));
  }catch(error){report.fixtureError=scrub(error.message);res.writeHead(500);res.end('synthetic fixture rejected request');}
});
async function listen(server){await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});return server.address().port;}
async function request(route,options={}){
  const url=new URL(route,base);assert.equal(url.origin,base);assert.equal(url.hostname,'127.0.0.1');
  const response=await fetch(url,{...options,redirect:'manual',signal:AbortSignal.timeout(20000),headers:{Origin:base,Cookie:[...cookies].map(([k,v])=>k+'='+v).join('; '),...options.headers}});
  for(const header of response.headers.getSetCookie()){const pair=header.split(';',1)[0],at=pair.indexOf('=');cookies.set(pair.slice(0,at),pair.slice(at+1));}
  return response;
}
async function status(){const response=await request('/api/qx-content-watch/status',{headers:{'x-qx-content-watch':'1'}});assert.equal(response.status,200);return response.json();}
async function events(){
  const method='session/events',response=await request('/api/'+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:randomUUID(),method,payload:{args:{request:{address:{kind:'session',sessionId},maxMessages:1000}}}})});
  assert.ok(response.ok);const value=await response.json();assert.ok(value.result?.ok,JSON.stringify(value.result?.error));
  const result=value.result.value;return (result.records??result.entries??result.events??[]).map(row=>row.event??row);
}
async function stopHost(){
  if(!child||child.exitCode!==null)return;
  const stopped=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await Promise.race([stopped,delay(5000)]);
  if(child.exitCode===null){child.kill('SIGKILL');await stopped;}child=null;
}
async function startHost(){
  const reserve=http.createServer(),port=await listen(reserve);await new Promise(resolve=>reserve.close(resolve));cookies=new Map();hostTail='';
  const env=systemEnvironment();
  Object.assign(env,{DSH_HOME:home,QX_INSTALL_DATA:data,DSH_TELEMETRY_MODE:'OFF',NODE_PATH:path.join(app,'node_modules'),NARB_NATIVE_CACHE_DIR:path.join(data,'native-cache'),QX_UI_FAKE_MODEL_KEY:'synthetic-ui-model-key',QX_UI_GUARD_LOG:guardLog,
    TEMP:path.join(data,'temp'),TMP:path.join(data,'temp'),APPDATA:path.join(data,'appdata'),LOCALAPPDATA:path.join(data,'localappdata'),HOME:home,NO_PROXY:'127.0.0.1,localhost,::1'});
  await fs.mkdir(env.TEMP,{recursive:true});
  const binary=path.join(app,'node_modules/@deepseek-ai/dsh/lib/bin.js');
  child=spawn(path.join(app,'runtime/node.exe'),['--import',pathToFileURL(path.join(here,'content-watch-windows-ui.guard.mjs')).href,binary,'web','--no-open','--host','127.0.0.1','--port',String(port)],{cwd:workspace,env,windowsHide:true,stdio:['ignore','pipe','pipe']});
  hostUrl=await new Promise((resolve,reject)=>{
    let settled=false;const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(value);};
    const timer=setTimeout(()=>finish(Error('isolated UI host timeout: '+scrub(hostTail))),45000);
    child.once('error',error=>finish(error));child.once('exit',code=>finish(Error('isolated UI host exited '+code+': '+scrub(hostTail))));
    const capture=chunk=>{hostTail=(hostTail+chunk).slice(-20000);void fs.appendFile(path.join(data,'host.log'),scrub(chunk));const match=hostTail.match(/dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);if(match)finish(null,match[1]);};
    child.stdout.on('data',capture);child.stderr.on('data',capture);
  });
  base=new URL(hostUrl).origin;let response=await request(hostUrl);
  for(let i=0;i<4&&response.status>=300&&response.status<400;i++)response=await request(response.headers.get('location'));
  assert.equal(response.status,200);await status();
}
async function openBrowser(){
  context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN',serviceWorkers:'block'});
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    if(url.protocol==='http:'&&url.hostname==='127.0.0.1'||['data:','blob:'].includes(url.protocol))return route.continue();
    report.blockedBrowserRequests.push(url.origin);return route.abort();
  });
  await context.routeWebSocket('**/*',socket=>{
    const url=new URL(socket.url());
    if(url.protocol==='ws:'&&url.hostname==='127.0.0.1')return socket.connectToServer();
    report.blockedBrowserRequests.push(url.origin);return socket.close();
  });
  await context.route('**/api/qx-account/balance*',route=>route.fulfill({json:{status:'unavailable',balances:[]}}));
  page=await context.newPage();page.on('pageerror',error=>report.pageErrors.push(error.message));
  page.on('response',response=>{if(response.url().includes('/api/qx-content-watch/')&&response.headers()['content-type']?.includes('application/json'))publicResponses.push(response.text().catch(()=>''));});
  await page.goto(hostUrl,{waitUntil:'domcontentloaded'});
  const welcome=page.getByRole('button',{name:'开始使用',exact:true});
  try{await welcome.click({timeout:10000});}catch{}
  await page.getByRole('button',{name:'拓客内容',exact:true}).click({timeout:60000});
  await page.getByLabel('业务方向',{exact:true}).waitFor({state:'visible'});
}
async function noFrontendToken(){
  assert.equal(await page.getByLabel('JustOneAPI Token',{exact:true}).inputValue(),'');
  assert.ok(!(await page.locator('body').innerText()).includes(fakeToken));
  const storage=await page.evaluate(()=>({local:{...localStorage},session:{...sessionStorage}}));
  assert.ok(!JSON.stringify(storage).includes(fakeToken));
  assert.ok(!JSON.stringify(await context.storageState({indexedDB:true})).includes(fakeToken));
}
try{
  await fs.mkdir(workspace,{recursive:true});await fs.mkdir(path.join(profile,'node_modules/@qunxing'),{recursive:true});
  await fs.symlink(path.join(app,'node_modules/@deepseek-ai'),path.join(profile,'node_modules/@deepseek-ai'),'junction');
  await fs.symlink(integration,path.join(profile,'node_modules/@qunxing/desktop-session'),'junction');
  const fixtureApi='http://127.0.0.1:'+await listen(fixture);
  await fs.writeFile(path.join(profile,'package.json'),JSON.stringify({name:'content-watch-windows-ui-synthetic',private:true,dependencies:{'@qunxing/desktop-session':'0.1.0'},dsh:{profile:{bundles:['@deepseek-ai/dsh-base','@deepseek-ai/dsh-web-app']}}}));
  await fs.writeFile(path.join(profile,'cordis.yml'),'[]\n');
  await fs.writeFile(path.join(profile,'cordis.patch.yml'),JSON.stringify([
    {id:'workspace-controller',config:{documentsDirectory:data}},{id:'session-title-llm',disabled:true},{id:'session-telemetry-otel',disabled:true},
    {id:'agent-default-model',config:{provider:'deepseek-official',model:'content-ui-fixture',reasoningEffort:'off'}},
    {id:'llm-deepseek',config:{baseURL:fixtureApi,apiKeyEnv:'QX_UI_FAKE_MODEL_KEY',thinking:'disabled',reasoningEffort:'off',models:[{id:'content-ui-fixture',contextWindow:100000,maxTokens:8000,inputModalities:['text']}]}},
    {insert:[{id:'qx-desktop-session',name:'@qunxing/desktop-session'},
      {id:'preset-qunxing',name:'@deepseek-ai/dsh-agent-preset',config:{id:'qunxing',plugins:[{id:'synthetic-persona',name:'@deepseek-ai/dsh-persona',config:{prefix:'合成界面验收，不提供真实法律分析。'}}]}},
      {id:'qx-content-ui-fixture',name:path.join(here,'content-watch-windows-ui.plugin.mjs'),config:{productRoot,workspace,stateDir,fixtureApi}}]},
  ],null,2));
  report.inputs=[];
  for(const file of [path.join(app,'runtime/node.exe'),path.join(app,'node_modules/@deepseek-ai/dsh/package.json'),path.join(integration,'index.mjs'),path.join(integration,'client.js'),...['index.mjs','client.js','core.mjs','connection.mjs','session.mjs','justone.mjs'].map(name=>path.join(productRoot,'plugins/content-watch',name))])report.inputs.push({path:file,sha256:createHash('sha256').update(await fs.readFile(file)).digest('hex')});
  await startHost();
  const initial=await status();assert.equal(initial.enabled,false);assert.equal(initial.profile,null);assert.equal(initial.connection.tokenConfigured,false);assert.equal(contentRequests.length,0);assert.equal(modelRequests.length,0);
  browser=await chromium.launch({executablePath:process.env.QX_TEST_CHROME||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,downloadsPath:path.join(data,'downloads'),
    env:{...systemEnvironment(),TEMP:process.env.TEMP,TMP:process.env.TMP,HOME:home,APPDATA:path.join(data,'browser-appdata'),LOCALAPPDATA:path.join(data,'browser-localappdata')},args:['--disk-cache-dir='+path.join(data,'browser-cache')]});
  await openBrowser();await page.screenshot({path:path.join(data,'01-default-disabled.png')});check('default task is disabled before lawyer configuration');
  await page.getByLabel('JustOneAPI Token',{exact:true}).fill(fakeToken);
  await page.getByRole('button',{name:'保存连接设置',exact:true}).click();
  await page.getByText('已保存 API 凭据；首次整理时验证服务连接。',{exact:true}).last().waitFor({state:'visible'});
  assert.equal((await status()).enabled,false);assert.equal(contentRequests.length,0);assert.equal(modelRequests.length,0);await noFrontendToken();
  const connection=await fs.readFile(path.join(stateDir,'connection.json'),'utf8');assert.ok(!connection.includes(fakeToken));assert.ok(JSON.parse(connection).token.startsWith('dpapi:'));
  check('UI saves encrypted Windows credentials without collection, model calls or frontend storage');
  await page.getByLabel('业务方向',{exact:true}).fill('劳动争议');await page.getByLabel('目标客户',{exact:true}).fill('企业负责人');
  await page.getByRole('button',{name:'保存并启用',exact:true}).click();
  await page.getByText('已保存。每 3 天整理一次，结果进入专用会话。',{exact:true}).waitFor({state:'visible'});
  await page.getByRole('button',{name:'立即整理',exact:true}).click();
  await page.getByText('本期内容已整理到专用会话。',{exact:true}).waitFor({state:'visible',timeout:60000});
  const first=await status();assert.equal(first.enabled,true);assert.equal(first.lastReport.submitted,true);assert.equal(first.lastReport.pending,false);
  assert.ok(first.nextRunAt-first.lastRunAt>=interval&&first.nextRunAt-first.lastRunAt<interval+1000);
  assert.equal(contentRequests.filter(r=>r.kind==='search').length,4);assert.equal(contentRequests.filter(r=>r.kind==='detail').length,1);assert.equal(modelRequests.length,1);
  assert.match(first.lastReport.content,/合成模型报告/);assert.ok(!JSON.stringify(first).includes(fakeToken));
  await page.getByText('查看已保存的报告',{exact:true}).click();await page.screenshot({path:path.join(data,'02-report-1440.png')});
  await page.setViewportSize({width:390,height:1000});await page.screenshot({path:path.join(data,'03-report-390.png')});
  assert.ok(await page.locator('.qx-content-panel').evaluate(el=>el.scrollWidth<=el.clientWidth+2));await page.setViewportSize({width:1440,height:1000});
  check('real UI immediately collects and persists a report with the next run scheduled 72 hours later',{searches:4,details:1,syntheticModels:1,nextIntervalMs:first.nextRunAt-first.lastRunAt});
  await page.getByRole('button',{name:'查看整理会话',exact:true}).click();
  await page.waitForFunction(id=>document.documentElement.dataset.qxSessionId===id,sessionId,{timeout:30000});
  await page.getByText(/合成模型报告：劳动争议与企业负责人相关/).last().waitFor({state:'visible',timeout:30000});
  await page.screenshot({path:path.join(data,'04-dedicated-session.png')});
  const firstEvents=await events();assert.equal(firstEvents.filter(event=>event.type==='user/message'&&event.data.source?.kind==='qx-content-watch').length,1);
  assert.equal(firstEvents.filter(event=>event.type==='turn/end').at(-1)?.data.reason.kind,'completed');
  check('session entry opens qx-content-watch and displays the actual completed persistent conversation');
  const firstPath=path.join(stateDir,'reports',first.lastReport.id+'.md'),reportBytes=await fs.readFile(firstPath);assert.ok(!reportBytes.includes(Buffer.from(fakeToken)));
  await context.close();context=null;await stopHost();await startHost();await openBrowser();
  assert.equal(await page.getByLabel('业务方向',{exact:true}).inputValue(),'劳动争议');assert.equal(await page.getByLabel('目标客户',{exact:true}).inputValue(),'企业负责人');
  await noFrontendToken();const restored=await status();assert.equal(restored.connection.secretStorage,'dpapi');assert.equal(restored.connection.tokenConfigured,true);assert.equal(restored.enabled,true);assert.equal(restored.lastReport.id,first.lastReport.id);
  assert.deepEqual(await fs.readFile(firstPath),reportBytes);assert.equal(modelRequests.length,1);assert.equal(contentRequests.length,5);
  await page.screenshot({path:path.join(data,'05-reopened-settings.png')});
  await page.getByRole('button',{name:'查看整理会话',exact:true}).click();await page.waitForFunction(id=>document.documentElement.dataset.qxSessionId===id,sessionId);
  await page.getByText(/合成模型报告：劳动争议与企业负责人相关/).last().waitFor({state:'visible',timeout:30000});
  assert.equal((await events()).filter(event=>event.type==='user/message'&&event.data.source?.kind==='qx-content-watch').length,1);
  check('host restart preserves profile, encrypted credential, report and one dedicated-session submission');
  assert.ok(!(await Promise.all(publicResponses)).some(value=>value.includes(fakeToken)));assert.equal(report.fixtureError,undefined);assert.deepEqual(report.pageErrors,[]);
  let denied='';try{denied=await fs.readFile(guardLog,'utf8');}catch(error){if(error.code!=='ENOENT')throw error;}assert.equal(denied,'');
  check('no plaintext token in public responses, frontend stores, reports or model requests; no page errors or host egress');
  report.status='passed';
}catch(error){
  report.status='failed';report.error=scrub(error.stack||error.message);report.hostTail=scrub(hostTail);process.exitCode=1;
  if(page)try{await page.screenshot({path:path.join(data,'failure.png')});await fs.writeFile(path.join(data,'failure.txt'),scrub(await page.locator('body').innerText()));}catch{}
}finally{
  await context?.close().catch(()=>{});await browser?.close().catch(()=>{});await stopHost();fixture.closeAllConnections();if(fixture.listening)await new Promise(resolve=>fixture.close(resolve));
  report.finishedAt=new Date().toISOString();report.calls={search:contentRequests.filter(r=>r.kind==='search').length,detail:contentRequests.filter(r=>r.kind==='detail').length,syntheticModel:modelRequests.length};
  await fs.writeFile(reportPath,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({status:report.status,report:reportPath,checks:report.checks.length,calls:report.calls,...report.error?{error:report.error.split('\n')[0]}:{}}));
}
