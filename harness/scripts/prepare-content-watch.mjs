// Explicitly prepare a pinned local component. Importing this module never downloads or executes it.
import {mkdir,readFile,writeFile,open,rename,rm,chmod,lstat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash,randomUUID} from 'node:crypto';

export const COMPONENT_VERSION='v2.7.2';
const release='https://github.com/xpzouying/xiaohongshu-mcp/releases/download/'+COMPONENT_VERSION+'/';
const assets={
  'win32-x64':{name:'xiaohongshu-mcp-windows-amd64.exe',size:16353280,sha256:'1f62e1fe137d0293595197b3a76e280e4114293b425e9c4082a334d1f7fb5316'},
  'darwin-arm64':{name:'xiaohongshu-mcp-darwin-arm64',size:16834514,sha256:'e3068363fc4d6572d1e4cf2aeccda7e1d37844191aa8ce0944706f73700a4130'},
  'linux-x64':{name:'xiaohongshu-mcp-linux-amd64',size:17076384,sha256:'269a79a48d7310f6a2ef015f6b835af4300ae6cbfe8eb254237c3006a05869fc'},
};
export function componentAsset(platform=process.platform,arch=process.arch){
  const asset=assets[platform+'-'+arch];
  if(!asset)throw new Error('当前系统暂不支持自动准备小红书连接组件。');
  return {...asset,url:release+asset.name};
}
const pending=new Map();
async function noLink(file){
  try{if((await lstat(file)).isSymbolicLink())throw new Error('连接组件目录不能使用符号链接。');}
  catch(error){if(error.code!=='ENOENT')throw error;}
}
async function prepare({stateDir,platform,arch,fetchImpl,asset}){
  if(typeof stateDir!=='string'||!stateDir)throw new Error('小红书连接组件缺少本机资料目录。');
  asset=asset||componentAsset(platform,arch);
  const directory=resolve(stateDir),runtime=join(directory,'runtime');
  const executable=join(runtime,platform==='win32'?'xiaohongshu-mcp.exe':'xiaohongshu-mcp');
  await noLink(directory);await noLink(runtime);await noLink(executable);
  await mkdir(runtime,{recursive:true,mode:0o700});await chmod(runtime,0o700);
  const license=await readFile(new URL('../sources/xiaohongshu-mcp-Apache-2.0.txt',import.meta.url));
  let existing;
  try{existing=await readFile(executable);}catch(error){if(error.code!=='ENOENT')throw error;}
  const ready=()=>({ready:true,executable,version:COMPONENT_VERSION});
  if(existing&&existing.length===asset.size&&createHash('sha256').update(existing).digest('hex')===asset.sha256){
    await chmod(executable,0o700);
    await noLink(join(runtime,'LICENSE.xiaohongshu-mcp.txt'));
    await writeFile(join(runtime,'LICENSE.xiaohongshu-mcp.txt'),license,{mode:0o600});
    return ready();
  }
  const temporary=join(runtime,'.component-'+randomUUID()+'.tmp');let file;
  try{
    let response;
    try{response=await fetchImpl(asset.url,{headers:{accept:'application/octet-stream'},signal:AbortSignal.timeout(120000)});}
    catch{throw new Error('小红书连接组件下载失败，请检查网络后重试。');}
    if(!response.ok||!response.body)throw new Error('小红书连接组件下载失败，请稍后重试。');
    const size=Number(response.headers.get('content-length'));
    if(size&&size!==asset.size)throw new Error('小红书连接组件大小不符，未替换原组件。');
    file=await open(temporary,'wx',0o600);
    const hash=createHash('sha256'),reader=response.body.getReader();let received=0;
    try{
      while(true){let chunk;try{chunk=await reader.read();}catch{throw new Error('小红书连接组件下载中断，请检查网络后重试。');}const {done,value}=chunk;if(done)break;
        received+=value.byteLength;
        if(received>asset.size){await reader.cancel();throw new Error('小红书连接组件大小不符，未替换原组件。');}
        hash.update(value);await file.writeFile(value);
      }
    }finally{reader.releaseLock();}
    if(received!==asset.size)throw new Error('小红书连接组件大小不符，未替换原组件。');
    if(hash.digest('hex')!==asset.sha256)throw new Error('小红书连接组件校验失败，未替换原组件。');
    await file.sync();await file.close();file=null;await chmod(temporary,0o700);
    await noLink(executable);await rename(temporary,executable);
    const licensePath=join(runtime,'LICENSE.xiaohongshu-mcp.txt');await noLink(licensePath);
    await writeFile(licensePath,license,{mode:0o600});
    return ready();
  }finally{await file?.close();await rm(temporary,{force:true});}
}
export async function prepareContentWatch({stateDir,platform=process.platform,arch=process.arch,fetchImpl=fetch,asset}={}){
  // asset/fetchImpl are injected only by isolated tests; the product forwards no request fields here.
  const key=resolve(stateDir||'.');
  if(pending.has(key))return pending.get(key);
  const work=prepare({stateDir,platform,arch,fetchImpl,asset});pending.set(key,work);
  try{return await work;}finally{pending.delete(key);}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const stateDir=process.argv[2];
  if(!stateDir)throw new Error('请提供工作台的小红书连接组件资料目录。');
  const result=await prepareContentWatch({stateDir});
  console.log(JSON.stringify(result));
}
