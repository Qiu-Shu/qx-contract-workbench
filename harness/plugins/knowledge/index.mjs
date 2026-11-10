import {spawn} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {mkdir,realpath,lstat,rename,rm} from 'node:fs/promises';
import {createWriteStream,createReadStream} from 'node:fs';
import {resolve,join,extname,basename,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Readable,Transform} from 'node:stream';
import {pipeline} from 'node:stream/promises';
import {materialCategory} from '../../desktop/integration/knowledge-materials.mjs';

export const name='qx-local-knowledge';
export const inject=['connection'];
const formats=new Set('.txt .md .csv .tsv .json .html .htm .rtf .doc .docx .pdf .xls .xlsx .ppt .pptx .odt .ods .odp .png .jpg .jpeg .webp .gif .bmp .tif .tiff'.split(' '));
const identifier=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function apply(ctx,config={}){
  if(!config.workspace||!config.python)throw new Error('知识库需要配置 workspace 和 python。');
  const workspace=resolve(config.workspace),root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
  const jobs=new Map(),children=new Set(),downloads=new Map();let disposed=false,indexQueue=Promise.resolve(),transferring=false,mutations=0;
  const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store'}});
  function stop(child){
    if(!child.pid||child.exitCode!==null)return;
    // A parser runs below this worker; terminate only this owned process tree.
    if(process.platform==='win32'){
      const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
      killer.on('error',()=>child.kill());
    }else child.kill();
  }
  function run(action,args={}){
    if(disposed)return Promise.reject(new Error('知识库正在重新加载，请稍后重试。'));
    return new Promise((resolveResult,reject)=>{
      const child=spawn(config.python,[join(root,'bridge/knowledge.py'),'--workspace',workspace],{
        cwd:workspace,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
      children.add(child);let stdout='',ended=false;
      const finish=(error,value)=>{if(ended)return;ended=true;clearTimeout(timer);children.delete(child);error?reject(error):resolveResult(value);};
      const timer=setTimeout(()=>{stop(child);finish(new Error('处理超时，原件保留。请稍后重试。'));},['index','backup','restore'].includes(action)?1800000:60000);
      child.stdout.setEncoding('utf8');child.stdout.on('data',value=>{stdout+=value;if(stdout.length>4*1024*1024){stop(child);finish(new Error('返回内容过多，请缩小读取范围。'));}});
      child.stderr.resume();
      child.on('error',()=>finish(new Error('无法启动文档服务，请检查本机运行环境。')));
      child.stdin.on('error',()=>{});
      child.on('close',code=>{
        if(ended)return;
        if(code!==0)return finish(new Error('文档进程中断，原件保留。'));
        try{const data=JSON.parse(stdout.trim());data.ok?finish(null,data.result):finish(new Error(data.error||'知识库操作失败。'));}
        catch{finish(new Error('知识库返回异常。'));}
      });
      child.stdin.end(JSON.stringify({action,args}));
    });
  }
  function startIndex(id){
    if(jobs.has(id))return;
    const job=indexQueue.then(()=>run('index',{document_id:id})).catch(async error=>{
      if(!disposed)await run('set_state',{document_id:id,state:'error',error:error.message}).catch(()=>{});
    }).finally(()=>jobs.delete(id));
    indexQueue=job;
    jobs.set(id,job);
  }
  // All routes use Harness's authenticated owner-only /api carrier.
  function route(path,methods,handler,requestBody='buffered'){
    ctx.connection.fetch.register({path:'/api/qx-knowledge/'+path,methods,requestBody,fetch:async request=>{
      let counted=false;
      try{
        if(request.method!=='GET'){
          const origin=request.headers.get('origin');
          const expected=new URL(request.url);
          // Harness replaces the URL authority with dsh.internal but preserves Host.
          if(request.headers.get('host'))expected.host=request.headers.get('host');
          if(request.headers.get('x-qx-knowledge')!=='1'||(origin&&origin!==expected.origin))return json({error:'请从本机知识库页面操作。'},403);
          if(transferring)return json({error:'正在备份或恢复，请完成后再修改资料。'},409);
          mutations++;counted=true;
        }
        return await handler(request);
      }catch(error){return json({error:error.message||'知识库暂时不可用。'},400);}
      finally{if(counted)mutations--;}
    }});
  }
  const idFrom=url=>{const id=url.searchParams.get('id');if(!identifier.test(id||''))throw new Error('资料编号无效。');return id;};
  const integer=(url,key,fallback)=>{const n=Number(url.searchParams.get(key)??fallback);if(!Number.isSafeInteger(n)||n<0)throw new Error('分页参数无效。');return n;};
  route('documents',['GET'],async request=>{
    const url=new URL(request.url),data=await run('list',{offset:integer(url,'offset',0),limit:50,archived:url.searchParams.get('archived')==='1'});
    data.documents=data.documents.map(d=>({...d,busy:jobs.has(d.id),state:d.state==='indexing'&&!jobs.has(d.id)?'interrupted':d.state}));
    return json(data);
  });
  route('search',['GET'],async request=>{
    const u=new URL(request.url);return json(await run('search',{query:u.searchParams.get('q')||'',category:u.searchParams.get('category')||'',offset:integer(u,'offset',0)}));
  });
  route('read',['GET'],async request=>{const u=new URL(request.url);return json(await run('read',{document_id:idFrom(u),start:integer(u,'start',0)}));});
  route('citation',['GET'],async request=>json(await run('citation',{reference:new URL(request.url).searchParams.get('reference')||''})));
  route('index',['POST'],async request=>{const id=idFrom(new URL(request.url));await run('read',{document_id:id,start:0,limit:1});startIndex(id);return json({id,state:'indexing'},202);});
  route('archive',['POST'],async request=>{
    const u=new URL(request.url),id=idFrom(u);
    if(jobs.has(id))return json({error:'资料正在解析，请完成后再归档。'},409);
    return json(await run('archive',{document_id:id,archived:u.searchParams.get('restore')!=='1'}));
  });
  route('source',['GET'],async request=>{
    const data=await run('source',{document_id:idFrom(new URL(request.url))});
    const base=await realpath(join(workspace,'knowledge')),file=await realpath(data.path);
    if(!file.startsWith(base+sep))throw new Error('原件路径不在知识库内。');
    return new Response(Readable.toWeb(createReadStream(file)),{headers:{'content-type':'application/octet-stream',
      'content-disposition':`attachment; filename*=UTF-8''${encodeURIComponent(data.title)}`,'cache-control':'no-store','x-content-type-options':'nosniff'}});
  });
  async function transferPath(id){
    let parent=await realpath(workspace);
    for(const part of ['knowledge','.qx-materials','transfers']){
      parent=join(parent,part);await mkdir(parent,{recursive:true});
      if((await lstat(parent)).isSymbolicLink()||(await realpath(parent))!==parent)throw new Error('备份目录不能是符号链接或联接。');
    }
    return join(parent,id+'.zip');
  }
  function beginTransfer(){
    if(jobs.size||mutations>1)throw new Error('资料正在上传或解析，请完成后再备份或恢复。');
    transferring=true;
  }
  async function discardDownload(id){
    const entry=downloads.get(id);if(!entry)return;
    downloads.delete(id);clearTimeout(entry.timer);await rm(entry.file,{force:true}).catch(()=>{});
  }
  route('backup',['POST'],async()=>{
    beginTransfer();const id=randomUUID();let file;
    try{
      file=await transferPath(id);
      const result=await run('backup',{destination:file});
      const timer=setTimeout(()=>void discardDownload(id),30*60*1000);timer.unref?.();
      downloads.set(id,{file,timer});
      return json({documents:result.documents,download:'/api/qx-knowledge/backup-download?id='+id});
    }catch(error){if(file)await rm(file,{force:true}).catch(()=>{});throw error;}
    finally{transferring=false;}
  });
  route('backup-download',['GET'],async request=>{
    const id=idFrom(new URL(request.url)),entry=downloads.get(id);
    if(!entry)return json({error:'备份下载已过期，请重新生成。'},404);
    const file=await realpath(entry.file);
    if(file!==entry.file||(await lstat(entry.file)).isSymbolicLink())throw new Error('备份文件路径已变化。');
    return new Response(Readable.toWeb(createReadStream(file)),{headers:{'content-type':'application/zip',
      'content-disposition':`attachment; filename="knowledge-backup-${new Date().toISOString().slice(0,10)}.zip"`,
      'cache-control':'no-store','x-content-type-options':'nosniff'}});
  });
  route('restore',['POST'],async request=>{
    if(!request.body)throw new Error('没有收到备份文件。');
    beginTransfer();let file;
    try{
      file=await transferPath(randomUUID());let bytes=0;
      const limit=new Transform({transform(chunk,encoding,callback){bytes+=chunk.length;callback(bytes>2*1024**3+16*1024**2?new Error('备份文件超过大小上限（2 GiB 加归档开销）。'):null,chunk);}});
      await pipeline(Readable.fromWeb(request.body),limit,createWriteStream(file,{flags:'wx'}));
      return json(await run('restore',{archive:file}));
    }finally{if(file)await rm(file,{force:true}).catch(()=>{});transferring=false;}
  },'streaming');
  route('upload',['POST'],async request=>{
    const session=request.headers.get('x-qx-session')||'';
    const scope=session?await ctx.serial('qx/knowledge/resolve-session',session):null;
    if(session&&!scope)throw new Error('当前工作暂未就绪，请稍后重试。');
    const filename=decodeURIComponent(request.headers.get('x-qx-filename')||'');
    if(!filename||filename.length>180||basename(filename)!==filename||/[<>:"/\\|?*\x00-\x1f]/.test(filename)||/[. ]$/.test(filename)||/^(con|prn|aux|nul|com[0-9¹²³]|lpt[0-9¹²³])(?:\.|$)/i.test(filename))throw new Error('文件名无效，请重命名后上传。');
    if(!formats.has(extname(filename).toLowerCase()))throw new Error('请上传文档、表格、PDF 或图片。');
    if(!request.body)throw new Error('没有收到文件内容。');
    const category=decodeURIComponent(request.headers.get('x-qx-category')||'')||materialCategory(filename);
    if(category.length>80)throw new Error('分类不超过 80 字。');
    const id=randomUUID();
    await mkdir(workspace,{recursive:true});const canonical=await realpath(workspace);
    let parent=canonical;
    for(const part of ['knowledge','documents',id]){
      parent=join(parent,part);await mkdir(parent,{recursive:true});
      if((await lstat(parent)).isSymbolicLink()||(await realpath(parent))!==parent)throw new Error('知识库目录不能是符号链接或联接。');
    }
    const temporary=join(parent,'.upload-part'),target=join(parent,filename);
    try{
      await pipeline(Readable.fromWeb(request.body),createWriteStream(temporary,{flags:'wx'}));
      await rename(temporary,target);
      const document=await run('register',{document_id:id,title:filename,category});
      let linkWarning;
      if(session)try{await ctx.serial('qx/knowledge/document',{session,scope,document:id,title:filename.slice(0,120)});}catch{linkWarning='资料已保存；工作归属正在变化，可在管理中关联，无需重复上传。';}
      startIndex(id);return json({...document,state:'indexing',...linkWarning?{linkWarning}:{}},201);
    }catch(error){await rm(temporary,{force:true}).catch(()=>{});throw error;}
  },'streaming');
  ctx.effect(()=>()=>{disposed=true;for(const child of children)stop(child);for(const id of downloads.keys())void discardDownload(id);},'qx knowledge worker cleanup');
}
