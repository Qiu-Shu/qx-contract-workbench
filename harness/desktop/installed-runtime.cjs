const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const http=require('node:http');
const {randomBytes}=require('node:crypto');
const {spawn}=require('node:child_process');
const {createSupervisor,createEventLog}=require('./host-recovery.cjs');
const {createCaseMemoryRuntime}=require('./case-memory-runtime.cjs');
const {assertRestoreReviewed,processAlive,hostProcessAlive,readHostRecord,readHostState,readControl,launcherOwnsPipe,stopRuntime,stopInstalledHost,restartRuntime}=require('./installed-stop.cjs');
const {migrateInstalledMedia,migrateInstalledLazyTools,relocateInstalledPaths,migrateInstalledAgentDesktop,migrateInstalledVerifiedDelivery,migrateInstalledSkillRoots}=require('./installed-migrations.cjs');
const {migrateInstalledKnowledge,migrateInstalledPrivacy,migrateInstalledContract,migrateInstalledModelRecovery,migrateInstalledSkillFixes,migrateInstalledSkillQuality,migrateInstalledLegalSearch,migrateInstalledCaseMemory}=require('./installed-migrations.cjs');

function redactedLines(secret,write){
  let pending='',dropping=false;
  const scrub=value=>value.replaceAll(secret,'[REDACTED]').replace(/([?&]token=)[^\s]+/g,'$1[REDACTED]');
  return {
    push(chunk){
      pending+=chunk.toString();let end;
      while((end=pending.indexOf('\n'))>=0){
        const line=pending.slice(0,end);pending=pending.slice(end+1);
        if(!dropping)write(scrub(line)+'\n');dropping=false;
      }
      if(pending.length>65536){if(!dropping)write('[过长日志已省略]\n');pending='';dropping=true;}
    },
    end(){if(pending&&!dropping)write(scrub(pending));pending='';},
  };
}

function initialize(payload,data){
  assertRestoreReviewed(data);
  const local=path.join(data,'.local'),profile=path.join(local,'dsh-home/profiles/web');
  const marker=path.join(local,'initialized-payload.json');
  let identity=null,previous=null;
  try{previous=JSON.parse(fs.readFileSync(marker,'utf8'))}catch{}
  try{
    const build=JSON.parse(fs.readFileSync(path.join(payload,'config/initialization.json'),'utf8'));
    // Runtime migrations have their own version; an unchanged package fingerprint must not skip a newly added migration.
    if(build.schema===1&&/^[a-f0-9]{64}$/.test(build.id))identity={schema:2,id:build.id,payload:path.resolve(payload),data:path.resolve(data)};
  }catch{/* Older packages have no fingerprint; initialize conservatively. */}
  if(identity){
    try{
      const required=['package.json','cordis.yml','cordis.patch.yml','node_modules'];
      if(previous?.schema===identity.schema&&previous.id===identity.id&&previous.payload===identity.payload&&previous.data===identity.data&&
        required.every(file=>fs.existsSync(path.join(profile,file)))&&fs.existsSync(path.join(data,'workspace/AGENTS.md'))&&
        JSON.stringify(JSON.parse(fs.readFileSync(path.join(profile,'package.json'),'utf8')))===JSON.stringify(JSON.parse(fs.readFileSync(path.join(payload,'config/profile-package.json'),'utf8')))&&
        fs.readFileSync(path.join(profile,'cordis.yml')).equals(fs.readFileSync(path.join(payload,'config/profile-cordis.yml')))&&
        fs.realpathSync(path.join(profile,'node_modules'))===fs.realpathSync(path.join(payload,'node_modules')))return {status:'unchanged'};
    }catch{/* An incomplete initialization is retried, never marked successful. */}
  }
  fs.mkdirSync(profile,{recursive:true});
  fs.mkdirSync(path.join(data,'workspace'),{recursive:true});
  const instructions=path.join(data,'workspace/AGENTS.md');
  const hadInstructions=fs.existsSync(instructions);
  // Seed only application-owned skills and empty instructions, never user history.
  fs.cpSync(path.join(payload,'workspace-seed'),path.join(data,'workspace'),{recursive:true,force:false,errorOnExist:false});
  const replacements={'@APP@':payload.replaceAll('\\','/'),'@DATA@':data.replaceAll('\\','/')};
  const original=fs.readFileSync(instructions,'utf8');
  if(!hadInstructions&&original.includes('@APP@'))fs.writeFileSync(instructions,original.replaceAll('@APP@',replacements['@APP@']));
  const transform=value=>typeof value==='string'?Object.entries(replacements).reduce((s,[from,to])=>s.replaceAll(from,to),value)
    :Array.isArray(value)?value.map(transform):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).map(([k,v])=>[k,transform(v)])):value;
  const patch=path.join(profile,'cordis.patch.yml');
  const template=JSON.parse(fs.readFileSync(path.join(payload,'config/portable.json'),'utf8'));
  const portableConfig=transform(template);
  relocateInstalledPaths({data,payload,template,previousData:previous?.data});
  if(!fs.existsSync(patch))fs.writeFileSync(patch,JSON.stringify(portableConfig,null,2));
  const skillRoots=migrateInstalledSkillRoots({data,payload,portableConfig});
  migrateInstalledKnowledge({data,payload,portableConfig,
    seedInstructions:transform(fs.readFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'utf8'))});
  migrateInstalledPrivacy({data,payload,portableConfig});
  migrateInstalledAgentDesktop({data,payload,portableConfig});
  migrateInstalledVerifiedDelivery({data,payload,portableConfig});
  migrateInstalledMedia({data,payload,portableConfig});
  migrateInstalledCaseMemory({data,payload,portableConfig,seedInstructions:transform(fs.readFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'utf8'))});
  migrateInstalledLegalSearch({data,payload,portableConfig});
  migrateInstalledModelRecovery({data,payload,portableConfig});
  migrateInstalledContract({data,payload});
  const skillFixes=migrateInstalledSkillFixes({data,payload});
  const skillQuality=migrateInstalledSkillQuality({data,payload,portableConfig,seedInstructions:transform(fs.readFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'utf8'))});
  const lazyTools=migrateInstalledLazyTools({data,payload,portableConfig});
  const pkg=JSON.parse(fs.readFileSync(path.join(payload,'config/profile-package.json'),'utf8'));
  fs.writeFileSync(path.join(profile,'package.json'),JSON.stringify(pkg,null,2));
  fs.copyFileSync(path.join(payload,'config/profile-cordis.yml'),path.join(profile,'cordis.yml'));
  // One link to bundled dependencies; no installation or network needed at startup.
  const modules=path.join(profile,'node_modules'),target=path.join(payload,'node_modules');
  if(!fs.existsSync(modules))fs.symlinkSync(target,modules,'junction');
  const pending=skillRoots.status==='deferred'||skillFixes.status==='deferred'||
    (skillQuality.status==='deferred'&&fs.existsSync(path.join(payload,'config/skill-quality-upgrades.json')))||
    (lazyTools.status==='deferred'&&JSON.stringify(template).includes('@APP@/plugins/lazy-mcp/'));
  if(identity&&!pending)writeJson(marker,identity);
  return {status:'initialized'};
}
async function readRuntime(data){
  try{
    const runtime=JSON.parse(fs.readFileSync(path.join(data,'.local/runtime.json'),'utf8'));
    const url=new URL(runtime.url);
    if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!Number.isInteger(runtime.hostPid))return null;
    process.kill(runtime.hostPid,0);
    // The main UI can work while optional plugins are disabled or still starting.
    let response=await fetch(url,{signal:AbortSignal.timeout(1200),redirect:'manual'});
    if(response.status===302||response.status===303){
      const location=response.headers.get('location'),cookies=response.headers.getSetCookie().map(value=>value.split(';',1)[0]).join('; ');
      await response.body?.cancel();
      if(!location||!cookies)return null;
      const next=new URL(location,url);
      if(next.origin!==url.origin||next.pathname!=='/'||next.search)return null;
      response=await fetch(next,{headers:{cookie:cookies},signal:AbortSignal.timeout(1200),redirect:'error'});
    }
    const ready=response.ok&&response.headers.get('content-type')?.includes('text/html');
    await response.body?.cancel();return ready?runtime:null;
  }catch{return null}
}
async function inspectHost(data){
  const runtime=await readRuntime(data),record=readHostRecord(data),control=await readControl(data);
  return {runtime,control,state:readHostState(data),hostAlive:runtime||control?processAlive(record?.hostPid):await hostProcessAlive(record),launcherAlive:await launcherOwnsPipe(data)};
}
function writeJson(file,value){const temporary=file+'.tmp';fs.writeFileSync(temporary,JSON.stringify(value));fs.renameSync(temporary,file);}
const freePort=(preferred=0)=>new Promise((resolve,reject)=>{
  const requested=Number.isInteger(preferred)&&preferred>0&&preferred<=65535?preferred:0;
  const server=net.createServer();
  server.once('error',error=>{
    if(requested&&['EADDRINUSE','EACCES'].includes(error.code))resolve(freePort());else reject(error);
  });
  server.listen(requested,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port))});
});
async function runHost({payload,data,store,app}){
  const events=createEventLog(data,'host'),initializingAt=Date.now();
  events('initialization_start');
  const initialized=initialize(payload,data);
  events('initialization_complete',{elapsedMs:Date.now()-initializingAt,phase:initialized.status});
  const local=path.join(data,'.local'),runtimePath=path.join(local,'runtime.json');
  let supervisor,readyUrl=null;
  // Preserve the browser origin across launcher restarts when its previous port is still free.
  const port=await freePort(readHostRecord(data)?.port);
  const controlToken=randomBytes(32).toString('hex');
  const control=http.createServer((request,response)=>{
    if(request.headers.authorization!==`Bearer ${controlToken}`){response.writeHead(403).end();return;}
    if(request.method==='GET'&&request.url==='/status'){response.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({launcherPid:process.pid,phase:supervisor?.state().phase||'starting'}));return;}
    if(request.method!=='POST'||!['/stop','/restart'].includes(request.url)){response.writeHead(403).end();return;}
    if(!supervisor){response.writeHead(503).end();return;}
    if(request.url==='/restart'){const started=supervisor.retry();response.writeHead(started?200:409).end();return;}
    response.writeHead(200).end('stopping');supervisor.stop();
  });
  await new Promise((resolve,reject)=>{control.once('error',reject);control.listen(0,'127.0.0.1',resolve)});
  const controlUrl=`http://127.0.0.1:${control.address().port}/stop`;
  const log=fs.createWriteStream(path.join(local,'host.log'),{flags:'a'});
  const kill=child=>{
    if(process.platform!=='win32'){child.kill();return;}
    const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
    killer.once('error',()=>child.kill());killer.once('exit',code=>{if(code&&processAlive(child.pid))child.kill()});
  };
  const result=await store.withSecret(async secret=>{
    let memoryRuntime;
    try{memoryRuntime=await createCaseMemoryRuntime({data,payload,secret});}catch{events('case_memory_unavailable');}
    supervisor=createSupervisor({log:events,kill,onStopped:()=>{void (async()=>{
      let code=0;try{await memoryRuntime?.stop();}catch{code=1;events('case_memory_shutdown_unconfirmed');}
      control.close();log.end(()=>app.exit(code));
    })();},
      onState:state=>{
        if(state.phase!=='running')readyUrl=null;
        writeJson(path.join(local,'host-state.json'),{...state,launcherPid:process.pid,time:new Date().toISOString()});
        writeJson(runtimePath,{url:readyUrl,hostPid:state.hostPid,launcherPid:process.pid,port,controlUrl,controlToken,controlProtocol:1});
      },start:onReady=>{
      const serviceStartedAt=Date.now();
      const child=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port',String(port)],{
        cwd:path.join(data,'workspace'),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,...memoryRuntime?.env,
          DSH_HOME:path.join(local,'dsh-home'),DEEPSEEK_API_KEY:secret,DSH_TELEMETRY_MODE:'OFF',
          PATH:path.join(payload,'runtime')+path.delimiter+(process.env.PATH||''),
          PYTHONPATH:path.join(payload,'legacy/src'),QX_LEGACY_ROOT:path.join(payload,'legacy'),
          BB_BROWSER_NODE:path.join(payload,'runtime/node.exe'),BB_BROWSER_CLI:path.join(payload,'browser/node_modules/bb-browser/dist/cli.js'),
        }});
      let pending='';
      const scrub=text=>text.replaceAll(secret,'[REDACTED]').replace(/([?&]token=)[^\s]+/g,'$1[REDACTED]');
      child.stdout.on('data',chunk=>{
        pending+=chunk.toString();let end;
        while((end=pending.indexOf('\n'))>=0){
          const line=pending.slice(0,end);pending=pending.slice(end+1);
          const match=line.match(/^dsh web: (http:\/\/127\.0\.0\.1:\d+\/\?token=\S+)/);
          if(match){readyUrl=match[1];onReady();events('service_listening',{elapsedMs:Date.now()-serviceStartedAt});log.write('本机工作台已启动。\n');}
          else log.write(scrub(line)+'\n');
        }
      });
      const errors=redactedLines(secret,text=>log.write(text));
      child.stderr.on('data',chunk=>errors.push(chunk));
      child.stderr.on('end',()=>errors.end());
      return child;
    }});
    supervisor.start();
  });
  if(result.status!=='saved'){
    control.close();log.end();events('credential_unavailable');throw Error('Credential unavailable');
  }
  return supervisor;
}
module.exports={initialize,readRuntime,readControl,readHostState,inspectHost,runHost,stopRuntime,stopInstalledHost,restartRuntime,redactedLines};
