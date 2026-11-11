import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {createContentWatch} from './core.mjs';
import {createConnectionStore} from './connection.mjs';
import {createXhsClient} from './xiaohongshu.mjs';
import {createXhsRuntime} from './xhs-runtime.mjs';
import {createSessionDelivery} from './session.mjs';
import {prepareContentWatch} from '../../scripts/prepare-content-watch.mjs';

export const name='qx-content-watch';
export const inject=['connection','agents','workspaceRegistry','qxKnowledge'];
const fail=(message,status=400)=>{throw Object.assign(Error(message),{status});};
const json=(value,status=200)=>Response.json(value,{status,headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
async function body(request){
  if(!request.headers.get('content-type')?.startsWith('application/json'))fail('需要 JSON 请求。',415);
  const reader=request.body?.getReader();if(!reader)fail('请求为空。');const parts=[];let bytes=0;
  try{while(true){const {value,done}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>16384){await reader.cancel();fail('请求过长，请缩短输入。',413);}parts.push(value);}}
  finally{reader.releaseLock();}
  let result;try{result=JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{fail('请求格式无效。');}
  if(!result||typeof result!=='object'||Array.isArray(result))fail('请求格式无效。');return result;
}

export async function installContentWatch(ctx,config={},dependencies={}){
  if(!config.workspace||!config.stateDir)throw Error('拓客助手需要明确的工作区与资料目录。');
  const stateDir=resolve(config.stateDir),workspace=resolve(config.workspace);
  const connection=dependencies.connectionStore||await createConnectionStore({stateDir});
  const runtime=dependencies.runtime||createXhsRuntime({stateDir});
  const local=createXhsClient({authToken:()=>runtime.authToken});
  const api=dependencies.client?null:(await import('./justone.mjs')).createJustOneClient({token:()=>connection.token(),fetchImpl:dependencies.fetchImpl});
  const selected=()=>dependencies.client||(connection.status().provider==='justone'?api:local);
  const delivery=dependencies.sessionDelivery||createSessionDelivery(ctx,{workspace,stateDir});
  const ensureStarted=async()=>{if(connection.status().provider==='local-xhs')await runtime.ensureStarted();};
  const prepare=async()=>{
    if(connection.status().provider!=='local-xhs')return;
    await (dependencies.prepareComponent||prepareContentWatch)({stateDir});await runtime.ensureStarted();
  };
  const service=await createContentWatch({stateDir,client:{checkLogin:options=>selected().checkLogin(options),
    loginQr:options=>selected().loginQr(options),collect:(profile,options)=>selected().collect(profile,options)},
    prepareDelivery:()=>delivery.prepare(),deliver:report=>delivery.deliver(report),draft:(report,item)=>delivery.draft(report,item),ensureStarted,prepare});
  let background=null,backgroundKind=null,disposed=false,mutating=false;
  const status=()=>({...service.status(),connection:connection.status(),
    ...(backgroundKind==='draft'?{scriptPending:true}:background?{status:'running'}:{})});
  const busy=()=>background||service.isBusy();
  function start(kind,task){
    if(busy())fail('正在处理，请稍后再试。',409);
    backgroundKind=kind;
    background=Promise.resolve().then(task).catch(()=>{}).finally(()=>{background=null;backgroundKind=null;});
    return json(status(),202);
  }
  function route(path,methods,handler){ctx.connection.fetch.register({path:'/api/qx-content-watch/'+path,methods,
    requestBody:methods.includes('POST')?'streaming':'buffered',fetch:async request=>{
      let held=false;
      try{
        if(disposed)fail('拓客助手已停止，请重新打开工作台。',503);
        const expected=new URL(request.url),host=request.headers.get('host');if(host)expected.host=host;
        if(request.headers.get('x-qx-content-watch')!=='1'||(request.headers.get('origin')&&request.headers.get('origin')!==expected.origin))fail('请从工作台内操作。',403);
        if(request.method==='POST'){if(mutating)fail('设置正在保存，请稍后再试。',409);mutating=true;held=true;}
        const data=request.method==='POST'?await body(request):{};
        return await handler(data);
      }catch(error){return json({error:error.status?error.message:'操作未完成，已有资料保留；请检查输入或稍后重试。'},error.status||400);}
      finally{if(held)mutating=false;}
    }});}
  route('status',['GET'],()=>json(status()));
  route('profile',['POST'],async data=>{
    if(busy())fail('正在整理，请完成后修改业务方向和目标客户。',409);
    for(const [key,label] of [['practice','业务方向'],['targetClients','目标客户']])if(typeof data[key]!=='string'||!data[key].trim()||data[key].trim().length>500||data[key].includes('\0'))fail(label+'请填写 1–500 字。');
    if(typeof data.enabled!=='boolean')fail('启用状态无效。');
    await service.saveProfile(data);return json(status());
  });
  route('connection',['POST'],async data=>{
    if(busy())fail('正在整理，请完成后修改采集设置。',409);
    await connection.save(data);return json(status());
  });
  route('action',['POST'],async data=>{
    if(busy()&&data.action!=='pause')fail('正在处理，请稍后再试。',409);
    if(data.action==='run'){
      if(!service.status().profile)fail('请先填写业务方向和目标客户。');
      if(data.retryReportId!==undefined&&(typeof data.retryReportId!=='string'||!data.retryReportId||data.retryReportId.length>128))fail('请从已保存的报告重试。');
      return start('run',()=>service.run({retryReportId:data.retryReportId}));
    }
    if(data.action==='draft'){
      const report=service.status().lastReport;
      if(!report||data.reportId!==report.id||!report.items?.some(item=>item.id===data.itemId))fail('请从本期报告选择有效选题。');
      return start('draft',()=>service.draft(data));
    }
    if(['prepare','login'].includes(data.action)&&connection.status().provider!=='local-xhs')fail('当前使用 API 采集，请在采集设置中更新 Token。');
    if(data.action==='prepare')return start('prepare',()=>service.prepare());
    if(data.action==='login')return json({...await service.login(),connection:connection.status()});
    if(data.action==='check-login')await service.checkLogin();
    else if(data.action==='pause')await service.pause();
    else if(data.action==='resume')await service.resume();
    else fail('操作无效。');
    return json(status());
  });
  for(const [file,type] of [['client.js','text/javascript'],['panel.css','text/css']])ctx.connection.fetch.register({
    path:'/api/qx-content-watch/'+file,methods:['GET'],requestBody:'buffered',fetch:async()=>new Response(await readFile(new URL(file,import.meta.url)),
      {headers:{'content-type':type+'; charset=utf-8','cache-control':'no-store','x-content-type-options':'nosniff'}})});
  let timer,initial;
  const tick=()=>{if(!disposed&&!busy()&&!mutating)void service.tick().catch(()=>{});};
  if(dependencies.schedule!==false){timer=setInterval(tick,60000);timer.unref?.();initial=setTimeout(tick,30000);initial.unref?.();}
  async function dispose(){
    if(disposed)return;disposed=true;clearInterval(timer);clearTimeout(initial);delivery.dispose();
    await Promise.allSettled([runtime.stop(),service.dispose()]);await background;
  }
  ctx.effect(()=>dispose,'qx-content-watch lifetime');
  return {status,dispose,whenIdle:async()=>{await background;},service};
}
export async function apply(ctx,config){await installContentWatch(ctx,config);}
