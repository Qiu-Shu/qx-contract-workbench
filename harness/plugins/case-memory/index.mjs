import {spawn} from 'node:child_process';
import {resolve,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {isIP} from 'node:net';

export const name='qx-case-memory';
export const inject=['connection'];
const identifier=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const MAX_BODY=64*1024,MAX_OUTPUT=4*1024*1024;
const fail=(message,status=400)=>{throw Object.assign(new Error(message),{status});};
const object=value=>{if(!value||typeof value!=='object'||Array.isArray(value))fail('请提供有效的请求内容。');return value;};
const keys=(value,allowed)=>{object(value);if(Object.keys(value).some(key=>!allowed.includes(key)))fail('请求包含不支持的字段。');};
const id=value=>{if(typeof value!=='string'||!identifier.test(value))fail('案件或记忆编号无效。');return value;};
const text=(value,max,label)=>{if(typeof value!=='string'||!value.trim()||value.length>max||value.includes('\0'))fail(`${label}须为 1–${max} 字。`);return value;};
const revision=value=>{if(!Number.isSafeInteger(value)||value<1)fail('修订号无效，请刷新记忆后重试。');return value;};

async function body(request){
  if(request.headers.get('content-type')?.split(';')[0].trim().toLowerCase()!=='application/json')fail('请使用 JSON 请求。',415);
  if(Number(request.headers.get('content-length'))>MAX_BODY)fail('提交内容超过 64 KiB 上限。',413);
  const reader=request.body?.getReader();if(!reader)fail('请求内容为空。');
  const parts=[];let bytes=0;
  try{
    while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;
      if(bytes>MAX_BODY){await reader.cancel();fail('提交内容超过 64 KiB 上限。',413);}parts.push(value);}
  }finally{reader.releaseLock();}
  try{return object(JSON.parse(Buffer.concat(parts).toString('utf8')));}
  catch(error){if(error.status)throw error;fail('请求 JSON 无效。');}
}

function query(request,allowed){
  const params=new URL(request.url).searchParams;
  if([...params.keys()].some(key=>!allowed.includes(key)||params.getAll(key).length!==1))fail('查询参数无效。');
  return params;
}
function page(params,max=50){
  const number=(key,fallback)=>{const raw=params.get(key);if(raw!==null&&!/^\d+$/.test(raw))fail('分页参数无效。');const value=Number(raw??fallback);if(!Number.isSafeInteger(value))fail('分页参数无效。');return value;};
  const offset=number('offset',0),limit=number('limit',20);if(limit<1||limit>max)fail(`每页数量须为 1–${max}。`);return {offset,limit};
}

export function apply(ctx,config={}){
  if(!config.workspace||!config.python)throw new Error('案件记忆需要配置 workspace 和 python。');
  const workspace=resolve(config.workspace),root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
  const children=new Map(),pending=new Set();let disposed=false,draining=false,retrying=false;
  let lastError='',lastFinished=null;
  const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
  async function runtime(action){
    const address=process.env.QX_CASE_MEMORY_CONTROL_URL,token=process.env.QX_CASE_MEMORY_CONTROL_TOKEN;
    if(!address||!token){if(action==='prepare')fail('当前环境尚未提供一键准备，请更新或重新启动工作台。',503);return {available:false,phase:'unavailable'};}
    let url;try{url=new URL(address);}catch{fail('增强记忆控制服务配置无效。',503);}
    const host=url.hostname.replace(/^\[|\]$/g,'');
    if(!['http:','https:'].includes(url.protocol)||!url.port||!isIP(host)||!(host==='::1'||host.startsWith('127.'))||
      url.username||url.password||url.search||url.hash||!['','/'].includes(url.pathname)||/[\r\n]/.test(token))fail('增强记忆控制服务配置无效。',503);
    const phases=new Set(['not-installed','installing','starting','ready','error','stopped']);
    try{
      const response=await fetch(new URL('/'+action,url),{method:action==='prepare'?'POST':'GET',
        headers:{authorization:'Bearer '+token,accept:'application/json'},redirect:'error',signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw Error('control unavailable');
      const reader=response.body.getReader();let bytes=0;const parts=[];
      try{while(true){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>65536){await reader.cancel();throw Error('control response too large');}parts.push(value);}}finally{reader.releaseLock();}
      const value=JSON.parse(Buffer.concat(parts).toString('utf8'));
      if(!phases.has(value.phase))throw Error('invalid phase');
      // Never forward raw messages, URLs, model credentials, or installation stderr.
      return {available:true,phase:value.phase,engine:'hindsight',version:typeof value.version==='string'&&/^\d+\.\d+\.\d+$/.test(value.version)?value.version:undefined};
    }catch{if(action==='prepare')fail('增强引擎未能开始准备，请稍后重试。本机记录已保留。',503);return {available:true,phase:'error'};}
  }
  function stop(child){
    if(!child.pid||child.exitCode!==null)return;
    if(process.platform==='win32'){
      const killer=spawn('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
      killer.on('error',()=>child.kill());
    }else child.kill();
  }
  function run(action,args={}){
    if(disposed)return Promise.reject(new Error('案件记忆正在重新加载，请稍后重试。'));
    return new Promise((resolveResult,reject)=>{
      const child=spawn(config.python,[join(root,'bridge/case_memory.py'),'--workspace',workspace],{
        cwd:workspace,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
      let stdout='',bytes=0,ended=false;
      const finish=(error,value)=>{if(ended)return;ended=true;clearTimeout(timer);children.delete(child);error?reject(error):resolveResult(value);};
      const timer=setTimeout(()=>{stop(child);finish(new Error(action==='sync'?'同步超时，本机记录已保留，将稍后重试。':'读取超时，请稍后重试。'));},action==='sync'?420000:60000);
      children.set(child,()=>{stop(child);finish(new Error('案件记忆正在重新加载，请稍后重试。'));});
      child.stdout.setEncoding('utf8');child.stdout.on('data',value=>{bytes+=Buffer.byteLength(value);if(bytes>MAX_OUTPUT){stop(child);finish(new Error('返回内容过多，请缩小读取范围。'));return;}stdout+=value;});
      child.stderr.resume();child.stdin.on('error',()=>{});
      child.on('error',()=>finish(new Error('无法启动案件记忆服务，请检查本机运行环境。')));
      child.on('close',code=>{
        if(ended)return;if(code!==0)return finish(new Error('案件记忆进程中断，请稍后重试。'));
        let data;try{data=JSON.parse(stdout.trim());}catch{return finish(new Error('案件记忆返回异常。'));}
        if(!data||typeof data!=='object'||typeof data.ok!=='boolean')return finish(new Error('案件记忆返回异常。'));
        data.ok?finish(null,data.result):finish(new Error(typeof data.error==='string'?data.error:'案件记忆操作未完成。'));
      });
      child.stdin.end(JSON.stringify({action,args}));
    });
  }
  function queue(caseId){
    if(disposed)return;pending.add(caseId);if(!draining)void drain();
  }
  async function drain(){
    draining=true;
    try{
      while(pending.size&&!disposed){
        const caseId=pending.values().next().value;pending.delete(caseId);
        try{
          const state=await run('sync',{case_id:caseId});lastError='';lastFinished=new Date().toISOString();
          // A successful bounded batch leaves the next batch pending. Rotate cases fairly.
          if(state.enabled&&state.service_configured&&state.sync_state==='pending')pending.add(caseId);
        }
        catch{lastError='同步未完成，本机记录已保留；后台将稍后重试。';}
      }
    }finally{draining=false;}
  }
  async function retryPending(){
    if(disposed||retrying)return;retrying=true;
    try{
      let offset=0;
      do{
        const list=await run('list_cases',{offset,limit:50});
        for(const item of list.cases||[]){
          if(disposed)break;
          const state=await run('status',{case_id:id(item.id)});
          if(state.pending_cleanup||['pending','error','syncing'].includes(state.sync_state))queue(item.id);
        }
        const next=list.next_offset;
        if(next==null)break;if(!Number.isSafeInteger(next)||next<=offset)throw Error('Invalid pagination');offset=next;
      }while(!disposed);
    }catch{if(!disposed)lastError='暂未完成待同步检查，将稍后重试。';}
    finally{retrying=false;}
  }
  function route(path,methods,handler){
    // Harness authenticates its owner-only /api carrier before dispatching here.
    ctx.connection.fetch.register({path:'/api/qx-case-memory/'+path,methods,requestBody:methods.includes('POST')?'streaming':'buffered',fetch:async request=>{
      try{
        if(disposed)return json({error:'案件记忆正在重新加载，请稍后重试。'},503);
        if(request.method!=='GET'){
          const expected=new URL(request.url),host=request.headers.get('host');if(host)expected.host=host;
          const origin=request.headers.get('origin');
          if(request.headers.get('x-qx-case-memory')!=='1'||(origin&&origin!==expected.origin))return json({error:'请从本机案件记忆页面操作。'},403);
        }
        return await handler(request);
      }catch(error){return json({error:error.message||'案件记忆暂时不可用。'},error.status||400);}
    }});
  }
  route('status',['GET'],async request=>{
    const p=query(request,['case_id']);const args=p.has('case_id')?{case_id:id(p.get('case_id'))}:{};
    return json({...await run('status',args),worker:{running:draining,queued:pending.size,last_error:lastError,last_finished_at:lastFinished}});
  });
  route('runtime-status',['GET'],async request=>{query(request,[]);return json(await runtime('status'));});
  route('prepare',['POST'],async request=>{keys(await body(request),[]);return json(await runtime('prepare'),202);});
  route('list_cases',['GET'],async request=>{
    const p=query(request,['query','offset','limit']);const search=p.get('query')||'';if(search.length>300)fail('案件检索词不超过 300 字。');
    return json(await run('list_cases',{query:search,...page(p)}));
  });
  for(const action of ['list','sources'])route(action,['GET'],async request=>{
    const p=query(request,['case_id','offset','limit']);return json(await run(action,{case_id:id(p.get('case_id')),...page(p)}));
  });
  route('read',['GET'],async request=>{
    const p=query(request,['case_id','memory_id']);return json(await run('read',{case_id:id(p.get('case_id')),memory_id:id(p.get('memory_id'))}));
  });
  route('recall',['GET'],async request=>{
    const p=query(request,['case_id','query','limit']);const limit=Number(p.get('limit')||10);if(!Number.isSafeInteger(limit)||limit<1||limit>30)fail('检索数量须为 1–30。');
    return json(await run('recall',{case_id:id(p.get('case_id')),query:text(p.get('query'),300,'检索词'),limit,use_hindsight:true}));
  });
  route('add',['POST'],async request=>{
    const args=await body(request);keys(args,['case_id','note_id','content','source','confirmed']);id(args.case_id);
    if(args.note_id!==undefined){id(args.note_id);if(args.content!==undefined||args.source!==undefined)fail('选中案件记录后不能覆盖来源正文。');if(args.confirmed!==undefined&&args.confirmed!==true)fail('确认字段无效。');}
    else{text(args.content,16000,'记忆正文');text(args.source,1000,'来源说明');if(args.confirmed!==true)fail('请确认手工记忆的来源和内容。');}
    const result=await run('add',args);queue(args.case_id);return json(result,201);
  });
  for(const action of ['update','delete'])route(action,['POST'],async request=>{
    const args=await body(request);keys(args,action==='update'?['case_id','memory_id','revision','content']:['case_id','memory_id','revision']);
    id(args.case_id);id(args.memory_id);revision(args.revision);if(action==='update')text(args.content,16000,'记忆正文');
    const result=await run(action,args);queue(args.case_id);return json(result);
  });
  route('settings',['POST'],async request=>{
    const args=await body(request);keys(args,['case_id','enabled']);if(typeof args.enabled!=='boolean')fail('启用状态必须为布尔值。');if(args.case_id!==undefined)id(args.case_id);
    const result=await run('settings',args);
    if(args.case_id)queue(args.case_id);else void retryPending();
    return json(result);
  });
  route('sync',['POST'],async request=>{
    const args=await body(request);keys(args,['case_id']);id(args.case_id);await run('status',args);queue(args.case_id);
    return json({case_id:args.case_id,queued:true,notice:'已安排后台同步，本机记录可继续查看。'},202);
  });
  ctx.effect(()=>{
    const startup=setTimeout(()=>void retryPending(),1000),retry=setInterval(()=>void retryPending(),30000);
    startup.unref?.();retry.unref?.();
    return()=>{disposed=true;clearTimeout(startup);clearInterval(retry);pending.clear();for(const cancel of [...children.values()])cancel();};
  },'qunxing: selected case memories and pending cleanup');
}
