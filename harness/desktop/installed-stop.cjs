// Kept independent of application dependencies so an upgrade can stop older hosts.
const fs=require('node:fs'),path=require('node:path'),net=require('node:net');
const {createHash}=require('node:crypto');
const execFile=require('node:util').promisify(require('node:child_process').execFile);
function processAlive(pid){if(!Number.isInteger(pid)||pid<=0)return false;try{process.kill(pid,0);return true}catch{return false}}
async function hostProcessAlive(record){
  if(!processAlive(record?.hostPid))return false;
  let port=record.port;try{port=port||Number(new URL(record.url).port)}catch{}
  if(process.platform!=='win32'||!Number.isInteger(port)||port<1||port>65535)return true;
  try{
    // Query only the recorded PID; a reused PID must never identify an unrelated process as our host.
    const command=`$p=Get-CimInstance Win32_Process -Filter "ProcessId = ${record.hostPid}" -ErrorAction Stop; if($p){$p | Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress}`;
    const {stdout}=await execFile('powershell.exe',['-NoProfile','-NonInteractive','-Command',command],{windowsHide:true,timeout:5000,maxBuffer:65536});
    if(!stdout.trim())return false;
    const info=JSON.parse(stdout);
    if(!info.ExecutablePath||!info.CommandLine)return true;
    const args=Array.from(info.CommandLine.matchAll(/"([^"]*)"|(\S+)/g),match=>match[1]??match[2]);
    return path.basename(info.ExecutablePath).toLowerCase()==='node.exe'&&
      args[1]?.replaceAll('\\','/').toLowerCase().endsWith('/@deepseek-ai/dsh/lib/bin.js')&&
      JSON.stringify(args.slice(2))===JSON.stringify(['web','--no-open','--host','127.0.0.1','--port',String(port)]);
  }catch{return true;} // Lack of process-query permission cannot authorize an unsafe replacement.
}
function readHostRecord(data){try{return JSON.parse(fs.readFileSync(path.join(data,'.local/runtime.json'),'utf8'))}catch{return null}}
function readHostState(data){try{return JSON.parse(fs.readFileSync(path.join(data,'.local/host-state.json'),'utf8'))}catch{return null}}
function hostPipe(data){
  let canonical=path.resolve(data);try{canonical=fs.realpathSync.native(canonical)}catch{}
  return '\\\\.\\pipe\\qx-host-'+createHash('sha256').update(canonical.toLowerCase()).digest('hex').slice(0,24);
}
function hostPipes(data){
  const legacy='\\\\.\\pipe\\qx-host-'+createHash('sha256').update(data.toLowerCase()).digest('hex').slice(0,24);
  return [...new Set([hostPipe(data),legacy])];
}
async function claimLauncher(data){
  const servers=[];
  const close=()=>Promise.all(servers.map(server=>new Promise(resolve=>server.close(resolve))));
  try{
    for(const pipe of hostPipes(data)){
      const server=net.createServer(socket=>socket.end());servers.push(server);
      await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(pipe,resolve)});
    }
    return {close};
  }catch(error){await close();throw error;}
}
function pipeOwned(pipe){
  return new Promise(resolve=>{
    const socket=net.createConnection(pipe);
    const done=value=>{socket.destroy();resolve(value)};
    socket.once('connect',()=>done(true));
    socket.once('error',error=>done(!['ENOENT','ECONNREFUSED'].includes(error.code)));
    socket.setTimeout(1200,()=>done(true));
  });
}
async function launcherOwnsPipe(data){
  for(const pipe of hostPipes(data))if(await pipeOwned(pipe))return true;
  return false;
}
function controlEndpoint(runtime){
  const url=new URL(runtime.controlUrl);
  if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.pathname!=='/stop'||url.username||url.password||url.search||url.hash||typeof runtime.controlToken!=='string'||!runtime.controlToken)throw Error('Invalid control endpoint');
  return url;
}
async function readControl(data){
  const runtime=readHostRecord(data);
  try{
    const state=readHostState(data);
    if(state?.phase==='stopped'&&state.launcherPid===runtime.launcherPid&&state.hostPid===null&&runtime.hostPid===null)return null;
    const url=controlEndpoint(runtime);
    if(!processAlive(runtime.launcherPid)||!await launcherOwnsPipe(data))return null;
    if(runtime.controlProtocol===1){
      url.pathname='/status';
      const response=await fetch(url,{headers:{Authorization:`Bearer ${runtime.controlToken}`},signal:AbortSignal.timeout(1200),redirect:'error'});
      if(!response.ok){await response.body?.cancel();return null;}
      const status=await response.json();
      if(status.launcherPid!==runtime.launcherPid)return null;
    }
    return runtime;
  }catch{return null}
}
async function restartRuntime(runtime){
  const url=controlEndpoint(runtime);url.pathname='/restart';
  const response=await fetch(url,{method:'POST',headers:{Authorization:`Bearer ${runtime.controlToken}`},signal:AbortSignal.timeout(5000),redirect:'error'});
  await response.body?.cancel();if(!response.ok)throw Error('Background restart failed');
}
async function stopRuntime(runtime,data){
  const url=controlEndpoint(runtime);
  const response=await fetch(url,{method:'POST',headers:{Authorization:`Bearer ${runtime.controlToken}`},signal:AbortSignal.timeout(5000),redirect:'error'});
  await response.body?.cancel();if(!response.ok)throw Error('Background stop failed');
  const deadline=Date.now()+45000;
  while(Date.now()<deadline){
    // The OS lock is released on process exit, and cannot be confused with a reused PID.
    if(data?!await launcherOwnsPipe(data):!processAlive(runtime.launcherPid))return;
    await new Promise(resolve=>setTimeout(resolve,200));
  }
  throw Error('Background stop timed out');
}
async function stopInstalledHost(data){
  const runtime=await readControl(data);
  if(runtime)await stopRuntime(runtime,data);
  if(await hostProcessAlive(readHostRecord(data))||await launcherOwnsPipe(data))throw Error('Background control unavailable');
}
module.exports={processAlive,hostProcessAlive,readHostRecord,readHostState,hostPipe,claimLauncher,launcherOwnsPipe,readControl,restartRuntime,stopRuntime,stopInstalledHost};
