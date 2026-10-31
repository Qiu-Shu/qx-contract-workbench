const auth=require('./model-approval.cjs');
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const STATES=new Set(['disconnected','starting','waiting_scan','need_verifycode','connected','paused']);
const exact=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&
  Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const check=guard=>{try{return guard()===true;}catch{return false;}};
const denied=()=>({ok:false,code:'STATE_CONFLICT'});
function registerPersonalWeixin({ipcMain,runtime,captureContext,readJSON=auth.readJSON}){
  let connection=null,pending=null,closed=false,epoch=0;
  const supported=context=>context&&check(context.guard)&&!context.backend.closing&&
    context.backend.control?.personalWeixinEnabled===true;
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
    const paths=['/api/session'];
    const token=await auth.tokenFor(context,paths,context.guard,expected);
    const actor=await readJSON(context.origin,paths[0],token);
    if(typeof actor?.username!=='string'||!actor.username)throw new Error();
    if(context.actor&&context.actor!==actor.username)throw new Error();
    context.actor=actor.username;
    if(!check(context.guard))throw new Error();
    return token;
  }
  async function sameConnection(context,captured){
    if(!captured||captured.backend!==context.backend||captured.origin!==context.origin||captured.workspace!==context.workspace)throw new Error();
    await authenticated(context,captured.token);
    if(context.actor!==captured.actor)throw new Error();
    if(connection!==captured)throw new Error();
  }
  async function globalStatus(context,token){
    const value=await readJSON(context.origin,'/api/assistant/personal-weixin/status',token);
    if(!check(context.guard)||!value||value.mode!=='service'||!UUID.test(value.workspace_id)||
        value.conversation_id!==null||!STATES.has(value.state)||typeof value.automatic!=='boolean'||
        typeof value.jev_available!=='boolean'||typeof value.notice!=='string'||value.notice.length>2000||
        !Array.isArray(value.batches)||value.batches.length>50)throw new Error();
    const batches=value.batches.map(row=>{
      if(!UUID.test(row.id)||!Number.isSafeInteger(row.revision)||row.revision<1||
          !['collecting','held','clarify','waiting','routed','executing','completed'].includes(row.state)||
          row.conversation_id!==null&&!UUID.test(row.conversation_id)||
          row.workflow!==null&&!['contract','case','court','sales'].includes(row.workflow))throw new Error();
      return {id:row.id,revision:row.revision,state:row.state,conversation_id:row.conversation_id,workflow:row.workflow};
    });
    return {workspace_id:value.workspace_id,jev_available:value.jev_available,batches,
      connection:value.state==='disconnected'?null:{mode:'service',state:value.state,conversation_id:null,
        automatic:value.automatic,notice:value.notice,qr_ready:value.state==='waiting_scan'&&typeof value.qr_url==='string'}};
  }
  async function status(context,captured){
    await sameConnection(context,captured);
    const result=await globalStatus(context,captured.token);
    await sameConnection(context,captured);
    if(result.workspace_id!==captured.workspace_id)throw new Error();
    if(!result.connection)connection=null;
    return result;
  }
  async function operate(event,value,operation){
    // Logout/disconnect waits for the current bounded read or ACK, then rechecks its page.
    if(pending&&operation==='disable'){await pending;return operate(event,value,operation);}
    if(closed||pending||!exact(value,operation==='verify'?['code']:[])||
        operation==='verify'&&(typeof value.code!=='string'||! /^[0-9]{4,12}$/.test(value.code)))return denied();
    const context=captureContext(event);
    if(!supported(context))return denied();
    const captured=connection,startedEpoch=epoch;
    pending=(async()=>{
      let attempted=null;
      try{
        if(operation==='status'){
          if(!captured){const token=await authenticated(context),result=await globalStatus(context,token);
            await authenticated(context,token);return {ok:true,...result};}
          return {ok:true,...await status(context,captured)};
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
          const service=await globalStatus(context,token);
          if(service.connection||!check(policy.guard))return denied();
          await authenticated(context,token);
          if(closed||epoch!==startedEpoch||!check(policy.guard))return denied();
          attempted={...context,token,workspace_id:service.workspace_id};connection=attempted;
          const result=await context.backend.startPersonalWeixin({session_token:token,workspace_id:service.workspace_id,
            automatic_policy:policy.automatic_policy});
          if(!exact(result,['ok','status'])||result.ok!==true||result.status!=='started')throw new Error();
          await sameConnection(context,attempted);
          if(closed||epoch!==startedEpoch||!check(policy.guard))throw new Error();
          return {ok:true,status:'started'};
        }
        if(!captured)return denied();
        const policy=runtime.personalWeixinPolicy(context.backend,context.guard);
        if(!policy|| (await status(context,captured))?.connection?.state!=='need_verifycode')return denied();
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
