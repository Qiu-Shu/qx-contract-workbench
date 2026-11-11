import {execFile} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {mkdir,readFile,writeFile,rename,rm} from 'node:fs/promises';
import {join} from 'node:path';
import {dpapi,CIPHER_PREFIX} from '../wechat/secrets.js';

function systemProtector(){
  return dpapi({exec:(file,args,options)=>new Promise((resolve,reject)=>{
    execFile(file,args,{timeout:options.timeoutMs,windowsHide:true,maxBuffer:65536},(error,stdout)=>error?reject(Error('系统凭据保护不可用。')):resolve(stdout));
  })});
}
// Credentials stay separate from reports, model prompts, exports and public status.
export async function createConnectionStore({stateDir,protector=systemProtector()}={}){
  const file=join(stateDir,'connection.json');await mkdir(stateDir,{recursive:true,mode:0o700});
  let record={provider:'justone',token:''},token='';
  try{
    record=JSON.parse(await readFile(file,'utf8'));
    if(!['justone','local-xhs'].includes(record.provider)||typeof record.token!=='string')throw Error();
    token=record.token.startsWith(CIPHER_PREFIX)?await protector.reveal(record.token.slice(CIPHER_PREFIX.length)):record.token;
  }catch(error){if(error.code!=='ENOENT')throw Error('连接设置无法读取，原记录已保留，请检查本机凭据。');}
  const status=()=>({provider:record.provider,tokenConfigured:!!token,secretStorage:!token?'none':record.token.startsWith(CIPHER_PREFIX)?'dpapi':'restricted-file'});
  return {
    status,token:()=>token,
    async save(input){
      if(!['justone','local-xhs'].includes(input.provider))throw Error('采集方式无效。');
      if(input.token!==undefined&&(typeof input.token!=='string'||input.token.length>2048||/[\s\x00-\x1f]/.test(input.token.trim())))throw Error('Token 格式无效。');
      if(input.clearToken!==undefined&&typeof input.clearToken!=='boolean')throw Error('凭据清除选项无效。');
      const nextToken=input.clearToken?'':input.token?.trim()||token;
      let temporary;
      try{
        const next={provider:input.provider,token:nextToken&&protector.available?CIPHER_PREFIX+await protector.protect(nextToken):nextToken};
        temporary=file+'.'+randomUUID()+'.tmp';
        await writeFile(temporary,JSON.stringify(next)+'\n',{mode:0o600});await rename(temporary,file);
        record=next;token=nextToken;
      }catch{throw Error('无法保存连接设置，请检查本机凭据保护与磁盘后重试。');}
      finally{if(temporary)await rm(temporary,{force:true}).catch(()=>{});}
      return status();
    },
  };
}
