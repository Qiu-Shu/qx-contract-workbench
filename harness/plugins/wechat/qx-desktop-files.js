import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {opendir,realpath,stat,mkdtemp,copyFile,rm} from 'node:fs/promises';
import {constants} from 'node:fs';
import {basename,dirname,extname,isAbsolute,join,relative,resolve,sep} from 'node:path';
import {workspaceFile} from './qx-owner.js';

const run=promisify(execFile);
export async function desktopDirectories(){
  if(process.platform!=='win32')throw Error('桌面文件回传目前支持 Windows');
  // Known folders follow OneDrive/redirection/localized desktops; no hard-coded user path.
  const script="[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); ConvertTo-Json -Compress -InputObject @([Environment]::GetFolderPath('DesktopDirectory'),[Environment]::GetFolderPath('CommonDesktopDirectory'))";
  const {stdout}=await run('powershell.exe',['-NoProfile','-NonInteractive','-Command',script],{windowsHide:true,encoding:'utf8',timeout:10000,maxBuffer:16384});
  const directories=JSON.parse(stdout.replace(/^\uFEFF/,''));
  if(!Array.isArray(directories)||directories.some(x=>typeof x!=='string'||(x&&!isAbsolute(x))))throw Error('无法确定本机桌面目录');
  return [...new Set(directories.filter(Boolean))];
}
function inside(base,target){const r=relative(base,target);return r!== '..'&&!r.startsWith(`..${sep}`)&&!isAbsolute(r);}
const shortcut=file=>['.lnk','.url'].includes(extname(file).toLowerCase());

export function createDesktopFileAccess({workspace,getDirectories=desktopDirectories}){
  async function roots(){
    const values=[];
    for(const dir of await getDirectories()){
      try{const base=await realpath(dir);if(!values.includes(base))values.push(base);}
      catch(e){if(e.code!=='ENOENT')throw e;}
    }
    return values;
  }
  return {
    async find(name,directory='.'){
      if(typeof name!=='string'||!name.trim())throw Error('请提供要找的文件名或文件名片段');
      if(typeof directory!=='string'||isAbsolute(directory))throw Error('只能查询桌面内的相对目录');
      const files=[],seen=new Set(),query=name.trim().toLocaleLowerCase();
      for(const base of await roots()){
        const requested=resolve(base,directory);
        if(!inside(base,requested))throw Error('只能查询桌面内的目录');
        let folder;try{folder=await realpath(requested);}catch(e){if(e.code==='ENOENT')continue;throw e;}
        if(!inside(base,folder))throw Error('目录链接指向桌面之外');
        for await(const item of await opendir(folder)){
          if(!item.name.toLocaleLowerCase().includes(query)||shortcut(item.name))continue;
          let file;try{file=await workspaceFile(base,join(folder,item.name));}catch{continue;}
          if(seen.has(file))continue;seen.add(file);
          if(files.length===30)return {files,truncated:true};
          const info=await stat(file);
          files.push({name:basename(file),path:file,bytes:info.size,modifiedAt:info.mtime.toISOString()});
        }
      }
      return {files,truncated:false};
    },
    async prepare(input){
      if(typeof input!=='string'||!isAbsolute(input))throw Error('请提供工作区或桌面内文件的绝对路径');
      try{return await workspaceFile(workspace,input);}catch{}
      if(shortcut(input))throw Error('请指定原文件，不能发送或跟随桌面快捷方式');
      let source;
      for(const base of await roots()){
        try{source=await workspaceFile(base,input);break;}catch{}
      }
      if(!source)throw Error('只能发送当前工作区或桌面内的文件');
      const base=await realpath(workspace),before=await stat(source),outbox=await mkdtemp(join(base,'wechat-outbound-'));
      const target=join(outbox,basename(source));
      try{
        await copyFile(source,target,constants.COPYFILE_EXCL);
        const after=await stat(source);
        if(await realpath(source)!==source||before.ino!==after.ino||before.size!==after.size||before.mtimeMs!==after.mtimeMs)throw Error('文件正在变化，请保存后重试');
        return await workspaceFile(workspace,target);
      }catch(e){
        if(dirname(outbox)===base&&basename(outbox).startsWith('wechat-outbound-'))await rm(outbox,{recursive:true,force:true});
        throw e;
      }
    },
  };
}
