/** Personal WeChat-only Harness adapter. Protocol/media/login are MIT upstream modules. */
import {randomBytes,randomUUID} from 'node:crypto';
import {mkdir, readFile, writeFile, rename} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {readFileSync} from 'node:fs';
import * as protocol from './ilink.js';
import {WechatLoginManager} from './login.js';
import {WechatState} from './state.js';
import {saveInboundMedia, describeForModel, prepareOutbound} from './media.js';
import qrcode from './vendor/qrcode-generator.mjs';
import {ReplyCollector, chunkText} from './qx-reply.js';
import {ownerAccepts, workspaceFile, publicLogin} from './qx-owner.js';
import {openSessionAgent} from './session.js';
import {MessageCoalescer} from './qx-coalescer.js';

export const name='qx-personal-wechat';
export const inject=['agents'];
export async function apply(ctx,config={}) {
  if (!config.workspace || !config.stateDir) throw new Error('微信插件需要明确的 workspace 与 stateDir');
  const workspace=resolve(config.workspace), stateDir=resolve(config.stateDir);
  await mkdir(workspace,{recursive:true});
  const state=new WechatState({root:stateDir}); await state.init();
  const logins=new WechatLoginManager({state,ilink:protocol,reuseStoredBinding:false});
  const collector=new ReplyCollector(ctx);
  const csrf=randomBytes(24).toString('hex');
  let sessionId=config.sessionId || 'qx-personal-workbench';
  let account=null, login=null, monitor=null, monitorTask=null, stopped=false, disposed=false, actionBusy=false, lastError='', forwarded=0, ignored=0;
  let seen=[],loginPending=false;
  const routePath=join(stateDir,'qx-route.json'), seenPath=join(stateDir,'qx-seen.json');
  const activeAccountPath=join(stateDir,'qx-active-account.json');
  async function readOptional(path,fallback) {
    try{return JSON.parse(await readFile(path,'utf8'));}catch(error){if(error.code==='ENOENT')return fallback;throw error;}
  }
  async function writeAtomic(path,value) {
    const temporary=path+'.tmp';await writeFile(temporary,JSON.stringify(value)+'\n');await rename(temporary,path);
  }
  const route=await readOptional(routePath,{});
  if(route.sessionId) sessionId=route.sessionId;
  let materialized=Boolean(route.sessionId);
  seen=await readOptional(seenPath,[]);
  async function harness(module) {
    const loader=ctx.loader;
    if(loader?.internal?.import) return loader.internal.import(module,loader.baseUrl ?? ctx.baseUrl,{});
    return import(module);
  }
  async function getAgent(targetSessionId=sessionId) {
    const registry=ctx.get('workspaceRegistry');
    if(!registry)throw new Error('工作区服务尚未就绪');
    const workspaceEntry=await registry.create(workspace,'群兴工作区');
    const active=ctx.agents.get(targetSessionId);
    if(active){await workspaceEntry.attachSession(targetSessionId);return active;}
    const {SessionPersistenceNotFoundError}=await harness('@deepseek-ai/dsh-session-persistence');
    const presets=ctx.get('agentPresets'), preset=config.agentPreset || presets?.defaultId;
    const selection=ctx.get('agentDefaultModel')?.currentSelection?.();
    const opened=await openSessionAgent({agents:ctx.agents,sessionId:targetSessionId,
      meta:{cwd:workspace,...(preset?{agentPreset:preset}:{})},agentOptions:selection,
      isMissingSession:error=>targetSessionId===sessionId && !materialized && error instanceof SessionPersistenceNotFoundError,
      setup:async agentCtx=>{if(preset && presets) await presets.mount(agentCtx,preset);}});
    ctx.effect(()=>opened.handle.dispose,`qx-wechat session ${targetSessionId}`);
    await workspaceEntry.attachSession(targetSessionId);
    if(targetSessionId===sessionId){await writeAtomic(routePath,{sessionId});materialized=true;}
    return opened.handle.agent;
  }
  async function reply(text,recipient=account) {
    if(!recipient?.userId) throw new Error('尚未绑定本人微信');
    const context=(await state.loadContextTokens(recipient.accountId))[recipient.userId]?.token;
    if(!context) throw new Error('请先从本人微信发送一条消息');
    for(const chunk of chunkText(text)) {
      await protocol.sendText({baseUrl:recipient.baseUrl,token:recipient.token,toWxid:recipient.userId,text:chunk,contextToken:context});
    }
  }
  const inboxPath=join(stateDir,'qx-pending.json');
  const batcher=new MessageCoalescer({state:await readOptional(inboxPath,undefined),
    quietMs:config.coalesceQuietMs ?? 8000,mediaQuietMs:config.coalesceMediaQuietMs ?? 12000,
    persist:value=>writeAtomic(inboxPath,value),process:processBatch,
    onError:error=>{lastError=String(error.message ?? error);}});
  await batcher.recover();
  async function processBatch(batch) {
    const recipient=account;let processingAgent;
    try {
      if(!recipient || batch.accountId!==recipient.accountId || batch.items.some(item=>item.userId!==recipient.userId))throw new Error('这批消息所属微信已变更，材料已保留，请在本机查看。');
      const failed=batch.items.filter(item=>item.error);
      if(!batch.items.some(item=>item.lines.length))throw new Error('这批消息没有可读取内容：'+failed.map(item=>item.error).join('；')+'。请重新发送文字或失败附件。');
      const text=batch.items.map((item,index)=>`[第${index+1}条微信]\n${item.lines.join('\n\n')}${item.error?'\n[附件未读取：'+item.error+'。不得推断其内容，请明确说明缺失并请求补发。]':''}`).join('\n\n');
      const agent=processingAgent=await getAgent(batch.sessionId);
      await agent.whenIdle?.();
      const {createUserMessage}=await harness('@deepseek-ai/dsh-llm');
      const userMessage=createUserMessage({content:[{type:'text',text:'以下是本人连续发送的一批微信消息，请按发送顺序合并理解，统一处理和回复。\n\n'+text}],source:{kind:'user'}});
      const waiting=collector.wait(batch.sessionId,userMessage.id,config.replyTimeoutMs ?? 300000);
      agent.followup(userMessage);forwarded++;
      const outcome=await waiting;
      if(outcome.error || ['timeout','not-claimed'].includes(outcome.stopReason))throw new Error(outcome.error || `当前会话尚未完成（${outcome.stopReason}），请到工作台查看；不会自动重发。`);
      if(outcome.text)await reply(outcome.text,recipient);
      else if(!outcome.deliveredByTool)await reply('本轮已结束，没有可发送的文字；请在工作台查看处理记录。',recipient);
      lastError='';
    } catch(error) {
      lastError=String(error.message ?? error);
      if(recipient?.accountId===batch.accountId)await reply(`处理未完成（批次 ${batch.id.slice(0,8)}）：${lastError}`,recipient).catch(()=>{});
      throw error;
    } finally {
      // A reply timeout does not mean the shared desktop Agent stopped running.
      await processingAgent?.whenIdle?.();
    }
  }
  async function receive(message) {
    if(!ownerAccepts(account,message)){ignored++;return;}
    const messageId=String(message.message_id ?? message.client_id ?? '');
    const id=account.accountId+':'+(messageId || randomUUID());
    if(messageId && (seen.includes(id)||batcher.has(id)))return;
    if(message.context_token)await state.saveContextToken(account.accountId,account.userId,message.context_token);
    const normalized=protocol.describeInbound(message),lines=[],errors=[];
    if(['text','voice'].includes(normalized.kind) && normalized.text?.trim())lines.push(normalized.text.trim());
    for(const item of normalized.media ?? []) {
      try {
        const saved=await saveInboundMedia({ilink:protocol,chatId:account.userId,item:item.item ?? item,
          inboxPath:join(workspace,'wechat-inbox'),maxBytes:Number.MAX_SAFE_INTEGER});
        lines.push(describeForModel(saved));
      }catch(error){errors.push(String(error.message ?? error));}
    }
    if(!lines.length&&!errors.length)errors.push('消息暂时无法读取，请发送文字、图片或文件');
    await batcher.add({id,key:account.accountId+':'+account.userId+':'+sessionId,accountId:account.accountId,
      userId:account.userId,sessionId,text:normalized.text??'',lines,hasMedia:Boolean(normalized.media?.length),
      ...(errors.length?{error:errors.join('；')}:{})});
    // Only acknowledge deduplication after normalized text and local attachment paths are durable.
    if(messageId){seen=[...seen.slice(-499),id];await writeAtomic(seenPath,seen);}
  }
  async function startMonitor(record) {
    if(monitor)return;
    if(!record?.userId || !record?.token)throw new Error('扫码结果缺少本人标识或凭据，尚未接通');
    account=record;stopped=false;batcher.resume();const control=new AbortController();monitor=control;
    monitorTask=(async()=>{
      let cursor=await state.loadCursor(record.accountId);
      while(!stopped && !control.signal.aborted) {
        try {
          const result=await protocol.getUpdates({baseUrl:record.baseUrl,token:record.token,cursor,signal:control.signal});
          if(control.signal.aborted)break;
          if(Number(result.ret ?? 0)!==0 || Number(result.errcode ?? 0)!==0) {
            if([Number(result.ret),Number(result.errcode)].includes(-14)) {lastError='微信登录已失效，请重新扫码';break;}
            throw new Error(`微信接收失败：${result.ret ?? result.errcode}`);
          }
          batcher.beginReceive();
          try{for(const message of result.messages ?? [])await receive(message);}
          finally{batcher.endReceive();}
          if(result.cursor){cursor=result.cursor;await state.saveCursor(record.accountId,cursor);}
        } catch(error) {
          if(control.signal.aborted)break;
          lastError=String(error.message ?? error);
          await new Promise(resolve=>{const t=setTimeout(resolve,5000);control.signal.addEventListener('abort',()=>{clearTimeout(t);resolve();},{once:true});});
        }
      }
    })().catch(error=>{lastError=String(error.message ?? error);}).finally(()=>{if(monitor===control)monitor=null;});
  }
  function stop(){stopped=true;batcher.pause();monitor?.abort();if(login)logins.cancel(login);}
  async function pauseReceiving(){stop();await monitorTask;monitor=null;}
  ctx.effect(()=>()=>{disposed=true;stop();},'qx-wechat cleanup');
  const accounts=await state.loadAccounts();
  const activeAccount=await readOptional(activeAccountPath,{});
  account=accounts.find(record=>record.accountId===activeAccount.accountId) || (accounts.length===1?accounts[0]:null);
  if(account)seen=seen.map(id=>id.includes(':')?id:account.accountId+':'+id);
  if(account && config.autoConnect!==false) await startMonitor(account);

  const activating=()=>loginPending&&login?.status==='confirmed';
  const scanning=()=>loginPending||login&&!['confirmed','cancelled','error','give_up'].includes(login.status);
  function assertSwitchable(){
    const pending=batcher.snapshot();
    if(pending.active||pending.pendingMessages)throw new Error('微信还有消息待处理，请处理完成后再切换会话或微信。');
  }
  async function selectableSessions(){
    const controller=ctx.get('sessionController');
    if(!controller)throw new Error('会话列表暂时不可用，请稍后重试。');
    const {items}=await controller.list({},new AbortController().signal);
    const archived=new Set(ctx.get('workspaceRegistry')?.archivedSessionIds || []);
    return items.filter(row=>row.cwd&&resolve(row.cwd)===workspace&&!archived.has(row.sessionId))
      .map(row=>({id:row.sessionId,title:typeof row.projections?.values?.title==='string'?row.projections.values.title:'新会话',updatedAt:row.updatedAt}));
  }
  async function beginLogin(){
    if(scanning())throw new Error('已有扫码请求，请先完成或取消。');
    assertSwitchable();await pauseReceiving();assertSwitchable();
    lastError='';const attempt=login=await logins.start();loginPending=true;
    void logins.run(attempt).then(async result=>{
      if(disposed||login!==attempt||result.status!=='confirmed')return;
      const record={accountId:result.accountId,...await state.loadAccount(result.accountId)};
      if(!record.userId||!record.token)throw new Error('扫码未返回完整账号，请重试。');
      await writeAtomic(activeAccountPath,{accountId:record.accountId});
      if(!disposed&&login===attempt)await startMonitor(record);
    }).catch(error=>{lastError=String(error.message??error);}).finally(()=>{if(login===attempt)loginPending=false;});
  }
  async function bindSession(target){
    if(scanning())throw new Error('请完成或取消当前扫码后再切换会话。');
    assertSwitchable();
    const resume=Boolean(monitor);await pauseReceiving();
    try{
      assertSwitchable();await getAgent(target);
      await writeAtomic(routePath,{sessionId:target});sessionId=target;materialized=true;
    }finally{if(resume&&account)await startMonitor(account);}
  }

  ctx.inject(['tools'],toolCtx=>{
    const dispose=toolCtx.tools.register({
      name:'wechat_send_file',description:'把当前工作区的文件发回已经扫码绑定的本人微信。没有客户或群收件人参数。',
      parameters:{path:{type:'string',required:true,description:'工作区内文件的绝对路径'}},
      output:{schema:{type:'string'},render:(_args,value)=>[{type:'text',text:value}]},timeoutMs:300000,
      async execute(args){
        const recipient=account;
        if(!recipient?.userId)throw new Error('尚未绑定本人微信');
        const path=await workspaceFile(workspace,args.path);
        const file=await prepareOutbound(path,{maxBytes:Number.MAX_SAFE_INTEGER});
        const context=(await state.loadContextTokens(recipient.accountId))[recipient.userId]?.token;
        if(!context)throw new Error('请先从本人微信发送一条消息');
        const send=file.kind==='image'?protocol.sendImage:file.kind==='video'?protocol.sendVideo:protocol.sendFile;
        if(disposed||account!==recipient)throw new Error('微信已切换，文件未发送，请在当前会话重新操作。');
        await send({baseUrl:recipient.baseUrl,token:recipient.token,toWxid:recipient.userId,filePath:path,fileName:file.name,contextToken:context});
        return `已发回本人微信：${file.name}`;
      },
    });
    toolCtx.effect(()=>dispose,'qx-wechat file tool');
  });
  const json=(res,status,value)=>{res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});res.end(JSON.stringify(value));};
  ctx.inject(['webServer'],webCtx=>{
    const handlers={
      '/qx-wechat':async(req,res)=>{
        if(req.method!=='GET')return json(res,405,{error:'GET only'});
        res.writeHead(200,{'content-type':'text/html; charset=utf-8','cache-control':'no-store','Content-Security-Policy':"default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'self'"});
        res.end(readFileSync(new URL('./qx-panel.html',import.meta.url),'utf8').replaceAll('__QX_CSRF__',csrf));
      },
      '/qx-wechat/state':async(req,res)=>{
        const loginState=publicLogin(login);
        if(loginState&&activating()){loginState.status='activating';delete loginState.qrPayload;loginState.verifyCodeNeeded=false;}
        if(loginState?.qrPayload){const qr=qrcode(0,'M');qr.addData(loginState.qrPayload);qr.make();loginState.qrImage=qr.createDataURL(5,8);delete loginState.qrPayload;}
        return json(res,200,{sessionId,workspace,connected:Boolean(monitor),owner:account?.userId ?? null,login:loginState,lastError,forwarded,ignored,batching:batcher.snapshot()});
      },
      '/qx-wechat/settings':async(req,res)=>{
        if(req.method!=='GET')return json(res,405,{error:'GET only'});
        return json(res,200,{csrf,sessions:await selectableSessions()});
      },
      '/qx-wechat/action':async(req,res)=>{
        if(req.method!=='POST' || req.headers['x-qx-token']!==csrf)return json(res,403,{error:'请从本机微信设置页操作'});
        if(actionBusy||activating())return json(res,409,{error:'上一项操作尚未完成，请稍后重试。'});
        actionBusy=true;
        try{
        let text='';for await(const part of req){text+=part;if(text.length>8192)return json(res,413,{error:'设置内容过长'});}
        const body=JSON.parse(text || '{}');
        if(activating())return json(res,409,{error:'正在连接新微信，请稍后重试。'});
        if(body.action==='login'||body.action==='switch-account') {
          await beginLogin();
        } else if(body.action==='prepare'){await getAgent();}
        else if(body.action==='cancel'){if(login)logins.cancel(login);}
        else if(body.action==='verify'){if(!login)throw new Error('没有扫码请求');logins.submitVerifyCode(login,body.code);}
        else if(body.action==='pause'){await pauseReceiving();}
        else if(body.action==='resume'){if(scanning())throw new Error('请先取消扫码。');if(!account)throw new Error('请先扫码连接微信。');await startMonitor(account);}
        else if(body.action==='new-session'){
          if(scanning())throw new Error('请完成或取消当前扫码后再新建会话。');
          assertSwitchable();const controller=ctx.get('sessionController');if(!controller)throw new Error('会话服务尚未就绪。');
          const created=await controller.create({sessionId:'session-'+randomUUID(),cwd:workspace,agentPreset:config.agentPreset||'qunxing'});
          await bindSession(created.sessionId);
        }
        else if(body.action==='session') {
          if(!(await selectableSessions()).some(row=>row.id===body.sessionId))throw new Error('该会话不可用，请刷新会话列表。');
          await bindSession(body.sessionId);
        } else throw new Error('未知操作');
        return json(res,200,{ok:true,sessionId});
        }finally{actionBusy=false;}
      },
    };
    for(const [path,handler] of Object.entries(handlers))webCtx.effect(()=>webCtx.webServer.register({kind:'exact',path,handler:async(req,res)=>{
      const remote=req.socket?.remoteAddress;
      if(!['127.0.0.1','::1','::ffff:127.0.0.1'].includes(remote))return json(res,403,{error:'仅本机'});
      const origin=req.headers.origin;
      if(origin && origin!==`http://${req.headers.host}`)return json(res,403,{error:'跨站请求已拒绝'});
      try{await handler(req,res);}catch(error){json(res,400,{error:String(error.message ?? error)});}
    }}),`qx-wechat ${path}`);
  });
}
