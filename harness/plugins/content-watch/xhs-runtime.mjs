import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {mkdir,readFile,writeFile,chmod,stat} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {setTimeout as pause} from 'node:timers/promises';
import {localServiceUrl} from './xiaohongshu.mjs';

const unavailable=()=>Object.assign(new Error('小红书组件未能启动，请稍后重新连接。本机登录资料已保留。'),{code:'COMPONENT_UNAVAILABLE'});
const missing=()=>Object.assign(new Error('请先准备小红书连接组件，再扫码连接。'),{code:'COMPONENT_MISSING'});

export function createXhsRuntime({stateDir,executable,baseUrl='http://127.0.0.1:18060',spawnImpl=spawn,fetchImpl=fetch,readyTimeoutMs=180000,pollMs=500}={}){
  if(!stateDir)throw new Error('小红书组件需要独立的本机资料目录。');
  const root=resolve(stateDir),authDir=join(root,'auth'),cookiePath=join(authDir,'cookies.json'),tokenPath=join(authDir,'service-token');
  const binary=executable?resolve(executable):join(root,'runtime',process.platform==='win32'?'xiaohongshu-mcp.exe':'xiaohongshu-mcp');
  const origin=localServiceUrl(baseUrl),address=new URL(origin),control=new AbortController();
  let token='',child=null,preparing=null,stopped=false;

  async function initialize(){
    await mkdir(authDir,{recursive:true,mode:0o700});
    if(process.platform!=='win32'){await chmod(root,0o700);await chmod(authDir,0o700);}
    try{token=(await readFile(tokenPath,'utf8')).trim();}
    catch(error){if(error.code!=='ENOENT')throw error;token=randomBytes(32).toString('hex');await writeFile(tokenPath,token,{flag:'wx',mode:0o600});}
    if(!/^[a-f0-9]{64}$/.test(token))throw unavailable();
    try{await writeFile(cookiePath,'[]',{flag:'wx',mode:0o600});}catch(error){if(error.code!=='EEXIST')throw error;}
    if(process.platform!=='win32'){await chmod(cookiePath,0o600);await chmod(tokenPath,0o600);}
  }
  function options(headers={},body){
    return {method:body?'POST':'GET',redirect:'error',headers:{accept:'application/json',...headers},...(body?{body}:{}),
      signal:AbortSignal.any([control.signal,AbortSignal.timeout(3000)])};
  }
  async function probe(){
    let response,value;
    try{response=await fetchImpl(origin+'/health',options());value=await response.json();}catch{return false;}
    if(!response.ok||value?.success!==true||value.data?.service!=='xiaohongshu-mcp')throw unavailable();
    // This invalid, read-only search checks local authentication without opening a site browser.
    const path=origin+'/api/v1/feeds/search';
    const accepted=await fetchImpl(path,options({'content-type':'application/json',authorization:'Bearer '+token},'{}'));
    const code=(await accepted.json())?.code;
    if(accepted.status!==400||!['INVALID_REQUEST','MISSING_KEYWORD'].includes(code))throw unavailable();
    const unauthenticated=await fetchImpl(path,options({'content-type':'application/json'},'{}'));
    if(unauthenticated.status!==401)throw unavailable();
    return true;
  }
  async function stopOwned(){
    const owned=child;child=null;
    if(!owned||owned.exitCode!==null)return;
    if(process.platform==='win32'&&owned.pid){
      const killer=spawnImpl('taskkill',['/PID',String(owned.pid),'/T','/F'],{windowsHide:true,stdio:'ignore',shell:false});
      killer.on('error',()=>owned.kill());
    }else owned.kill();
  }
  async function start(){
    try{
      await initialize();if(stopped)throw unavailable();
      if(await probe())return {ready:true};
      try{if(!(await stat(binary)).isFile())throw missing();}catch(error){if(error.code==='ENOENT'||error.code==='COMPONENT_MISSING')throw missing();throw error;}
      if(stopped)throw unavailable();
      const inherited=['PATH','Path','SystemRoot','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','TMPDIR','HOME','USERPROFILE','LOCALAPPDATA','APPDATA','XDG_CACHE_HOME','XDG_CONFIG_HOME','DISPLAY','WAYLAND_DISPLAY','LANG','LC_ALL','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY'];
      const env=Object.fromEntries(inherited.filter(key=>process.env[key]!==undefined).map(key=>[key,process.env[key]]));
      let failed=false;
      const owned=spawnImpl(binary,['-headless=true','-port='+address.host],{cwd:root,env:{...env,COOKIES_PATH:cookiePath,AUTH_TOKEN:token},windowsHide:true,stdio:'ignore',shell:false});
      child=owned;
      owned.on('error',()=>{failed=true;});
      owned.once('exit',()=>{failed=true;if(child===owned)child=null;});
      const deadline=Date.now()+readyTimeoutMs;
      while(!stopped&&!failed&&Date.now()<deadline){
        if(await probe()){if(stopped||failed)throw unavailable();return {ready:true};}
        await pause(Math.min(pollMs,Math.max(1,deadline-Date.now())),undefined,{signal:control.signal});
      }
      throw unavailable();
    }catch(error){await stopOwned();if(error.code==='COMPONENT_MISSING')throw error;throw unavailable();}
  }
  function ensureStarted(){
    if(stopped)return Promise.reject(unavailable());
    if(!preparing)preparing=start().finally(()=>{preparing=null;});
    return preparing;
  }
  async function stop(){
    stopped=true;control.abort();await stopOwned();await preparing?.catch(()=>{});
  }
  return {ensureStarted,stop,get authToken(){return token;}};
}
