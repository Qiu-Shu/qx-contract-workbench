import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {mkdir,realpath,lstat,readFile,unlink} from 'node:fs/promises';
import {createReadStream,createWriteStream} from 'node:fs';
import {resolve,dirname,join,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Readable} from 'node:stream';
import {pipeline} from 'node:stream/promises';

export const name='qx-upload-privacy';
export const inject=['connection'];
const formats=new Set('.txt .md .csv .tsv .json .html .htm .rtf .doc .docx .pdf .xls .xlsx .ppt .pptx .odt .ods .odp .png .jpg .jpeg .webp .gif .bmp .tif .tiff'.split(' '));
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const errorResponse=(error,status=400)=>Response.json({error},{status,headers:{'cache-control':'no-store'}});
function stop(child){
  if(!child.pid||child.exitCode!==null)return;
  if(process.platform==='win32')spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'}).on('error',()=>child.kill());
  else child.kill();
}
export function runPrivacy(python,args,children=new Set(),signal){
  return new Promise((accept,reject)=>{
    if(signal?.aborted)return reject(new Error('已取消脱敏，原件未发送。'));
    const child=spawn(python,[join(root,'bridge/privacy.py')],{windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
    children.add(child);let output='',settled=false;
    const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(timer);signal?.removeEventListener('abort',abort);children.delete(child);error?reject(error):accept(value);};
    const abort=()=>{stop(child);finish(new Error('已取消脱敏，原件未发送。'));};
    const timer=setTimeout(()=>{stop(child);finish(new Error('本机脱敏超时，原件未发送。请拆分资料后重试。'));},1800000);
    signal?.addEventListener('abort',abort,{once:true});
    child.stdout.setEncoding('utf8');child.stdout.on('data',chunk=>{output+=chunk;if(output.length>1024*1024){stop(child);finish(new Error('脱敏服务返回异常，原件未发送。'));}});
    child.stderr.resume();child.stdin.on('error',()=>{});
    child.on('error',()=>finish(new Error('本机脱敏服务未能启动，原件未发送。')));
    child.on('close',code=>{
      if(settled)return;
      try{const value=JSON.parse(output);if(code!==0||value.status!=='ready')return finish(new Error(value.error||'本机脱敏未完成，原件未发送。'));finish(null,value);}
      catch{finish(new Error('本机脱敏未完成，原件未发送。'));}
    });
    child.stdin.end(JSON.stringify(args));
  });
}
export function apply(ctx,config={}){
  if(!config.workspace||!config.python)throw new Error('上传脱敏需要 workspace 和 python。');
  const workspace=resolve(config.workspace),vault=resolve(dirname(workspace),'.qx-private','uploads');
  const children=new Set();let disposed=false;
  ctx.effect(()=>()=>{disposed=true;for(const child of children)stop(child);},'qx privacy workers');
  ctx.connection.fetch.register({path:'/api/qx-privacy/client.js',methods:['GET'],requestBody:'buffered',fetch:async()=>new Response(await readFile(join(root,'plugins/privacy/client.js')),{headers:{'content-type':'text/javascript; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}})});
  ctx.connection.fetch.register({path:'/api/qx-privacy/prepare',methods:['POST'],requestBody:'streaming',fetch:async request=>{
    let incoming;
    try{
      if(disposed)return errorResponse('脱敏服务正在重启，请稍后重新添加附件。',503);
      const origin=request.headers.get('origin'),expected=new URL(request.url);
      // Harness bridges its Request URL through dsh.internal; the authenticated
      // carrier has already checked Host/Origin. Compare with that real Host.
      if(request.headers.get('host'))expected.host=request.headers.get('host');
      if(request.headers.get('x-qx-privacy')!=='1'||(origin&&origin!==expected.origin))return errorResponse('请从工作台上传资料。',403);
      if(!request.body)return errorResponse('没有收到文件，原件未发送。');
      const url=new URL(request.url),extension=extname(url.searchParams.get('name')||'').toLowerCase();
      if(!formats.has(extension))return errorResponse('此格式暂不支持本机脱敏，原件未发送。请转换为文档、图片或纯文本后重试。');
      const contextId=url.searchParams.get('context')||undefined;
      if(contextId&&!/^[A-Za-z0-9_-]{1,128}$/.test(contextId))return errorResponse('上传批次无效。');
      const terms=JSON.parse(request.headers.get('x-qx-terms')?decodeURIComponent(request.headers.get('x-qx-terms')):'[]');
      if(!Array.isArray(terms)||terms.some(t=>typeof t!=='string'))return errorResponse('敏感词格式无效。');
      await mkdir(workspace,{recursive:true});await mkdir(vault,{recursive:true});
      const actualWorkspace=await realpath(workspace),actualVault=await realpath(vault);
      if(actualVault===actualWorkspace||actualVault.startsWith(actualWorkspace+sep)||(await lstat(vault)).isSymbolicLink())throw Error('vault');
      const inbox=join(actualVault,'incoming');await mkdir(inbox,{recursive:true});
      if((await lstat(inbox)).isSymbolicLink())throw Error('vault');
      const id=randomUUID();incoming=join(inbox,id+extension);
      await pipeline(Readable.fromWeb(request.body),createWriteStream(incoming,{flags:'wx'}),{signal:request.signal});
      const result=await runPrivacy(config.python,{source_path:incoming,vault_dir:actualVault,workspace_dir:actualWorkspace,document_id:id,custom_terms:terms,context_id:contextId},children,request.signal);
      const safe=await realpath(result.safe_path);
      if(!safe.startsWith(actualVault+sep)||extname(safe)!=='.txt')throw Error('safe path');
      // Only the plain-text derivative crosses into Harness. Never expose vault paths or maps.
      return new Response(Readable.toWeb(createReadStream(safe)),{headers:{'content-type':'text/plain; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff',
        'x-qx-safe-name':encodeURIComponent(result.display_name),'x-qx-replacements':String(result.replacement_count||0),
        'x-qx-privacy-warning':encodeURIComponent('已生成脱敏文字副本；图片与版式不随附。自动识别可能遗漏，请核对关键身份信息。')}});
    }catch(error){return errorResponse(error.message?.includes('原件未发送')?error.message:'本机脱敏未完成，原件未发送。请检查文件后重新添加。');}
    finally{if(incoming)await unlink(incoming).catch(()=>{});}
  }});
}
