import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {readFile,realpath} from 'node:fs/promises';
import {resolve,join,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {registerConversation} from './conversation.mjs';

export const name='qx-media';
export const inject=['connection','credentials','tools','systemPrompt','sessionQuery','webServer'];
const root=fileURLToPath(new URL('../../',import.meta.url));
const LIMIT=256*1024;
const actions=new Set(['status','list','save_profile','save_project','add_memory','confirm_memory','revoke_memory',
  'import_source','confirm_source','save_event','save_content','save_feedback','approve','submit','job','job_by_request','cancel','recommendations']);
const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store'}});

export function apply(ctx,config={}){
  if(!config.workspace||!config.python)throw Error('新媒体需要配置工作区和 Python。');
  let worker=null,starting=null,closed=false,buffer='';const pending=new Map();
  async function start(){
    if(closed)throw Error('新媒体服务已关闭。');
    if(worker)return worker;if(starting)return starting;
    starting=(async()=>{
      const key=(await ctx.credentials?.resolve('DEEPSEEK_API_KEY'))?.value||'';
      const args=['-X','utf8',join(root,'bridge/media_service.py'),'--workspace',resolve(config.workspace)];
      if(config.scraperPython)args.push('--scraper-python',config.scraperPython);
      const child=spawn(config.python,args,{cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],
        env:{...process.env,DEEPSEEK_API_KEY:key,PYTHONIOENCODING:'utf-8'}});
      worker=child;buffer='';
      const fail=()=>{if(worker===child)worker=null;for(const item of pending.values()){clearTimeout(item.timer);item.reject(Error('新媒体后台中断，已保存资料保留；请重新进入查看任务状态。'));}pending.clear();};
      child.on('error',fail);child.on('close',fail);child.stdin.on('error',()=>{});child.stderr.resume();
      child.stdout.setEncoding('utf8');child.stdout.on('data',chunk=>{
        buffer+=chunk;if(Buffer.byteLength(buffer)>8*1024*1024){child.kill();fail();return;}
        for(let at;(at=buffer.indexOf('\n'))>=0;){const line=buffer.slice(0,at);buffer=buffer.slice(at+1);
          let result;try{result=JSON.parse(line);}catch{child.kill();fail();return;}
          const item=pending.get(result.id);if(!item)continue;pending.delete(result.id);clearTimeout(item.timer);
          result.ok?item.resolve(result.result):item.reject(Object.assign(Error(result.error||'操作未完成'),{status:result.code==='PermissionError'?403:400}));
        }
      });return child;
    })().finally(()=>{starting=null;});return starting;
  }
  async function run(action,args){
    const child=await start();const id=randomUUID();
    return new Promise((resolveResult,reject)=>{
      const timer=setTimeout(()=>{pending.delete(id);reject(Object.assign(Error('提交等待超时，请查看任务记录；不要重复提交。'),{status:504}));},30000);
      pending.set(id,{resolve:resolveResult,reject,timer});child.stdin.write(JSON.stringify({id,action,args})+'\n');
    });
  }
  ctx.connection.fetch.register({path:'/api/qx-media/action',methods:['POST'],requestBody:'streaming',fetch:async request=>{
    try{
      const expected=new URL(request.url);if(request.headers.get('host'))expected.host=request.headers.get('host');
      if(request.headers.get('x-qx-media')!=='1'||(request.headers.get('origin')&&request.headers.get('origin')!==expected.origin))return json({ok:false,error:'请从本机工作台操作。'},403);
      if(request.headers.get('content-type')?.split(';')[0]!=='application/json')return json({ok:false,error:'请求格式不正确。'},415);
      if(Number(request.headers.get('content-length'))>LIMIT)return json({ok:false,error:'内容超过 256 KiB，请分段保存。'},413);
      const reader=request.body?.getReader();if(!reader)return json({ok:false,error:'没有请求内容。'},400);
      const chunks=[];let size=0;
      try{while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>LIMIT){await reader.cancel();return json({ok:false,error:'内容过长，请分段保存。'},413);}chunks.push(value);}}finally{reader.releaseLock();}
      const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if(Object.keys(value).some(k=>!['action','args'].includes(k))||!actions.has(value.action))return json({ok:false,error:'不支持此操作。'},400);
      if(['status','submit'].includes(value.action)){
        // Private stdio message only: callers cannot set credentials via HTTP.
        const key=(await ctx.credentials?.resolve('DEEPSEEK_API_KEY'))?.value||'';
        await run('_credential',{value:key});
      }
      return json({ok:true,result:await run(value.action,value.args)});
    }catch(error){return json({ok:false,error:error.message},error.status||400);}
  }});
  if(ctx.tools&&ctx.systemPrompt&&ctx.sessionQuery)registerConversation(ctx,run);
  ctx.connection.fetch.register({path:'/api/qx-media/panel',methods:['GET'],requestBody:'buffered',fetch:async()=>
    new Response(null,{status:303,headers:{location:'/', 'cache-control':'no-store'}})});
  for(const [route,file,mime] of [['client.js','client.js','text/javascript'],['style.css','style.css','text/css']]){
    ctx.connection.fetch.register({path:'/api/qx-media/'+route,methods:['GET'],requestBody:'buffered',fetch:async()=>
      new Response(await readFile(join(root,'plugins/media',file)),{headers:{'content-type':mime+'; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}})});
  }
  ctx.connection.fetch.register({path:'/api/qx-media/download',methods:['GET'],requestBody:'buffered',fetch:async request=>{
    try{
      const id=new URL(request.url).searchParams.get('id');if(!/^[a-f0-9-]{36}$/.test(id||''))throw Error('内容包编号无效。');
      const result=await run('download',{id});const path=await realpath(result.path);
      const base=await realpath(join(config.workspace,'.qx-media','exports'));
      if(!path.startsWith(base+sep))throw Error('内容包路径无效。');
      return new Response(await readFile(path),{headers:{'content-type':'application/zip','content-disposition':`attachment; filename="media-${id}.zip"`,'cache-control':'no-store'}});
    }catch(error){return json({ok:false,error:error.message},error.status||400);}
  }});
  ctx.effect(()=>async()=>{
    closed=true;const child=worker;if(!child)return;
    const exited=new Promise(resolve=>child.once('close',resolve));child.stdin.end();
    const timer=setTimeout(()=>child.kill(),3000);await exited;clearTimeout(timer);
  },'qx media worker cleanup');
}
