const auth=require('./model-approval.cjs');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const STATES=new Set(['disconnected','starting','waiting_scan','need_verifycode','connected','paused']);
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&
  Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const check=guard=>{try{return guard()===true;}catch{return false;}};
const denied=()=>({ok:false,code:'STATE_CONFLICT'});
function validScope(scope,cid){
  return exact(scope,['workspace_id','conversation_id','scope_kind','scope_ref','binding_revision','input_revision','materials_revision'])&&
    UUID.test(scope.workspace_id)&&scope.conversation_id===cid&&['conversation','intake','matter'].includes(scope.scope_kind)&&
    (scope.scope_kind==='conversation'?scope.scope_ref===null:UUID.test(scope.scope_ref))&&
    ['binding_revision','input_revision','materials_revision'].every(key=>Number.isSafeInteger(scope[key])&&scope[key]>=0)&&scope.binding_revision>0;
}
function registerPersonalWeixin({ipcMain,runtime,captureContext,readJSON=auth.readJSON}){
  let connection=null,pending=null,closed=false,epoch=0;
  const supported=context=>context&&check(context.guard)&&!context.backend.closing&&
    context.backend.control?.personalWeixinEnabled===true&&(context.conversation_id===null||UUID.test(context.conversation_id));
  async function stop(captured){
    if(!captured)return;
    if(connection===captured)connection=null;
    try{
      const result=await captured.backend.disablePersonalWeixin();
      if(!exact(result,['ok','status'])||result.ok!==true||result.status!=='disabled')throw new Error();
    }catch{try{await captured.backend.stop();}catch{}}
  }
  async function authenticated(context,expected){
    if(!supported(context))throw new Error();
    const paths=['/api/session',...(context.conversation_id?['/api/assistant/conversations/'+context.conversation_id]:[])];
    const token=await auth.tokenFor(context,paths,context.guard,expected);
    await readJSON(context.origin,paths[0],token);
    if(!check(context.guard))throw new Error();
    return token;
  }
  async function sameConnection(context,captured){
    if(!captured||captured.backend!==context.backend||captured.origin!==context.origin||captured.workspace!==context.workspace)throw new Error();
    await authenticated(context,captured.token);
    if(connection!==captured)throw new Error();
  }
  async function status(context,captured){
    await sameConnection(context,captured);
    const value=await readJSON(context.origin,'/api/assistant/conversations/'+captured.conversation_id+'/personal-weixin/status',captured.token);
    await sameConnection(context,captured);
    if(!exact(value,['state','conversation_id','automatic','notice','qr_url'])||!STATES.has(value.state)||
        typeof value.automatic!=='boolean'||typeof value.notice!=='string'||value.notice.length>2000||
        (value.state!=='disconnected'&&value.conversation_id!==captured.conversation_id))throw new Error();
    if(value.state==='disconnected'){connection=null;return null;}
    return {state:value.state,conversation_id:captured.conversation_id,automatic:value.automatic,notice:value.notice,
      qr_ready:value.state==='waiting_scan'&&typeof value.qr_url==='string'};
  }
  async function operate(event,value,operation){
    // Logout/disconnect waits for the current bounded read or ACK, then rechecks its page.
    if(pending&&operation==='disable'){await pending;return operate(event,value,operation);}
    if(closed||pending||!exact(value,operation==='verify'?['code']:[])||
        operation==='verify'&&(typeof value.code!=='string'||! /^[0-9]{4,12}$/.test(value.code)))return denied();
    const context=captureContext(event);
    if(!supported(context))return denied();
    if(['start','verify'].includes(operation)&&!UUID.test(context.conversation_id))return denied();
    const captured=connection,startedEpoch=epoch;
    pending=(async()=>{
      let attempted=null;
      try{
        if(operation==='status'){
          if(!captured){await authenticated(context);return {ok:true,connection:null};}
          return {ok:true,connection:await status(context,captured)};
        }
        if(operation==='disable'){
          if(captured)await sameConnection(context,captured);else await authenticated(context);
          await stop(captured||{backend:context.backend});return {ok:true,status:'disabled'};
        }
        if(operation==='start'){
          if(captured)return denied();
          const policy=runtime.personalWeixinPolicy(context.backend,context.guard);
          if(!policy)return denied();
          const token=await authenticated(context);
          const draft=await readJSON(context.origin,'/api/assistant/conversations/'+context.conversation_id,token);
          if(!validScope(draft?.scope,context.conversation_id)||draft.archived_at!==null||!check(policy.guard))return denied();
          await authenticated(context,token);
          if(closed||epoch!==startedEpoch||!check(policy.guard))return denied();
          attempted={...context,token};connection=attempted;
          const result=await context.backend.startPersonalWeixin({session_token:token,expected_scope:draft.scope,
            automatic_policy:policy.automatic_policy});
          if(!exact(result,['ok','status'])||result.ok!==true||result.status!=='started')throw new Error();
          await sameConnection(context,attempted);
          if(closed||epoch!==startedEpoch||!check(policy.guard))throw new Error();
          return {ok:true,status:'started'};
        }
        if(!captured||captured.conversation_id!==context.conversation_id)return denied();
        const policy=runtime.personalWeixinPolicy(context.backend,context.guard);
        if(!policy|| (await status(context,captured))?.state!=='need_verifycode')return denied();
        if(closed||epoch!==startedEpoch||!check(policy.guard))return denied();
        attempted=captured;
        const result=await captured.backend.verifyPersonalWeixin({code:value.code});
        if(!exact(result,['ok','status'])||result.ok!==true||result.status!=='accepted')throw new Error();
        await sameConnection(context,captured);
        if(closed||epoch!==startedEpoch||!check(policy.guard))throw new Error();
        return {ok:true,status:'accepted'};
      }catch{
        // A stale ACK must retire the backend that received it, even after replacement.
        // A stale read has no authority to withdraw an established connection on browsing.
        if(operation!=='status'||check(context.guard))await stop(attempted||captured);
        return denied();
      }
    })();
    try{return await pending;}finally{pending=null;}
  }
  for(const operation of ['start','disable','verify','status'])
    ipcMain.handle('desktop:personal-weixin-'+operation,(event,value)=>operate(event,value,operation));
  return {async invalidate(){++epoch;await stop(connection);},async close(){closed=true;++epoch;await stop(connection);if(pending)await pending;},wait:()=>pending};
}
module.exports={registerPersonalWeixin};
