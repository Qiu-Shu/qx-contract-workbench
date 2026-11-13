const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const net=require('node:net');
const {spawn}=require('node:child_process');
const {randomBytes,randomUUID,timingSafeEqual,createHash}=require('node:crypto');
const {assertRestoreReviewed}=require('./installed-stop.cjs');

const VERSION='1.2.0';
const REQUIREMENTS='hindsight-api-slim[embedded-db,local-onnx]==1.2.0\npg0-embedded==0.15.2\n';
const messages={
  'not-installed':'案件来源账本已启用；增强记忆引擎尚未安装。点击一键准备将下载本机运行组件和模型。',
  installing:'正在下载并安装本机增强记忆组件；首次准备需要网络连接，请保持工作台开启。',
  starting:'正在启动本机数据库和本地检索模型；首次加载可能需要下载模型。',
  ready:'增强记忆引擎已就绪。只有明确选中的记忆会使用已保存的 DeepSeek 密钥调用 Flash 模型。',
  error:'增强记忆引擎暂不可用。请检查网络、可用空间和模型设置后重试；本机来源账本仍可使用。',
  stopped:'增强记忆引擎已停止；本机来源账本仍可使用。',
};
function safeEnvironment(){
  const env={};
  for(const key of ['SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATH','PATHEXT','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','PROGRAMDATA'])if(process.env[key])env[key]=process.env[key];
  return {...env,PYTHONIOENCODING:'utf-8',PYTHONUNBUFFERED:'1',PYTHON_DOTENV_DISABLED:'1',PYTHONNOUSERSITE:'1'};
}
function buildServiceEnvironment({root,instance,secret,token,port,model}){
  const directory=path.resolve(root),identity=process.platform==='win32'?directory.toLowerCase():directory;
  const name=`qx-${instance.id}-${createHash('sha256').update(identity).digest('hex').slice(0,16)}`;
  return {...safeEnvironment(),QX_MEMORY_SERVICE_TOKEN:token,QX_MEMORY_SERVICE_PORT:String(port),
    QX_MEMORY_DATABASE_DIR:path.join(root,'database'),HF_HOME:path.join(root,'models'),HF_HUB_DISABLE_TELEMETRY:'1',HF_HUB_DISABLE_XET:'1',DO_NOT_TRACK:'1',TOKENIZERS_PARALLELISM:'false',OMP_NUM_THREADS:'2',LITELLM_LOCAL_MODEL_COST_MAP:'True',
    HINDSIGHT_API_HOST:'127.0.0.1',HINDSIGHT_API_PORT:String(port),HINDSIGHT_API_WORKERS:'1',
    HINDSIGHT_API_DATABASE_URL:`pg0://qx_memory:${instance.databasePassword}@${name}?listen_addresses=127.0.0.1&shared_buffers=128MB&work_mem=8MB`,
    HINDSIGHT_API_TENANT_EXTENSION:'hindsight_api.extensions.builtin.tenant:ApiKeyTenantExtension',HINDSIGHT_API_TENANT_API_KEY:token,
    HINDSIGHT_API_LLM_PROVIDER:'openai',HINDSIGHT_API_LLM_BASE_URL:'https://api.deepseek.com/v1',HINDSIGHT_API_LLM_MODEL:model,HINDSIGHT_API_LLM_API_KEY:secret,
    HINDSIGHT_API_LLM_STRICT_SCHEMA:'false',HINDSIGHT_API_LLM_OPENAI_COMPATIBLE_JSON_MODE:'true',
    HINDSIGHT_API_EMBEDDINGS_PROVIDER:'onnx',HINDSIGHT_API_EMBEDDINGS_ONNX_MODEL_ID:'intfloat/multilingual-e5-small',
    HINDSIGHT_API_EMBEDDINGS_ONNX_BATCH_SIZE:'4',HINDSIGHT_API_EMBEDDINGS_ONNX_DEVICE:'cpu',HINDSIGHT_API_RERANKER_PROVIDER:'rrf',
    HINDSIGHT_API_ENABLE_AUTO_CONSOLIDATION:'false',HINDSIGHT_API_ENABLE_OBSERVATIONS:'false',HINDSIGHT_API_MCP_ENABLED:'false',HINDSIGHT_API_SKIP_LLM_VERIFICATION:'true',
  };
}
function lockFromPlan(plan){
  if(!Array.isArray(plan.install)||!plan.install.length)throw Error('Empty dependency plan');
  return plan.install.map(row=>{
    const name=row.metadata?.name,info=row.download_info,url=new URL(info?.url),hash=info?.archive_info?.hashes?.sha256;
    if(typeof name!=='string'||/^(torch|nvidia|triton)(-|$)/i.test(name)||url.protocol!=='https:'||url.hostname!=='files.pythonhosted.org'||!url.pathname.endsWith('.whl')||!/^\w[\w.-]*$/.test(name)||!/^[a-f0-9]{64}$/.test(hash))throw Error('Unsupported dependency in installation plan');
    return `${name} @ ${url.href} --hash=sha256:${hash}`;
  }).join('\n')+'\n';
}
function atomicJson(file,value){const temp=file+'.'+randomUUID()+'.tmp';try{fs.writeFileSync(temp,JSON.stringify(value,null,2)+'\n',{mode:0o600,flag:'wx'});fs.renameSync(temp,file);}finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}}
function noLinks(base,target){let current=base;for(const part of path.relative(base,target).split(path.sep)){current=path.join(current,part);try{if(fs.lstatSync(current).isSymbolicLink())throw Error('Linked runtime directory is not supported');}catch(e){if(e.code!=='ENOENT')throw e;}}}
function alive(pid){if(!Number.isInteger(pid)||pid<1)return false;try{process.kill(pid,0);return true;}catch{return false;}}
const wait=ms=>new Promise(resolve=>{const timer=setTimeout(resolve,ms);timer.unref?.();});
const freePort=()=>new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port));});});

// Native API authentication is enforced even on routes without tenant-extension hooks.
// stdin EOF is a parent-death signal; graceful app shutdown also stops this instance's pg0.
const SERVICE=String.raw`import asyncio, hmac, os, sys
from pathlib import Path
DATABASE_URL=os.environ['HINDSIGHT_API_DATABASE_URL']

def owned_database():
    from pg0 import Pg0
    from urllib.parse import urlsplit, parse_qsl
    parsed=urlsplit(DATABASE_URL)
    directory=Path(os.environ['QX_MEMORY_DATABASE_DIR']).resolve()
    pg=Pg0(name=parsed.hostname,username=parsed.username,password=parsed.password,database='hindsight',data_dir=str(directory),config=dict(parse_qsl(parsed.query)))
    prior=pg.info()
    if (prior.running and not prior.data_dir) or (prior.data_dir and Path(prior.data_dir).resolve()!=directory):
        raise RuntimeError('Owned database path does not match runtime data directory')
    return pg,prior

def stop_database():
    pid_file=Path(os.environ['QX_MEMORY_DATABASE_DIR'])/'postmaster.pid'
    if not pid_file.exists(): return
    pg,prior=owned_database()
    # pg0 health can fail while its owned postmaster is still alive.
    if prior.data_dir: pg.stop()
    if pid_file.exists(): raise RuntimeError('Owned database shutdown could not be verified')

def parent_stopped():
    if os.name=='nt':
        # Poll without blocking CRT stdin while NumPy/ONNX load native DLLs.
        import ctypes, msvcrt
        from ctypes import wintypes
        available=wintypes.DWORD()
        ok=ctypes.windll.kernel32.PeekNamedPipe(wintypes.HANDLE(msvcrt.get_osfhandle(0)),None,0,None,ctypes.byref(available),None)
        return not ok or available.value>0
    import select
    return bool(select.select([sys.stdin],[],[],0)[0])
async def main():
    pg,prior=owned_database()
    started=False
    try:
        if parent_stopped(): return
        info=prior if prior and prior.running else await asyncio.to_thread(pg.start)
        started=True
        os.environ['HINDSIGHT_API_DATABASE_URL']=info.uri
        import uvicorn
        from hindsight_api.server import app
        token=os.environ['QX_MEMORY_SERVICE_TOKEN'].encode()
        async def guarded(scope,receive,send):
            if scope['type']=='http':
                headers=dict(scope.get('headers',[]))
                if b'origin' in headers or not hmac.compare_digest(headers.get(b'authorization',b''),b'Bearer '+token):
                    await send({'type':'http.response.start','status':403,'headers':[(b'content-type',b'application/json')]})
                    await send({'type':'http.response.body','body':b'{"error":"unauthorized"}'})
                    return
            await app(scope,receive,send)
        server=uvicorn.Server(uvicorn.Config(guarded,host='127.0.0.1',port=int(os.environ['QX_MEMORY_SERVICE_PORT']),access_log=False,log_level='warning',timeout_graceful_shutdown=10))
        async def monitor():
            while not parent_stopped(): await asyncio.sleep(0.25)
            server.should_exit=True
        task=asyncio.create_task(monitor())
        try:
            if not parent_stopped(): await server.serve()
        finally: task.cancel()
    finally:
        if started:
            try: await asyncio.to_thread(stop_database)
            except Exception: pass
if __name__=='__main__':
    if sys.argv[1:]==['--stop-database']: stop_database()
    else: asyncio.run(main())
`;

async function createCaseMemoryRuntime({data,payload,python,secret='',model=process.env.QX_CASE_MEMORY_MODEL||'deepseek-flash',spawnProcess=spawn,startupTimeoutMs=900000}){
  assertRestoreReviewed(data);
  data=path.resolve(data);let root=path.join(data,'.local/case-memory-runtime');noLinks(data,root);fs.mkdirSync(root,{recursive:true});root=fs.realpathSync.native(root);
  for(const entry of fs.readdirSync(root))noLinks(root,path.join(root,entry));
  const instancePath=path.join(root,'instance.json');
  if(!fs.existsSync(instancePath)){
    try{fs.writeFileSync(instancePath,JSON.stringify({id:randomUUID(),databasePassword:randomBytes(32).toString('hex')}),{flag:'wx',mode:0o600});}catch(error){if(error.code!=='EEXIST')throw error;}
  }
  const instance=JSON.parse(fs.readFileSync(instancePath,'utf8'));
  if(!/^[a-f0-9-]{36}$/.test(instance.id)||!/^[a-f0-9]{64}$/.test(instance.databasePassword))throw Error('Invalid case-memory datastore identity');
  if(!/^[a-zA-Z0-9_.:/-]{1,100}$/.test(model))throw Error('Invalid case-memory model');
  const marker=path.join(root,'installed.json'),venv=path.join(root,'venv'),interpreter=path.join(venv,process.platform==='win32'?'Scripts/python.exe':'bin/python');
  const isInstalled=()=>{try{return JSON.parse(fs.readFileSync(marker,'utf8')).version===VERSION&&fs.statSync(interpreter).isFile();}catch{return false;}};
  const controlToken=randomBytes(32).toString('hex'),engineToken=randomBytes(32).toString('hex');
  let phase=isInstalled()?'stopped':'not-installed',job=null,child=null,installer=null,enginePort=null,disposed=false,ownsLock=false,serviceStarted=false,stopPromise=null;
  const state=()=>({phase,message:messages[phase],engine:'hindsight',version:VERSION,databaseMode:'embedded-cache',model,instanceId:instance.id});
  function setPhase(next){phase=next;try{atomicJson(path.join(root,'status.json'),state());}catch{}}
  const lockPath=path.join(root,'owner.json'),owner={pid:process.pid,nonce:randomUUID()};
  function claim(){
    if(ownsLock)return;
    if(fs.existsSync(lockPath)){
      const text=fs.readFileSync(lockPath,'utf8'),prior=JSON.parse(text);
      if(alive(prior.pid))throw Error('Another process owns the memory engine');
      if(fs.readFileSync(lockPath,'utf8')!==text)throw Error('Memory owner changed');fs.unlinkSync(lockPath);
    }
    fs.writeFileSync(lockPath,JSON.stringify(owner),{flag:'wx',mode:0o600});ownsLock=true;
  }
  function release(){if(ownsLock){try{if(JSON.parse(fs.readFileSync(lockPath,'utf8')).nonce===owner.nonce)fs.unlinkSync(lockPath);}catch{}ownsLock=false;}}
  function logProcess(proc){
    // Never persist raw provider output: it can contain credential URLs or retained case text.
    proc.stdout?.resume();proc.stderr?.resume();
  }
  function execute(command,args,timeoutMs=1200000){return new Promise((resolve,reject)=>{
    if(disposed){reject(Error('Runtime stopped'));return;}
    installer=spawnProcess(command,args,{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:safeEnvironment()});
    const current=installer;logProcess(current);const timer=setTimeout(()=>{current.kill();reject(Error('Preparation timed out'));},timeoutMs);
    current.once('error',error=>{clearTimeout(timer);if(installer===current)installer=null;reject(error);});
    current.once('close',code=>{clearTimeout(timer);if(installer===current)installer=null;code===0?resolve():reject(Error('Preparation command failed'));});
  });}
  async function install(){
    setPhase('installing');
    python=python||path.join(payload,'runtime/python/python.exe');
    if(!fs.existsSync(interpreter))await execute(python,['-m','venv',venv]);
    const requirements=path.join(root,'requirements.in'),report=path.join(root,'dependency-plan.json'),lock=path.join(root,'requirements.lock');
    fs.writeFileSync(requirements,REQUIREMENTS);
    const bundledLock=[path.join(payload,'config/case-memory-requirements.lock'),path.join(payload,'packaging/case-memory-requirements.lock')].find(file=>fs.existsSync(file));
    if(bundledLock)fs.copyFileSync(bundledLock,lock);
    else{
      await execute(interpreter,['-m','pip','--isolated','install','--dry-run','--ignore-installed','--only-binary=:all:','--report',report,'-r',requirements]);
      fs.writeFileSync(lock,lockFromPlan(JSON.parse(fs.readFileSync(report,'utf8'))));
    }
    await execute(interpreter,['-m','pip','--isolated','install','--no-deps','--require-hashes','--only-binary=:all:','-r',lock]);
    await execute(interpreter,['-c','import importlib.metadata as m; import onnxruntime,pg0; assert m.version("hindsight-api-slim")=="1.2.0"']);
    atomicJson(marker,{version:VERSION,preparedAt:new Date().toISOString()});
  }
  async function terminateOwned(current){
    if(current.exitCode!==null)return;
    if(process.platform==='win32'&&current.pid){
      await new Promise(resolve=>{const killer=spawn('taskkill',['/PID',String(current.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});killer.once('error',resolve);killer.once('close',resolve);});
    }else current.kill('SIGKILL');
  }
  function stopEngine(){
    if(!stopPromise)stopPromise=stopEngineOnce().catch(error=>{setPhase('error');throw error;}).finally(()=>{stopPromise=null;});
    return stopPromise;
  }
  async function stopEngineOnce(){
    const current=child;child=null;enginePort=null;
    if(current){
      const done=new Promise(resolve=>{if(current.exitCode!==null)resolve();else current.once('close',resolve);});
      current.stdin?.end('stop\n');
      await Promise.race([done,wait(12000)]);
      if(current.exitCode===null){
        await terminateOwned(current);
        await Promise.race([done,wait(2000)]);
      }
    }
    if(serviceStarted&&ownsLock){
      if(!fs.existsSync(interpreter))throw Error('Owned database shutdown could not be verified');
      const stopped=await new Promise(resolve=>{
        const cleaner=spawnProcess(interpreter,['-u',path.join(root,'service.py'),'--stop-database'],{cwd:root,windowsHide:true,stdio:'ignore',env:buildServiceEnvironment({root,instance,secret:'',token:'',port:0,model})});
        const timer=setTimeout(()=>{cleaner.kill();resolve(false);},15000);cleaner.once('error',()=>{clearTimeout(timer);resolve(false);});cleaner.once('close',code=>{clearTimeout(timer);resolve(code===0);});
      });
      if(!stopped){setPhase('error');throw Error('Owned database shutdown could not be verified');}
    }
    serviceStarted=false;
    release();setPhase('stopped');
  }
  async function startEngine(){
    if(!secret)throw Error('Model credential unavailable');
    setPhase('starting');enginePort=await freePort();
    const service=path.join(root,'service.py');fs.writeFileSync(service,SERVICE);
    const current=spawnProcess(interpreter,['-u',service],{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:buildServiceEnvironment({root,instance,secret,token:engineToken,port:enginePort,model})});
    child=current;serviceStarted=true;logProcess(current);
    let exited=false;current.once('error',()=>{exited=true;if(child===current){child=null;enginePort=null;setPhase('error');}});
    current.once('close',()=>{exited=true;if(child===current){child=null;enginePort=null;setPhase('error');}});
    const deadline=Date.now()+startupTimeoutMs;
    while(Date.now()<deadline&&!disposed&&!exited&&child===current){
      try{
        const response=await fetch(`http://127.0.0.1:${enginePort}/health/ready`,{headers:{Authorization:`Bearer ${engineToken}`},signal:AbortSignal.timeout(2000),redirect:'error'});
        if(response.ok){
          const banks=await fetch(`http://127.0.0.1:${enginePort}/v1/default/banks`,{headers:{Authorization:`Bearer ${engineToken}`},signal:AbortSignal.timeout(2000),redirect:'error'});
          const denied=await fetch(`http://127.0.0.1:${enginePort}/v1/default/banks`,{signal:AbortSignal.timeout(2000),redirect:'error'});
          if(banks.ok&&[401,403].includes(denied.status)){setPhase('ready');return;}
        }
      }catch{}
      await wait(750);
    }
    throw Error('Engine did not become authenticated and ready');
  }
  function prepare(){
    if(job)return job;if(disposed)return Promise.resolve(state());if(phase==='ready')return Promise.resolve(state());
    job=(async()=>{
      try{if(child)await stopEngine();claim();if(!isInstalled())await install();if(!disposed)await startEngine();}
      catch{try{await stopEngine();}catch{}if(!disposed)setPhase('error');}
      finally{job=null;}return state();
    })();return job;
  }
  const server=http.createServer((request,response)=>{
    const send=(code,value)=>{response.writeHead(code,{'content-type':'application/json','cache-control':'no-store'});response.end(JSON.stringify(value));};
    if(request.headers.origin){send(403,{error:'Origin not permitted'});return;}
    const proxy=request.url?.startsWith('/engine/'),expected=Buffer.from(`Bearer ${proxy?engineToken:controlToken}`),received=Buffer.from(String(request.headers.authorization||''));
    if(received.length!==expected.length||!timingSafeEqual(received,expected)){send(401,{error:'Authentication required'});return;}
    if(!proxy){
      if(request.method==='GET'&&request.url==='/status'){
        void (async()=>{
          if(phase==='ready'){
            try{const health=await fetch(`http://127.0.0.1:${enginePort}/health/ready`,{headers:{Authorization:`Bearer ${engineToken}`},signal:AbortSignal.timeout(2000),redirect:'error'});if(!health.ok)setPhase('error');}
            catch{setPhase('error');}
          }
          send(200,state());
        })();return;
      }
      if(request.method==='POST'&&request.url==='/prepare'){void prepare();send(202,state());return;}
      send(404,{error:'Not found'});return;
    }
    const target=request.url.slice('/engine'.length);
    if(!/^\/(?:health(?:\/ready)?(?:\?|$)|v1\/default\/banks(?:\/|\?|$))/.test(target)){send(404,{error:'Not found'});return;}
    if(phase!=='ready'||!enginePort){
      if(phase==='stopped'&&isInstalled())void prepare();
      send(503,{error:'Memory engine is not ready'});return;
    }
    const upstream=http.request({host:'127.0.0.1',port:enginePort,path:target,method:request.method,headers:{authorization:`Bearer ${engineToken}`,'content-type':'application/json'},timeout:360000},incoming=>{
      if(incoming.statusCode>=300&&incoming.statusCode<400){incoming.resume();send(502,{error:'Unexpected engine redirect'});return;}
      response.writeHead(incoming.statusCode,{'content-type':incoming.headers['content-type']||'application/json','cache-control':'no-store'});incoming.pipe(response);
    });
    upstream.on('timeout',()=>upstream.destroy());upstream.on('error',()=>{if(!response.headersSent)send(503,{error:'Memory engine unavailable'});else response.destroy();});
    let size=0;request.on('data',chunk=>{size+=chunk.length;if(size>8*1024*1024){upstream.destroy();request.destroy();}});request.on('aborted',()=>upstream.destroy());request.pipe(upstream);
  });
  server.requestTimeout=370000;server.headersTimeout=15000;
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
  const base=`http://127.0.0.1:${server.address().port}`;
  setPhase(phase);
  const result={env:{QX_CASE_MEMORY_CONTROL_URL:base,QX_CASE_MEMORY_CONTROL_TOKEN:controlToken,QX_HINDSIGHT_URL:base+'/engine',QX_HINDSIGHT_TOKEN:engineToken,QX_HINDSIGHT_INSTANCE_ID:instance.id},status:state,prepare,
    async stop(){
      if(disposed&&!serviceStarted)return;disposed=true;
      try{if(installer)await terminateOwned(installer);await stopEngine();}
      finally{if(server.listening){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}}
    }};
  return result;
}
module.exports={createCaseMemoryRuntime,buildServiceEnvironment,lockFromPlan};
