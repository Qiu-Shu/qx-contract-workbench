const {validMaterialInput,createMaterialSnapshot}=require('./material-approval.cjs');
const http=require('node:http');
const {createHash}=require('node:crypto');
const {TextDecoder}=require('node:util');
const {validProfileInput,createProfileSnapshot}=require('./profile-approval.cjs');
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
function validContextInput(value) {
  const scope=value?.expected_scope;
  if(!exact(value,['conversation_id','request_id','expected_scope','expected_composer_revision','citation_ids']) ||
      !uuid(value.conversation_id) || !uuid(value.request_id) || !count(value.expected_composer_revision) ||
      !exact(scope,SCOPE) || !uuid(scope.workspace_id) || scope.conversation_id!==value.conversation_id ||
      !['conversation','intake','matter'].includes(scope.scope_kind) ||
      (scope.scope_kind==='conversation' ? scope.scope_ref!==null : !uuid(scope.scope_ref)) ||
      !count(scope.binding_revision) || scope.binding_revision<1 || !count(scope.input_revision) ||
      !count(scope.materials_revision))return false;
  if(!Array.isArray(value.citation_ids) || value.citation_ids.length<1 || value.citation_ids.length>8)return false;
  const seen=new Set();
  for(const id of value.citation_ids) {
    if(typeof id!=='string' || !uuid(id) || seen.has(id))return false;
    seen.add(id);
  }
  return true;
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
        if(bytes>524288){response.destroy();request.destroy();finish(true);return;}
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
async function csrfCookie(context,path,guard) {
  if(!check(guard))fail();
  const values=await context.session.cookies.get({url:context.origin+path});
  if(!check(guard) || !Array.isArray(values))fail();
  const matches=values.filter(value=>value?.name==='qx_csrf');
  if(matches.length!==1 || typeof matches[0].value!=='string' || !/^[A-Za-z0-9_-]{1,256}$/.test(matches[0].value))fail();
  return matches[0].value;
}
function postJSON(origin,path,token,csrf,body) {
  return new Promise((resolve,reject)=>{
    let bytes=0,parts=[],done=false;
    const finish=(error,value)=>{
      if(done)return;done=true;clearTimeout(timer);parts=[];
      if(error)reject(new Error('BLOCKED_LIVE'));else resolve(value);
    };
    let payload;
    try{payload=JSON.stringify(body);}catch{finish(true);return;}
    const request=http.request(origin+path,{agent:false,method:'POST',maxHeaderSize:8192,
      headers:{Accept:'application/json','Content-Type':'application/json',
        'X-CSRF-Token':csrf,Cookie:'qx_session='+token+'; qx_csrf='+csrf}},response=>{
      if(response.statusCode!==200 || !/^application\/json(?:\s*;|$)/i.test(response.headers['content-type'] || '') ||
          (response.headers['content-encoding'] && response.headers['content-encoding']!=='identity')){
        response.destroy();request.destroy();finish(true);return;
      }
      response.on('data',chunk=>{
        bytes+=chunk.length;
        if(bytes>524288){response.destroy();request.destroy();finish(true);return;}
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
    request.end(payload);
  });
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
// The desktop rebuilds the exact proposed bytes itself; the renderer only names the selection.
async function contextSnapshot(context,input,base,guard,expectedToken) {
  const paths=[base+'?limit=1',base+'/materials'];
  const token=await tokenFor(context,paths,guard,expectedToken);
  const csrf=await csrfCookie(context,base+'?limit=1',guard);
  const [draft,materials]=await Promise.all(paths.map(path=>readJSON(context.origin,path,token)));
  const preview=await postJSON(context.origin,base+'/context-preview',token,csrf,{
    expected_scope:input.expected_scope,expected_composer_revision:input.expected_composer_revision,
    citation_ids:input.citation_ids,max_rounds:1,request_id:input.request_id});
  if(!check(guard) || !same(input.expected_scope,draft?.scope) || !same(input.expected_scope,materials?.scope) ||
      draft.archived_at!==null || draft.composer_revision!==input.expected_composer_revision ||
      !Array.isArray(materials.items) || materials.items.length ||
      (draft.latest_run!==null && (!draft.latest_run || ACTIVE.has(draft.latest_run.state))) ||
      typeof draft.draft_input!=='string' || !draft.draft_input.trim() ||
      Buffer.byteLength(draft.draft_input,'utf8')>65536)fail();
  const basis=preview?.send_basis;
  if(!preview || preview.state!=='ready' || preview.sending_enabled!==false ||
      !same(preview.scope,input.expected_scope) ||
      preview.composer_revision!==input.expected_composer_revision ||
      preview.manifest?.question!==draft.draft_input ||
      !Array.isArray(preview.manifest?.sources) ||
      preview.manifest.sources.length!==input.citation_ids.length ||
      !preview.manifest.sources.every((source,index)=>source?.saved_citation_id===input.citation_ids[index]) ||
      !basis || typeof basis!=='object' || Array.isArray(basis) || basis.request_id!==input.request_id ||
      !same(basis.expected_scope,input.expected_scope) ||
      basis.expected_composer_revision!==input.expected_composer_revision ||
      basis.input_format!=='library-context-v1' ||
      basis.template_version!=='saved-library-context-system-v1' ||
      !Array.isArray(basis.source_bindings) || basis.source_bindings.length!==input.citation_ids.length ||
      !basis.source_bindings.every((binding,index)=>binding?.saved_citation_id===input.citation_ids[index]) ||
      basis.manifest_sha256!==preview.manifest_sha256 || basis.wire_sha256!==preview.wire_sha256 ||
      basis.config_sha256!==preview.config_sha256)fail();
  const sources=preview.manifest.sources.map(source=>{
    if(typeof source?.title!=='string' || !source.title.trim() || source.title.length>2000 ||
        !['case_csv','law_markdown'].includes(source?.kind) ||
        !Number.isSafeInteger(source?.line_start) || !Number.isSafeInteger(source?.line_end) ||
        source.line_start<1 || source.line_end<source.line_start)fail();
    return {saved_citation_id:source.saved_citation_id,title:source.title,kind:source.kind,
      line_start:source.line_start,line_end:source.line_end};
  });
  await tokenFor(context,paths,guard,token);
  return {token,content:draft.draft_input,sources,basis,basisKey:JSON.stringify(basis)};
}
function registerModelApproval({ipcMain,runtime,judgeRuntime,captureContext,isBusy,setBusy,confirm}) {
  let pending=null;
  const materialSnapshot=createMaterialSnapshot({tokenFor,csrfCookie,readJSON,postJSON,check,fail});
  const profileSnapshot=createProfileSnapshot({tokenFor,csrfCookie,readJSON,postJSON,check,fail});
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
  async function approveSelection(event,value,profile=false,material=false) {
    if(pending || !check(()=>!isBusy()))return denied('STATE_CONFLICT');
    let context,input;
    try{
      if(!(material?validMaterialInput(value):profile?validProfileInput(value):validContextInput(value)))return denied();
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
    const takeSnapshot=material?materialSnapshot:profile?profileSnapshot:contextSnapshot;
    const authorize=material?'authorizeMaterial':profile?'authorizeProfile':'authorizeContext';
    setBusy(true);
    const task=Promise.resolve().then(()=>runtime.withAuthorization(context.backend,guard,async lease=>{
      if(typeof lease?.[authorize]!=='function')return denied();
      const before=await takeSnapshot(context,input,base,guard);
      if(!check(guard))return denied('STATE_CONFLICT');
      const accepted=await confirm({parent:context.parent,guard,
        details:{kind:material?'material_business':profile?'profile_draft':'library_context',content:before.content,
          ...(profile||material?{basis:structuredClone(before.basis)}:{sources:before.sources}),
          model:lease.model,max_total_usd:lease.max_total_usd,recipient:'DeepSeek（api.deepseek.com）'}});
      if(accepted!==true)return {ok:false,code:'APPROVAL_CANCELED',canceled:true};
      if(!check(guard))return denied('STATE_CONFLICT');
      const after=await takeSnapshot(context,input,base,guard,before.token);
      if(after.content!==before.content || after.basisKey!==before.basisKey || !check(guard))
        return denied('STATE_CONFLICT');
      const result=await lease[authorize]({session_token:after.token,basis:before.basis});
      if(!result.ok)return result;
      await tokenFor(context,after.paths || [base+'?limit=1',base+'/materials'],guard,after.token);
      return result;
    }));
    pending=task;
    try{
      const result=await task;
      if(result?.ok===true){
        if(!profile)return {ok:true};
        return exact(result,['ok','status']) && ['authorized','existing'].includes(result.status)
          ?{ok:true,status:result.status}:denied();
      }
      return {ok:false,code:CODES.has(result?.code)?result.code:'BLOCKED_LIVE',
        ...(result?.canceled===true?{canceled:true}:{})};
    }catch{return denied();}
    finally{pending=null;setBusy(false);}
  }
  ipcMain.handle('desktop:approve-context',(event,value)=>approveSelection(event,value));
  ipcMain.handle('desktop:approve-material',(event,value)=>approveSelection(event,value,false,true));
  ipcMain.handle('desktop:approve-profile',(event,value)=>approveSelection(event,value,true));
  return {wait:()=>Promise.allSettled([pending])};
}
module.exports={registerModelApproval};
