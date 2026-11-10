import {access,readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {runComponent} from './component-process.mjs';

const samePath=(a,b)=>process.platform==='win32'?path.resolve(a).toLowerCase()===path.resolve(b).toLowerCase():path.resolve(a)===path.resolve(b);
async function exists(file){try{await access(file);return true}catch(error){if(error.code==='ENOENT')return false;throw error}}

export async function describeComponent(config,{payload=fileURLToPath(new URL('../../',import.meta.url)),data=process.env.QX_INSTALL_DATA}={}){
  if(config.command&&!path.isAbsolute(config.command))return {mode:'external',phase:'external'};
  if(!config.command)return {mode:'unavailable',phase:'unavailable'};
  if(!samePath(config.command,path.join(payload,'runtime/windows/python.exe')))
    return {mode:'external',phase:await exists(config.command)?'ready':'unavailable'};
  if(await exists(config.command))return {mode:'bundled',phase:'ready'};
  try{
    const catalog=JSON.parse(await readFile(path.join(payload,'config/components.json'),'utf8')),item=catalog.components?.['windows-python'];
    if(catalog.schema!==1||!item||!Number.isSafeInteger(item.size)||item.size<=0||!/^[a-f0-9]{64}$/.test(item.sha256))throw Error('metadata');
    const cached=data&&await exists(path.join(data,'components/windows-python',item.sha256,'installed.json'));
    return {mode:'on-demand',phase:cached?'cached':'idle',total:item.size};
  }catch{return {mode:'unavailable',phase:'unavailable'}}
}

// Only reached by the first actual call to a registered lazy tool, never plugin setup.
export async function resolveOptionalComponent(config,{
  payload=fileURLToPath(new URL('../../',import.meta.url)),
  data=process.env.QX_INSTALL_DATA,signal,run=runComponent,onProgress=()=>{},
}={}){
  if(config.serverName!=='windows'||!config.command||!samePath(config.command,path.join(payload,'runtime/windows/python.exe')))return config;
  if(await exists(config.command))return config;
  const manifest=path.join(payload,'config/components.json');
  if(!await exists(manifest))throw Error('Windows 自动化组件缺失，且未配置组件清单，请修复安装。');
  if(!data||!path.isAbsolute(data))throw Error('Windows 自动化组件缺少本机资料目录。');
  const catalog=JSON.parse(await readFile(manifest,'utf8')),sha=catalog.components?.['windows-python']?.sha256;
  if(catalog.schema!==1||!/^[a-f0-9]{64}$/.test(sha||''))throw Error('Windows 自动化组件清单无效。');
  signal?.throwIfAborted();
  let stdout;
  try{
    ({stdout}=await run(path.join(payload,'runtime/python/python.exe'),['-X','utf8',path.join(payload,'component-install.py'),'--progress',payload,data,'windows-python'],
      {windowsHide:true,encoding:'utf8',timeout:360000,maxBuffer:65536,signal,onProgress}));
  }catch(error){
    signal?.throwIfAborted();
    // The helper exits nonzero with a bounded, user-facing JSON error. Never expose stderr.
    try{const result=JSON.parse(error.stdout);if(result.ok===false&&typeof result.message==='string')throw Object.assign(Error(result.message),{componentError:true,code:result.code})}
    catch(parsed){if(parsed.componentError)throw parsed}
    throw Object.assign(Error(error.code==='TIMEOUT'?'组件准备超时，请稍后重试。':'Windows 自动化组件准备未完成，请检查网络和可用空间后重试。'),{code:error.code==='TIMEOUT'?'TIMEOUT':'PREPARE_FAILED'});
  }
  signal?.throwIfAborted();
  const result=JSON.parse(stdout);
  if(result.ok!==true)throw Object.assign(Error(typeof result.message==='string'?result.message:'Windows 自动化组件准备失败。'),{code:result.code});
  const expected=path.join(data,'components/windows-python',sha,'python.exe');
  if(typeof result.executable!=='string'||!samePath(result.executable,expected)||!await exists(expected))throw Error('Windows 自动化组件入口路径无效。');
  return {...config,command:expected};
}
