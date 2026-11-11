import {randomUUID} from 'node:crypto';
import {mkdir,readFile,writeFile,rename,open,unlink,stat} from 'node:fs/promises';
import {join,resolve} from 'node:path';

export const INTERVAL_MS=72*60*60*1000;
const field=(value,label)=>{
  if(typeof value!=='string'||!value.trim()||value.trim().length>500||value.includes('\0'))throw Error(`${label}请填写 1–500 字。`);
  return value.trim();
};
const fresh=()=>({version:1,profile:null,enabled:false,nextRunAt:null,lastRunAt:null,lastReport:null,seen:[],drafts:{},active:null,status:'unconfigured',message:'填写业务方向和目标客户，配置采集方式后开始整理。',login:null});
const blocked=new Set(['login_required','unavailable','error','token_required','token_invalid','rate_limited','quota_exceeded','budget_exceeded','provider_unavailable','model_required']);
const apiErrors={
  TOKEN_REQUIRED:['token_required','请先在采集设置中保存 JustOneAPI Token。'],
  TOKEN_INVALID:['token_invalid','JustOneAPI 凭据已失效，请更新 Token 后重试。'],
  RATE_LIMIT:['rate_limited','采集服务暂时限流，本轮已停止；请稍后手动重试。'],
  QUOTA_EXCEEDED:['quota_exceeded','采集服务今日额度已用完，请检查账户额度后恢复整理。'],
  BUDGET_EXCEEDED:['budget_exceeded','采集服务余额或 Token 预算不足，请检查账户后恢复整理。'],
  API_PERMISSION:['provider_unavailable','当前 Token 没有此接口权限，请检查 JustOneAPI 账户设置。'],
  PROVIDER_UNAVAILABLE:['provider_unavailable','采集服务暂不可用，本轮已停止；已有报告保留，请稍后重试。'],
};

function sourceReport(profile,items,warnings,at){
  const lines=[`# 小红书拓客内容观察｜${new Date(at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}`,
    `业务方向：${profile.practice}`,`目标客户：${profile.targetClients}`,'',
    '以下为本轮实际采集内容；互动指标是采集时的快照。候选排序不代表全平台爆款榜。'];
  if(warnings.length)lines.push('',...warnings.map(w=>'采集说明：'+w));
  items.forEach((item,index)=>{
    const metrics=[['赞',item.likes],['评论',item.comments],['收藏',item.collected],['分享',item.shares]]
      .map(([label,value])=>label+'：'+(value==null?'未取得':value)).join('，');
    lines.push('',`## ${index+1}. ${item.title||'未取得标题'}`,item.url||'',
      `作者：${item.author||'未取得'}；发布时间：${item.publishedAt||'未取得'}；${metrics}`,
      `读取范围：${item.textCoverage||'标题简介'}`,(item.text||item.title||'未取得正文').slice(0,8000));
  });
  return lines.join('\n');
}

/** Durable single-user task. All model/network effects are injected at the boundary. */
export async function createContentWatch({stateDir,client,deliver,draft,prepareDelivery=async()=>{},ensureStarted=async()=>{},prepare=ensureStarted,clock=Date.now}={}){
  if(!stateDir||!client||!deliver)throw Error('拓客内容服务配置不完整。');
  const directory=resolve(stateDir),statePath=join(directory,'state.json'),lockPath=join(directory,'run.lock');
  await mkdir(join(directory,'reports'),{recursive:true,mode:0o700});
  let state;
  try{
    state=JSON.parse(await readFile(statePath,'utf8'));
    if(state.version!==1||!Array.isArray(state.seen))throw Error('invalid state');
  }catch(error){if(error.code==='ENOENT')state=fresh();else throw Error('拓客内容记录无法读取，原记录已保留，请先检查本机资料。');}
  let operation=null,disposed=false,scriptPending=false,lockNotice='',controlVersion=0;const lifetime=new AbortController();
  let saving=Promise.resolve();
  const save=()=>{
    const work=saving.then(async()=>{
      const temporary=statePath+'.'+randomUUID()+'.tmp';
      await writeFile(temporary,JSON.stringify(state)+'\n',{mode:0o600});await rename(temporary,statePath);
    });
    saving=work.catch(()=>{});return work;
  };
  async function reloadState(version){
    const saved=JSON.parse(await readFile(statePath,'utf8'));
    // A local pause/resume after this operation started takes precedence over its older disk read.
    if(controlVersion!==version){
      saved.enabled=state.enabled;
      if(!saved.enabled){saved.status='paused';saved.message='已暂停定时整理。';}
    }
    state=saved;
  }
  async function liveOwner(){
    try{const owner=JSON.parse(await readFile(lockPath,'utf8'));if(!Number.isSafeInteger(owner.pid)||owner.pid<1)return false;process.kill(owner.pid,0);return true;}
    catch(error){return error.code==='EPERM';}
  }
  if(state.active&&!await liveOwner()){
    state.enabled=false;state.status='error';state.message='上次整理中断，已有报告保留；请先核对整理会话，再恢复后续整理。';state.active=null;await save();
  }
  const snapshot=()=>structuredClone({profile:state.profile,enabled:state.enabled,nextRunAt:state.nextRunAt,lastRunAt:state.lastRunAt,
    status:lockNotice?'error':state.status,message:lockNotice||state.message,sessionId:'qx-content-watch',lastReport:state.lastReport,login:state.login,scriptPending});
  function failure(error){
    if(error.code==='MODEL_REQUIRED'){
      state.status='model_required';state.message='请先在工作台选择并配置摘要模型，再点击立即整理或恢复整理。';
    }else if(apiErrors[error.code]){
      [state.status,state.message]=apiErrors[error.code];state.login=null;
    }else if(error.code==='LOGIN_REQUIRED'){
      state.status='login_required';state.login={loggedIn:false};state.message='小红书登录已失效或尚未连接，请重新扫码，再检查连接。';
    }else if(['COMPONENT_MISSING','UNAVAILABLE','COMPONENT_UNAVAILABLE','COMPONENT_NOT_READY'].includes(error.code)){
      state.status='unavailable';state.message='小红书连接组件未就绪，请准备组件后重新连接。';
    }else{
      state.status='error';state.message='本次整理未完成，已有资料已保留。请检查采集设置或工作台会话后手动重试。';
    }
  }
  async function inspectLogin(){
    await ensureStarted();const login=await client.checkLogin({signal:lifetime.signal});
    state.login={loggedIn:login.loggedIn===true,...(typeof login.verified==='boolean'?{verified:login.verified}:{}),...(typeof login.username==='string'?{username:login.username.slice(0,100)}:{})};
    if(!state.login.loggedIn)throw Object.assign(Error('login required'),{code:'LOGIN_REQUIRED'});
    return state.login;
  }
  async function acquire(){
    lockNotice='';
    for(let attempt=0;attempt<2;attempt++){
      let handle;
      try{
        handle=await open(lockPath,'wx',0o600);
        try{await handle.writeFile(JSON.stringify({pid:process.pid}));return handle;}
        catch(error){await handle.close();await unlink(lockPath).catch(()=>{});throw error;}
      }catch(error){
        if(error.code!=='EEXIST')throw error;
        let raw,info;try{raw=await readFile(lockPath,'utf8');info=await stat(lockPath);}catch(e){if(e.code==='ENOENT')continue;throw e;}
        let owner;try{owner=JSON.parse(raw);}catch{}
        if(Number.isSafeInteger(owner?.pid)&&owner.pid>0){
          try{process.kill(owner.pid,0);return null;}catch(e){if(e.code!=='ESRCH')return null;}
        }else{
          // Give a concurrently initializing owner time to finish writing its PID.
          lockNotice='整理任务锁尚在确认，请稍后重试；已启用的任务会在约 1 分钟后自动再检查。';
          if(Date.now()-info.mtimeMs<60000)return null;
        }
        // Do not remove a lock replaced or completed since it was inspected.
        try{const current=await stat(lockPath);
          if(current.ino!==info.ino||current.mtimeMs!==info.mtimeMs||await readFile(lockPath,'utf8')!==raw)return null;
          await unlink(lockPath);lockNotice='';
        }catch(e){if(e.code!=='ENOENT')throw e;}
      }
    }
    return null;
  }
  async function runImpl(scheduled,retryReportId){
    if(disposed||!state.profile)return snapshot();
    const version=controlVersion;
    const lock=await acquire();if(!lock)return snapshot();
    const startedAt=clock();
    try{
      // Another process or a reloaded plugin may have completed the same occurrence.
      try{await reloadState(version);}catch(error){if(error.code!=='ENOENT')throw error;}
      if(scheduled&&(!state.enabled||clock()<state.nextRunAt||blocked.has(state.status)))return snapshot();
      const profile={...state.profile};
      let cached;
      // Only an explicit, durable pre-submission record is safe to retry. Older or uncertain records stay conservative.
      if(state.lastReport?.pending&&state.lastReport.submitted===false){
        const report=JSON.parse(await readFile(join(directory,'reports',state.lastReport.id+'.json'),'utf8'));
        if(report.id!==state.lastReport.id||!Array.isArray(report.items))throw Error('保存的报告无法读取。');
        if(report.profile?.practice===profile.practice&&report.profile?.targetClients===profile.targetClients)cached=report;
      }
      if(retryReportId!==undefined&&(!cached||cached.id!==retryReportId))throw Error('待整理报告或业务方向已变化，请刷新后重试。');
      const id=cached?.id||randomUUID(),createdAt=cached?.createdAt??startedAt;
      state.status='running';state.message=cached?'正在将已保存的内容整理到专用会话…':'正在读取小红书并整理本期内容…';state.active={id,phase:'preparing-session',startedAt};await save();
      if(!cached)await inspectLogin();
      await prepareDelivery();if(disposed)throw Error('service disposed');
      if(!cached){state.active.phase='collecting';await save();}
      const result=cached||await client.collect(profile,{signal:lifetime.signal,seenIds:[...state.seen]});
      if(disposed)throw Error('service disposed');
      if(!cached&&state.login?.verified===false)state.login.verified=true;
      const seen=new Set(state.seen),unique=new Map();
      for(const item of result.items||[]){
        const published=typeof item?.publishedAt==='string'?Date.parse(item.publishedAt):NaN;
        if(!cached&&Number.isFinite(published)&&(published<startedAt-7*24*60*60*1000||published>startedAt+24*60*60*1000))continue;
        if(item&&typeof item.id==='string'&&item.id&&!seen.has(item.id)&&!unique.has(item.id))unique.set(item.id,item);
      }
      const items=[...unique.values()].slice(0,6);
      if(!items.length){
        state.message='本期没有新增相关内容；上期报告已保留。';
      }else{
        const content=sourceReport(profile,items,(result.warnings||[]).slice(0,10),createdAt);
        const path=join(directory,'reports',id+'.md');
        await writeFile(path,content+'\n',{mode:0o600});
        await writeFile(join(directory,'reports',id+'.json'),JSON.stringify({id,createdAt,profile,items,warnings:result.warnings||[]})+'\n',{mode:0o600});
        state.lastReport={id,title:'本期小红书内容观察',createdAt,profile,path,content,pending:true,submitted:false,items:items.map(({id,title,url})=>({id,title,url}))};
        state.active.phase='preparing-session';await save();
        const remember=()=>{state.seen=[...new Set([...state.seen,...items.map(item=>item.id)])].slice(-10000);};
        const delivered=await deliver({id,profile,items,content,path,createdAt,
          onSubmitting:async({messageId})=>{
            // Persist intent at the queue boundary, after session preparation succeeds.
            state.active.phase='submitting';state.active.messageId=messageId;state.lastReport.submitted=true;remember();await save();
          }});
        state.lastReport.submitted=true;remember();
        if(delivered?.content){state.lastReport.content=delivered.content+'\n\n---\n\n'+content;await writeFile(path,state.lastReport.content+'\n',{mode:0o600});}
        state.lastReport.pending=delivered?.pending===true;
        state.message=delivered?.pending?'本期来源已保存并交给专用会话；请到会话查看整理进度。':'本期内容已整理到专用会话。';
      }
      state.lastRunAt=clock();state.nextRunAt=clock()+INTERVAL_MS;state.status=state.enabled?'ready':'paused';
    }catch(error){failure(error);}
    finally{state.active=null;try{await save();}finally{await lock.close();await unlink(lockPath).catch(()=>{});}}
    return snapshot();
  }
  function run({scheduled=false,retryReportId}={}){
    if(operation)return operation;
    operation=runImpl(scheduled,retryReportId).finally(()=>{operation=null;});return operation;
  }
  async function checkLoginImpl(){
    if(operation)return snapshot();
    try{await inspectLogin();state.status=state.profile?(state.enabled?'ready':'paused'):'unconfigured';state.message=state.login.verified===false?'已保存 API 凭据；首次整理时验证服务连接。':'小红书已连接。';}
    catch(error){failure(error);}await save();return snapshot();
  }
  async function draftImpl({reportId,itemId}={}){
    if(typeof draft!=='function')throw Error('拍摄稿会话尚未就绪。');
    if(typeof reportId!=='string'||reportId!==state.lastReport?.id||typeof itemId!=='string'||!state.lastReport.items?.some(item=>item.id===itemId))throw Error('请从本期报告选择有效选题。');
    const key=reportId+':'+itemId;
    if(state.drafts?.[key]){state.message='此选题已交给会话，请到会话继续修改稿件。';return snapshot();}
    const version=controlVersion;
    const lock=await acquire();if(!lock)throw Error('正在整理，请稍后生成拍摄稿。');
    scriptPending=true;
    try{
      await reloadState(version);
      if(state.drafts?.[key])return snapshot();
      const report=JSON.parse(await readFile(join(directory,'reports',reportId+'.json'),'utf8'));
      const item=report.items?.find(item=>item.id===itemId);if(report.id!==reportId||!item)throw Error('选题来源记录无效。');
      state.active={id:randomUUID(),phase:'draft-preparing',reportId,itemId};state.message='正在核对选题来源并生成口播与拍摄稿…';await save();
      const result=await draft({...report,onSubmitting:async({messageId})=>{
        state.active.phase='draft-submitting';state.active.messageId=messageId;
        state.drafts={...state.drafts,[key]:{messageId,submittedAt:clock()}};
        state.drafts=Object.fromEntries(Object.entries(state.drafts).slice(-200));await save();
      }},item);
      if(result?.content)await writeFile(join(directory,'reports',reportId+'-draft-'+report.items.indexOf(item)+'.md'),result.content+'\n',{mode:0o600});
      state.message=result?.pending?'拍摄稿已交给会话，请到会话查看进度并继续修改。':'口播与拍摄稿已生成，请到会话查看并核对来源。';
    }catch(error){failure(error);}
    finally{scriptPending=false;state.active=null;try{await save();}finally{await lock.close();await unlink(lockPath).catch(()=>{});}}
    return snapshot();
  }
  return {
    status:snapshot,isBusy:()=>!!operation,
    async saveProfile(input){
      if(operation)throw Error('正在整理，请完成后修改业务方向和目标客户。');
      const profile={practice:field(input.practice,'业务方向'),targetClients:field(input.targetClients,'目标客户')};
      if(typeof input.enabled!=='boolean')throw Error('启用状态无效。');
      state.profile=profile;state.enabled=input.enabled;state.nextRunAt??=clock();
      state.status=input.enabled?'ready':'paused';state.message=input.enabled?'已启用，每 3 天整理到专用会话。':'已保存，定时整理暂停。';await save();return snapshot();
    },
    run,
    async tick(){
      if(disposed||!state.enabled||!state.profile||operation||blocked.has(state.status)||clock()<state.nextRunAt)return snapshot();
      return run({scheduled:true});
    },
    async pause(){controlVersion++;state.enabled=false;if(!operation){state.status='paused';state.message='已暂停定时整理。';}await save();return snapshot();},
    async resume(){if(!state.profile)throw Error('请先填写业务方向和目标客户。');controlVersion++;state.enabled=true;if(!operation)state.status=state.login?.loggedIn===false?'login_required':'ready';await save();return snapshot();},
    checkLogin(){if(operation)return operation;operation=checkLoginImpl().finally(()=>{operation=null;});return operation;},
    draft(input){if(operation)return Promise.reject(Error('正在整理，请稍后生成拍摄稿。'));operation=draftImpl(input).finally(()=>{operation=null;});return operation;},
    async login(){
      if(operation)throw Error('正在整理，请稍后连接。');
      try{await ensureStarted();const qr=await client.loginQr();state.login={loggedIn:qr.isLoggedIn===true};state.message=qr.isLoggedIn?'小红书已连接，请检查连接后继续。':'请用本人小红书扫码，完成后点击检查连接。';state.status=qr.isLoggedIn?(state.enabled?'ready':'paused'):'login_required';await save();return {...snapshot(),qr};}
      catch(error){failure(error);await save();return snapshot();}
    },
    async prepare(){
      if(operation)return operation;
      operation=(async()=>{
        state.status='running';state.message='正在准备小红书连接组件，首次准备可能需要几分钟…';await save();
        try{await prepare();await inspectLogin();state.status=state.profile?(state.enabled?'ready':'paused'):'unconfigured';state.message='小红书连接组件已就绪。';}
        catch(error){failure(error);}await save();return snapshot();
      })().finally(()=>{operation=null;});return operation;
    },
    async dispose(){disposed=true;lifetime.abort();await operation?.catch(()=>{});},
  };
}
