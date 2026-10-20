const http=require('node:http');
const {createHash}=require('node:crypto');
const {TextDecoder}=require('node:util');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SCOPE=['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'];
const CODES=new Set(['BLOCKED_LIVE','VERSION_CONFLICT','STATE_CONFLICT','BUDGET_EXCEEDED',
  'CROSS_MATTER_DENIED','ACCESS_DENIED','APPROVAL_CANCELED']);
const ACTIVE=new Set(['queued','preparing','routing','retrieving','generating','persisting']);
const exact=(value,fields)=>value && typeof value==='object' && !Array.isArray(value) &&
  Object.keys(value).length===fields.length && fields.every(key=>Object.hasOwn(value,key));
const uuid=value=>typeof value==='string' && UUID.test(value);
const count=value=>Number.isSafeInteger(value) && value>=0;
const check=guard=>{try{return guard()===true;}catch{return false;}};
const denied=(code='BLOCKED_LIVE')=>({ok:false,code});
const fail=()=>{throw new Error('BLOCKED_LIVE');};
const same=(left,right)=>SCOPE.every(key=>left?.[key]===right?.[key]);
function validInput(value) {
  const scope=value?.expected_scope;
  return exact(value,['conversation_id','request_id','expected_scope','expected_composer_revision','content_sha256']) &&
    uuid(value.conversation_id) && uuid(value.request_id) && count(value.expected_composer_revision) &&
    typeof value.content_sha256==='string' && /^[0-9a-f]{64}$/.test(value.content_sha256) && exact(scope,SCOPE) &&
    uuid(scope.workspace_id) && scope.conversation_id===value.conversation_id &&
    ['conversation','intake','matter'].includes(scope.scope_kind) &&
    (scope.scope_kind==='conversation' ? scope.scope_ref===null : uuid(scope.scope_ref)) &&
    count(scope.binding_revision) && scope.binding_revision>0 && count(scope.input_revision) && count(scope.materials_revision);
}
function validOrigin(origin) {
  if(typeof origin!=='string' || !/^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(origin))return false;
  try{return new URL(origin).origin===origin;}catch{return false;}
}
function readJSON(origin,path,token) {
  return new Promise((resolve,reject)=>{
    let bytes=0,parts=[],done=false;
    const finish=(error,value)=>{
      if(done)return;done=true;clearTimeout(timer);parts=[];
      if(error)reject(new Error('BLOCKED_LIVE'));else resolve(value);
    };
    const request=http.get(origin+path,{agent:false,maxHeaderSize:8192,
      headers:{Accept:'application/json',Cookie:'qx_session='+token}},response=>{
      if(response.statusCode!==200 || !/^application\/json(?:\s*;|$)/i.test(response.headers['content-type'] || '') ||
          (response.headers['content-encoding'] && response.headers['content-encoding']!=='identity')){
        response.destroy();request.destroy();finish(true);return;
      }
      response.on('data',chunk=>{
        bytes+=chunk.length;
        if(bytes>262144){response.destroy();request.destroy();finish(true);return;}
        parts.push(chunk);
      });
      response.on('error',()=>finish(true));
      response.on('aborted',()=>finish(true));
      response.on('end',()=>{
        try{finish(false,JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(parts))));}
        catch{finish(true);}
      });
    });
    const timer=setTimeout(()=>{request.destroy();finish(true);},5000);
    request.on('error',()=>finish(true));
  });
}
async function cookie(context,path,guard) {
  if(!check(guard))fail();
  const values=await context.session.cookies.get({url:context.origin+path});
  if(!check(guard) || !Array.isArray(values))fail();
  const matches=values.filter(value=>value?.name==='qx_session');
  if(matches.length!==1 || typeof matches[0].value!=='string' || !/^[A-Za-z0-9_-]{1,256}$/.test(matches[0].value))fail();
  return matches[0].value;
}
async function tokenFor(context,paths,guard,expected) {
  let token=expected;
  for(const path of paths){
    const actual=await cookie(context,path,guard);
    if(token!==undefined && token!==actual)fail();token=actual;
  }
  return token;
}
async function snapshot(context,input,paths,guard,expectedToken) {
  const token=await tokenFor(context,paths,guard,expectedToken);
  const [draft,capability,materials]=await Promise.all(paths.map(path=>readJSON(context.origin,path,token)));
  if(!check(guard) || !same(input.expected_scope,draft?.scope) || !same(input.expected_scope,capability?.scope) ||
      !same(input.expected_scope,materials?.scope) || draft.archived_at!==null ||
      draft.composer_revision!==input.expected_composer_revision || capability.composer_revision!==input.expected_composer_revision ||
      capability.basis!=='saved_draft' || !['ready','unapproved','budget_exhausted'].includes(capability.state) ||
      capability.content_sha256!==input.content_sha256 || !Array.isArray(materials.items) || materials.items.length ||
      (draft.latest_run!==null && (!draft.latest_run || ACTIVE.has(draft.latest_run.state))) ||
      typeof draft.draft_input!=='string' || !draft.draft_input.trim() || Buffer.byteLength(draft.draft_input,'utf8')>65536 ||
      createHash('sha256').update(draft.draft_input,'utf8').digest('hex')!==input.content_sha256)fail();
  await tokenFor(context,paths,guard,token);
  return {token,content:draft.draft_input};
}
function registerModelApproval({ipcMain,runtime,judgeRuntime,captureContext,isBusy,setBusy,confirm}) {
  let pending=null;
  async function approve(event,value) {
    if(pending || !check(()=>!isBusy()))return denied('STATE_CONFLICT');
    let context,input;
    try{
      if(!validInput(value))return denied();
      input=structuredClone(value);context=captureContext(event);
      if(!context || !validOrigin(context.origin) || context.conversation_id!==input.conversation_id ||
          !check(context.guard))return denied('ACCESS_DENIED');
    }catch{return denied('ACCESS_DENIED');}
    const guard=()=>{
      if(!check(context.guard))return false;
      const next=captureContext(event);
      return Boolean(next && check(next.guard) && ['origin','session','parent','backend','conversation_id']
        .every(key=>next[key]===context[key]));
    };
    const base='/api/assistant/conversations/'+input.conversation_id;
    const paths=[base+'?limit=1',base+'/generation-capability',base+'/materials'];
    setBusy(true);
    let closedJudgeGrant=false;
    const task=Promise.resolve().then(()=>runtime.withAuthorization(context.backend,guard,async lease=>{
      let judgeGranted=false;
      const approveSelected=async judgeLease=>{
        const before=await snapshot(context,input,paths,guard);
        if(!check(guard))return denied('STATE_CONFLICT');
        const accepted=await confirm({parent:context.parent,guard,
          details:{content:before.content,model:lease.model,max_total_usd:lease.max_total_usd,
            recipient:'DeepSeek（api.deepseek.com）',...(judgeRuntime?{judge:{available:Boolean(judgeLease),
              max_total_usd:judgeLease?.max_total_usd??null}}:{})}});
        const selected=judgeRuntime && exact(accepted,['main','judge']) && accepted.main===true &&
          typeof accepted.judge==='boolean' && (!accepted.judge||Boolean(judgeLease));
        if(judgeRuntime?!selected:accepted!==true)return {ok:false,code:'APPROVAL_CANCELED',canceled:true};
        if(!check(guard))return denied('STATE_CONFLICT');
        const after=await snapshot(context,input,paths,guard,before.token);
        if(after.content!==before.content || !check(guard))return denied('STATE_CONFLICT');
        const payload={session_token:after.token,basis:{request_id:input.request_id,
          expected_scope:input.expected_scope,expected_composer_revision:input.expected_composer_revision,
          content_sha256:input.content_sha256}};
        const result=await lease.authorize(payload);
        if(!result.ok)return result;
        await tokenFor(context,paths,guard,after.token);
        if(selected&&accepted.judge){
          const auxiliary=await judgeLease.authorize({...payload,basis:{...payload.basis,purpose:'primary_intent'}});
          judgeGranted=auxiliary.ok===true;
          // Both leases remain open through this last asynchronous identity check.
          await tokenFor(context,paths,guard,after.token);
        }
        return result;
      };
      if(!judgeRuntime)return approveSelected(null);
      const result=await judgeRuntime.withAuthorization(context.backend,guard,approveSelected);
      closedJudgeGrant=result?.ok===true&&judgeGranted;
      return result;
    }));
    pending=task;
    try{
      const result=await task;
      if(result?.ok===true)return {ok:true};
      // A final outer-lease failure cannot leave a completed inner grant alive.
      if(closedJudgeGrant)await context.backend.stop();
      return {ok:false,code:CODES.has(result?.code)?result.code:'BLOCKED_LIVE',
        ...(result?.canceled===true?{canceled:true}:{})};
    }catch{
      if(closedJudgeGrant)try{await context.backend.stop();}catch{}
      return denied();
    }
    finally{pending=null;setBusy(false);}
  }
  ipcMain.handle('desktop:approve-generation',approve);
  return {wait:()=>Promise.allSettled([pending])};
}
module.exports={registerModelApproval};
