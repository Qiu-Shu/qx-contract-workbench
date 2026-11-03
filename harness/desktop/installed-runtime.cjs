const fs=require('node:fs');
const path=require('node:path');
const net=require('node:net');
const http=require('node:http');
const {randomBytes}=require('node:crypto');
const {spawn}=require('node:child_process');
const {migrateInstalledKnowledge,migrateInstalledPrivacy,migrateInstalledContract,migrateInstalledModelRecovery}=require('./installed-migrations.cjs');

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
  const local=path.join(data,'.local'),profile=path.join(local,'dsh-home/profiles/web');
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
  const portableConfig=transform(JSON.parse(fs.readFileSync(path.join(payload,'config/portable.json'),'utf8')));
  if(!fs.existsSync(patch))fs.writeFileSync(patch,JSON.stringify(portableConfig,null,2));
  migrateInstalledKnowledge({data,payload,portableConfig,
    seedInstructions:transform(fs.readFileSync(path.join(payload,'workspace-seed/AGENTS.md'),'utf8'))});
  migrateInstalledPrivacy({data,payload,portableConfig});
  migrateInstalledModelRecovery({data,payload,portableConfig});
  migrateInstalledContract({data,payload});
  const pkg=JSON.parse(fs.readFileSync(path.join(payload,'config/profile-package.json'),'utf8'));
  fs.writeFileSync(path.join(profile,'package.json'),JSON.stringify(pkg,null,2));
  fs.copyFileSync(path.join(payload,'config/profile-cordis.yml'),path.join(profile,'cordis.yml'));
  // One link to bundled dependencies; no installation or network needed at startup.
  const modules=path.join(profile,'node_modules'),target=path.join(payload,'node_modules');
  if(!fs.existsSync(modules))fs.symlinkSync(target,modules,'junction');
}
async function readRuntime(data){
  try{
    const runtime=JSON.parse(fs.readFileSync(path.join(data,'.local/runtime.json'),'utf8'));
    const url=new URL(runtime.url);
    if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||!Number.isInteger(runtime.hostPid))return null;
    process.kill(runtime.hostPid,0);
    const response=await fetch(new URL('/qx-wechat/state',url),{signal:AbortSignal.timeout(1200)});
    return response.ok?runtime:null;
  }catch{return null}
}
const freePort=()=>new Promise((resolve,reject)=>{
  const server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port))});
});
async function runHost({payload,data,store,app}){
  initialize(payload,data);
  const local=path.join(data,'.local'),runtimePath=path.join(local,'runtime.json');
  let child;
  const controlToken=randomBytes(32).toString('hex');
  const control=http.createServer((request,response)=>{
    if(request.method!=='POST'||request.url!=='/stop'||request.headers.authorization!==`Bearer ${controlToken}`){response.writeHead(403).end();return;}
    response.writeHead(200).end('stopping');
    if(child){
      if(process.platform==='win32'){
        const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
        killer.once('error',()=>child.kill());
      }else child.kill();
    }else app.exit(0);
  });
  await new Promise((resolve,reject)=>{control.once('error',reject);control.listen(0,'127.0.0.1',resolve)});
  const controlUrl=`http://127.0.0.1:${control.address().port}/stop`;
  const log=fs.createWriteStream(path.join(local,'host.log'),{flags:'a'});
  async function start(){
    const port=await freePort();
    const result=await store.withSecret(secret=>{
      child=spawn(path.join(payload,'runtime/node.exe'),[path.join(payload,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'web','--no-open','--host','127.0.0.1','--port',String(port)],{
        cwd:path.join(data,'workspace'),windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,
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
          if(match){fs.writeFileSync(runtimePath,JSON.stringify({url:match[1],hostPid:child.pid,launcherPid:process.pid,port,controlUrl,controlToken}));log.write('本机工作台已启动。\n');}
          else log.write(scrub(line)+'\n');
        }
      });
      const errors=redactedLines(secret,text=>log.write(text));
      child.stderr.on('data',chunk=>errors.push(chunk));
      child.stderr.on('end',()=>errors.end());
      child.on('error',()=>{log.write('本机服务进程启动失败。\n');app.exit(1)});
      child.on('close',code=>app.exit(code||0));
    });
    if(result.status!=='saved'){
      fs.appendFileSync(path.join(local,'host.log'),'加密配置读取失败：'+result.status+' '+(result.code||'')+'\n');
      throw Error('Credential unavailable');
    }
  }
  await start();
}
async function stopRuntime(runtime){
  const url=new URL(runtime.controlUrl);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.pathname!=='/stop')throw Error('Invalid control endpoint');
  const response=await fetch(url,{method:'POST',headers:{Authorization:`Bearer ${runtime.controlToken}`},signal:AbortSignal.timeout(5000),redirect:'error'});
  if(!response.ok)throw Error('Background restart failed');
  const deadline=Date.now()+15000;
  while(Date.now()<deadline){
    try{process.kill(runtime.launcherPid,0)}catch{return}
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw Error('Background stop timed out');
}
module.exports={initialize,readRuntime,runHost,stopRuntime,redactedLines};
