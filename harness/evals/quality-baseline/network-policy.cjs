// Development-run policy for audited dependencies, not an OS sandbox for hostile code/native addons.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net'),dns=require('node:dns');
const {AsyncLocalStorage}=require('node:async_hooks');
const {syncBuiltinESMExports}=require('node:module');
const childProcess=require('node:child_process');
let installed;
const modelOrigin='https://api.deepseek.com/chat/completions';
function install({log,python}){
 if(installed)throw Error('Evaluation network policy already installed');
 if(!path.isAbsolute(log))throw Error('Evaluation audit path must be absolute');
 const context=new AsyncLocalStorage(),rawFetch=globalThis.fetch;
 const live=process.env.QX_EVAL_MODE==='live'&&process.env.QX_REAL_MODEL_TEST==='1'
  &&Number(process.env.QX_EVAL_BUDGET_CNY)>0.5&&Number(process.env.QX_EVAL_BUDGET_CNY)<=20&&Boolean(process.env.DEEPSEEK_API_KEY);
 const record=(event,operation)=>fs.appendFileSync(log,JSON.stringify({event,operation,pid:process.pid,runtime:'node'})+'\n');
 function deny(operation){record('denied',operation);throw Object.assign(Error('Evaluation network/process request denied: '+operation),{code:'EVAL_NETWORK_DENIED'});}
 const blocked=operation=>()=>deny(operation);
 const socketConnect=net.Socket.prototype.connect;
 net.Socket.prototype.connect=function(...args){
  const values=Array.isArray(args[0])?args[0]:args;
  const options=typeof values[0]==='object'?values[0]:{port:values[0],host:values[1]};
  if(!context.getStore()||options.host!=='api.deepseek.com'||Number(options.port)!==443)deny('socket.connect');
  return socketConnect.apply(this,args);
 };
 for(const target of [dns,dns.promises])for(const name of Object.keys(target)){
  if(!/^(?:lookup|resolve|reverse)/.test(name)||typeof target[name]!=='function')continue;
  const original=target[name];
  target[name]=function(host,...args){
   if(name!=='lookup'||!context.getStore()||host!=='api.deepseek.com')deny('dns.'+name);
   return original.call(this,host,...args);
  };
 }
 for(const Type of [dns.Resolver,dns.promises.Resolver])for(const name of Object.getOwnPropertyNames(Type.prototype)){
  if(/^(?:resolve|reverse)/.test(name))Type.prototype[name]=blocked('dns.Resolver.'+name);
 }
 const Datagram=require('node:dgram').Socket;
 for(const name of ['send','connect'])Datagram.prototype[name]=blocked('udp.'+name);
 globalThis.fetch=async()=>deny('fetch');
 require('node:worker_threads').Worker=class{constructor(){deny('worker');}};
 const spawn=childProcess.spawn,relay=path.join(__dirname,'relay.py'),guard=path.join(__dirname,'guarded-python.py');
 const pythonPath=python&&path.isAbsolute(python)?fs.realpathSync(python):null;
 const pythonPathEnv=process.env.PYTHONPATH||'';
 childProcess.spawn=function(command,args,options={}){
  if(!pythonPath||!path.isAbsolute(command)||fs.realpathSync(command)!==pythonPath||!Array.isArray(args)
   ||args.length!==1||path.resolve(args[0])!==relay||options.shell||options.detached)deny('child_process.spawn');
  const env={...options.env,PYTHONPATH:pythonPathEnv,PYTHONINSPECT:'',PYTHONSTARTUP:'',NODE_OPTIONS:'',
   QX_EVAL_NETWORK_LOG:log,DEEPSEEK_API_KEY:'',OPENAI_API_KEY:'',ANTHROPIC_API_KEY:''};
  return spawn(command,[guard,relay],{...options,env});
 };
 for(const name of ['spawnSync','exec','execSync','execFile','execFileSync','fork'])childProcess[name]=blocked('child_process.'+name);
 syncBuiltinESMExports();
 installed={record,deny,live,context,rawFetch};record('guard_ready','default_deny');
}
async function modelFetch(url,options){
 // Direct adapter unit tests supply a fake global fetch; official runs always preload this policy.
 if(!installed)return globalThis.fetch(url,options);
 if(!installed.live||url!==modelOrigin||options?.method!=='POST'||options.dispatcher||options.agent)installed.deny('model.fetch');
 installed.record('model_request','approved_endpoint');
 return installed.context.run(true,()=>installed.rawFetch(url,{...options,redirect:'error'}));
}
function summarize(log){
 const events=fs.readFileSync(log,'utf8').trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
 const denied=events.filter(e=>e.event==='denied');
 return {policy:'audited-runtime-default-deny',deniedAttempts:denied.length,
  guardedProcesses:events.filter(e=>e.event==='guard_ready'),modelRequests:events.filter(e=>e.event==='model_request').length,
  telemetryPatched:events.some(e=>e.event==='telemetry_patch'),configProbePatched:events.some(e=>e.event==='config_probe_patch'),passed:denied.length===0};
}
module.exports={install,modelFetch,summarize};
